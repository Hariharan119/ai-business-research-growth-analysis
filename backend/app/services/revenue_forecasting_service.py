
from datetime import timedelta
from decimal import Decimal

import numpy as np
import pandas as pd

from sqlalchemy import select
from statsmodels.tsa.statespace.sarimax import SARIMAX

from app.models.company import Company
from app.models.financial_record import FinancialRecord
from app.services.financial_analysis_service import _select_latest_versions


MODEL_ORDER = (1, 1, 0)
SEASONAL_ORDER = (1, 1, 0, 4)

# Rolling-origin backtest settings. Metrics are computed from the stored
# revenue series on every forecast request; nothing is hardcoded.
VALIDATION_WINDOWS = 2
VALIDATION_WINDOW_QUARTERS = 8
MIN_TRAINING_QUARTERS = 12


def build_quarterly_revenue_dataset(records):
    """
    Build a continuous quarterly revenue series.

    Reported quarterly records are retained.
    Missing Q4 records are derived as annual revenue minus Q1-Q3.
    Derived observations retain their SEC source provenance.
    Only the most recent continuous run of fiscal quarters is kept; the
    number of excluded older observations is stored in df.attrs.
    """
    selected = _select_latest_versions(records)

    annual = {
        record.fiscal_year: record
        for record in selected
        if record.period_type == "annual"
        and record.fiscal_year is not None
    }

    quarterly = {
        (record.fiscal_year, record.fiscal_quarter): record
        for record in selected
        if record.period_type == "quarterly"
        and record.fiscal_year is not None
        and record.fiscal_quarter is not None
    }

    rows = []

    # Preserve all reported quarterly observations.
    for (fiscal_year, fiscal_quarter), record in quarterly.items():
        rows.append({
            "fiscal_year": int(fiscal_year),
            "fiscal_quarter": int(fiscal_quarter),
            "period_start": record.period_start,
            "period_end": record.period_end,
            "revenue": Decimal(str(record.metric_value)),
            "unit": record.unit,
            "is_derived": False,
            "source_urls": [record.source_url] if record.source_url else [],
        })

    # Derive Q4 only where annual revenue and Q1-Q3 are available.
    for fiscal_year, annual_record in annual.items():
        if (fiscal_year, 4) in quarterly:
            continue

        q1 = quarterly.get((fiscal_year, 1))
        q2 = quarterly.get((fiscal_year, 2))
        q3 = quarterly.get((fiscal_year, 3))

        if not all([q1, q2, q3]):
            continue

        if not all([
            annual_record.period_start,
            annual_record.period_end,
            q1.period_start,
            q3.period_end,
        ]):
            continue

        units = {
            annual_record.unit,
            q1.unit,
            q2.unit,
            q3.unit,
        }

        if len(units) != 1:
            raise ValueError(
                f"Revenue unit mismatch for FY{fiscal_year}"
            )

        if annual_record.period_start != q1.period_start:
            raise ValueError(
                f"Annual and Q1 period starts do not match for FY{fiscal_year}"
            )

        if q3.period_end >= annual_record.period_end:
            raise ValueError(
                f"Invalid Q3/annual period dates for FY{fiscal_year}"
            )

        annual_value = Decimal(str(annual_record.metric_value))
        q1_value = Decimal(str(q1.metric_value))
        q2_value = Decimal(str(q2.metric_value))
        q3_value = Decimal(str(q3.metric_value))

        q4_value = annual_value - q1_value - q2_value - q3_value

        if q4_value <= 0:
            raise ValueError(
                f"Derived Q4 revenue is not positive for FY{fiscal_year}"
            )

        source_urls = list(dict.fromkeys(
            url for url in [
                annual_record.source_url,
                q1.source_url,
                q2.source_url,
                q3.source_url,
            ] if url
        ))

        rows.append({
            "fiscal_year": int(fiscal_year),
            "fiscal_quarter": 4,
            "period_start": q3.period_end + timedelta(days=1),
            "period_end": annual_record.period_end,
            "revenue": q4_value,
            "unit": annual_record.unit,
            "is_derived": True,
            "source_urls": source_urls,
        })

    if not rows:
        raise ValueError("No usable quarterly revenue observations found")

    rows.sort(
        key=lambda row: (
            row["fiscal_year"],
            row["fiscal_quarter"],
        )
    )

    quarter_numbers = [
        row["fiscal_year"] * 4 + row["fiscal_quarter"]
        for row in rows
    ]

    if len(set(quarter_numbers)) != len(quarter_numbers):
        raise ValueError("Duplicate fiscal quarter in revenue dataset")

    # Keep the most recent continuous run of fiscal quarters. Older
    # observations separated by a reporting gap (for example years before
    # quarterly XBRL data exists) cannot be modelled as one series.
    segment_start = 0
    for index in range(1, len(quarter_numbers)):
        if quarter_numbers[index] - quarter_numbers[index - 1] != 1:
            segment_start = index

    excluded_count = segment_start
    rows = rows[segment_start:]
    derived_count = sum(1 for row in rows if row["is_derived"])

    df = pd.DataFrame(rows)

    if df["unit"].nunique() != 1:
        raise ValueError("Revenue observations contain mixed units")

    if (df["revenue"] <= 0).any():
        raise ValueError("Revenue observations must all be positive")

    df["revenue_billions"] = df["revenue"].map(
        lambda value: float(value / Decimal("1000000000"))
    )
    df.attrs["excluded_observations"] = excluded_count

    return df, derived_count


def future_period_ends(period_ends, horizon):
    """
    Estimate future fiscal quarter end dates from the company's own history.

    Quarters that end on calendar month ends (for example Microsoft, fiscal
    year ending 30 June) advance by three month ends. Quarters on a 52/53-week
    calendar (for example NVIDIA, fiscal year ending on the last Sunday of
    January) repeat the prior-year end date of the same fiscal quarter plus
    52 weeks.

    Returns (list of ISO dates, basis label).
    """
    ends = [pd.Timestamp(value) for value in period_ends]

    if len(ends) < 4:
        raise ValueError("At least four historical quarter ends are required")

    if all(end.is_month_end for end in ends[-8:]):
        basis = "calendar_month_end_quarters"
        future = []
        last = ends[-1]
        for _ in range(horizon):
            last = last + pd.offsets.MonthEnd(3)
            future.append(last)
    else:
        basis = "52_53_week_fiscal_calendar_estimate"
        extended = list(ends)
        for _ in range(horizon):
            extended.append(extended[-4] + pd.Timedelta(weeks=52))
        future = extended[len(ends):]

    return [end.date().isoformat() for end in future], basis


def _fit_log_sarimax(values):
    model = SARIMAX(
        np.log(values),
        order=MODEL_ORDER,
        seasonal_order=SEASONAL_ORDER,
        trend="n",
        enforce_stationarity=False,
        enforce_invertibility=False,
    )
    return model.fit(disp=False, maxiter=500)


def _error_metrics(actual, predicted):
    errors = predicted - actual
    return {
        "mae_billions": round(float(np.mean(np.abs(errors))), 3),
        "rmse_billions": round(float(np.sqrt(np.mean(errors ** 2))), 3),
        "mape_percent": round(float(np.mean(np.abs(errors / actual)) * 100), 3),
    }


def evaluate_rolling_forecast(
    values,
    labels=None,
    windows=VALIDATION_WINDOWS,
    window_quarters=VALIDATION_WINDOW_QUARTERS,
):
    """
    Rolling-origin backtest computed from the revenue series.

    Each window refits the model on all quarters before the window and
    forecasts every quarter in the window. A seasonal naive baseline
    (latest observed value of the same fiscal quarter) is scored on the
    same quarters for comparison.
    """
    values = np.asarray(values, dtype=float)
    labels = list(labels) if labels is not None else [str(i) for i in range(len(values))]
    results = []

    for window in range(windows, 0, -1):
        origin = len(values) - window * window_quarters

        if origin < MIN_TRAINING_QUARTERS:
            results.append({"status": "insufficient_training_data"})
            continue

        actual = values[origin:origin + window_quarters]
        period = f"{labels[origin]} to {labels[origin + window_quarters - 1]}"

        try:
            fitted = _fit_log_sarimax(values[:origin])
        except Exception as exc:
            results.append({"test_period": period, "status": f"fit_failed: {type(exc).__name__}"})
            continue

        if not fitted.mle_retvals.get("converged", False):
            results.append({"test_period": period, "status": "not_converged"})
            continue

        predicted = np.exp(np.asarray(
            fitted.get_forecast(steps=window_quarters).predicted_mean
        ))
        baseline = np.array([
            values[origin - 4 + (step % 4)]
            for step in range(window_quarters)
        ])

        results.append({
            "test_period": period,
            "training_quarters": int(origin),
            "status": "completed",
            "model": _error_metrics(actual, predicted),
            "seasonal_naive": _error_metrics(actual, baseline),
        })

    completed = [item for item in results if item["status"] == "completed"]

    summary = {
        "method": (
            f"Rolling-origin backtest: {windows} windows of "
            f"{window_quarters} quarters, model refit before each window"
        ),
        "computed": True,
        "windows_completed": len(completed),
        "windows": results,
    }

    if not completed:
        summary["status"] = "insufficient_data"
        return summary

    for key in ("mae_billions", "rmse_billions", "mape_percent"):
        summary[f"mean_{key}"] = round(float(np.mean(
            [item["model"][key] for item in completed]
        )), 3)
        summary[f"baseline_mean_{key}"] = round(float(np.mean(
            [item["seasonal_naive"][key] for item in completed]
        )), 3)

    summary["beats_seasonal_naive"] = bool(
        summary["mean_mape_percent"] < summary["baseline_mean_mape_percent"]
    )
    summary["status"] = "completed"
    return summary


def forecast_company_revenue(
    session,
    ticker,
    horizon=4,
    confidence_level=0.95,
):
    """
    Generate a quarterly revenue forecast for a stored company.

    Returns historical data, forecast values, prediction intervals,
    rolling validation metrics, model metadata, and SEC source provenance.
    """
    if not isinstance(horizon, int) or horizon < 1 or horizon > 8:
        raise ValueError("horizon must be an integer from 1 to 8")

    if not 0 < confidence_level < 1:
        raise ValueError("confidence_level must be between 0 and 1")

    company = session.scalar(
        select(Company).where(
            Company.ticker.ilike(ticker.strip())
        )
    )

    if company is None:
        raise ValueError(f"Company not found: {ticker}")

    records = list(session.scalars(
        select(FinancialRecord).where(
            FinancialRecord.company_id == company.company_id,
            FinancialRecord.metric_name == "Revenue",
            FinancialRecord.period_type.in_(["annual", "quarterly"]),
        )
    ).all())

    history, derived_count = build_quarterly_revenue_dataset(records)

    if len(history) < 20:
        raise ValueError(
            "At least 20 continuous quarterly observations are required for forecasting"
        )

    values = history["revenue_billions"].astype(float).to_numpy()
    labels = [
        f"FY{int(year)} Q{int(quarter)}"
        for year, quarter in zip(history["fiscal_year"], history["fiscal_quarter"])
    ]

    fitted = _fit_log_sarimax(values)

    if not fitted.mle_retvals.get("converged", False):
        raise RuntimeError("SARIMAX model did not converge")

    result = fitted.get_forecast(steps=horizon)

    forecast_log = np.asarray(result.predicted_mean)
    interval_log = np.asarray(
        result.conf_int(alpha=1 - confidence_level)
    )

    forecast_values = np.exp(forecast_log)
    lower_values = np.exp(interval_log[:, 0])
    upper_values = np.exp(interval_log[:, 1])

    last_date = pd.Timestamp(history.iloc[-1]["period_end"])
    future_dates, period_end_basis = future_period_ends(
        history["period_end"], horizon
    )

    validation = evaluate_rolling_forecast(values, labels)

    fiscal_year = int(history.iloc[-1]["fiscal_year"])
    fiscal_quarter = int(history.iloc[-1]["fiscal_quarter"])

    forecast_rows = []

    for index in range(horizon):
        fiscal_quarter += 1

        if fiscal_quarter > 4:
            fiscal_quarter = 1
            fiscal_year += 1

        forecast_rows.append({
            "fiscal_year": fiscal_year,
            "fiscal_quarter": fiscal_quarter,
            "period_end": future_dates[index],
            "period_end_is_estimated": True,
            "forecast_revenue_billions": float(forecast_values[index]),
            "lower_billions": float(lower_values[index]),
            "upper_billions": float(upper_values[index]),
            "interval_confidence_level": confidence_level,
        })

    historical_rows = []

    for row in history.to_dict("records"):
        historical_rows.append({
            "fiscal_year": int(row["fiscal_year"]),
            "fiscal_quarter": int(row["fiscal_quarter"]),
            "period_end": row["period_end"].isoformat(),
            "revenue_billions": float(row["revenue_billions"]),
            "is_derived": bool(row["is_derived"]),
            "source_urls": row["source_urls"],
        })

    excluded_count = int(history.attrs.get("excluded_observations", 0))

    limitations = [
        "Historical Q4 observations may be derived from annual revenue less Q1-Q3.",
        "Prediction intervals are model-based, not guarantees.",
        "Future period end dates are estimated from the company's historical fiscal calendar.",
        "Forecasts are estimates, not investment recommendations.",
    ]

    # Report weak backtest performance honestly in the forecast itself.
    if validation.get("status") != "completed":
        limitations.append(
            "The rolling backtest could not be completed; forecast accuracy is unverified."
        )
    elif not validation["beats_seasonal_naive"]:
        limitations.append(
            f"In backtesting the model did not beat a seasonal naive baseline "
            f"(MAPE {validation['mean_mape_percent']}% vs "
            f"{validation['baseline_mean_mape_percent']}%). Treat this forecast as low confidence."
        )
    elif validation["mean_mape_percent"] > 15:
        limitations.append(
            f"Backtest MAPE is {validation['mean_mape_percent']}%; forecast accuracy "
            "is low for this company."
        )

    if excluded_count:
        limitations.append(
            f"{excluded_count} older quarterly observations before the most recent "
            "reporting gap were excluded from the model."
        )

    metadata = {
        "model": "SARIMAX",
        "order": MODEL_ORDER,
        "seasonal_order": SEASONAL_ORDER,
        "converged": True,
        "aic": float(fitted.aic),
        "bic": float(fitted.bic),
        "training_observations": len(history),
        "reported_observations": int((~history["is_derived"]).sum()),
        "derived_observations": derived_count,
        "excluded_observations": excluded_count,
        "first_historical_period": labels[0],
        "latest_historical_period": last_date.date().isoformat(),
        "forecast_horizon": horizon,
        "confidence_level": confidence_level,
        "period_end_basis": period_end_basis,
        "validation": validation,
        "unit": history.iloc[0]["unit"],
        "limitations": limitations,
    }

    return {
        "company": {
            "name": company.name,
            "ticker": company.ticker,
        },
        "metadata": metadata,
        "historical_observations": historical_rows,
        "forecast": forecast_rows,
    }

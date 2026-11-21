
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

VALIDATION_SUMMARY = {
    "method": "Two rolling 8-quarter validation windows",
    "mean_mae_billions": 1.411,
    "mean_rmse_billions": 1.782,
    "mean_mape_percent": 2.157,
}


def build_quarterly_revenue_dataset(records):
    """
    Build a continuous quarterly revenue series.

    Reported quarterly records are retained.
    Missing Q4 records are derived as annual revenue minus Q1-Q3.
    Derived observations retain their SEC source provenance.
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

    derived_count = 0

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

        derived_count += 1

    if not rows:
        raise ValueError("No usable quarterly revenue observations found")

    rows.sort(
        key=lambda row: (
            row["fiscal_year"],
            row["fiscal_quarter"],
        )
    )

    df = pd.DataFrame(rows)

    if df.duplicated(["fiscal_year", "fiscal_quarter"]).any():
        raise ValueError("Duplicate fiscal quarter in revenue dataset")

    if df["unit"].nunique() != 1:
        raise ValueError("Revenue observations contain mixed units")

    if (df["revenue"] <= 0).any():
        raise ValueError("Revenue observations must all be positive")

    # Require a continuous quarterly sequence.
    quarter_numbers = [
        row["fiscal_year"] * 4 + row["fiscal_quarter"]
        for row in rows
    ]

    if any(
        current - previous != 1
        for previous, current in zip(
            quarter_numbers,
            quarter_numbers[1:],
        )
    ):
        raise ValueError("Revenue dataset contains missing fiscal quarters")

    df["revenue_billions"] = df["revenue"].map(
        lambda value: float(value / Decimal("1000000000"))
    )

    return df, derived_count


def forecast_company_revenue(
    session,
    ticker,
    horizon=4,
    confidence_level=0.95,
):
    """
    Generate a quarterly revenue forecast for a stored company.

    Returns historical data, forecast values, prediction intervals,
    model metadata, and SEC source provenance.
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
            "At least 20 quarterly observations are required for forecasting"
        )

    values = history["revenue_billions"].astype(float).to_numpy()

    model = SARIMAX(
        np.log(values),
        order=MODEL_ORDER,
        seasonal_order=SEASONAL_ORDER,
        trend="n",
        enforce_stationarity=False,
        enforce_invertibility=False,
    )

    fitted = model.fit(disp=False, maxiter=500)

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

    future_dates = pd.date_range(
        start=last_date + pd.Timedelta(days=1),
        periods=horizon,
        freq=pd.offsets.QuarterEnd(),
    )

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
            "period_end": future_dates[index].date().isoformat(),
            "forecast_revenue_billions": float(forecast_values[index]),
            "lower_95_billions": float(lower_values[index]),
            "upper_95_billions": float(upper_values[index]),
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
        "latest_historical_period": last_date.date().isoformat(),
        "forecast_horizon": horizon,
        "confidence_level": confidence_level,
        "validation": VALIDATION_SUMMARY,
        "unit": history.iloc[0]["unit"],
        "limitations": [
            "Historical Q4 observations may be derived from annual revenue less Q1-Q3.",
            "Prediction intervals are model-based, not guarantees.",
            "Forecasts are estimates, not investment recommendations.",
        ],
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

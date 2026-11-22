
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import numpy as np

from app.services.revenue_forecasting_service import (
    build_quarterly_revenue_dataset,
    evaluate_rolling_forecast,
    future_period_ends,
)


def make_record(
    metric_name,
    period_type,
    fiscal_year,
    fiscal_quarter,
    value,
    period_start,
    period_end,
    record_id,
):
    return SimpleNamespace(
        financial_record_id=record_id,
        metric_name=metric_name,
        period_type=period_type,
        fiscal_year=fiscal_year,
        fiscal_quarter=fiscal_quarter,
        metric_value=Decimal(str(value)),
        unit="USD",
        period_start=period_start,
        period_end=period_end,
        filing_date=date(2024, 8, 1),
        accession_number=f"ACCESSION-{record_id}",
        source_url=f"https://www.sec.gov/Archives/record-{record_id}",
    )


def make_fy2024_records(include_q4=False):
    records = [
        make_record(
            "Revenue", "annual", 2024, None, 50,
            date(2023, 7, 1), date(2024, 6, 30), 1
        ),
        make_record(
            "Revenue", "quarterly", 2024, 1, 10,
            date(2023, 7, 1), date(2023, 9, 30), 2
        ),
        make_record(
            "Revenue", "quarterly", 2024, 2, 11,
            date(2023, 10, 1), date(2023, 12, 31), 3
        ),
        make_record(
            "Revenue", "quarterly", 2024, 3, 12,
            date(2024, 1, 1), date(2024, 3, 31), 4
        ),
    ]

    if include_q4:
        records.append(
            make_record(
                "Revenue", "quarterly", 2024, 4, 17,
                date(2024, 4, 1), date(2024, 6, 30), 5
            )
        )

    return records


def test_missing_q4_is_derived_with_provenance():
    df, derived_count = build_quarterly_revenue_dataset(
        make_fy2024_records()
    )

    q4 = df[
        (df["fiscal_year"] == 2024)
        & (df["fiscal_quarter"] == 4)
    ].iloc[0]

    assert derived_count == 1
    assert q4["revenue"] == Decimal("17")
    assert q4["is_derived"]
    assert q4["period_start"] == date(2024, 4, 1)
    assert q4["period_end"] == date(2024, 6, 30)
    assert len(q4["source_urls"]) == 4
    assert len(df) == 4


def test_reported_q4_is_not_derived_again():
    df, derived_count = build_quarterly_revenue_dataset(
        make_fy2024_records(include_q4=True)
    )

    q4 = df[
        (df["fiscal_year"] == 2024)
        & (df["fiscal_quarter"] == 4)
    ].iloc[0]

    assert derived_count == 0
    assert len(df) == 4
    assert q4["revenue"] == Decimal("17")
    assert not q4["is_derived"]
    assert len(q4["source_urls"]) == 1

def test_reporting_gap_keeps_most_recent_continuous_run():
    records = make_fy2024_records(include_q4=True) + [
        make_record(
            "Revenue", "quarterly", 2022, 1, 8,
            date(2021, 7, 1), date(2021, 9, 30), 10
        ),
        make_record(
            "Revenue", "quarterly", 2022, 2, 9,
            date(2021, 10, 1), date(2021, 12, 31), 11
        ),
    ]

    df, derived_count = build_quarterly_revenue_dataset(records)

    assert len(df) == 4
    assert df.attrs["excluded_observations"] == 2
    assert list(df["fiscal_year"]) == [2024, 2024, 2024, 2024]
    assert derived_count == 0


def test_future_period_ends_month_end_calendar():
    ends = [date(2025, 9, 30), date(2025, 12, 31), date(2026, 3, 31), date(2026, 6, 30)]

    future, basis = future_period_ends(ends, 4)

    assert basis == "calendar_month_end_quarters"
    assert future == ["2026-09-30", "2026-12-31", "2027-03-31", "2027-06-30"]


def test_future_period_ends_52_53_week_calendar():
    # NVIDIA-style quarters ending on Sundays near the end of Apr/Jul/Oct/Jan.
    ends = [date(2025, 4, 27), date(2025, 7, 27), date(2025, 10, 26), date(2026, 1, 25)]

    future, basis = future_period_ends(ends, 2)

    assert basis == "52_53_week_fiscal_calendar_estimate"
    assert future == ["2026-04-26", "2026-07-26"]


def test_rolling_validation_metrics_are_computed():
    quarters = np.arange(40)
    seasonal = np.array([1.00, 1.05, 0.97, 1.10])[quarters % 4]
    noise = 1 + 0.01 * np.sin(quarters * 1.7)
    values = 10 * (1.02 ** quarters) * seasonal * noise

    summary = evaluate_rolling_forecast(values)

    assert summary["computed"] is True
    assert summary["windows_completed"] == 2
    assert summary["status"] == "completed"
    assert summary["mean_mape_percent"] >= 0
    assert summary["baseline_mean_mape_percent"] >= 0
    assert isinstance(summary["beats_seasonal_naive"], bool)
    assert [w["training_quarters"] for w in summary["windows"]] == [24, 32]

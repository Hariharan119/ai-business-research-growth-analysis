
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.services.revenue_forecasting_service import (
    build_quarterly_revenue_dataset,
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

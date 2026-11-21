
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.services.financial_analysis_service import (
    _select_latest_versions,
    _add_growth,
    _calculate_margins,
    _calculate_balance_sheet_ratios,
)


def make_record(
    metric_name,
    period_type,
    value,
    period_end,
    *,
    fiscal_year=2026,
    fiscal_quarter=None,
    filing_date=date(2026, 4, 1),
    accession_number="0000000000-26-000001",
    financial_record_id=1,
    period_start=date(2026, 1, 1),
    unit="USD",
):
    return SimpleNamespace(
        metric_name=metric_name,
        period_type=period_type,
        metric_value=Decimal(str(value)),
        period_end=period_end,
        period_start=period_start,
        fiscal_year=fiscal_year,
        fiscal_quarter=fiscal_quarter,
        filing_date=filing_date,
        accession_number=accession_number,
        financial_record_id=financial_record_id,
        unit=unit,
        form_type="10-Q",
        source_url="https://www.sec.gov/example",
        is_derived=False,
    )


def test_latest_filing_version_is_selected():
    old = make_record(
        "Revenue", "quarterly", 100,
        date(2026, 3, 31),
        filing_date=date(2026, 4, 1),
        financial_record_id=1,
    )

    revised = make_record(
        "Revenue", "quarterly", 105,
        date(2026, 3, 31),
        filing_date=date(2026, 5, 1),
        financial_record_id=2,
    )

    selected = _select_latest_versions([old, revised])

    assert len(selected) == 1
    assert selected[0].metric_value == Decimal("105")


def test_annual_growth_compares_previous_fiscal_year():
    previous = make_record(
        "Revenue", "annual", 100,
        date(2025, 6, 30),
        fiscal_year=2025,
    )

    current = make_record(
        "Revenue", "annual", 120,
        date(2026, 6, 30),
        fiscal_year=2026,
    )

    results = _add_growth([previous, current])

    assert results[0]["year_over_year_growth_pct"] is None
    assert results[1]["year_over_year_growth_pct"] == 20.0


def test_quarterly_growth_compares_same_fiscal_quarter():
    previous_q1 = make_record(
        "Revenue", "quarterly", 20,
        date(2025, 9, 30),
        fiscal_year=2026,
        fiscal_quarter=1,
    )

    current_q1 = make_record(
        "Revenue", "quarterly", 25,
        date(2026, 9, 30),
        fiscal_year=2027,
        fiscal_quarter=1,
    )

    results = _add_growth([previous_q1, current_q1])

    assert results[0]["year_over_year_growth_pct"] is None
    assert results[1]["year_over_year_growth_pct"] == 25.0


def test_margins_use_matching_periods_only():
    revenue = make_record(
        "Revenue", "quarterly", 100,
        date(2026, 3, 31),
        fiscal_quarter=3,
    )

    operating_income = make_record(
        "OperatingIncome", "quarterly", 30,
        date(2026, 3, 31),
        fiscal_quarter=3,
    )

    net_income = make_record(
        "NetIncome", "quarterly", 20,
        date(2026, 3, 31),
        fiscal_quarter=3,
    )

    cash_flow = make_record(
        "OperatingCashFlow", "quarterly", 40,
        date(2026, 3, 31),
        fiscal_quarter=3,
    )

    # This YTD record must not be matched to quarterly revenue.
    ytd_cash_flow = make_record(
        "OperatingCashFlow", "ytd", 90,
        date(2026, 3, 31),
        fiscal_quarter=3,
    )

    results = _calculate_margins({
        "Revenue": [revenue],
        "OperatingIncome": [operating_income],
        "NetIncome": [net_income],
        "OperatingCashFlow": [cash_flow, ytd_cash_flow],
    })

    assert results["operating_margin"][0]["value_pct"] == 30.0
    assert results["net_margin"][0]["value_pct"] == 20.0
    assert results["operating_cash_flow_margin"][0]["value_pct"] == 40.0
    assert len(results["operating_cash_flow_margin"]) == 1


def test_zero_revenue_does_not_create_margin():
    revenue = make_record(
        "Revenue", "quarterly", 0,
        date(2026, 3, 31),
    )

    operating_income = make_record(
        "OperatingIncome", "quarterly", 10,
        date(2026, 3, 31),
    )

    results = _calculate_margins({
        "Revenue": [revenue],
        "OperatingIncome": [operating_income],
    })

    assert results["operating_margin"] == []


def test_balance_sheet_ratios():
    period = date(2026, 3, 31)

    assets = make_record(
        "TotalAssets", "instant", 200, period,
    )

    liabilities = make_record(
        "TotalLiabilities", "instant", 80, period,
    )

    cash = make_record(
        "CashAndCashEquivalents", "instant", 20, period,
    )

    results = _calculate_balance_sheet_ratios({
        "TotalAssets": [assets],
        "TotalLiabilities": [liabilities],
        "CashAndCashEquivalents": [cash],
    })

    assert len(results) == 1
    assert results[0]["total_assets"] == 200.0
    assert results[0]["liabilities_to_assets_pct"] == 40.0
    assert results[0]["cash_to_assets_pct"] == 10.0


def test_missing_balance_sheet_metrics_return_none():
    assets = make_record(
        "TotalAssets", "instant", 200,
        date(2026, 3, 31),
    )

    results = _calculate_balance_sheet_ratios({
        "TotalAssets": [assets],
        "TotalLiabilities": [],
        "CashAndCashEquivalents": [],
    })

    assert results[0]["liabilities_to_assets_pct"] is None
    assert results[0]["cash_to_assets_pct"] is None

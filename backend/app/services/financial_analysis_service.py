"""Deterministic financial analysis using stored SEC financial records."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.financial_record import FinancialRecord


FLOW_METRICS = {
    "Revenue",
    "NetIncome",
    "OperatingIncome",
    "OperatingCashFlow",
}

INSTANT_METRICS = {
    "TotalAssets",
    "TotalLiabilities",
    "CashAndCashEquivalents",
}


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value))


def _percentage(numerator: Decimal, denominator: Decimal) -> float | None:
    if denominator == 0:
        return None
    return round(float(numerator / denominator * Decimal("100")), 2)


def _select_latest_versions(records: list[FinancialRecord]) -> list[FinancialRecord]:
    """Select the latest filing for each metric, period type and period end."""
    selected = {}

    for record in records:
        key = (
            record.metric_name,
            record.period_type,
            record.period_end,
        )

        current = selected.get(key)

        if current is None or (
            record.filing_date,
            record.accession_number,
            record.financial_record_id,
        ) > (
            current.filing_date,
            current.accession_number,
            current.financial_record_id,
        ):
            selected[key] = record

    return list(selected.values())


def _record_dict(record: FinancialRecord) -> dict[str, Any]:
    return {
        "metric_name": record.metric_name,
        "period_type": record.period_type,
        "value": float(record.metric_value),
        "unit": record.unit,
        "fiscal_year": record.fiscal_year,
        "fiscal_quarter": record.fiscal_quarter,
        "period_start": (
            record.period_start.isoformat() if record.period_start else None
        ),
        "period_end": record.period_end.isoformat(),
        "filing_date": record.filing_date.isoformat(),
        "form_type": record.form_type,
        "accession_number": record.accession_number,
        "source_url": record.source_url,
        "is_derived": record.is_derived,
    }


def _add_growth(records: list[FinancialRecord]) -> list[dict[str, Any]]:
    """Calculate annual or same-quarter-prior-year growth."""
    annual_lookup = {}
    quarterly_lookup = {}

    for record in records:
        if record.period_type == "annual":
            annual_lookup[record.fiscal_year] = record
        elif (
            record.period_type == "quarterly"
            and record.fiscal_quarter is not None
        ):
            quarterly_lookup[
                (record.fiscal_year, record.fiscal_quarter)
            ] = record

    output = []

    for record in sorted(records, key=lambda item: item.period_end):
        item = _record_dict(record)
        previous = None

        if record.period_type == "annual":
            previous = annual_lookup.get(record.fiscal_year - 1)

        elif (
            record.period_type == "quarterly"
            and record.fiscal_quarter is not None
        ):
            previous = quarterly_lookup.get(
                (record.fiscal_year - 1, record.fiscal_quarter)
            )

        growth = None

        if previous is not None:
            previous_value = _decimal(previous.metric_value)

            if previous_value != 0:
                growth = round(
                    float(
                        (
                            _decimal(record.metric_value) / previous_value
                            - Decimal("1")
                        ) * Decimal("100")
                    ),
                    2,
                )

        item["year_over_year_growth_pct"] = growth
        output.append(item)

    return output


def _calculate_margins(
    records_by_metric: dict[str, list[FinancialRecord]],
) -> dict[str, list[dict[str, Any]]]:
    """Calculate margins only when numerator and denominator share a period."""
    revenue = {
        (r.period_type, r.period_end): r
        for r in records_by_metric.get("Revenue", [])
    }

    results = {
        "operating_margin": [],
        "net_margin": [],
        "operating_cash_flow_margin": [],
    }

    definitions = {
        "operating_margin": "OperatingIncome",
        "net_margin": "NetIncome",
        "operating_cash_flow_margin": "OperatingCashFlow",
    }

    for output_name, numerator_metric in definitions.items():
        for numerator in records_by_metric.get(numerator_metric, []):
            key = (numerator.period_type, numerator.period_end)
            denominator = revenue.get(key)

            if denominator is None or _decimal(denominator.metric_value) == 0:
                continue

            results[output_name].append({
                "period_type": numerator.period_type,
                "period_end": numerator.period_end.isoformat(),
                "fiscal_year": numerator.fiscal_year,
                "fiscal_quarter": numerator.fiscal_quarter,
                "value_pct": _percentage(
                    _decimal(numerator.metric_value),
                    _decimal(denominator.metric_value),
                ),
                "numerator_source_url": numerator.source_url,
                "denominator_source_url": denominator.source_url,
            })

    return results


def _calculate_balance_sheet_ratios(
    records_by_metric: dict[str, list[FinancialRecord]],
) -> dict[str, list[dict[str, Any]]]:
    assets = {
        r.period_end: r
        for r in records_by_metric.get("TotalAssets", [])
    }

    liabilities = {
        r.period_end: r
        for r in records_by_metric.get("TotalLiabilities", [])
    }

    cash = {
        r.period_end: r
        for r in records_by_metric.get("CashAndCashEquivalents", [])
    }

    results = []

    for period_end, asset_record in sorted(assets.items()):
        asset_value = _decimal(asset_record.metric_value)

        if asset_value == 0:
            continue

        liability_record = liabilities.get(period_end)
        cash_record = cash.get(period_end)

        results.append({
            "period_end": period_end.isoformat(),
            "total_assets": float(asset_value),
            "liabilities_to_assets_pct": (
                _percentage(
                    _decimal(liability_record.metric_value),
                    asset_value,
                )
                if liability_record else None
            ),
            "cash_to_assets_pct": (
                _percentage(
                    _decimal(cash_record.metric_value),
                    asset_value,
                )
                if cash_record else None
            ),
            "assets_source_url": asset_record.source_url,
            "liabilities_source_url": (
                liability_record.source_url if liability_record else None
            ),
            "cash_source_url": (
                cash_record.source_url if cash_record else None
            ),
        })

    return results


class FinancialAnalysisService:
    """Read-only financial analysis for a supported company."""

    def analyze_company(self, session: Session, ticker: str) -> dict[str, Any]:
        company = session.scalar(
            select(Company).where(Company.ticker.ilike(ticker))
        )

        if company is None:
            raise ValueError(f"Company not found: {ticker}")

        records = list(session.scalars(
            select(FinancialRecord).where(
                FinancialRecord.company_id == company.company_id
            )
        ).all())

        latest_records = _select_latest_versions(records)

        records_by_metric = defaultdict(list)

        for record in latest_records:
            records_by_metric[record.metric_name].append(record)

        metrics = {}

        for metric_name, metric_records in records_by_metric.items():
            if metric_name in FLOW_METRICS:
                metric_records = [
                    r for r in metric_records
                    if r.period_type in ("annual", "quarterly")
                ]
                metrics[metric_name] = _add_growth(metric_records)

            elif metric_name in INSTANT_METRICS:
                metrics[metric_name] = [
                    _record_dict(r)
                    for r in sorted(
                        metric_records,
                        key=lambda item: item.period_end,
                    )
                    if r.period_type == "instant"
                ]

            else:
                metrics[metric_name] = [
                    _record_dict(r)
                    for r in sorted(
                        metric_records,
                        key=lambda item: item.period_end,
                    )
                    if r.period_type in ("annual", "quarterly")
                ]

        return {
            "company": {
                "name": company.name,
                "ticker": company.ticker,
                "cik": company.cik,
            },
            "data_quality": {
                "raw_records": len(records),
                "selected_period_records": len(latest_records),
                "superseded_versions_excluded": (
                    len(records) - len(latest_records)
                ),
            },
            "metrics": metrics,
            "margins": _calculate_margins(records_by_metric),
            "balance_sheet_ratios": _calculate_balance_sheet_ratios(
                records_by_metric
            ),
        }

"""Normalisation of SEC company facts into period-based financial records.

Handles differences in XBRL tags between companies and over time, classifies reporting
periods by duration, derives fiscal years and quarters from each company's fiscal
calendar, and retains restated values as separate versions.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Optional

from app.core.exceptions import DataNormalizationError
from app.schemas.financial import (
    CompanyProfile,
    MetricCoverage,
    NormalizationResult,
    NormalizedFinancialFact,
)

logger = logging.getLogger(__name__)

SEC_ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data"
ACCEPTED_FORMS = ("10-K", "10-Q")

ANNUAL_DAYS = (350, 380)
QUARTER_DAYS = (80, 100)
YTD_DAYS = ((170, 200), (260, 290))


@dataclass(frozen=True)
class MetricDefinition:
    name: str
    tags: tuple[str, ...]
    unit: str
    kind: str  # "flow" (duration) or "instant" (balance sheet date)
    allow_ytd: bool = False


METRIC_DEFINITIONS: tuple[MetricDefinition, ...] = (
    MetricDefinition(
        "Revenue",
        (
            "Revenues",
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "RevenueFromContractWithCustomerIncludingAssessedTax",
            "SalesRevenueNet",
            "SalesRevenueGoodsNet",
        ),
        "USD",
        "flow",
    ),
    MetricDefinition(
        "NetIncome",
        ("NetIncomeLoss", "ProfitLoss", "NetIncomeLossAvailableToCommonStockholdersBasic"),
        "USD",
        "flow",
    ),
    MetricDefinition("OperatingIncome", ("OperatingIncomeLoss",), "USD", "flow"),
    MetricDefinition("TotalAssets", ("Assets",), "USD", "instant"),
    MetricDefinition("TotalLiabilities", ("Liabilities",), "USD", "instant"),
    MetricDefinition(
        "CashAndCashEquivalents",
        (
            "CashAndCashEquivalentsAtCarryingValue",
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        ),
        "USD",
        "instant",
    ),
    MetricDefinition(
        "OperatingCashFlow",
        (
            "NetCashProvidedByUsedInOperatingActivities",
            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
        ),
        "USD",
        "flow",
        allow_ytd=True,
    ),
    MetricDefinition("EarningsPerShareBasic", ("EarningsPerShareBasic",), "USD/shares", "flow"),
    MetricDefinition("EarningsPerShareDiluted", ("EarningsPerShareDiluted",), "USD/shares", "flow"),
)

_TOTAL_LIABILITIES_AND_EQUITY = MetricDefinition(
    "_LiabilitiesAndStockholdersEquity", ("LiabilitiesAndStockholdersEquity",), "USD", "instant"
)
_TOTAL_EQUITY = MetricDefinition(
    "_StockholdersEquity",
    (
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        "StockholdersEquity",
    ),
    "USD",
    "instant",
)


@dataclass(frozen=True)
class _Candidate:
    tag_rank: int
    tag: str
    period_type: str
    period_start: Optional[date]
    period_end: date
    value: Decimal
    accession: str
    filed: date
    form: str


def build_source_url(cik: str, accession: str, primary_document: Optional[str]) -> str:
    folder = f"{SEC_ARCHIVES_URL}/{int(cik)}/{accession.replace('-', '')}"
    return f"{folder}/{primary_document}" if primary_document else f"{folder}/"


def fiscal_year_end_month(value: Optional[str]) -> Optional[int]:
    """Parse the SEC fiscalYearEnd value (MMDD) into a month number."""
    if not value or len(value) < 2 or not value[:2].isdigit():
        return None
    month = int(value[:2])
    return month if 1 <= month <= 12 else None


def fiscal_period(period_end: date, fye_month: int, period_type: str) -> tuple[int, Optional[int]]:
    """Derive (fiscal_year, fiscal_quarter) from the period end date and fiscal year end month.

    A seven-day offset absorbs 52/53-week calendars whose periods end in the first days
    of the following month. Annual periods have no fiscal quarter.
    """
    effective = period_end - timedelta(days=7)
    month = effective.month
    fiscal_year = effective.year + (1 if month > fye_month else 0)
    if period_type == "annual":
        return fiscal_year, None
    quarter = ((month - fye_month - 1) % 12) // 3 + 1
    return fiscal_year, quarter


def classify_period(start: Optional[date], end: date, definition: MetricDefinition) -> Optional[str]:
    if definition.kind == "instant":
        return "instant" if start is None else None
    if start is None:
        return None
    days = (end - start).days + 1
    if ANNUAL_DAYS[0] <= days <= ANNUAL_DAYS[1]:
        return "annual"
    if QUARTER_DAYS[0] <= days <= QUARTER_DAYS[1]:
        return "quarterly"
    if definition.allow_ytd and any(low <= days <= high for low, high in YTD_DAYS):
        return "ytd"
    return None


def _parse_date(value: Any) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _parse_value(value: Any) -> Optional[Decimal]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() else None


def _parse_entry(entry: Any, rank: int, tag: str, definition: MetricDefinition) -> Optional[_Candidate]:
    if not isinstance(entry, dict):
        return None
    form = str(entry.get("form") or "")
    if not form.startswith(ACCEPTED_FORMS):
        return None
    start = _parse_date(entry.get("start"))
    end = _parse_date(entry.get("end"))
    filed = _parse_date(entry.get("filed"))
    accession = entry.get("accn")
    value = _parse_value(entry.get("val"))
    if end is None or filed is None or not accession or value is None:
        return None
    period_type = classify_period(start, end, definition)
    if period_type is None:
        return None
    return _Candidate(
        tag_rank=rank,
        tag=tag,
        period_type=period_type,
        period_start=start,
        period_end=end,
        value=value,
        accession=str(accession),
        filed=filed,
        form=form,
    )


def _collect(us_gaap: Mapping[str, Any], definition: MetricDefinition) -> dict[tuple[str, date], list[_Candidate]]:
    grouped: dict[tuple[str, date], list[_Candidate]] = defaultdict(list)
    for rank, tag in enumerate(definition.tags):
        node = us_gaap.get(tag)
        if not isinstance(node, dict):
            continue
        entries = (node.get("units") or {}).get(definition.unit) or []
        for entry in entries:
            candidate = _parse_entry(entry, rank, tag, definition)
            if candidate is not None:
                grouped[(candidate.period_type, candidate.period_end)].append(candidate)
    return grouped


def _build_fact(
    *,
    metric_name: str,
    unit: str,
    candidate: _Candidate,
    fye_month: int,
    cik: str,
    filing_documents: Mapping[str, str],
    value: Optional[Decimal] = None,
    source_tag: Optional[str] = None,
    is_derived: bool = False,
) -> NormalizedFinancialFact:
    fiscal_year, fiscal_quarter = fiscal_period(candidate.period_end, fye_month, candidate.period_type)
    return NormalizedFinancialFact(
        metric_name=metric_name,
        period_type=candidate.period_type,
        metric_value=candidate.value if value is None else value,
        unit=unit,
        fiscal_year=fiscal_year,
        fiscal_quarter=fiscal_quarter,
        period_start=candidate.period_start,
        period_end=candidate.period_end,
        filing_date=candidate.filed,
        form_type=candidate.form,
        accession_number=candidate.accession,
        source_url=build_source_url(cik, candidate.accession, filing_documents.get(candidate.accession)),
        source_tag=source_tag or candidate.tag,
        is_derived=is_derived,
    )


def _extract_metric(
    us_gaap: Mapping[str, Any],
    definition: MetricDefinition,
    *,
    fye_month: int,
    cik: str,
    filing_documents: Mapping[str, str],
) -> list[NormalizedFinancialFact]:
    facts: list[NormalizedFinancialFact] = []
    for candidates in _collect(us_gaap, definition).values():
        best_rank = min(candidate.tag_rank for candidate in candidates)
        selected = sorted(
            (candidate for candidate in candidates if candidate.tag_rank == best_rank),
            key=lambda candidate: (candidate.filed, candidate.accession),
        )
        seen_accessions: set[str] = set()
        last_value: Optional[Decimal] = None
        for candidate in selected:
            if candidate.accession in seen_accessions:
                continue
            seen_accessions.add(candidate.accession)
            if last_value is not None and candidate.value == last_value:
                continue
            last_value = candidate.value
            facts.append(
                _build_fact(
                    metric_name=definition.name,
                    unit=definition.unit,
                    candidate=candidate,
                    fye_month=fye_month,
                    cik=cik,
                    filing_documents=filing_documents,
                )
            )
    return facts


def _derive_liabilities(
    us_gaap: Mapping[str, Any],
    existing_periods: set[tuple[str, date]],
    *,
    fye_month: int,
    cik: str,
    filing_documents: Mapping[str, str],
) -> list[NormalizedFinancialFact]:
    """Derive total liabilities as total liabilities and equity minus total equity."""
    totals = _collect(us_gaap, _TOTAL_LIABILITIES_AND_EQUITY)
    equities = _collect(us_gaap, _TOTAL_EQUITY)
    derived: list[NormalizedFinancialFact] = []
    for key, total_candidates in totals.items():
        if key in existing_periods:
            continue
        total = min(total_candidates, key=lambda c: (c.tag_rank, c.filed, c.accession))
        matching = [c for c in equities.get(key, []) if c.accession == total.accession]
        if not matching:
            continue
        equity = min(matching, key=lambda c: c.tag_rank)
        derived.append(
            _build_fact(
                metric_name="TotalLiabilities",
                unit="USD",
                candidate=total,
                fye_month=fye_month,
                cik=cik,
                filing_documents=filing_documents,
                value=total.value - equity.value,
                source_tag=f"derived:{total.tag}-{equity.tag}",
                is_derived=True,
            )
        )
    return derived


def _coverage(facts: list[NormalizedFinancialFact]) -> list[MetricCoverage]:
    by_metric: dict[str, list[NormalizedFinancialFact]] = defaultdict(list)
    for fact in facts:
        by_metric[fact.metric_name].append(fact)
    coverage: list[MetricCoverage] = []
    for definition in METRIC_DEFINITIONS:
        items = by_metric.get(definition.name, [])
        ends = [item.period_end for item in items]
        coverage.append(
            MetricCoverage(
                metric_name=definition.name,
                record_count=len(items),
                first_period_end=min(ends) if ends else None,
                last_period_end=max(ends) if ends else None,
                source_tags=sorted({item.source_tag for item in items}),
            )
        )
    return coverage


def normalize_company_facts(
    payload: Mapping[str, Any],
    *,
    cik: str,
    fiscal_year_end_month: int,
    filing_documents: Mapping[str, str],
) -> NormalizationResult:
    us_gaap = (payload.get("facts") or {}).get("us-gaap")
    if not us_gaap:
        raise DataNormalizationError("Company facts payload contains no us-gaap taxonomy data.")

    facts: list[NormalizedFinancialFact] = []
    for definition in METRIC_DEFINITIONS:
        metric_facts = _extract_metric(
            us_gaap, definition, fye_month=fiscal_year_end_month, cik=cik, filing_documents=filing_documents
        )
        if definition.name == "TotalLiabilities":
            existing = {(fact.period_type, fact.period_end) for fact in metric_facts}
            metric_facts.extend(
                _derive_liabilities(
                    us_gaap,
                    existing,
                    fye_month=fiscal_year_end_month,
                    cik=cik,
                    filing_documents=filing_documents,
                )
            )
        facts.extend(metric_facts)

    facts.sort(key=lambda f: (f.metric_name, f.period_type, f.period_end, f.filing_date))
    result = NormalizationResult(facts=facts, coverage=_coverage(facts))
    if result.missing_metrics:
        logger.warning("metrics_unavailable", extra={"cik": cik, "missing_metrics": result.missing_metrics})
    return result


def parse_submissions(payload: Mapping[str, Any]) -> tuple[CompanyProfile, dict[str, str]]:
    """Extract the company profile and an accession-to-document mapping from submissions data."""
    recent = (payload.get("filings") or {}).get("recent") or {}
    accessions = recent.get("accessionNumber") or []
    documents = recent.get("primaryDocument") or []
    filing_documents = {
        accession: document for accession, document in zip(accessions, documents) if accession and document
    }
    sic = payload.get("sic")
    profile = CompanyProfile(
        name=payload.get("name"),
        sic=str(sic) if sic else None,
        industry=payload.get("sicDescription") or None,
        fiscal_year_end=payload.get("fiscalYearEnd") or None,
        tickers=list(payload.get("tickers") or []),
    )
    return profile, filing_documents

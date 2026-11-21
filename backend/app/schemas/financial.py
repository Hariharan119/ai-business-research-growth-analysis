"""Schemas for normalised SEC financial data."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel

PeriodType = Literal["annual", "quarterly", "ytd", "instant"]


class NormalizedFinancialFact(BaseModel):
    metric_name: str
    period_type: PeriodType
    metric_value: Decimal
    unit: str
    fiscal_year: int
    fiscal_quarter: Optional[int] = None
    period_start: Optional[date] = None
    period_end: date
    filing_date: date
    form_type: str
    accession_number: str
    source_url: str
    source_tag: str
    is_derived: bool = False


class MetricCoverage(BaseModel):
    metric_name: str
    record_count: int
    first_period_end: Optional[date] = None
    last_period_end: Optional[date] = None
    source_tags: list[str]


class NormalizationResult(BaseModel):
    facts: list[NormalizedFinancialFact]
    coverage: list[MetricCoverage]

    @property
    def missing_metrics(self) -> list[str]:
        return [item.metric_name for item in self.coverage if item.record_count == 0]


class CompanyProfile(BaseModel):
    name: Optional[str] = None
    sic: Optional[str] = None
    industry: Optional[str] = None
    fiscal_year_end: Optional[str] = None
    tickers: list[str] = []

"""Company response schema."""

from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict


class CompanyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    company_id: int
    name: str
    ticker: str
    cik: str
    industry: Optional[str] = None
    fiscal_year_end: Optional[str] = None
    is_active: bool
    latest_filing_date: Optional[date] = None

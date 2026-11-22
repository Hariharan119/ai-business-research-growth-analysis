"""Schemas for data refresh requests, results and status."""
from __future__ import annotations
from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field

class RefreshRequest(BaseModel):
    tickers: Optional[list[str]] = None
    sources: list[Literal["SEC", "NEWSDATA"]] = Field(default_factory=lambda: ["SEC", "NEWSDATA"])

class RefreshAccepted(BaseModel):
    status: str
    tickers: Optional[list[str]] = None
    sources: list[str]

class RefreshResult(BaseModel):
    source: str
    ticker: str
    status: str
    records_fetched: int = 0
    records_inserted: int = 0
    records_skipped: int = 0
    missing_metrics: list[str] = Field(default_factory=list)
    error: Optional[str] = None
    duration_seconds: float = 0.0

class RefreshLogEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    data_refresh_log_id: int
    source: str
    company_id: Optional[int] = None
    trigger_type: str
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    records_fetched: int = 0
    records_inserted: int = 0
    records_skipped: int = 0
    error_message: Optional[str] = None

class LastSuccessEntry(BaseModel):
    company_id: Optional[int] = None
    source: str
    completed_at: Optional[datetime] = None

class RefreshStatusResponse(BaseModel):
    is_running: bool
    last_success: list[LastSuccessEntry] = Field(default_factory=list)
    recent: list[RefreshLogEntry] = Field(default_factory=list)

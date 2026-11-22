"""Request and response schemas for multi-agent research."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.companies import normalize_ticker


class ResearchRequest(BaseModel):
    ticker: str

    forecast_horizon: int = Field(default=4, ge=1, le=8)
    confidence_level: float = Field(default=0.95, gt=0.5, lt=1.0)

    news_days: int = Field(default=30, ge=1, le=365)
    news_limit: int = Field(default=100, ge=1, le=100)

    @field_validator("ticker")
    @classmethod
    def validate_ticker(cls, value: str) -> str:
        """Accept any configured company; reject others before agents run."""
        return normalize_ticker(value)


class ResearchReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    research_report_id: int
    ticker: str
    status: str
    request_data: dict[str, Any]
    result_data: dict[str, Any] | None = None
    error_message: str | None = None
    created_at: datetime
    completed_at: datetime | None = None

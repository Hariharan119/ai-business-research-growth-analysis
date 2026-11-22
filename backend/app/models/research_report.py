"""Persisted multi-agent research reports."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class ResearchReport(Base):
    __tablename__ = "research_reports"

    research_report_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )

    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.company_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    ticker: Mapped[str] = mapped_column(
        String(16), nullable=False, index=True
    )

    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="running", index=True
    )

    request_data: Mapped[dict] = mapped_column(
        JSON, nullable=False
    )

    result_data: Mapped[dict | None] = mapped_column(JSON)

    error_message: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    completed_at: Mapped[datetime | None] = mapped_column(DateTime)

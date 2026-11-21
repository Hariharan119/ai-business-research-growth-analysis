"""Normalized SEC financial facts."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Integer, Numeric,
    String, UniqueConstraint, func
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class FinancialRecord(Base):
    __tablename__ = "financial_records"

    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "metric_name",
            "period_type",
            "period_end",
            "accession_number",
            "source_tag",
            name="uq_financial_record_version",
        ),
    )

    financial_record_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.company_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    metric_name: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )
    period_type: Mapped[str] = mapped_column(String(16), nullable=False)
    metric_value: Mapped[Decimal] = mapped_column(
        Numeric(38, 10), nullable=False
    )
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    fiscal_quarter: Mapped[int | None] = mapped_column(Integer)
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    filing_date: Mapped[date] = mapped_column(Date, nullable=False)
    form_type: Mapped[str] = mapped_column(String(16), nullable=False)
    accession_number: Mapped[str] = mapped_column(
        String(32), nullable=False
    )
    source_url: Mapped[str] = mapped_column(String(2000), nullable=False)
    source_tag: Mapped[str] = mapped_column(String(200), nullable=False)
    is_derived: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

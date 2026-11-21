"""Company database model."""

from datetime import date

from sqlalchemy import Boolean, Date, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class Company(Base):
    __tablename__ = "companies"

    company_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    ticker: Mapped[str] = mapped_column(
        String(16), nullable=False, unique=True, index=True
    )
    cik: Mapped[str] = mapped_column(
        String(10), nullable=False, unique=True, index=True
    )
    industry: Mapped[str | None] = mapped_column(String(255))
    fiscal_year_end: Mapped[str | None] = mapped_column(String(4))
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    latest_filing_date: Mapped[date | None] = mapped_column(Date)
    news_query: Mapped[str] = mapped_column(
        String(300), nullable=False
    )

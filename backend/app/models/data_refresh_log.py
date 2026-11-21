"""Source refresh execution history."""

from datetime import datetime

from sqlalchemy import (
    DateTime, ForeignKey, Integer, String, Text
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class DataRefreshLog(Base):
    __tablename__ = "data_refresh_logs"

    data_refresh_log_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    source: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True
    )
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.company_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    trigger_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="manual"
    )
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="running", index=True
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    records_fetched: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    records_inserted: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    records_skipped: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    error_message: Mapped[str | None] = mapped_column(Text)


SOURCES = ("SEC", "NEWSDATA")

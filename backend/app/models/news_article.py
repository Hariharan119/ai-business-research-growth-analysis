"""Normalized news article metadata."""

from datetime import datetime

from sqlalchemy import (
    DateTime, ForeignKey, Integer, String, Text,
    UniqueConstraint, func
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class NewsArticle(Base):
    __tablename__ = "news_articles"

    __table_args__ = (
        UniqueConstraint(
            "company_id", "url_hash",
            name="uq_news_article_company_url",
        ),
    )

    news_article_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.company_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    headline: Mapped[str] = mapped_column(String(500), nullable=False)
    article_url: Mapped[str] = mapped_column(String(2000), nullable=False)
    url_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    title_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )
    source_name: Mapped[str | None] = mapped_column(String(255))
    language: Mapped[str | None] = mapped_column(String(32))
    source_country: Mapped[str | None] = mapped_column(String(64))
    snippet: Mapped[str | None] = mapped_column(Text)
    provider_category: Mapped[str | None] = mapped_column(String(128))
    published_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

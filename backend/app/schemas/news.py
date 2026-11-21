"""Schemas for normalised news article metadata."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class NormalizedArticle(BaseModel):
    headline: str
    article_url: str
    url_hash: str
    title_hash: str
    source_name: Optional[str] = None
    language: Optional[str] = None
    source_country: Optional[str] = None
    snippet: Optional[str] = None
    provider_category: Optional[str] = None
    published_at: datetime

"""Normalisation and deduplication of NewsData.io article metadata."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Iterable, Optional

from app.schemas.news import NormalizedArticle
from app.utils.text import canonicalize_url, extract_plain_url, normalize_title, sha256_hex

logger = logging.getLogger(__name__)

TITLE_DUPLICATE_WINDOW = timedelta(days=3)
MAX_HEADLINE_LENGTH = 500
MAX_URL_LENGTH = 2000
MAX_SNIPPET_LENGTH = 1500


def _parse_pub_date(value: Any) -> Optional[datetime]:
    try:
        return datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _clean(value: Any, limit: int) -> Optional[str]:
    if isinstance(value, (list, tuple)):
        value = ", ".join(str(item) for item in value if item)
    text = " ".join(str(value).split()) if value else ""
    return text[:limit] if text else None


def _parse_article(item: Any) -> Optional[NormalizedArticle]:
    if not isinstance(item, dict) or item.get("duplicate") is True:
        return None
    url = extract_plain_url(str(item.get("link") or ""))
    headline = _clean(item.get("title"), MAX_HEADLINE_LENGTH)
    published_at = _parse_pub_date(item.get("pubDate"))
    if not url.lower().startswith(("http://", "https://")) or len(url) > MAX_URL_LENGTH:
        return None
    if headline is None or published_at is None:
        return None
    return NormalizedArticle(
        headline=headline,
        article_url=url,
        url_hash=sha256_hex(canonicalize_url(url)),
        title_hash=sha256_hex(normalize_title(headline)),
        source_name=_clean(item.get("source_name") or item.get("source_id"), 255),
        language=_clean(item.get("language"), 32),
        source_country=_clean(item.get("country"), 64),
        snippet=_clean(item.get("description"), MAX_SNIPPET_LENGTH),
        provider_category=_clean(item.get("category"), 128),
        published_at=published_at,
    )


def normalize_articles(raw_articles: Iterable[Any]) -> list[NormalizedArticle]:
    """Parse raw records and remove duplicates by URL and by near-identical headline."""
    parsed = [article for article in (_parse_article(item) for item in raw_articles) if article is not None]
    parsed.sort(key=lambda article: article.published_at)

    seen_urls: set[str] = set()
    title_dates: dict[str, list[datetime]] = {}
    result: list[NormalizedArticle] = []
    for article in parsed:
        if article.url_hash in seen_urls:
            continue
        dates = title_dates.setdefault(article.title_hash, [])
        if any(abs(article.published_at - seen) <= TITLE_DUPLICATE_WINDOW for seen in dates):
            continue
        seen_urls.add(article.url_hash)
        dates.append(article.published_at)
        result.append(article)
    return result

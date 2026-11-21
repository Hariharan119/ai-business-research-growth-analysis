"""Asynchronous client for the NewsData.io latest news endpoint."""

from __future__ import annotations

import logging
from typing import Any, Optional
from urllib.parse import urlencode

import httpx

from app.core.config import Settings, get_settings
from app.core.exceptions import ExternalApiError, TemporaryApiError
from app.utils.cache import JsonFileCache
from app.utils.rate_limiter import AsyncRateLimiter
from app.utils.retry import retry_async

logger = logging.getLogger(__name__)

RETRYABLE_STATUS_CODES = {500, 502, 503, 504}


class NewsDataClient:
    def __init__(
        self,
        settings: Optional[Settings] = None,
        *,
        http_client: Optional[httpx.AsyncClient] = None,
        cache: Optional[JsonFileCache] = None,
        rate_limiter: Optional[AsyncRateLimiter] = None,
        retry_base_delay: float = 2.0,
    ) -> None:
        self._settings = settings or get_settings()
        self._client = http_client
        self._owns_client = http_client is None
        self._cache = cache or JsonFileCache(
            self._settings.cache_dir / "newsdata", ttl_seconds=self._settings.newsdata_cache_ttl_minutes * 60
        )
        self._limiter = rate_limiter or AsyncRateLimiter(self._settings.newsdata_min_interval_seconds)
        self._retry_base_delay = retry_base_delay

    async def __aenter__(self) -> "NewsDataClient":
        return self

    async def __aexit__(self, *_exc_info) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers={"Accept": "application/json"},
                timeout=self._settings.http_timeout_seconds,
                follow_redirects=True,
            )
        return self._client

    async def search_articles(self, query: str, *, max_pages: Optional[int] = None) -> list[dict[str, Any]]:
        pages = max_pages or self._settings.newsdata_max_pages
        settings = self._settings
        key_parts = {
            "qInTitle": query,
            "language": settings.newsdata_language,
            "size": settings.newsdata_page_size,
            "pages": pages,
        }
        cache_key = f"{settings.newsdata_base_url}/latest?{urlencode(sorted(key_parts.items()))}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        settings.require_newsdata_key()
        try:
            articles, complete = await self._collect(query, pages)
        except ExternalApiError:
            stale = self._cache.get(cache_key, allow_stale=True)
            if stale is not None:
                logger.warning("newsdata_stale_cache_served", extra={"query": query})
                return stale
            raise
        if complete:
            self._cache.set(cache_key, articles)
        return articles

    async def _collect(self, query: str, pages: int) -> tuple[list[dict[str, Any]], bool]:
        settings = self._settings
        articles: list[dict[str, Any]] = []
        cursor: Optional[str] = None
        for index in range(pages):
            params = {
                "apikey": settings.require_newsdata_key(),
                "qInTitle": query,
                "language": settings.newsdata_language,
                "size": str(settings.newsdata_page_size),
            }
            if cursor:
                params["page"] = cursor
            try:
                payload = await retry_async(
                    lambda params=params: self._request(params),
                    attempts=settings.http_max_attempts,
                    base_delay=self._retry_base_delay,
                    retry_on=(TemporaryApiError,),
                    description="newsdata_request",
                )
            except ExternalApiError:
                if index == 0:
                    raise
                logger.warning("newsdata_partial_result", extra={"query": query, "pages_retrieved": index})
                return articles, False
            results = payload.get("results")
            if isinstance(results, list):
                articles.extend(item for item in results if isinstance(item, dict))
            cursor = payload.get("nextPage")
            if not cursor or not results:
                break
        return articles, True

    async def _request(self, params: dict[str, str]) -> dict[str, Any]:
        await self._limiter.wait()
        client = self._ensure_client()
        url = f"{self._settings.newsdata_base_url}/latest"
        try:
            response = await client.get(url, params=params)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise TemporaryApiError(f"NewsData.io request failed: {type(exc).__name__}") from exc

        status = response.status_code
        if status in (401, 403):
            raise ExternalApiError(f"NewsData.io rejected the API key (HTTP {status}).")
        if status == 429:
            raise TemporaryApiError("NewsData.io rate or daily credit limit reached (HTTP 429).")
        if status in RETRYABLE_STATUS_CODES:
            raise TemporaryApiError(f"NewsData.io returned HTTP {status}")
        if status >= 400:
            raise ExternalApiError(f"NewsData.io returned HTTP {status}: {self._error_message(response)}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise ExternalApiError("NewsData.io returned a non-JSON response") from exc
        if not isinstance(payload, dict) or payload.get("status") != "success":
            raise ExternalApiError(f"NewsData.io returned an unsuccessful response: {self._error_message(response)}")
        return payload

    @staticmethod
    def _error_message(response: httpx.Response) -> str:
        try:
            results = response.json().get("results")
            if isinstance(results, dict) and results.get("message"):
                return str(results["message"])[:200]
        except (ValueError, AttributeError):
            pass
        return response.text[:200]

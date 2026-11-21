"""Asynchronous client for the GDELT DOC 2.0 API (article list mode)."""

from __future__ import annotations

import json
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

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class GdeltClient:
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
            self._settings.cache_dir / "gdelt", ttl_seconds=self._settings.gdelt_cache_ttl_minutes * 60
        )
        self._limiter = rate_limiter or AsyncRateLimiter(self._settings.gdelt_min_interval_seconds)
        self._retry_base_delay = retry_base_delay

    async def __aenter__(self) -> "GdeltClient":
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

    async def search_articles(
        self,
        query: str,
        *,
        timespan: Optional[str] = None,
        max_records: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        params = {
            "query": f"{query} sourcelang:english",
            "mode": "ArtList",
            "format": "json",
            "maxrecords": str(max_records or self._settings.gdelt_max_records),
            "timespan": timespan or self._settings.gdelt_timespan,
            "sort": "DateDesc",
        }
        cache_key = f"{self._settings.gdelt_base_url}?{urlencode(sorted(params.items()))}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return self._articles(cached)
        try:
            payload = await retry_async(
                lambda: self._request(params),
                attempts=self._settings.http_max_attempts,
                base_delay=self._retry_base_delay,
                retry_on=(TemporaryApiError,),
                description="gdelt_request",
            )
        except ExternalApiError:
            stale = self._cache.get(cache_key, allow_stale=True)
            if stale is not None:
                logger.warning("gdelt_stale_cache_served", extra={"query": query})
                return self._articles(stale)
            raise
        self._cache.set(cache_key, payload)
        return self._articles(payload)

    @staticmethod
    def _articles(payload: dict[str, Any]) -> list[dict[str, Any]]:
        articles = payload.get("articles", [])
        return articles if isinstance(articles, list) else []

    async def _request(self, params: dict[str, str]) -> dict[str, Any]:
        await self._limiter.wait()
        client = self._ensure_client()
        try:
            response = await client.get(self._settings.gdelt_base_url, params=params)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise TemporaryApiError(f"GDELT request failed: {type(exc).__name__}") from exc

        if response.status_code in RETRYABLE_STATUS_CODES:
            raise TemporaryApiError(f"GDELT returned HTTP {response.status_code}")
        if response.status_code >= 400:
            raise ExternalApiError(f"GDELT returned HTTP {response.status_code}")

        text = response.text.strip()
        if not text:
            return {}
        try:
            payload = json.loads(text, strict=False)
        except ValueError:
            snippet = text[:200]
            if "limit requests" in snippet.lower():
                raise TemporaryApiError(f"GDELT rate limit response: {snippet}")
            raise ExternalApiError(f"GDELT returned a non-JSON response: {snippet}")
        if not isinstance(payload, dict):
            raise ExternalApiError("GDELT returned an unexpected JSON structure")
        return payload

"""Asynchronous client for the SEC EDGAR data APIs."""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from app.core.config import Settings, get_settings
from app.core.exceptions import ExternalApiError, TemporaryApiError
from app.utils.cache import JsonFileCache
from app.utils.rate_limiter import AsyncRateLimiter
from app.utils.retry import retry_async

logger = logging.getLogger(__name__)

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class SecEdgarClient:
    def __init__(
        self,
        settings: Optional[Settings] = None,
        *,
        http_client: Optional[httpx.AsyncClient] = None,
        cache: Optional[JsonFileCache] = None,
        rate_limiter: Optional[AsyncRateLimiter] = None,
        retry_base_delay: float = 1.0,
    ) -> None:
        self._settings = settings or get_settings()
        self._client = http_client
        self._owns_client = http_client is None
        self._cache = cache or JsonFileCache(
            self._settings.cache_dir / "sec", ttl_seconds=self._settings.sec_cache_ttl_hours * 3600
        )
        self._limiter = rate_limiter or AsyncRateLimiter(1.0 / self._settings.sec_requests_per_second)
        self._retry_base_delay = retry_base_delay

    async def __aenter__(self) -> "SecEdgarClient":
        return self

    async def __aexit__(self, *_exc_info) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            user_agent = self._settings.require_sec_user_agent()
            self._client = httpx.AsyncClient(
                headers={"User-Agent": user_agent, "Accept": "application/json"},
                timeout=self._settings.http_timeout_seconds,
                follow_redirects=True,
            )
        return self._client

    @staticmethod
    def _cik10(cik: str) -> str:
        return str(int(cik)).zfill(10)

    async def get_company_facts(self, cik: str) -> dict[str, Any]:
        url = f"{self._settings.sec_base_url}/api/xbrl/companyfacts/CIK{self._cik10(cik)}.json"
        return await self._get_json(url)

    async def get_submissions(self, cik: str) -> dict[str, Any]:
        url = f"{self._settings.sec_base_url}/submissions/CIK{self._cik10(cik)}.json"
        return await self._get_json(url)

    async def _get_json(self, url: str) -> dict[str, Any]:
        cached = self._cache.get(url)
        if cached is not None:
            return cached
        try:
            payload = await retry_async(
                lambda: self._request(url),
                attempts=self._settings.http_max_attempts,
                base_delay=self._retry_base_delay,
                retry_on=(TemporaryApiError,),
                description="sec_request",
            )
        except Exception:
            stale = self._cache.get(url, allow_stale=True)
            if stale is not None:
                logger.warning("sec_stale_cache_served", extra={"url": url})
                return stale
            raise
        self._cache.set(url, payload)
        return payload

    async def _request(self, url: str) -> dict[str, Any]:
        await self._limiter.wait()
        client = self._ensure_client()
        try:
            response = await client.get(url)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise TemporaryApiError(f"SEC request failed: {type(exc).__name__}") from exc

        status = response.status_code
        if status in RETRYABLE_STATUS_CODES:
            raise TemporaryApiError(f"SEC returned HTTP {status}")
        if status == 403:
            raise ExternalApiError("SEC returned HTTP 403. Verify SEC_USER_AGENT and the request rate.")
        if status == 404:
            raise ExternalApiError(f"SEC resource not found: {url}")
        if status >= 400:
            raise ExternalApiError(f"SEC returned HTTP {status}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise ExternalApiError("SEC returned a non-JSON response") from exc
        if not isinstance(payload, dict):
            raise ExternalApiError("SEC returned an unexpected JSON structure")
        return payload

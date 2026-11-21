"""Entry point for executing a full refresh with managed client lifecycles."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Optional

from app.core.config import get_settings
from app.database.session import get_session_factory
from app.schemas.data_refresh import RefreshResult
from app.services.data_refresh_service import DataRefreshService
from app.services.newsdata_client import NewsDataClient
from app.services.sec_client import SecEdgarClient


async def run_refresh_job(
    tickers: Optional[Sequence[str]],
    sources: Sequence[str],
    trigger: str = "manual",
) -> list[RefreshResult]:
    settings = get_settings()
    async with SecEdgarClient(settings) as sec_client, NewsDataClient(settings) as news_client:
        service = DataRefreshService(get_session_factory(), sec_client, news_client)
        return await service.refresh_all(tickers, sources, trigger)

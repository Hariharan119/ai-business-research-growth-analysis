"""Orchestration of SEC and news data refreshes with logging and failure isolation."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session, sessionmaker

from app.core.exceptions import CompanyNotFoundError
from app.repositories.company_repository import CompanyRepository
from app.repositories.financial_repository import FinancialRepository
from app.repositories.news_repository import NewsRepository
from app.repositories.refresh_log_repository import RefreshLogRepository
from app.schemas.data_refresh import RefreshResult
from app.services.financial_normalizer import (
    fiscal_year_end_month,
    normalize_company_facts,
    parse_submissions,
)
from app.services.news_normalizer import normalize_articles

logger = logging.getLogger(__name__)

CORE_METRICS = frozenset({"Revenue", "NetIncome", "OperatingIncome", "TotalAssets", "TotalLiabilities"})
VALID_SOURCES = ("SEC", "NEWSDATA")


@dataclass(frozen=True)
class CompanyRef:
    company_id: int
    name: str
    ticker: str
    cik: str
    news_query: str


def _error_text(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"[:1000]


class DataRefreshService:
    def __init__(self, session_factory: sessionmaker[Session], sec_client, news_client) -> None:
        self._session_factory = session_factory
        self._sec = sec_client
        self._news = news_client

    @contextmanager
    def _session(self) -> Iterator[Session]:
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def load_company_refs(self, tickers: Optional[Sequence[str]] = None) -> list[CompanyRef]:
        with self._session() as session:
            repository = CompanyRepository(session)
            if tickers:
                companies = []
                for ticker in tickers:
                    company = repository.get_by_ticker(ticker)
                    if company is None:
                        raise CompanyNotFoundError(f"Unsupported ticker: {ticker}")
                    companies.append(company)
            else:
                companies = repository.list_active()
            return [CompanyRef(c.company_id, c.name, c.ticker, c.cik, c.news_query) for c in companies]

    def _open_log(self, source: str, company_id: int, trigger: str) -> int:
        with self._session() as session:
            return RefreshLogRepository(session).start(source, company_id, trigger)

    def _close_log(self, log_id: int, status: str, **values) -> None:
        with self._session() as session:
            RefreshLogRepository(session).finish(log_id, status, **values)

    async def refresh_company_financials(self, ref: CompanyRef, trigger: str = "manual") -> RefreshResult:
        started = time.monotonic()
        log_id = self._open_log("SEC", ref.company_id, trigger)
        try:
            submissions = await self._sec.get_submissions(ref.cik)
            profile, filing_documents = parse_submissions(submissions)
            facts_payload = await self._sec.get_company_facts(ref.cik)
            fye_month = fiscal_year_end_month(profile.fiscal_year_end) or 12
            normalized = normalize_company_facts(
                facts_payload,
                cik=ref.cik,
                fiscal_year_end_month=fye_month,
                filing_documents=filing_documents,
            )
            with self._session() as session:
                CompanyRepository(session).update_profile(ref.company_id, profile)
                inserted, skipped = FinancialRepository(session).insert_new(ref.company_id, normalized.facts)

            status = "partial" if CORE_METRICS.intersection(normalized.missing_metrics) else "success"
            self._close_log(log_id, status, fetched=len(normalized.facts), inserted=inserted, skipped=skipped)
            logger.info(
                "sec_refresh_completed",
                extra={"ticker": ref.ticker, "status": status, "records_inserted": inserted},
            )
            return RefreshResult(
                source="SEC",
                ticker=ref.ticker,
                status=status,
                records_fetched=len(normalized.facts),
                records_inserted=inserted,
                records_skipped=skipped,
                missing_metrics=normalized.missing_metrics,
                duration_seconds=round(time.monotonic() - started, 2),
            )
        except Exception as exc:
            message = _error_text(exc)
            logger.error("sec_refresh_failed", extra={"ticker": ref.ticker, "error": message}, exc_info=True)
            self._close_log(log_id, "failed", error=message)
            return RefreshResult(
                source="SEC",
                ticker=ref.ticker,
                status="failed",
                error=message,
                duration_seconds=round(time.monotonic() - started, 2),
            )

    async def refresh_company_news(self, ref: CompanyRef, trigger: str = "manual") -> RefreshResult:
        started = time.monotonic()
        log_id = self._open_log("NEWSDATA", ref.company_id, trigger)
        try:
            raw_articles = await self._news.search_articles(ref.news_query)
            articles = normalize_articles(raw_articles)
            with self._session() as session:
                inserted = NewsRepository(session).insert_new(ref.company_id, articles)
            fetched = len(raw_articles)
            skipped = fetched - inserted
            self._close_log(log_id, "success", fetched=fetched, inserted=inserted, skipped=skipped)
            logger.info(
                "news_refresh_completed",
                extra={"ticker": ref.ticker, "records_fetched": fetched, "records_inserted": inserted},
            )
            return RefreshResult(
                source="NEWSDATA",
                ticker=ref.ticker,
                status="success",
                records_fetched=fetched,
                records_inserted=inserted,
                records_skipped=skipped,
                duration_seconds=round(time.monotonic() - started, 2),
            )
        except Exception as exc:
            message = _error_text(exc)
            logger.error("news_refresh_failed", extra={"ticker": ref.ticker, "error": message}, exc_info=True)
            self._close_log(log_id, "failed", error=message)
            return RefreshResult(
                source="NEWSDATA",
                ticker=ref.ticker,
                status="failed",
                error=message,
                duration_seconds=round(time.monotonic() - started, 2),
            )

    async def refresh_all(
        self,
        tickers: Optional[Sequence[str]] = None,
        sources: Sequence[str] = VALID_SOURCES,
        trigger: str = "manual",
    ) -> list[RefreshResult]:
        selected = [source.upper() for source in sources]
        invalid = [source for source in selected if source not in VALID_SOURCES]
        if invalid:
            raise ValueError(f"Unsupported source(s): {', '.join(invalid)}")
        refs = self.load_company_refs(tickers)

        async def run_sec() -> list[RefreshResult]:
            return [await self.refresh_company_financials(ref, trigger) for ref in refs]

        async def run_news() -> list[RefreshResult]:
            return [await self.refresh_company_news(ref, trigger) for ref in refs]

        jobs = []
        if "SEC" in selected:
            jobs.append(run_sec())
        if "NEWSDATA" in selected:
            jobs.append(run_news())
        grouped = await asyncio.gather(*jobs)
        return [result for group in grouped for result in group]

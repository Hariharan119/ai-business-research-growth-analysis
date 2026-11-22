# DataRefreshService tests with fake SEC/NewsData clients and an in-memory database.

import asyncio

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (registers the core tables)
from app.core.companies import SUPPORTED_COMPANIES
from app.core.exceptions import CompanyNotFoundError
from app.database.base import Base
from app.models.data_refresh_log import DataRefreshLog
from app.models.news_article import NewsArticle
from app.repositories.company_repository import CompanyRepository
from app.services.data_refresh_service import DataRefreshService


def make_session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        CompanyRepository(session).seed_supported_companies()
        session.commit()
    return factory


class FailingSecClient:
    async def get_submissions(self, cik):
        raise RuntimeError("SEC unavailable")

    async def get_company_facts(self, cik):
        raise AssertionError("must not be called after get_submissions fails")


class FakeNewsClient:
    def __init__(self, articles):
        self.articles = articles
        self.queries = []

    async def search_articles(self, query):
        self.queries.append(query)
        return self.articles


def raw_article(link, title, published="2026-11-20 10:00:00"):
    return {
        "link": link,
        "title": title,
        "pubDate": published,
        "description": "Test article description.",
        "source_id": "test_source",
        "language": "english",
    }


def test_invalid_source_is_rejected_before_any_fetch():
    service = DataRefreshService(make_session_factory(), FailingSecClient(), FakeNewsClient([]))
    with pytest.raises(ValueError):
        asyncio.run(service.refresh_all(sources=["BLOOMBERG"]))


def test_unknown_ticker_raises_company_not_found():
    service = DataRefreshService(make_session_factory(), FailingSecClient(), FakeNewsClient([]))
    with pytest.raises(CompanyNotFoundError):
        service.load_company_refs(["ZZZZ"])


def test_sec_failure_is_isolated_and_logged():
    factory = make_session_factory()
    service = DataRefreshService(factory, FailingSecClient(), FakeNewsClient([]))
    ticker = SUPPORTED_COMPANIES[0].ticker

    results = asyncio.run(service.refresh_all([ticker], ["SEC", "NEWSDATA"]))
    by_source = {result.source: result for result in results}

    assert by_source["SEC"].status == "failed"
    assert "SEC unavailable" in by_source["SEC"].error
    assert by_source["NEWSDATA"].status == "success"  # the other source still runs

    with factory() as session:
        logs = {log.source: log for log in session.scalars(select(DataRefreshLog))}
    assert logs["SEC"].status == "failed"
    assert "SEC unavailable" in logs["SEC"].error_message
    assert logs["SEC"].completed_at is not None


def test_news_refresh_stores_articles_and_skips_duplicates():
    factory = make_session_factory()
    news = FakeNewsClient([
        raw_article("https://example.com/a", "Company announces new product"),
        raw_article("https://example.com/a", "Company announces new product"),
        raw_article("https://example.com/b", "Company reports quarterly results"),
    ])
    service = DataRefreshService(factory, FailingSecClient(), news)
    company = SUPPORTED_COMPANIES[0]

    first = asyncio.run(service.refresh_all([company.ticker], ["NEWSDATA"]))[0]
    second = asyncio.run(service.refresh_all([company.ticker], ["NEWSDATA"]))[0]

    assert news.queries == [company.news_query, company.news_query]
    assert first.status == "success"
    assert first.records_fetched == 3
    assert first.records_inserted == 2
    assert second.records_inserted == 0

    with factory() as session:
        assert len(session.scalars(select(NewsArticle)).all()) == 2

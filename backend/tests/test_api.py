# API tests for validation and read-only endpoints (no external API or LLM calls).

import pytest
from fastapi.testclient import TestClient

from app.core.companies import SUPPORTED_TICKERS, normalize_ticker
from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_normalize_ticker_accepts_supported_and_rejects_others():
    for ticker in SUPPORTED_TICKERS:
        assert normalize_ticker(f" {ticker.lower()} ") == ticker
    with pytest.raises(ValueError):
        normalize_ticker("ZZZZ")


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_companies_match_central_configuration(client):
    response = client.get("/api/v1/companies")
    assert response.status_code == 200
    tickers = {company["ticker"] for company in response.json()}
    assert SUPPORTED_TICKERS <= tickers


def test_unknown_company_returns_404(client):
    assert client.get("/api/v1/companies/ZZZZ").status_code == 404


def test_research_rejects_unsupported_ticker_before_running_agents(client):
    response = client.post("/api/v1/research", json={"ticker": "ZZZZ"})
    assert response.status_code == 422
    assert "Unsupported ticker" in response.text


def test_research_rejects_out_of_range_horizon(client):
    ticker = sorted(SUPPORTED_TICKERS)[0]
    response = client.post("/api/v1/research", json={"ticker": ticker, "forecast_horizon": 9})
    assert response.status_code == 422


def test_research_report_filter_rejects_unsupported_ticker(client):
    assert client.get("/api/v1/research", params={"ticker": "ZZZZ"}).status_code == 422


def test_research_report_filter_normalises_supported_ticker(client):
    ticker = sorted(SUPPORTED_TICKERS)[0]
    response = client.get("/api/v1/research", params={"ticker": ticker.lower()})
    assert response.status_code == 200
    assert all(report["ticker"] == ticker for report in response.json())


def test_refresh_rejects_unsupported_ticker_without_fetching(client):
    response = client.post("/api/v1/refresh", json={"tickers": ["ZZZZ"], "sources": ["SEC"]})
    assert response.status_code == 422


def test_refresh_status_structure(client):
    response = client.get("/api/v1/refresh/status")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["is_running"], bool)
    assert isinstance(body["last_success"], list)
    assert isinstance(body["recent"], list)

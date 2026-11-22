"""Static configuration of supported companies."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CompanyConfig:
    name: str
    ticker: str
    cik: str
    news_query: str
    # Lower-case terms used to detect mentions of the company in news text.
    aliases: tuple[str, ...] = ()


# Single source of truth for supported companies. Adding a company here makes
# it available to seeding, refresh, API validation, the agents and news
# competitor detection.
SUPPORTED_COMPANIES: tuple[CompanyConfig, ...] = (
    CompanyConfig("Microsoft", "MSFT", "0000789019", '"Microsoft" OR "MSFT"', ("microsoft", "msft")),
    CompanyConfig("NVIDIA", "NVDA", "0001045810", '"NVIDIA" OR "NVDA"', ("nvidia", "nvda")),
)

COMPANIES_BY_TICKER: dict[str, CompanyConfig] = {
    company.ticker: company for company in SUPPORTED_COMPANIES
}

SUPPORTED_TICKERS: frozenset[str] = frozenset(COMPANIES_BY_TICKER)


def company_aliases(company: CompanyConfig) -> list[str]:
    """Return the news-matching terms for a company."""
    return list(company.aliases) or [company.name.casefold(), company.ticker.casefold()]


def normalize_ticker(value: str) -> str:
    """Return the upper-case ticker, or raise ValueError if it is not supported."""
    ticker = str(value or "").strip().upper()
    if ticker not in SUPPORTED_TICKERS:
        supported = ", ".join(sorted(SUPPORTED_TICKERS))
        raise ValueError(f"Unsupported ticker: {ticker or value!r}. Supported tickers: {supported}.")
    return ticker

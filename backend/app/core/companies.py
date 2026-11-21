"""Static configuration of supported companies."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CompanyConfig:
    name: str
    ticker: str
    cik: str
    news_query: str


SUPPORTED_COMPANIES: tuple[CompanyConfig, ...] = (
    CompanyConfig("Microsoft", "MSFT", "0000789019", '"Microsoft" OR "MSFT"'),
    CompanyConfig("NVIDIA", "NVDA", "0001045810", '"NVIDIA" OR "NVDA"'),
)

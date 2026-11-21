"""Shared state passed between LangGraph research agents."""

from typing import Any, TypedDict


class ResearchState(TypedDict, total=False):
    ticker: str
    company_name: str
    forecast_horizon: int
    confidence_level: float
    news_days: int
    news_limit: int

    financial_analysis: dict[str, Any]
    revenue_forecast: dict[str, Any]
    news_intelligence: dict[str, Any]

    financial_agent_output: dict[str, Any]
    news_agent_output: dict[str, Any]
    strategic_agent_output: dict[str, Any]

    financial_agent_error: str
    news_agent_error: str
    strategic_agent_error: str

    workflow_status: str

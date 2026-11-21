
"""Financial analysis agent using existing backend services and Groq."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.agents.state import ResearchState
from app.core.config import get_settings
from app.database.session import get_session_factory
from app.schemas.agent_schemas import (
    EvidenceReference,
    FinancialAgentOutput,
)
from app.services.financial_analysis_service import FinancialAnalysisService
from app.services.llm_client import LlmClient, TokenUsage
from app.services.revenue_forecasting_service import forecast_company_revenue

logger = logging.getLogger(__name__)


def _to_dict(value: Any) -> Any:
    """Convert common service results into JSON-compatible data."""
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _to_dict(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_dict(item) for item in value]
    return value


def _compact_context(
    financial: dict[str, Any],
    forecast: dict[str, Any],
) -> dict[str, Any]:
    """Create a compact, evidence-backed financial context for the LLM."""

    def compact_metric(records):
        if not isinstance(records, list):
            return []

        # Preserve the latest annual and quarterly/instant observations.
        selected = []
        for period_type in ("quarterly", "instant", "annual"):
            matches = [
                item for item in records
                if isinstance(item, dict)
                and item.get("period_type") == period_type
            ]

            if matches:
                latest = max(
                    matches,
                    key=lambda item: (
                        item.get("period_end") or "",
                        item.get("filing_date") or "",
                    ),
                )
                selected.append({
                    key: latest.get(key)
                    for key in (
                        "metric_name",
                        "period_type",
                        "value",
                        "unit",
                        "fiscal_year",
                        "fiscal_quarter",
                        "period_end",
                        "filing_date",
                        "year_over_year_growth_pct",
                        "is_derived",
                        "source_url",
                    )
                    if key in latest
                })

        return selected

    metrics = financial.get("metrics") or {}
    compact_metrics = {
        name: compact_metric(records)
        for name, records in metrics.items()
    } if isinstance(metrics, dict) else {}

    margins = financial.get("margins") or {}
    compact_margins = {}

    if isinstance(margins, dict):
        for name, records in margins.items():
            if isinstance(records, list):
                compact_margins[name] = [
                    {
                        key: item.get(key)
                        for key in (
                            "period_type",
                            "period_end",
                            "fiscal_year",
                            "fiscal_quarter",
                            "value_pct",
                            "numerator_source_url",
                            "denominator_source_url",
                        )
                        if key in item
                    }
                    for item in records[-2:]
                    if isinstance(item, dict)
                ]

    ratios = financial.get("balance_sheet_ratios") or []
    compact_ratios = []

    if isinstance(ratios, list):
        compact_ratios = [
            {
                key: item.get(key)
                for key in (
                    "period_end",
                    "total_assets",
                    "liabilities_to_assets_pct",
                    "cash_to_assets_pct",
                    "assets_source_url",
                    "liabilities_source_url",
                    "cash_source_url",
                )
                if key in item
            }
            for item in ratios[-2:]
            if isinstance(item, dict)
        ]

    historical = forecast.get("historical_observations", [])

    return {
        "financial_analysis": {
            "company": financial.get("company"),
            "data_quality": financial.get("data_quality"),
            "metrics": compact_metrics,
            "margins": compact_margins,
            "balance_sheet_ratios": compact_ratios,
        },
        "revenue_forecast": {
            "company": forecast.get("company"),
            "metadata": forecast.get("metadata"),
            "recent_historical_observations": (
                historical[-4:] if isinstance(historical, list) else []
            ),
            "forecasts": forecast.get("forecast"),
        },
    }

def _collect_evidence(
    financial: dict[str, Any],
    forecast: dict[str, Any],
) -> list[EvidenceReference]:
    """Collect source URLs supplied by existing backend services."""
    found: dict[tuple[str, str], EvidenceReference] = {}

    def walk(value: Any, source_type: str) -> None:
        if isinstance(value, dict):
            url = value.get("source_url")

            if isinstance(url, str) and url.startswith(("http://", "https://")):
                metric = value.get("metric_name")
                period = value.get("period_end")

                note = (
                    "Backend source record"
                    + (f" for {metric}" if metric else "")
                    + (f", period ending {period}" if period else "")
                )

                key = (source_type, url)

                found[key] = EvidenceReference(
                    source_type=source_type,
                    source_url=url,
                    note=note,
                    metric_name=str(metric) if metric else None,
                    period_end=str(period) if period else None,
                )

            for child in value.values():
                walk(child, source_type)

        elif isinstance(value, (list, tuple)):
            for child in value:
                walk(child, source_type)

    walk(financial, "SEC")
    walk(forecast, "FORECAST")

    return list(found.values())[:40]


async def run_financial_agent(
    state: ResearchState,
    *,
    session_factory=None,
) -> dict[str, Any]:
    """Run financial analysis, forecasting and LLM interpretation."""

    ticker = str(state.get("ticker", "")).strip().upper()

    if ticker not in {"MSFT", "NVDA"}:
        return {
            "financial_agent_error": (
                f"Unsupported ticker: {ticker}. Use MSFT or NVDA."
            )
        }

    factory = session_factory or get_session_factory()
    horizon = int(state.get("forecast_horizon", 4))
    confidence_level = float(state.get("confidence_level", 0.95))

    try:
        # Retrieve financial analysis and forecast from existing services.
        with factory() as session:
            financial_service = FinancialAnalysisService()

            financial = _to_dict(
                financial_service.analyze_company(session, ticker)
            )

            forecast = _to_dict(
                forecast_company_revenue(
                    session,
                    ticker,
                    horizon=horizon,
                    confidence_level=confidence_level,
                )
            )

        context = _compact_context(financial, forecast)
        evidence = _collect_evidence(financial, forecast)

        settings = get_settings()
        usage = TokenUsage()

        system_prompt = """
You are the Financial Analysis Agent in a business research system.

Interpret financial analysis and revenue forecasts supplied by trusted
backend services.

Rules:
1. Use only the supplied data. Never invent financial figures.
2. Do not calculate or guess missing financial metrics.
3. Distinguish historical reported values from derived values and forecasts.
4. Explain revenue growth, profitability, margins and balance-sheet signals
   only when supported by the supplied data.
5. Explain uncertainty and forecast limitations.
6. Do not interpret revenue forecasts as stock-price forecasts.
7. Do not give personalized investment advice or guarantee future results.
8. Cite only source URLs supplied in the input. Do not invent URLs.
9. If data is missing or insufficient, explicitly say so.
10. Return output matching the requested Pydantic JSON schema.
"""

        user_prompt = (
            f"Analyze company ticker {ticker}.\n\n"
            "Here are the actual backend service results:\n"
            + json.dumps(context, default=str, ensure_ascii=False)
        )

        async with LlmClient(settings) as client:
            result = await client.complete_json(
                system=system_prompt,
                user=user_prompt,
                schema=FinancialAgentOutput,
                usage=usage,
            )

        # Only preserve evidence URLs originating from backend services.
        allowed_urls = {item.source_url for item in evidence}

        validated_insights = []

        for insight in result.metric_insights:
            safe_evidence = [
                item
                for item in insight.evidence
                if item.source_url in allowed_urls
            ]

            validated_insights.append(
                insight.model_copy(update={"evidence": safe_evidence})
            )

        result = result.model_copy(
            update={
                "metric_insights": validated_insights,
                "evidence": evidence,
            }
        )

        return {
            "financial_analysis": financial,
            "revenue_forecast": forecast,
            "financial_agent_output": result.model_dump(mode="json"),
            "financial_agent_error": "",
        }

    except Exception as exc:
        logger.exception("Financial agent failed for %s", ticker)

        return {
            "financial_agent_error": (
                f"{type(exc).__name__}: {str(exc)[:500]}"
            )
        }

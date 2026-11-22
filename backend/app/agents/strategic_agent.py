
import json
import logging
from typing import Any

from app.core.companies import SUPPORTED_TICKERS
from app.core.config import get_settings
from app.services.llm_client import LlmClient, TokenUsage
from app.schemas.agent_schemas import (
    EvidenceReference,
    StrategicAgentOutput,
)

logger = logging.getLogger(__name__)


def _compact_strategic_context(state: dict[str, Any]) -> dict[str, Any]:
    """Prepare compact financial and news context for the LLM."""

    financial = state.get("financial_agent_output") or {}
    news = state.get("news_agent_output") or {}
    analysis = state.get("financial_analysis") or {}
    forecast = state.get("revenue_forecast") or {}
    intelligence = state.get("news_intelligence") or {}

    # Retain only a manageable number of news signals.
    risks = news.get("risk_signals", [])[:8]
    opportunities = news.get("opportunities", [])[:8]

    return {
        "ticker": state.get("ticker"),
        "company_name": state.get("company_name"),
        "financial_agent": {
            "overall_assessment": financial.get("overall_assessment"),
            "performance_highlights": financial.get(
                "performance_highlights", []
            )[:8],
            "financial_concerns": financial.get(
                "financial_concerns", []
            )[:8],
            "forecast_interpretation": financial.get(
                "forecast_interpretation"
            ),
            "forecast_caveats": financial.get(
                "forecast_caveats", []
            )[:6],
            "confidence": financial.get("confidence"),
        },
        "news_agent": {
            "overall_assessment": news.get("overall_assessment"),
            "important_topics": news.get("important_topics", [])[:10],
            "risk_signals": risks,
            "opportunities": opportunities,
            "competitor_activity": news.get(
                "competitor_activity", []
            )[:8],
            "source_limitations": news.get(
                "source_limitations", []
            )[:8],
            "confidence": news.get("confidence"),
        },
        "financial_data_quality": analysis.get("data_quality"),
        "forecast_metadata": forecast.get("metadata"),
        "news_coverage": {
            "article_count": intelligence.get("article_count"),
            "period_days": intelligence.get("period_days"),
            "topic_summary": intelligence.get("topic_summary", {}),
            "risk_summary": intelligence.get("risk_summary", {}),
            "opportunity_summary": intelligence.get(
                "opportunity_summary", {}
            ),
        },
    }


def _collect_trusted_evidence(
    state: dict[str, Any],
) -> list[EvidenceReference]:
    """Collect evidence references from the first two agents."""

    evidence = []
    seen = set()

    def add(item: dict[str, Any]):
        url = item.get("source_url")

        if not isinstance(url, str) or not url.strip():
            return

        url = url.strip()

        if url in seen:
            return

        source_type = item.get("source_type")

        if source_type not in {"SEC", "NEWS", "FORECAST"}:
            return

        seen.add(url)

        evidence.append(
            EvidenceReference(
                source_type=source_type,
                source_url=url,
                note=str(item.get("note") or "Backend evidence.")[:500],
                article_id=item.get("article_id"),
                metric_name=item.get("metric_name"),
                period_end=item.get("period_end"),
            )
        )

    financial = state.get("financial_agent_output") or {}
    news = state.get("news_agent_output") or {}

    for item in financial.get("evidence", []):
        add(item)

    for insight in financial.get("metric_insights", []):
        for item in insight.get("evidence", []):
            add(item)

    for signal in news.get("risk_signals", []):
        add(signal.get("evidence", {}))

    for signal in news.get("opportunities", []):
        add(signal.get("evidence", {}))

    return evidence[:100]


async def run_strategic_agent(
    state: dict[str, Any],
) -> dict[str, Any]:
    """Combine financial and news analysis into strategic guidance."""

    ticker = str(state.get("ticker", "")).strip().upper()

    if ticker not in SUPPORTED_TICKERS:
        return {
            "strategic_agent_error": (
                f"Unsupported ticker: {ticker}. Supported tickers: {', '.join(sorted(SUPPORTED_TICKERS))}."
            )
        }

    financial = state.get("financial_agent_output") or {}
    news = state.get("news_agent_output") or {}

    if not financial:
        return {
            "strategic_agent_error": (
                "Financial Agent output is missing."
            )
        }

    if not news:
        return {
            "strategic_agent_error": (
                "News Agent output is missing."
            )
        }

    try:
        context = _compact_strategic_context(state)
        evidence = _collect_trusted_evidence(state)
        allowed_urls = {item.source_url for item in evidence}

        system_prompt = """
You are the Strategic Research and Decision Support Agent.

You combine financial analysis, revenue forecasts and business news
to produce a balanced, evidence-backed strategic assessment.

Rules:
1. Use only the supplied Financial Agent and News Agent results.
2. Never invent facts, metrics, events, sources or URLs.
3. Distinguish historical financial results, derived values and forecasts.
4. Treat forecast estimates as uncertain, not guaranteed outcomes.
5. Treat keyword-classified news as signals, not verified events.
6. Distinguish reported facts from strategic interpretations.
7. Consider financial strengths, concerns, business risks,
   opportunities and competitor activity.
8. Recommendations must be practical and supported by supplied evidence.
9. Do not give stock-price predictions or personalized investment advice.
10. Do not recommend buying or selling securities.
11. Cite only evidence URLs supplied in the input.
12. If the evidence is incomplete or conflicting, explain the limitation.
13. Do not claim that a company has a capability or problem unless
    the supplied evidence supports that conclusion.
14. Return output matching the requested Pydantic JSON schema.
15. Every strategic priority must include at least one supporting_evidence
    item whose source_url is copied exactly from the supplied input.

Create a concise executive summary and a small number of prioritized,
actionable strategic recommendations.
"""

        user_prompt = (
            f"Prepare a strategic business assessment for {ticker}.\n\n"
            "Use the following verified backend agent outputs:\n"
            + json.dumps(context, default=str, ensure_ascii=False)
        )

        settings = get_settings()
        usage = TokenUsage()

        async with LlmClient(settings) as client:
            result = await client.complete_json(
                system=system_prompt,
                user=user_prompt,
                schema=StrategicAgentOutput,
                usage=usage,
                max_completion_tokens=1500,
            )

        # Retain only evidence URLs originating from upstream agents, and do
        # not present a recommendation as evidence-backed when none remain.
        safe_priorities = []
        removed_priorities = []

        for priority in result.strategic_priorities:
            safe_evidence = [
                item
                for item in priority.supporting_evidence
                if item.source_url in allowed_urls
            ]

            if not safe_evidence:
                removed_priorities.append(priority.priority)
                continue

            safe_priorities.append(
                priority.model_copy(
                    update={"supporting_evidence": safe_evidence}
                )
            )

        limitations = list(result.limitations)
        if removed_priorities:
            limitations.append(
                "Removed recommendation(s) without traceable supporting evidence: "
                + "; ".join(removed_priorities)
            )

        result = result.model_copy(
            update={
                "strategic_priorities": safe_priorities,
                "limitations": limitations,
            }
        )

        return {
            "strategic_agent_output": result.model_dump(mode="json"),
            "strategic_agent_error": "",
        }

    except Exception as exc:
        logger.exception("Strategic agent failed for %s", ticker)

        return {
            "strategic_agent_error": (
                f"{type(exc).__name__}: {str(exc)[:500]}"
            )
        }


import json
import logging
from typing import Any

from app.database.session import get_session_factory
from app.core.config import get_settings
from app.services.news_intelligence_service import analyze_company_news
from app.services.llm_client import LlmClient, TokenUsage
from app.schemas.agent_schemas import (
    EvidenceReference,
    NewsAgentOutput,
)

logger = logging.getLogger(__name__)


def _compact_news_context(data: dict[str, Any]) -> dict[str, Any]:
    """Keep relevant news evidence while controlling prompt size."""

    articles = []

    for article in data.get("articles", [])[:30]:
        articles.append({
            "article_id": article.get("article_id"),
            "headline": article.get("headline"),
            "url": article.get("url"),
            "source": article.get("source"),
            "published_at": article.get("published_at"),
            "snippet": str(article.get("snippet") or "")[:1000],
            "target_company_mentions": article.get(
                "target_company_mentions", []
            ),
            "competitor_mentions": article.get(
                "competitor_mentions", []
            ),
            "topics": article.get("topics", []),
            "risks": article.get("risks", []),
            "opportunities": article.get("opportunities", []),
            "relevance_score": article.get("relevance_score"),
            "evidence_note": article.get("evidence_note"),
        })

    return {
        "company": data.get("company"),
        "period_days": data.get("period_days"),
        "article_count": data.get("article_count"),
        "topic_summary": data.get("topic_summary", {}),
        "risk_summary": data.get("risk_summary", {}),
        "opportunity_summary": data.get("opportunity_summary", {}),
        "limitations": data.get("limitations", []),
        "articles": articles,
    }


def _collect_news_evidence(
    data: dict[str, Any],
) -> list[EvidenceReference]:
    """Build evidence references exclusively from backend articles."""

    evidence = []
    seen = set()

    for article in data.get("articles", []):
        url = article.get("url")

        if not isinstance(url, str) or not url.strip():
            continue

        url = url.strip()

        if url in seen:
            continue

        seen.add(url)

        note = (
            str(article.get("evidence_note") or
                article.get("headline") or
                "News article collected by the backend.")
        )

        evidence.append(
            EvidenceReference(
                source_type="NEWS",
                source_url=url,
                note=note[:500],
                article_id=article.get("article_id"),
            )
        )

    return evidence[:100]


async def run_news_agent(
    state: dict[str, Any],
    *,
    session_factory=None,
) -> dict[str, Any]:
    """Run news intelligence and LLM interpretation."""

    ticker = str(state.get("ticker", "")).strip().upper()

    if ticker not in {"MSFT", "NVDA"}:
        return {
            "news_agent_error": (
                f"Unsupported ticker: {ticker}. Use MSFT or NVDA."
            )
        }

    factory = session_factory or get_session_factory()
    days = int(state.get("news_days", 30))
    limit = int(state.get("news_limit", 100))

    if not 1 <= days <= 365:
        return {"news_agent_error": "news_days must be between 1 and 365."}

    if not 1 <= limit <= 100:
        return {"news_agent_error": "news_limit must be between 1 and 100."}

    try:
        # Retrieve existing classified news from the database.
        with factory() as session:
            news_data = analyze_company_news(
                session=session,
                ticker=ticker,
                days=days,
                limit=limit,
            )

        context = _compact_news_context(news_data)
        evidence = _collect_news_evidence(news_data)
        allowed_urls = {item.source_url for item in evidence}

        system_prompt = """
You are the Business News Intelligence Agent in a business research system.

Interpret the news articles and deterministic classification results
provided by trusted backend services.

Rules:
1. Use only the supplied articles and classification results.
2. A keyword match is a signal, not proof that an event occurred.
3. Never describe an allegation, investigation, outage, partnership,
   acquisition or other event as confirmed unless the supplied article
   explicitly supports that wording.
4. Distinguish reported facts from possible implications.
5. Identify important topics, potential risks, opportunities and
   competitor activity only when supported by the supplied evidence.
6. Do not invent article headlines, companies, dates or URLs.
7. Every risk signal and opportunity must cite a supplied article URL.
8. Do not use a URL that was not supplied in the input.
9. Mention source coverage limitations and classification limitations.
10. If evidence is weak or insufficient, say so.
11. Return output matching the requested Pydantic JSON schema.
"""

        user_prompt = (
            f"Analyze business news for {ticker}.\n\n"
            "The following data comes from the existing backend news "
            "intelligence service:\n"
            + json.dumps(context, default=str, ensure_ascii=False)
        )

        settings = get_settings()
        usage = TokenUsage()

        async with LlmClient(settings) as client:
            result = await client.complete_json(
                system=system_prompt,
                user=user_prompt,
                schema=NewsAgentOutput,
                usage=usage,
            )

        # Reject any LLM-generated evidence URL not found in backend data.
        safe_risks = [
            signal
            for signal in result.risk_signals
            if signal.evidence.source_url in allowed_urls
        ]

        safe_opportunities = [
            signal
            for signal in result.opportunities
            if signal.evidence.source_url in allowed_urls
        ]

        result = result.model_copy(
            update={
                "risk_signals": safe_risks,
                "opportunities": safe_opportunities,
                "source_limitations": list(dict.fromkeys(
                    result.source_limitations
                    + news_data.get("limitations", [])
                )),
            }
        )

        return {
            "news_intelligence": news_data,
            "news_agent_output": result.model_dump(mode="json"),
            "news_agent_error": "",
        }

    except Exception as exc:
        logger.exception("News agent failed for %s", ticker)

        return {
            "news_agent_error": (
                f"{type(exc).__name__}: {str(exc)[:500]}"
            )
        }

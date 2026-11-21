
"""Deterministic news intelligence and evidence extraction."""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models.company import Company
from app.models.news_article import NewsArticle


TOPIC_KEYWORDS = {
    "AI": ["artificial intelligence", "generative ai", "machine learning", " AI "],
    "Cloud": ["cloud computing", "azure", "aws", "cloud services", "data center"],
    "Cybersecurity": ["cybersecurity", "cyber attack", "data breach", "ransomware"],
    "Regulation": ["regulation", "regulatory", "antitrust", "investigation", "compliance"],
    "Finance": ["revenue", "profit", "earnings", "financial results", "quarterly results"],
    "Products": ["product launch", "new product", "software release", "chip launch"],
    "Competition": ["competitor", "market share", "competition", "rival", "competitive"],
}

RISK_KEYWORDS = {
    "outage": ["outage", "service disruption", "service failure"],
    "cybersecurity": ["data breach", "cyber attack", "ransomware", "security vulnerability"],
    "legal_or_regulatory": [
        "lawsuit",
        "antitrust",
        "regulatory investigation",
        "investigation",
        "investigating",
        "investigated",
        "sec probe",
        "probe",
        "fined",
        "indicted",
    ],
    "accounting_or_financial_controls": [
        "accounting issues",
        "accounting irregularities",
        "accounting investigation",
        "financial misstatement",
        "financial reporting concerns",
        "accounting probe",
    ],
    "layoffs": ["layoffs", "job cuts", "workforce reduction"],
    "business_pressure": ["declining demand", "sales decline", "revenue decline", "losses widen"],
}

OPPORTUNITY_KEYWORDS = {
    "partnership": ["partnership", "strategic alliance", "collaboration"],
    "product_or_innovation": ["product launch", "new product", "announced a new", "unveiled"],
    "expansion": ["expansion", "enters new market", "opens new facility", "capacity expansion"],
    "acquisition": ["acquisition", "acquires", "to acquire", "merger"],
    "contracts": ["contract win", "new contract", "supply agreement", "customer agreement"],
}

COMPANY_ALIASES = {
    "MSFT": ["microsoft", "msft"],
    "NVDA": ["nvidia", "nvda"],
}


def _contains_term(text: str, term: str) -> bool:
    """Match a phrase without matching it as part of a larger word."""
    escaped = re.escape(term.strip())
    escaped = escaped.replace(r"\ ", r"\s+")
    return bool(re.search(r"(?<!\w)" + escaped + r"(?!\w)", text, re.IGNORECASE))


def _matches(text: str, keywords: list[str]) -> list[str]:
    return [term.strip() for term in keywords if _contains_term(text, term)]


def _confidence(match_count: int, has_target_mention: bool) -> str:
    if match_count >= 2 and has_target_mention:
        return "high"
    if match_count >= 2 or has_target_mention:
        return "medium"
    return "low"


def analyze_article(article, target_ticker: str, target_name: str) -> dict:
    """Analyze one stored article and preserve its original evidence."""
    text = f"{article.headline or ''} {article.snippet or ''}".casefold()

    aliases = COMPANY_ALIASES.get(target_ticker.upper(), [target_name.casefold(), target_ticker.casefold()])
    target_mentions = _matches(text, aliases)

    competitors = []
    for ticker, terms in COMPANY_ALIASES.items():
        if ticker == target_ticker.upper():
            continue
        matches = _matches(text, terms)
        if matches:
            competitors.append({
                "ticker": ticker,
                "name": "Microsoft" if ticker == "MSFT" else "NVIDIA",
                "matched_terms": matches,
            })

    topics = []
    for topic, keywords in TOPIC_KEYWORDS.items():
        # Allow AI as a standalone acronym, not as a substring of another word.
        matches = _matches(text, keywords)
        if matches:
            topics.append({"topic": topic, "matched_terms": matches})

    risks = []
    for category, keywords in RISK_KEYWORDS.items():
        matches = _matches(text, keywords)
        if matches:
            risks.append({
                "category": category,
                "matched_terms": matches,
                "confidence": _confidence(len(matches), bool(target_mentions)),
            })

    opportunities = []
    for category, keywords in OPPORTUNITY_KEYWORDS.items():
        matches = _matches(text, keywords)
        if matches:
            opportunities.append({
                "category": category,
                "matched_terms": matches,
                "confidence": _confidence(len(matches), bool(target_mentions)),
            })

    relevance_score = min(
        100,
        (40 if target_mentions else 0)
        + min(30, len(topics) * 10)
        + min(20, (len(risks) + len(opportunities)) * 10)
        + (10 if competitors else 0),
    )

    published_at = article.published_at
    if published_at and published_at.tzinfo:
        published_at = published_at.astimezone(timezone.utc).replace(tzinfo=None)

    return {
        "article_id": article.news_article_id,
        "headline": article.headline,
        "url": article.article_url,
        "source": article.source_name,
        "published_at": published_at.isoformat() if published_at else None,
        "snippet": article.snippet,
        "target_company_mentions": target_mentions,
        "competitor_mentions": competitors,
        "topics": topics,
        "risks": risks,
        "opportunities": opportunities,
        "relevance_score": relevance_score,
        "evidence_note": (
            "Signals are keyword-based indicators, not verified conclusions."
        ),
    }


def analyze_company_news(
    session,
    ticker: str,
    days: int = 30,
    limit: int = 100,
) -> dict:
    """Analyze recent stored news for a supported company."""
    if days < 1:
        raise ValueError("days must be at least 1")
    if limit < 1 or limit > 1000:
        raise ValueError("limit must be between 1 and 1000")

    company = session.scalar(
        select(Company).where(Company.ticker.ilike(ticker))
    )
    if company is None:
        raise ValueError(f"Company not found: {ticker}")

    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)

    articles = session.scalars(
        select(NewsArticle)
        .where(
            NewsArticle.company_id == company.company_id,
            NewsArticle.published_at >= cutoff,
        )
        .order_by(NewsArticle.published_at.desc())
        .limit(limit)
    ).all()

    results = [
        analyze_article(article, company.ticker, company.name)
        for article in articles
    ]

    topic_counts = Counter(
        item["topic"] for article in results for item in article["topics"]
    )
    risk_counts = Counter(
        item["category"] for article in results for item in article["risks"]
    )
    opportunity_counts = Counter(
        item["category"] for article in results for item in article["opportunities"]
    )

    return {
        "company": {"name": company.name, "ticker": company.ticker},
        "period_days": days,
        "article_count": len(results),
        "articles": results,
        "topic_summary": dict(topic_counts),
        "risk_summary": dict(risk_counts),
        "opportunity_summary": dict(opportunity_counts),
        "limitations": [
            "Classification uses transparent keyword rules.",
            "A detected keyword does not establish that an event occurred.",
            "News coverage depends on the articles collected by the configured provider.",
        ],
    }

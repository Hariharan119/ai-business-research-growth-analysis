
from types import SimpleNamespace

from app.services.news_intelligence_service import analyze_article


def make_article(headline, snippet=""):
    return SimpleNamespace(
        news_article_id=1,
        headline=headline,
        article_url="https://example.com/test-article",
        source_name="Test Source",
        published_at=None,
        snippet=snippet,
    )


def test_ai_and_cloud_topic_detection():
    article = make_article(
        "Microsoft expands Azure cloud services",
        "New artificial intelligence infrastructure is announced."
    )

    result = analyze_article(article, "MSFT", "Microsoft")
    topics = {item["topic"] for item in result["topics"]}

    assert "AI" in topics
    assert "Cloud" in topics


def test_accounting_and_investigation_risk_detection():
    article = make_article(
        "NVIDIA investigated over accounting issues by SEC"
    )

    result = analyze_article(article, "NVDA", "NVIDIA")
    risks = {item["category"] for item in result["risks"]}

    assert "legal_or_regulatory" in risks
    assert "accounting_or_financial_controls" in risks


def test_partnership_opportunity_detection():
    article = make_article(
        "Microsoft announces strategic partnership"
    )

    result = analyze_article(article, "MSFT", "Microsoft")
    opportunities = {
        item["category"] for item in result["opportunities"]
    }

    assert "partnership" in opportunities


def test_competitor_detection():
    article = make_article(
        "Microsoft and NVIDIA expand AI partnership"
    )

    result = analyze_article(article, "MSFT", "Microsoft")

    assert any(
        item["ticker"] == "NVDA"
        for item in result["competitor_mentions"]
    )


def test_ai_false_positive_prevention():
    article = make_article(
        "The company maintains its daily operations."
    )

    result = analyze_article(article, "MSFT", "Microsoft")

    assert "AI" not in {
        item["topic"] for item in result["topics"]
    }


def test_evidence_url_is_preserved():
    article = make_article("Microsoft announces a new product")

    result = analyze_article(article, "MSFT", "Microsoft")

    assert result["url"] == "https://example.com/test-article"
    assert result["headline"] == article.headline
    assert result["source"] == "Test Source"

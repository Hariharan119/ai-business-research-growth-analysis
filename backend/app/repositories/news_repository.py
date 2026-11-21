"""Database operations for normalized news article metadata."""

from sqlalchemy import select

from app.models.news_article import NewsArticle


class NewsRepository:
    def __init__(self, session):
        self.session = session

    def insert_new(self, company_id: int, articles):
        """Insert articles whose URL hashes are not already stored."""
        existing_hashes = set(
            self.session.scalars(
                select(NewsArticle.url_hash).where(
                    NewsArticle.company_id == company_id
                )
            ).all()
        )

        inserted = 0

        for article in articles:
            if article.url_hash in existing_hashes:
                continue

            self.session.add(
                NewsArticle(
                    company_id=company_id,
                    headline=article.headline,
                    article_url=article.article_url,
                    url_hash=article.url_hash,
                    title_hash=article.title_hash,
                    source_name=article.source_name,
                    language=article.language,
                    source_country=article.source_country,
                    snippet=article.snippet,
                    provider_category=article.provider_category,
                    published_at=article.published_at,
                )
            )

            existing_hashes.add(article.url_hash)
            inserted += 1

        self.session.flush()
        return inserted

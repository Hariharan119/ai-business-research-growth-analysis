"""Database model registry."""

from app.models.company import Company
from app.models.data_refresh_log import DataRefreshLog
from app.models.financial_record import FinancialRecord
from app.models.news_article import NewsArticle

__all__ = [
    "Company",
    "DataRefreshLog",
    "FinancialRecord",
    "NewsArticle",
]

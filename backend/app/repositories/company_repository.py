"""Database operations for supported companies."""

from sqlalchemy import func, select

from app.core.companies import SUPPORTED_COMPANIES
from app.models.company import Company


class CompanyRepository:
    def __init__(self, session):
        self.session = session

    def get_by_ticker(self, ticker: str):
        return self.session.scalar(
            select(Company).where(
                func.upper(Company.ticker) == ticker.strip().upper()
            )
        )

    def list_active(self):
        return list(
            self.session.scalars(
                select(Company)
                .where(Company.is_active.is_(True))
                .order_by(Company.ticker)
            ).all()
        )

    def update_profile(self, company_id: int, profile):
        company = self.session.get(Company, company_id)
        if company is None:
            raise ValueError(f"Company ID {company_id} does not exist")

        if profile.name:
            company.name = profile.name
        if profile.industry:
            company.industry = profile.industry
        if profile.fiscal_year_end:
            company.fiscal_year_end = profile.fiscal_year_end

        return company

    def seed_supported_companies(self):
        """Insert configured companies that are not already in the database."""
        inserted = 0

        for config in SUPPORTED_COMPANIES:
            company = self.get_by_ticker(config.ticker)

            if company is None:
                company = Company(
                    name=config.name,
                    ticker=config.ticker,
                    cik=config.cik,
                    news_query=config.news_query,
                    is_active=True,
                )
                self.session.add(company)
                inserted += 1
            else:
                # Keep the configured identifiers and query current.
                company.name = config.name
                company.cik = config.cik
                company.news_query = config.news_query

        self.session.flush()
        return inserted

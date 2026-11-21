"""Database operations for normalized SEC financial facts."""

from sqlalchemy import select

from app.models.financial_record import FinancialRecord


class FinancialRepository:
    def __init__(self, session):
        self.session = session

    def insert_new(self, company_id: int, facts):
        """Insert new filing versions without overwriting historical facts."""
        inserted = 0
        seen = set()

        for fact in facts:
            version_key = (
                company_id,
                fact.metric_name,
                fact.period_type,
                fact.period_end,
                fact.accession_number,
                fact.source_tag,
            )

            # Avoid duplicates within this incoming batch.
            if version_key in seen:
                continue
            seen.add(version_key)

            existing_id = self.session.scalar(
                select(FinancialRecord.financial_record_id).where(
                    FinancialRecord.company_id == company_id,
                    FinancialRecord.metric_name == fact.metric_name,
                    FinancialRecord.period_type == fact.period_type,
                    FinancialRecord.period_end == fact.period_end,
                    FinancialRecord.accession_number == fact.accession_number,
                    FinancialRecord.source_tag == fact.source_tag,
                ).limit(1)
            )

            if existing_id is not None:
                continue

            self.session.add(
                FinancialRecord(
                    company_id=company_id,
                    metric_name=fact.metric_name,
                    period_type=fact.period_type,
                    metric_value=fact.metric_value,
                    unit=fact.unit,
                    fiscal_year=fact.fiscal_year,
                    fiscal_quarter=fact.fiscal_quarter,
                    period_start=fact.period_start,
                    period_end=fact.period_end,
                    filing_date=fact.filing_date,
                    form_type=fact.form_type,
                    accession_number=fact.accession_number,
                    source_url=fact.source_url,
                    source_tag=fact.source_tag,
                    is_derived=fact.is_derived,
                )
            )
            inserted += 1

        self.session.flush()
        return inserted, len(facts) - inserted

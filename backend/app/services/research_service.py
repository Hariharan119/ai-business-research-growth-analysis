"""Service for executing and persisting multi-agent research."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.workflow import research_workflow
from app.models.company import Company
from app.models.research_report import ResearchReport
from app.schemas.research import ResearchRequest


def _json_safe(value: Any) -> Any:
    """Convert workflow output into JSON-serializable data."""
    if hasattr(value, "model_dump"):
        return _json_safe(value.model_dump(mode="json"))

    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}

    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]

    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, Decimal):
        return float(value)

    if isinstance(value, (str, int, float, bool)) or value is None:
        return value

    if hasattr(value, "isoformat"):
        return value.isoformat()

    return str(value)


async def execute_research(
    request: ResearchRequest,
    session: Session,
) -> ResearchReport:
    """Run the research workflow and persist its result."""

    company = session.scalar(
        select(Company).where(Company.ticker == request.ticker)
    )

    if company is None:
        raise ValueError(f"Company {request.ticker} was not found.")

    if hasattr(company, "is_active") and not company.is_active:
        raise ValueError(f"Company {request.ticker} is inactive.")

    report = ResearchReport(
        company_id=company.company_id,
        ticker=request.ticker,
        status="running",
        request_data=request.model_dump(mode="json"),
    )

    session.add(report)
    session.commit()
    session.refresh(report)

    report_id = report.research_report_id

    # Important: close the transaction opened by refresh()
    # before waiting for the multi-agent workflow.
    session.commit()

    initial_state = {
        "ticker": request.ticker,
        "company_name": getattr(company, "company_name", None)
            or getattr(company, "name", None)
            or request.ticker,
        "forecast_horizon": request.forecast_horizon,
        "confidence_level": request.confidence_level,
        "news_days": request.news_days,
        "news_limit": request.news_limit,
    }

    try:
        workflow_result = await research_workflow.ainvoke(initial_state)
        safe_result = _json_safe(workflow_result)

        final_status = workflow_result.get(
            "workflow_status", "completed"
        )

        # The workflow stores each agent's error under its own key.
        errors = [
            f"{label}: {workflow_result[key]}"
            for label, key in (
                ("Financial Agent", "financial_agent_error"),
                ("News Agent", "news_agent_error"),
                ("Strategic Agent", "strategic_agent_error"),
            )
            if workflow_result.get(key)
        ]
        error_message = (
            "; ".join(str(item) for item in errors)
            if errors else None
        )

        # Do not open session.begin() here. A normal ORM query
        # may autobegin a transaction, so update and commit directly.
        saved_report = session.get(ResearchReport, report_id)

        if saved_report is None:
            raise RuntimeError(
                f"Research report {report_id} disappeared."
            )

        saved_report.result_data = safe_result
        saved_report.status = final_status
        saved_report.error_message = error_message
        saved_report.completed_at = datetime.utcnow()

        session.commit()
        session.refresh(saved_report)

        return saved_report

    except Exception as exc:
        session.rollback()

        saved_report = session.get(ResearchReport, report_id)

        if saved_report is None:
            raise

        saved_report.status = "failed"
        saved_report.error_message = (
            f"{type(exc).__name__}: {str(exc)[:1000]}"
        )
        saved_report.completed_at = datetime.utcnow()

        session.commit()
        session.refresh(saved_report)

        return saved_report

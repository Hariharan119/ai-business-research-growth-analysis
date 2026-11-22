"""Multi-agent research endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.companies import normalize_ticker
from app.database.session import get_db
from app.models.research_report import ResearchReport
from app.schemas.research import ResearchRequest, ResearchReportRead
from app.services.research_service import execute_research

router = APIRouter(prefix="/research", tags=["Research"])


@router.post("", response_model=ResearchReportRead)
async def create_research(
    request: ResearchRequest,
    session: Session = Depends(get_db),
):
    """Execute the multi-agent research workflow and save its report."""
    try:
        return await execute_research(request, session)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Research execution failed: {type(exc).__name__}: {str(exc)[:300]}",
        ) from exc


@router.get("", response_model=list[ResearchReportRead])
def list_research_reports(
    ticker: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_db),
):
    """List the most recent saved research reports."""
    statement = select(ResearchReport)

    if ticker:
        try:
            ticker = normalize_ticker(ticker)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        statement = statement.where(ResearchReport.ticker == ticker)

    statement = (
        statement
        .order_by(desc(ResearchReport.created_at), desc(ResearchReport.research_report_id))
        .limit(limit)
    )

    return list(session.scalars(statement).all())


@router.get("/{research_id}", response_model=ResearchReportRead)
def get_research_report(
    research_id: int,
    session: Session = Depends(get_db),
):
    """Retrieve one saved research report."""
    report = session.get(ResearchReport, research_id)

    if report is None:
        raise HTTPException(
            status_code=404,
            detail=f"Research report {research_id} was not found.",
        )

    return report

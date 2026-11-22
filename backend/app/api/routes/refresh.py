"""Data refresh API endpoints."""

from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.data_refresh_log import DataRefreshLog
from app.schemas.data_refresh import (
    RefreshRequest,
    RefreshResult,
    RefreshStatusResponse,
    LastSuccessEntry,
    RefreshLogEntry,
)
from app.core.companies import SUPPORTED_TICKERS
from app.services.refresh_job import run_refresh_job

router = APIRouter(prefix="/refresh", tags=["Data Refresh"])


@router.post("", response_model=list[RefreshResult])
async def refresh_data(request: RefreshRequest):
    """Refresh selected SEC and/or NewsData sources."""

    tickers = (
        [ticker.strip().upper() for ticker in request.tickers]
        if request.tickers is not None
        else None
    )

    if tickers is not None:
        if not tickers:
            raise HTTPException(
                status_code=422,
                detail="At least one ticker must be provided.",
            )

        unsupported = sorted(set(tickers) - SUPPORTED_TICKERS)
        if unsupported:
            raise HTTPException(
                status_code=422,
                detail=f"Unsupported ticker(s): {', '.join(unsupported)}",
            )

        tickers = list(dict.fromkeys(tickers))

    sources = [source.upper() for source in request.sources]

    if not sources:
        raise HTTPException(
            status_code=422,
            detail="Select at least one refresh source.",
        )

    try:
        return await run_refresh_job(
            tickers=tickers,
            sources=sources,
            trigger="manual",
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc


@router.get("/status", response_model=RefreshStatusResponse)
def get_refresh_status(
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_db),
):
    """Return refresh activity, latest successes, and recent history."""

    running_log = session.scalars(
        select(DataRefreshLog)
        .where(DataRefreshLog.status == "running")
        .limit(1)
    ).first()

    latest_success_rows = session.execute(
        select(
            DataRefreshLog.company_id,
            DataRefreshLog.source,
            func.max(DataRefreshLog.completed_at).label("completed_at"),
        )
        .where(
            DataRefreshLog.status.in_(["success", "partial"]),
            DataRefreshLog.completed_at.is_not(None),
        )
        .group_by(
            DataRefreshLog.company_id,
            DataRefreshLog.source,
        )
        .order_by(
            DataRefreshLog.company_id,
            DataRefreshLog.source,
        )
    ).all()

    last_success = [
        LastSuccessEntry(
            company_id=row.company_id,
            source=row.source,
            completed_at=row.completed_at,
        )
        for row in latest_success_rows
    ]

    recent_logs = session.scalars(
        select(DataRefreshLog)
        .order_by(
            desc(DataRefreshLog.started_at),
            desc(DataRefreshLog.data_refresh_log_id),
        )
        .limit(limit)
    ).all()

    recent = [
        RefreshLogEntry.model_validate(log)
        for log in recent_logs
    ]

    return RefreshStatusResponse(
        is_running=running_log is not None,
        last_success=last_success,
        recent=recent,
    )

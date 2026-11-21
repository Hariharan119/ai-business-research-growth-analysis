"""Database operations for data refresh execution logs."""

from datetime import datetime, timezone

from app.models.data_refresh_log import DataRefreshLog


class RefreshLogRepository:
    def __init__(self, session):
        self.session = session

    def start(self, source: str, company_id: int, trigger: str = "manual"):
        log = DataRefreshLog(
            source=source.upper(),
            company_id=company_id,
            trigger_type=trigger,
            status="running",
            records_fetched=0,
            records_inserted=0,
            records_skipped=0,
        )
        self.session.add(log)
        self.session.flush()
        return log.data_refresh_log_id

    def finish(
        self,
        log_id: int,
        status: str,
        fetched: int = 0,
        inserted: int = 0,
        skipped: int = 0,
        error: str | None = None,
    ):
        log = self.session.get(DataRefreshLog, log_id)

        if log is None:
            raise ValueError(f"Refresh log ID {log_id} does not exist")

        log.status = status
        log.completed_at = datetime.now(timezone.utc)
        log.records_fetched = fetched
        log.records_inserted = inserted
        log.records_skipped = skipped
        log.error_message = error

        self.session.flush()
        return log

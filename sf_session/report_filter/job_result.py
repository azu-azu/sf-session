"""Probe job execution result model."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class JobResult:
    job_id: str
    status: str  # "pending" | "probed" | "failed"
    report_id: str | None = None
    report_name: str | None = None
    report_url: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    duration_seconds: float | None = None
    column_count: int | None = None
    row_count: int | None = None
    discovery_columns: list[str] = field(default_factory=list)
    error: str | None = None

    def finish(
        self,
        *,
        row_count: int | None = None,
        column_count: int | None = None,
        discovery_columns: list[str] | None = None,
        error: str | None = None,
    ) -> None:
        self.finished_at = _now_iso()
        if self.started_at is not None:
            started = datetime.fromisoformat(self.started_at)
            finished = datetime.fromisoformat(self.finished_at)
            self.duration_seconds = round(
                (finished - started).total_seconds(), 3
            )
        if column_count is not None:
            self.column_count = column_count
        if row_count is not None:
            self.row_count = row_count
        if discovery_columns is not None:
            self.discovery_columns = discovery_columns
        if error is not None:
            self.error = error


def make_result(job_id: str) -> JobResult:
    return JobResult(job_id=job_id, status="pending", started_at=_now_iso())


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")

"""Phase 35: admin scheduler-job monitor.

Read-only listing of the scheduled ticks plus a run-now trigger.
The run history rows themselves are written by
``app.services.job_monitor.record`` from each tick body, so this
router is just a thin presentation layer over that data.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.core.deps import require_permission
from app.core.permissions import ADMIN_SETTINGS
from app.db.session import get_db
from app.models.user import User
from app.services import job_monitor, scheduler_service

router = APIRouter(prefix="/admin/jobs", tags=["admin"])


class JobRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    started_at: datetime
    finished_at: datetime | None
    duration_ms: int
    ok: bool
    detail: str


class JobSummary(BaseModel):
    """Aggregated state for one scheduler tick.

    ``next_run_at`` reflects whatever APScheduler is currently
    planning; ``last_*`` reflect what actually happened. ``running``
    flips when the scheduler isn't started at all (e.g. tests).
    """

    job_id: str
    interval_seconds: int | None
    next_run_at: datetime | None
    running: bool
    last_run: JobRunRead | None
    last_ok: bool | None
    success_rate_recent: float | None


@router.get("", response_model=list[JobSummary])
def list_jobs(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(ADMIN_SETTINGS)),
) -> list[JobSummary]:
    out: list[JobSummary] = []
    for job_id in scheduler_service.known_job_ids():
        last = job_monitor.last_run(db, job_id)
        recent = job_monitor.recent(db, job_id, limit=50)
        rate = (
            (sum(1 for r in recent if r.ok) / len(recent)) if recent else None
        )
        out.append(
            JobSummary(
                job_id=job_id,
                interval_seconds=scheduler_service.job_interval_seconds(job_id),
                next_run_at=scheduler_service.next_run_at(job_id),
                running=scheduler_service._scheduler is not None,
                last_run=JobRunRead.model_validate(last) if last else None,
                last_ok=last.ok if last else None,
                success_rate_recent=rate,
            )
        )
    return out


@router.get("/{job_id}/history", response_model=list[JobRunRead])
def history(
    job_id: str,
    limit: int = 50,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(ADMIN_SETTINGS)),
) -> list[JobRunRead]:
    if job_id not in scheduler_service.known_job_ids():
        raise HTTPException(status_code=404, detail="Unknown job_id")
    rows = job_monitor.recent(db, job_id, limit=max(1, min(limit, 200)))
    return [JobRunRead.model_validate(r) for r in rows]


@router.post("/{job_id}/run-now")
def run_now(
    job_id: str,
    _: User = Depends(require_permission(ADMIN_SETTINGS)),
) -> dict:
    if job_id not in scheduler_service.known_job_ids():
        raise HTTPException(status_code=404, detail="Unknown job_id")
    triggered = scheduler_service.run_now(job_id)
    if not triggered:
        raise HTTPException(
            status_code=503,
            detail="Scheduler is not running. Restart the API to launch it.",
        )
    return {"triggered": True, "job_id": job_id}

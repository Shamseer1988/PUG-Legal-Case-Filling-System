"""Scheduled-report CRUD + run-now + history endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.scheduled_report import ScheduledReport, ScheduledReportRun
from app.models.user import User
from app.schemas.scheduled_report import (
    ScheduledReportCreate,
    ScheduledReportRead,
    ScheduledReportRunRead,
    ScheduledReportUpdate,
)
from app.services import reports as reports_registry
from app.services import scheduled_reports as runner
from app.services.scheduler_service import compute_next_run, parse_cron

router = APIRouter(prefix="/scheduled-reports", tags=["scheduled-reports"])


def _validate(payload_dict: dict) -> None:
    rkey = payload_dict.get("report_key")
    if rkey and not reports_registry.get_report(rkey):
        raise HTTPException(status_code=400, detail=f"Unknown report key: {rkey}")
    cron = payload_dict.get("cron")
    if cron is not None:
        try:
            parse_cron(cron)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
    fmts = payload_dict.get("formats")
    if fmts is not None:
        bad = [f for f in fmts if f.lower() not in ("pdf", "xlsx")]
        if bad:
            raise HTTPException(
                status_code=400, detail=f"Unsupported format(s): {bad}"
            )


def _scope(db: Session, user: User):
    q = db.query(ScheduledReport)
    if user.is_super:
        return q
    perms = user.role.permissions if user.role else []
    if "*" in perms:
        return q
    # Non-admins see only their own schedules
    return q.filter(ScheduledReport.created_by_id == user.id)


@router.get("", response_model=list[ScheduledReportRead])
def list_schedules(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ScheduledReportRead]:
    rows = _scope(db, user).order_by(ScheduledReport.id.desc()).all()
    return [ScheduledReportRead.model_validate(r) for r in rows]


@router.post("", response_model=ScheduledReportRead, status_code=status.HTTP_201_CREATED)
def create_schedule(
    payload: ScheduledReportCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ScheduledReportRead:
    _validate(payload.model_dump())
    s = ScheduledReport(
        **payload.model_dump(),
        created_by_id=user.id,
        is_active=True,
    )
    s.next_run_at = compute_next_run(s.cron)
    db.add(s)
    db.commit()
    db.refresh(s)
    return ScheduledReportRead.model_validate(s)


def _get_or_404(db: Session, user: User, sid: int) -> ScheduledReport:
    s = _scope(db, user).filter(ScheduledReport.id == sid).first()
    if not s:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return s


@router.get("/{sid}", response_model=ScheduledReportRead)
def get_schedule(
    sid: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ScheduledReportRead:
    return ScheduledReportRead.model_validate(_get_or_404(db, user, sid))


@router.patch("/{sid}", response_model=ScheduledReportRead)
def update_schedule(
    sid: int,
    payload: ScheduledReportUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ScheduledReportRead:
    s = _get_or_404(db, user, sid)
    data = payload.model_dump(exclude_unset=True)
    _validate(data)
    for k, v in data.items():
        setattr(s, k, v)
    if "cron" in data:
        s.next_run_at = compute_next_run(s.cron)
    db.commit()
    db.refresh(s)
    return ScheduledReportRead.model_validate(s)


@router.delete("/{sid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_schedule(
    sid: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    s = _get_or_404(db, user, sid)
    db.delete(s)
    db.commit()


@router.post("/{sid}/pause", response_model=ScheduledReportRead)
def pause(
    sid: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ScheduledReportRead:
    s = _get_or_404(db, user, sid)
    s.is_active = False
    db.commit()
    db.refresh(s)
    return ScheduledReportRead.model_validate(s)


@router.post("/{sid}/resume", response_model=ScheduledReportRead)
def resume(
    sid: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ScheduledReportRead:
    s = _get_or_404(db, user, sid)
    s.is_active = True
    if not s.next_run_at:
        s.next_run_at = compute_next_run(s.cron)
    db.commit()
    db.refresh(s)
    return ScheduledReportRead.model_validate(s)


@router.post("/{sid}/run-now", response_model=ScheduledReportRunRead)
def run_now(
    sid: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ScheduledReportRunRead:
    s = _get_or_404(db, user, sid)
    r = runner.execute_one(db, s)
    return ScheduledReportRunRead.model_validate(r)


@router.get("/{sid}/history", response_model=list[ScheduledReportRunRead])
def history(
    sid: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ScheduledReportRunRead]:
    _get_or_404(db, user, sid)
    rows = (
        db.query(ScheduledReportRun)
        .filter(ScheduledReportRun.schedule_id == sid)
        .order_by(ScheduledReportRun.id.desc())
        .limit(50)
        .all()
    )
    return [ScheduledReportRunRead.model_validate(r) for r in rows]

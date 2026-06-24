"""Phase 35: instrumentation around scheduled ticks.

Wrap a tick body with ``with record(db, job_id):`` and a ``JobRun``
row is written for every execution. The admin endpoints read from
this table to show last-run / last-ok / last-detail per job, and
the table is auto-pruned to a rolling window so it can't grow
unbounded.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

from loguru import logger
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.models.job_run import JobRun

# How many history rows to keep per job. Reports tick is 60s, SLA
# and hearings are 300s, email queue is 10s - 200 rows is roughly
# 33 minutes of email queue history and ~16 hours of SLA history.
# Plenty for "is this thing healthy?" without bloating the table.
HISTORY_PER_JOB = 200


class _TickHandle:
    """Mutable handle so the body of a tick can append a status
    summary that lands in JobRun.detail."""

    def __init__(self) -> None:
        self.detail: str = ""


@contextmanager
def record(db: Session, job_id: str) -> Iterator[_TickHandle]:
    """Wrap a scheduler tick. The ``JobRun`` row is inserted whether
    the body succeeds or raises; on raise the exception is logged
    and re-raised so APScheduler still sees the failure."""
    started = datetime.now(timezone.utc)
    t0 = time.perf_counter()
    handle = _TickHandle()
    ok = True
    err_detail = ""
    try:
        yield handle
    except Exception as exc:  # pragma: no cover - re-raised
        ok = False
        err_detail = f"{type(exc).__name__}: {exc}"
        logger.exception("Tick {} failed: {}", job_id, exc)
        raise
    finally:
        finished = datetime.now(timezone.utc)
        duration_ms = int((time.perf_counter() - t0) * 1000)
        try:
            db.add(
                JobRun(
                    job_id=job_id,
                    started_at=started,
                    finished_at=finished,
                    duration_ms=duration_ms,
                    ok=ok,
                    detail=(err_detail or handle.detail)[:2000],
                )
            )
            _prune(db, job_id)
            db.commit()
        except Exception as exc:  # pragma: no cover - defensive
            db.rollback()
            logger.warning("Could not persist JobRun for {}: {}", job_id, exc)


def _prune(db: Session, job_id: str) -> None:
    """Keep only the most recent ``HISTORY_PER_JOB`` rows once the
    new row (still in the session, not yet flushed) is committed.

    ``total`` counts the pre-insert DB state, so we keep
    ``HISTORY_PER_JOB - 1`` existing rows to make room for the
    incoming one.
    """
    total = (
        db.query(func.count(JobRun.id)).filter(JobRun.job_id == job_id).scalar() or 0
    )
    keep_existing = HISTORY_PER_JOB - 1
    if total <= keep_existing:
        return
    cutoff_row = (
        db.query(JobRun.id)
        .filter(JobRun.job_id == job_id)
        .order_by(desc(JobRun.id))
        .offset(keep_existing - 1)
        .first()
    )
    if cutoff_row is None:
        return
    db.query(JobRun).filter(
        JobRun.job_id == job_id, JobRun.id < cutoff_row[0]
    ).delete(synchronize_session=False)


def last_run(db: Session, job_id: str) -> JobRun | None:
    return (
        db.query(JobRun)
        .filter(JobRun.job_id == job_id)
        .order_by(desc(JobRun.id))
        .first()
    )


def recent(db: Session, job_id: str, *, limit: int = 50) -> list[JobRun]:
    return (
        db.query(JobRun)
        .filter(JobRun.job_id == job_id)
        .order_by(desc(JobRun.id))
        .limit(limit)
        .all()
    )

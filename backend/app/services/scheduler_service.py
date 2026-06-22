"""APScheduler-driven tick that runs due scheduled reports."""

from __future__ import annotations

from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

_scheduler: BackgroundScheduler | None = None
TICK_JOB_ID = "scheduled-reports-tick"
EMAIL_QUEUE_JOB_ID = "email-queue-tick"
SLA_JOB_ID = "sla-breach-tick"
HEARING_JOB_ID = "hearing-reminder-tick"


def start() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(
        _tick,
        "interval",
        seconds=60,
        id=TICK_JOB_ID,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    # Phase 25: drain the outbound email queue often enough that
    # transactional notifications feel near-real-time but not so
    # often that we hammer the DB when there's nothing to do.
    _scheduler.add_job(
        _email_tick,
        "interval",
        seconds=10,
        id=EMAIL_QUEUE_JOB_ID,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    # Phase 33: SLA breach scanner. 5 minutes is responsive enough
    # for human-scale SLAs (hours/days) without DB churn.
    _scheduler.add_job(
        _sla_tick,
        "interval",
        seconds=300,
        id=SLA_JOB_ID,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    # Phase 34: hearing reminder scanner. 5-minute interval is
    # fine - the 1h window has a 5-minute slack that's well below
    # human response time and the 24h window is even more forgiving.
    _scheduler.add_job(
        _hearing_tick,
        "interval",
        seconds=300,
        id=HEARING_JOB_ID,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    _scheduler.start()
    logger.info(
        "Scheduler started (reports=60s, email=10s, sla=300s, hearings=300s)"
    )


def stop() -> None:
    global _scheduler
    if _scheduler is None:
        return
    try:
        _scheduler.shutdown(wait=False)
    finally:
        _scheduler = None
        logger.info("Scheduler stopped")


def _tick() -> None:
    """Run any due schedules. Imports kept inside to avoid circular imports."""
    from app.db.session import SessionLocal
    from app.services import job_monitor, scheduled_reports

    db = SessionLocal()
    try:
        with job_monitor.record(db, TICK_JOB_ID) as h:
            ran = scheduled_reports.run_due(db)
            h.detail = f"due_ran={ran}"
    finally:
        db.close()


def _email_tick() -> None:
    """Drain the outbound email queue (Phase 25)."""
    from app.db.session import SessionLocal
    from app.services import email_service, job_monitor

    db = SessionLocal()
    try:
        with job_monitor.record(db, EMAIL_QUEUE_JOB_ID) as h:
            stats = email_service.process_queue(db)
            if stats["picked"]:
                logger.info(
                    "Email queue tick: picked={picked} sent={sent} retried={retried} failed={failed}",
                    **stats,
                )
            h.detail = ", ".join(f"{k}={v}" for k, v in stats.items())
    finally:
        db.close()


def _sla_tick() -> None:
    """Phase 33: escalate any newly breached cases."""
    from app.db.session import SessionLocal
    from app.services import job_monitor, sla_service

    db = SessionLocal()
    try:
        with job_monitor.record(db, SLA_JOB_ID) as h:
            stats = sla_service.scan_and_escalate(db)
            if stats["escalated"]:
                logger.info(
                    "SLA tick: scanned={scanned} escalated={escalated}", **stats
                )
            h.detail = ", ".join(f"{k}={v}" for k, v in stats.items())
    finally:
        db.close()


def _hearing_tick() -> None:
    """Phase 34: send any due hearing reminders."""
    from app.db.session import SessionLocal
    from app.services import hearing_reminder_service, job_monitor

    db = SessionLocal()
    try:
        with job_monitor.record(db, HEARING_JOB_ID) as h:
            stats = hearing_reminder_service.scan_and_notify(db)
            if stats["sent_24h"] or stats["sent_1h"]:
                logger.info(
                    "Hearing tick: scanned={scanned} sent_24h={sent_24h} sent_1h={sent_1h}",
                    **stats,
                )
            h.detail = ", ".join(f"{k}={v}" for k, v in stats.items())
    finally:
        db.close()


_JOB_INTERVALS_SECONDS: dict[str, int] = {
    TICK_JOB_ID: 60,
    EMAIL_QUEUE_JOB_ID: 10,
    SLA_JOB_ID: 300,
    HEARING_JOB_ID: 300,
}


def known_job_ids() -> list[str]:
    """List of every tick the scheduler manages.

    Returns a fixed list so the admin page renders predictably even
    before the scheduler has started (e.g. in the test client).
    """
    return [TICK_JOB_ID, EMAIL_QUEUE_JOB_ID, SLA_JOB_ID, HEARING_JOB_ID]


def job_interval_seconds(job_id: str) -> int | None:
    return _JOB_INTERVALS_SECONDS.get(job_id)


def next_run_at(job_id: str) -> datetime | None:
    """Return APScheduler's next fire time for ``job_id`` or None
    if the scheduler isn't running or the job is unknown."""
    if _scheduler is None:
        return None
    job = _scheduler.get_job(job_id)
    if job is None or job.next_run_time is None:
        return None
    nxt = job.next_run_time
    return nxt if nxt.tzinfo else nxt.replace(tzinfo=timezone.utc)


def run_now(job_id: str) -> bool:
    """Trigger ``job_id`` ASAP. Returns True if the job was scheduled,
    False if the scheduler is down or the id is unknown."""
    if _scheduler is None:
        return False
    job = _scheduler.get_job(job_id)
    if job is None:
        return False
    # ``modify`` rather than ``run`` so APScheduler still respects
    # max_instances/coalesce instead of racing with the running job.
    job.modify(next_run_time=datetime.now(timezone.utc))
    return True


def parse_cron(expr: str) -> CronTrigger:
    """Returns a CronTrigger - raises ValueError on a bad expression."""
    try:
        return CronTrigger.from_crontab(expr.strip(), timezone="UTC")
    except Exception as e:
        raise ValueError(f"Invalid cron expression: {e}") from e


def compute_next_run(cron_expr: str, base: datetime | None = None) -> datetime | None:
    try:
        trig = parse_cron(cron_expr)
    except ValueError:
        return None
    base = base or datetime.now(timezone.utc)
    nxt = trig.get_next_fire_time(None, base)
    if nxt is None:
        return None
    return nxt if nxt.tzinfo else nxt.replace(tzinfo=timezone.utc)

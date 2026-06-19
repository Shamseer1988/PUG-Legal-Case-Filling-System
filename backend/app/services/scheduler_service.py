"""APScheduler-driven tick that runs due scheduled reports."""

from __future__ import annotations

from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

_scheduler: BackgroundScheduler | None = None
TICK_JOB_ID = "scheduled-reports-tick"


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
    _scheduler.start()
    logger.info("Scheduler started (tick every 60s)")


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
    from app.services import scheduled_reports

    db = SessionLocal()
    try:
        scheduled_reports.run_due(db)
    except Exception as e:  # pragma: no cover (defensive)
        logger.exception("Scheduler tick failed: {}", e)
    finally:
        db.close()


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

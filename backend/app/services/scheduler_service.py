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
    _scheduler.start()
    logger.info(
        "Scheduler started (reports=60s, email=10s, sla=300s)"
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
    from app.services import scheduled_reports

    db = SessionLocal()
    try:
        scheduled_reports.run_due(db)
    except Exception as e:  # pragma: no cover (defensive)
        logger.exception("Scheduler tick failed: {}", e)
    finally:
        db.close()


def _email_tick() -> None:
    """Drain the outbound email queue (Phase 25)."""
    from app.db.session import SessionLocal
    from app.services import email_service

    db = SessionLocal()
    try:
        stats = email_service.process_queue(db)
        if stats["picked"]:
            logger.info(
                "Email queue tick: picked={picked} sent={sent} retried={retried} failed={failed}",
                **stats,
            )
    except Exception as e:  # pragma: no cover (defensive)
        logger.exception("Email queue tick failed: {}", e)
    finally:
        db.close()


def _sla_tick() -> None:
    """Phase 33: escalate any newly breached cases."""
    from app.db.session import SessionLocal
    from app.services import sla_service

    db = SessionLocal()
    try:
        stats = sla_service.scan_and_escalate(db)
        if stats["escalated"]:
            logger.info(
                "SLA tick: scanned={scanned} escalated={escalated}", **stats
            )
    except Exception as e:  # pragma: no cover (defensive)
        logger.exception("SLA tick failed: {}", e)
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

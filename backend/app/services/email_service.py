"""Outbound email queue + SMTP delivery.

Phase 25 rewrite: ``queue_email`` is now *truly* async.
- ``queue_email`` only inserts EmailLog (+ EmailLogAttachment rows)
  and commits. It never hits SMTP, so workflow transitions are
  never blocked by a slow / broken mail server.
- ``process_queue`` is called periodically by the scheduler and
  drains the eligible rows. Each delivery attempt updates
  ``attempts`` / ``last_attempted_at`` and on failure pushes
  ``next_attempt_at`` out by an exponential backoff (1m, 5m, 30m,
  2h, 12h). After ``MAX_ATTEMPTS`` failed tries the row is parked
  in status ``Failed`` and the admin can manually resend.
- ``resend`` and the admin "send test" both go through the same
  delivery code path, so behaviour is consistent.

When SMTP_HOST is blank the service runs in *console mode*: the
rendered email is logged and the row is marked Sent. This keeps
local dev painless and CI fast.
"""

from __future__ import annotations

import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from loguru import logger
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.notification import (
    EMAIL_STATUS_FAILED,
    EMAIL_STATUS_QUEUED,
    EMAIL_STATUS_SENT,
    EmailLog,
    EmailLogAttachment,
)

TEMPLATES = Path(__file__).resolve().parent.parent / "templates" / "email"

# Backoff schedule (seconds) after each failed attempt. The Nth
# failure waits BACKOFF_SECONDS[N-1] before the next try. If we run
# out of entries the row is parked in status=Failed and the admin
# can resend.
BACKOFF_SECONDS: tuple[int, ...] = (60, 300, 1800, 7200, 43200)
MAX_ATTEMPTS: int = len(BACKOFF_SECONDS) + 1  # 1 initial + N retries

# Hard ceiling on rows drained per scheduler tick. Prevents one
# bad SMTP server (slow / failing) from blocking the worker for
# minutes when there's a big backlog.
MAX_PER_TICK: int = 25


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@lru_cache
def env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        autoescape=select_autoescape(["html", "xml"]),
    )


def render_email(template: str, context: dict) -> tuple[str, str]:
    """Returns (body_html, body_text)."""
    ctx = {
        "brand_company_name": settings.brand_company_name,
        "app_url": settings.brand_app_url,
        **context,
    }
    body_html = env().get_template(template).render(**ctx)
    lines = ctx.get("lines") or []
    body_text = "\n\n".join(
        [str(ctx.get("title") or "")]
        + ([str(ctx["subtitle"])] if ctx.get("subtitle") else [])
        + [str(line) for line in lines]
        + ([f"\nOpen: {ctx['action_url']}"] if ctx.get("action_url") else [])
    )
    return body_html, body_text


def queue_email(
    db: Session,
    *,
    to_emails: list[str],
    subject: str,
    template: str,
    context: dict,
    cc_emails: list[str] | None = None,
    bcc_emails: list[str] | None = None,
    event: str = "",
    related_case_id: int | None = None,
    related_user_id: int | None = None,
    attachments: list[tuple[str, bytes, str]] | None = None,
) -> EmailLog:
    """Enqueue an email for the background worker to send.

    Returns the persisted EmailLog row. Does NOT hit SMTP. The
    scheduler will deliver it on the next tick (default every 10
    seconds).
    """
    body_html, body_text = render_email(template, {**context, "subject": subject})
    log = EmailLog(
        to_emails=",".join([e for e in to_emails if e]),
        cc_emails=",".join(cc_emails or []),
        bcc_emails=",".join(bcc_emails or []),
        subject=subject,
        template_name=template,
        body_html=body_html,
        body_text=body_text,
        status=EMAIL_STATUS_QUEUED,
        next_attempt_at=_utcnow(),
        event=event,
        related_case_id=related_case_id,
        related_user_id=related_user_id,
    )
    db.add(log)
    db.flush()
    for filename, blob, mime in attachments or []:
        db.add(
            EmailLogAttachment(
                email_log_id=log.id,
                filename=filename,
                mime_type=mime or "application/octet-stream",
                content=blob,
                size_bytes=len(blob),
            )
        )
    db.commit()
    db.refresh(log)
    return log


def resend(db: Session, log: EmailLog) -> EmailLog:
    """Admin "Resend" - re-queue the row for the worker.

    Attempt count is preserved so the admin can see the full
    delivery history, but the row is re-eligible immediately
    regardless of the prior backoff schedule.
    """
    log.status = EMAIL_STATUS_QUEUED
    log.error = ""
    log.next_attempt_at = _utcnow()
    db.commit()
    db.refresh(log)
    return log


def send_test_email(db: Session, *, to_email: str, requested_by: str) -> EmailLog:
    """Synchronously send a one-shot test email via the queue path.

    Used by the "Send test email" button on the Settings page.
    The row is queued + immediately delivered so the admin gets
    fast feedback (success / SMTP error / console mode hint).
    """
    log = queue_email(
        db,
        to_emails=[to_email],
        subject="PUG Legal - SMTP test",
        template="notification_email.html",
        context={
            "title": "Test email from PUG Legal Case Control System",
            "subtitle": (
                "If you can read this, your SMTP configuration is working."
            ),
            "lines": [
                f"Triggered by: {requested_by}",
                f"Server time: {_utcnow():%Y-%m-%d %H:%M UTC}",
            ],
            "action_url": settings.brand_app_url,
            "action_label": "Open App",
        },
        event="smtp.test",
    )
    # Bypass the scheduler for instant feedback.
    _deliver(db, log)
    db.commit()
    db.refresh(log)
    return log


# ---------------------------------------------------------------------------
# Scheduler-driven worker
# ---------------------------------------------------------------------------
def process_queue(db: Session, *, limit: int = MAX_PER_TICK) -> dict[str, int]:
    """Drain a slice of the email queue. Called by the scheduler.

    Picks up Queued rows whose ``next_attempt_at`` is now-or-past
    (or NULL) and delivers them. Returns a small stats dict so
    callers can record metrics.
    """
    now = _utcnow()
    q = (
        db.query(EmailLog)
        .filter(EmailLog.status == EMAIL_STATUS_QUEUED)
        .filter(
            (EmailLog.next_attempt_at.is_(None))
            | (EmailLog.next_attempt_at <= now)
        )
        .order_by(EmailLog.id)
        .limit(limit)
    )
    rows = q.all()
    stats = {"picked": len(rows), "sent": 0, "retried": 0, "failed": 0}
    for log in rows:
        _deliver(db, log)
        if log.status == EMAIL_STATUS_SENT:
            stats["sent"] += 1
        elif log.status == EMAIL_STATUS_FAILED:
            stats["failed"] += 1
        else:
            stats["retried"] += 1
        # Commit per-row so a single broken send doesn't roll
        # back the others in the batch.
        db.commit()
    return stats


def _schedule_retry(log: EmailLog) -> None:
    """Push next_attempt_at out by the backoff for this attempt
    count, or mark the row permanently Failed when we've run out
    of retries."""
    # ``attempts`` already includes the just-failed attempt.
    idx = log.attempts - 1
    if 0 <= idx < len(BACKOFF_SECONDS):
        log.status = EMAIL_STATUS_QUEUED
        log.next_attempt_at = _utcnow() + timedelta(seconds=BACKOFF_SECONDS[idx])
    else:
        log.status = EMAIL_STATUS_FAILED
        log.next_attempt_at = None


def _deliver(db: Session, log: EmailLog) -> None:
    """Attempt one delivery. Updates the row in-place; the caller
    commits."""
    log.attempts += 1
    log.last_attempted_at = _utcnow()

    to_list = [e.strip() for e in log.to_emails.split(",") if e.strip()]
    if not to_list:
        log.status = EMAIL_STATUS_FAILED
        log.next_attempt_at = None
        log.error = "No recipients"
        return

    # DB-stored settings (Phase 10) override env vars; fall back to env.
    try:
        from app.services import settings_service

        smtp_cfg = settings_service.effective_smtp(db)
    except Exception:  # pragma: no cover - defensive
        smtp_cfg = {
            "host": settings.smtp_host,
            "port": settings.smtp_port,
            "use_tls": settings.smtp_use_tls,
            "username": settings.smtp_username,
            "password": settings.smtp_password,
            "from_email": settings.smtp_from_email,
            "from_name": settings.smtp_from_name,
        }

    attachments = [
        (a.filename, bytes(a.content), a.mime_type)
        for a in log.attachments or []
    ]

    if not smtp_cfg["host"]:
        attach_note = (
            f" attachments={[a[0] for a in attachments]}" if attachments else ""
        )
        logger.info(
            "[email/console] to={} subject={} template={}{}",
            to_list,
            log.subject,
            log.template_name,
            attach_note,
        )
        log.status = EMAIL_STATUS_SENT
        log.sent_at = _utcnow()
        log.next_attempt_at = None
        log.error = "console mode (SMTP host not configured)"
        return

    try:
        msg = EmailMessage()
        msg["From"] = f"{smtp_cfg['from_name']} <{smtp_cfg['from_email']}>"
        msg["To"] = ", ".join(to_list)
        if log.cc_emails:
            msg["Cc"] = log.cc_emails
        msg["Subject"] = log.subject
        msg.set_content(log.body_text or " ")
        msg.add_alternative(log.body_html, subtype="html")
        for filename, blob, mime in attachments:
            maintype, _, subtype = (mime or "application/octet-stream").partition("/")
            msg.add_attachment(
                blob,
                maintype=maintype or "application",
                subtype=subtype or "octet-stream",
                filename=filename,
            )

        with smtplib.SMTP(smtp_cfg["host"], smtp_cfg["port"], timeout=20) as s:
            s.ehlo()
            if smtp_cfg["use_tls"]:
                s.starttls()
                s.ehlo()
            if smtp_cfg["username"]:
                s.login(smtp_cfg["username"], smtp_cfg["password"])
            recipients = list(
                to_list
                + [e.strip() for e in log.cc_emails.split(",") if e.strip()]
                + [e.strip() for e in log.bcc_emails.split(",") if e.strip()]
            )
            s.send_message(msg, to_addrs=recipients)

        log.status = EMAIL_STATUS_SENT
        log.sent_at = _utcnow()
        log.next_attempt_at = None
        log.error = ""
    except Exception as e:  # pragma: no cover (network errors in real env)
        log.error = f"{type(e).__name__}: {e}"
        logger.warning(
            "Email send failed (attempt {}/{}): {}",
            log.attempts,
            MAX_ATTEMPTS,
            log.error,
        )
        _schedule_retry(log)

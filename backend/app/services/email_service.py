"""Outbound email sender + Jinja2 template rendering.

Operates in two modes:
- console: SMTP_HOST blank -> logs the rendered email, marks EmailLog "Sent"
- smtp: actual SMTP delivery via smtplib

Real queue/retry comes in Phase 7 (Celery beat). Phase 5 is synchronous.
"""

from __future__ import annotations

import smtplib
from datetime import datetime, timezone
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
)

TEMPLATES = Path(__file__).resolve().parent.parent / "templates" / "email"


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
    """Send an email via SMTP (or log-only in console mode).

    ``attachments`` is a list of (filename, blob, mime). Attachments are NOT
    persisted to the database, so they cannot be replayed by ``resend``.
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
        event=event,
        related_case_id=related_case_id,
        related_user_id=related_user_id,
    )
    db.add(log)
    db.flush()
    _deliver(db, log, attachments=attachments)
    db.commit()
    db.refresh(log)
    return log


def resend(db: Session, log: EmailLog) -> EmailLog:
    log.status = EMAIL_STATUS_QUEUED
    log.error = ""
    db.flush()
    # Attachments aren't persisted; resend goes out without them.
    _deliver(db, log, attachments=None)
    db.commit()
    db.refresh(log)
    return log


def _deliver(
    db: Session,
    log: EmailLog,
    *,
    attachments: list[tuple[str, bytes, str]] | None = None,
) -> None:
    log.attempts += 1
    to_list = [e.strip() for e in log.to_emails.split(",") if e.strip()]
    if not to_list:
        log.status = EMAIL_STATUS_FAILED
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
        log.sent_at = datetime.now(timezone.utc)
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
        for filename, blob, mime in attachments or []:
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
        log.sent_at = datetime.now(timezone.utc)
        log.error = ""
    except Exception as e:  # pragma: no cover (network errors in real env)
        log.status = EMAIL_STATUS_FAILED
        log.error = f"{type(e).__name__}: {e}"
        logger.warning("Email send failed: {}", log.error)

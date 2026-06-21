"""Admin email log: list, preview, resend, bounce stub, SMTP test."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_permission, require_super
from app.core.permissions import ADMIN_EMAIL_LOG, ADMIN_SETTINGS
from app.db.session import get_db
from app.models.notification import EMAIL_STATUS_BOUNCED, EmailLog
from app.models.user import User
from app.schemas.notification import (
    EmailBounceWebhook,
    EmailLogDetail,
    EmailLogItem,
    TestEmailRequest,
    TestEmailResponse,
)
from app.services import email_service

router = APIRouter(prefix="/admin/email-log", tags=["admin"])


@router.get("", response_model=list[EmailLogItem])
def list_email_log(
    only: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(ADMIN_EMAIL_LOG)),
) -> list[EmailLogItem]:
    q = db.query(EmailLog)
    if only:
        q = q.filter(EmailLog.status == only)
    rows = q.order_by(EmailLog.id.desc()).limit(min(limit, 500)).all()
    return [EmailLogItem.model_validate(r) for r in rows]


@router.get("/{log_id}", response_model=EmailLogDetail)
def get_email_log(
    log_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(ADMIN_EMAIL_LOG)),
) -> EmailLogDetail:
    log = db.get(EmailLog, log_id)
    if not log:
        raise HTTPException(status_code=404, detail="Not found")
    return EmailLogDetail.model_validate(log)


@router.get("/{log_id}/preview", response_class=HTMLResponse)
def preview_email(
    log_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(ADMIN_EMAIL_LOG)),
) -> HTMLResponse:
    log = db.get(EmailLog, log_id)
    if not log:
        raise HTTPException(status_code=404, detail="Not found")
    return HTMLResponse(log.body_html or "<em>No HTML body.</em>")


@router.post("/{log_id}/resend", response_model=EmailLogDetail)
def resend_email(
    log_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(ADMIN_EMAIL_LOG)),
) -> EmailLogDetail:
    log = db.get(EmailLog, log_id)
    if not log:
        raise HTTPException(status_code=404, detail="Not found")
    log = email_service.resend(db, log)
    return EmailLogDetail.model_validate(log)


@router.post("/test", response_model=TestEmailResponse)
def send_test_email(
    payload: TestEmailRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(ADMIN_SETTINGS)),
) -> TestEmailResponse:
    """Phase 25: synchronously send a one-shot test email so the
    admin gets fast feedback while tuning SMTP config.

    The row goes through the same delivery path as a queued email
    (so console mode + SMTP errors both surface the same way), but
    it's sent inline rather than waiting for the scheduler tick.
    """
    addr = payload.to_email.strip()
    if not addr or "@" not in addr:
        raise HTTPException(status_code=400, detail="A valid recipient email is required")
    log = email_service.send_test_email(db, to_email=addr, requested_by=user.email)
    return TestEmailResponse(
        email_log_id=log.id,
        status=log.status,
        error=log.error,
        sent_at=log.sent_at,
    )


@router.post("/bounce", status_code=status.HTTP_200_OK)
def bounce_webhook(
    payload: EmailBounceWebhook,
    db: Session = Depends(get_db),
    _: User = Depends(require_super),
) -> dict:
    """Stub endpoint - real SES/SendGrid webhook integration is op-team config."""
    log = db.get(EmailLog, payload.email_log_id)
    if not log:
        raise HTTPException(status_code=404, detail="Not found")
    log.status = EMAIL_STATUS_BOUNCED
    log.error = payload.error
    db.commit()
    return {"status": "ok"}

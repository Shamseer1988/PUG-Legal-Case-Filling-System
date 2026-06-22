"""Notification orchestration: in-app bell + branded email per event.

Each function is small + defensive: missing fields just skip notification
rather than crashing the calling workflow.
"""

from __future__ import annotations

from loguru import logger
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.case import Case
from app.models.court import CashRequest
from app.models.notification import Notification
from app.models.user import User
from app.services import email_service

EMAIL_TEMPLATE = "notification_email.html"
# Phase 31: per-locale variants of the notification email. ``en``
# is the default; falling back to it for unknown locales keeps the
# pipeline robust if a new locale ships before its template does.
_EMAIL_TEMPLATES_BY_LOCALE = {
    "en": "notification_email.html",
    "ar": "notification_email.ar.html",
}


def _template_for(locale: str) -> str:
    return _EMAIL_TEMPLATES_BY_LOCALE.get((locale or "en").lower(), EMAIL_TEMPLATE)


def _case_url(case_id: int) -> str:
    return f"{settings.brand_app_url.rstrip('/')}/cases/{case_id}"


def _emit(
    db: Session,
    *,
    user_id: int,
    title: str,
    body: str,
    link: str,
    event: str,
    related_case_id: int | None,
    facts: list[tuple[str, str]] | None = None,
    lines: list[str] | None = None,
) -> None:
    user = db.get(User, user_id)
    if not user or not user.is_active:
        return

    db.add(
        Notification(
            user_id=user.id,
            title=title,
            body=body,
            link=link,
            event=event,
            related_case_id=related_case_id,
        )
    )

    if not user.email:
        return

    # Don't let an email failure (bad SMTP host, slow auth, etc.)
    # take down the workflow transition that triggered it. The
    # transition has already committed; the email is best-effort.
    try:
        # Phase 31: deliver the email in the user's preferred locale
        # by picking the matching template variant. The template's
        # own strings live in app/templates/email/.
        locale = (user.locale or "en").lower()
        is_rtl = locale == "ar"
        action_label = "Open Case" if locale != "ar" else "فتح القضية"
        email_service.queue_email(
            db,
            to_emails=[user.email],
            subject=title,
            template=_template_for(locale),
            context={
                "title": title,
                "subtitle": "",
                "lines": lines or ([body] if body else []),
                "facts": facts or [],
                "action_url": link,
                "action_label": action_label,
                "locale": locale,
                "is_rtl": is_rtl,
                "dir": "rtl" if is_rtl else "ltr",
            },
            event=event,
            related_case_id=related_case_id,
            related_user_id=user.id,
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("queue_email failed for {} ({}): {}", user.email, event, exc)

    # Phase 32: fire a web push too. Best-effort; subscription
    # failures must never block the workflow that triggered us.
    try:
        from app.services import push_service

        push_service.send_to_user(
            db,
            user_id=user.id,
            payload={
                "title": title,
                "body": body or (lines[0] if lines else ""),
                "url": link,
                "event": event,
                "case_id": related_case_id,
            },
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("push send failed for user {} ({}): {}", user.id, event, exc)


def _case_facts(case: Case) -> list[tuple[str, str]]:
    return [
        ("Case No.", case.case_no),
        ("Status", case.status),
        ("Current Stage", case.current_stage),
        ("Legal Amount", f"{case.legal_filing_amount}"),
    ]


# ===================== Workflow events =====================
def on_case_submitted(db: Session, case: Case, actor: User) -> None:
    target = case.sales_manager_id
    if not target:
        return
    _emit(
        db,
        user_id=target,
        title=f"New legal case submitted: {case.case_no}",
        body=f"{actor.full_name} submitted a case for your review.",
        link=_case_url(case.id),
        event="case.submitted",
        related_case_id=case.id,
        lines=[f"{actor.full_name} has submitted a new case for review."],
        facts=_case_facts(case),
    )


def on_case_advanced(db: Session, case: Case, actor: User, comment: str) -> None:
    """Notify the user assigned to the new (current) stage."""
    from app.core.workflow import get_stage

    cfg = get_stage(case.current_stage)
    user_field = cfg.user_field if cfg else None
    if not user_field:
        return
    target = getattr(case, user_field, None)
    if not target:
        return
    _emit(
        db,
        user_id=target,
        title=f"Case awaiting your approval: {case.case_no}",
        body=f"Approved by {actor.full_name}. Now at {case.current_stage}.",
        link=_case_url(case.id),
        event="case.advanced",
        related_case_id=case.id,
        lines=(
            [comment] if comment else []
        )
        + [f"Approved by {actor.full_name}. Now waiting at {case.current_stage}."],
        facts=_case_facts(case),
    )


def on_case_rejected(db: Session, case: Case, actor: User, comment: str) -> None:
    target = case.created_by_id
    _emit(
        db,
        user_id=target,
        title=f"Case rejected: {case.case_no}",
        body=f"Rejected by {actor.full_name} at {case.current_stage}.",
        link=_case_url(case.id),
        event="case.rejected",
        related_case_id=case.id,
        lines=[
            f"Rejected by {actor.full_name} at {case.current_stage}.",
            f"Reason: {comment}",
        ],
        facts=_case_facts(case),
    )


def on_case_clarification_requested(
    db: Session, case: Case, actor: User, comment: str
) -> None:
    target = case.created_by_id
    _emit(
        db,
        user_id=target,
        title=f"Clarification requested: {case.case_no}",
        body=f"{actor.full_name} asks: {comment}",
        link=_case_url(case.id),
        event="case.clarification_requested",
        related_case_id=case.id,
        lines=[f"{actor.full_name} requested clarification:", comment],
        facts=_case_facts(case),
    )


def on_case_resubmitted(db: Session, case: Case, actor: User) -> None:
    """Notify the stage receiving the resubmission."""
    from app.core.workflow import get_stage

    cfg = get_stage(case.current_stage)
    if not cfg or not cfg.user_field:
        return
    target = getattr(case, cfg.user_field, None)
    if not target:
        return
    _emit(
        db,
        user_id=target,
        title=f"Clarification answered: {case.case_no}",
        body=f"{actor.full_name} resubmitted with clarification.",
        link=_case_url(case.id),
        event="case.resubmitted",
        related_case_id=case.id,
        facts=_case_facts(case),
    )


# ===================== Lawyer / Court events =====================
def on_lawyer_approved(db: Session, case: Case, actor: User, comment: str) -> None:
    """Phase 20: Lawyer explicitly signs off after filing.

    Pings both the case author (so they know the matter is now
    cleared for closure) and the Chairman who gave final approval,
    so the chain of custody is visible end-to-end.
    """
    targets = {case.created_by_id, case.chairman_id}
    for uid in targets:
        if uid:
            _emit(
                db,
                user_id=uid,
                title=f"Lawyer approval recorded: {case.case_no}",
                body=f"{actor.full_name} signed off the filing.",
                link=_case_url(case.id),
                event="case.lawyer_approved",
                related_case_id=case.id,
                lines=(
                    [comment] if comment else []
                )
                + [f"{actor.full_name} confirmed the filing."],
                facts=_case_facts(case),
            )


def on_court_filed(db: Session, case: Case, actor: User) -> None:
    """Notify both the Finance Manager and the case author once a
    court filing is recorded - the FM needs to release legal cash
    against the filing reference, the Accountant needs to update
    their tracker."""
    targets = {case.fm_id, case.created_by_id}
    for uid in targets:
        if uid:
            _emit(
                db,
                user_id=uid,
                title=f"Case filed in court: {case.case_no}",
                body=f"Filed by {actor.full_name}.",
                link=_case_url(case.id),
                event="case.court_filed",
                related_case_id=case.id,
                facts=_case_facts(case),
            )


def on_signed_form_uploaded(db: Session, case: Case, actor: User) -> None:
    """Phase 24: signed copy of the printed form is now on file.

    Notify the case author (Accountant) and any Auditor mapped to
    the case so they can verify the signed copy matches the
    approved details before closure runs."""
    targets = {case.created_by_id, case.auditor_id}
    for uid in targets:
        if uid:
            _emit(
                db,
                user_id=uid,
                title=f"Signed form uploaded: {case.case_no}",
                body=f"{actor.full_name} attached the signed copy of the case form.",
                link=_case_url(case.id),
                event="case.signed_form_uploaded",
                related_case_id=case.id,
                facts=_case_facts(case),
            )


def on_case_closed(db: Session, case: Case, actor: User, closure_type: str) -> None:
    """Notify case author + Chairman + FM that closure is recorded."""
    targets = {case.created_by_id, case.chairman_id, case.fm_id}
    pretty_type = closure_type.replace("_", " ").title()
    for uid in targets:
        if uid:
            _emit(
                db,
                user_id=uid,
                title=f"Case closed: {case.case_no}",
                body=f"Closed by {actor.full_name} via {pretty_type}.",
                link=_case_url(case.id),
                event="case.closed",
                related_case_id=case.id,
                facts=_case_facts(case)
                + [("Closure Type", pretty_type)],
            )


def on_case_sla_breached(db: Session, case: Case) -> None:
    """Phase 33: scheduled escalation when a case overruns its stage SLA.

    Targets the signatory currently sitting on the case (the same
    person who would receive the ``case.advanced`` ping). If no
    assignee is mapped on the case for that stage, the breach is
    silently ignored — there's nobody to nudge.
    """
    from app.core.workflow import get_stage

    cfg = get_stage(case.current_stage)
    user_field = cfg.user_field if cfg else None
    if not user_field:
        return
    target = getattr(case, user_field, None)
    if not target:
        return
    due = case.sla_due_at
    facts = _case_facts(case)
    if due is not None:
        facts.append(("SLA Due", due.strftime("%Y-%m-%d %H:%M UTC")))
    _emit(
        db,
        user_id=target,
        title=f"SLA breach: {case.case_no}",
        body=(
            f"{case.case_no} is past its {case.current_stage} SLA. "
            "Please approve or request clarification."
        ),
        link=_case_url(case.id),
        event="case.sla_breached",
        related_case_id=case.id,
        lines=[
            f"{case.case_no} has overrun the {case.current_stage} stage SLA.",
            "Open the case to approve, reject, or ask for clarification.",
        ],
        facts=facts,
    )


def on_cash_request_created(db: Session, cash: CashRequest, case: Case) -> None:
    if not case.fm_id:
        return
    _emit(
        db,
        user_id=case.fm_id,
        title=f"Cash request: {case.case_no}",
        body=f"Amount {cash.amount}. {cash.purpose or ''}",
        link=_case_url(case.id),
        event="cash_request.created",
        related_case_id=case.id,
        facts=[("Amount", f"{cash.amount}"), ("Purpose", cash.purpose or "-"), ("Case", case.case_no)],
    )


def on_cash_request_approved(db: Session, cash: CashRequest, case: Case) -> None:
    # Notify the Accountant (case creator)
    _emit(
        db,
        user_id=case.created_by_id,
        title=f"Cash request approved: {case.case_no}",
        body=f"Approved amount {cash.amount}.",
        link=_case_url(case.id),
        event="cash_request.approved",
        related_case_id=case.id,
        facts=[("Amount", f"{cash.amount}"), ("Approval Note", cash.approval_comment or "-")],
    )


def on_cash_request_rejected(db: Session, cash: CashRequest, case: Case) -> None:
    _emit(
        db,
        user_id=cash.requested_by_id,
        title=f"Cash request rejected: {case.case_no}",
        body=cash.approval_comment or "",
        link=_case_url(case.id),
        event="cash_request.rejected",
        related_case_id=case.id,
        facts=[("Amount", f"{cash.amount}"), ("Reason", cash.approval_comment or "-")],
    )


def on_cash_request_paid(db: Session, cash: CashRequest, case: Case) -> None:
    _emit(
        db,
        user_id=cash.requested_by_id,
        title=f"Cash paid: {case.case_no}",
        body=f"Reference: {cash.payment_reference}",
        link=_case_url(case.id),
        event="cash_request.paid",
        related_case_id=case.id,
        facts=[("Amount", f"{cash.amount}"), ("Reference", cash.payment_reference or "-")],
    )

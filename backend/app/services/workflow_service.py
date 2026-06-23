"""Workflow transition logic and inbox query."""

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.data_scope import allowed_division_ids
from app.core.permissions import has_permission
from app.core.workflow import (
    APPROVAL_STAGE_ORDER,
    WORKFLOW_STAGES,
    StageConfig,
    get_stage,
)
from app.models.case import (
    ACTION_APPROVE,
    ACTION_LAWYER_APPROVE,
    ACTION_REJECT,
    ACTION_REQUEST_CLARIFICATION,
    ACTION_RESUBMIT,
    ACTION_SUBMIT,
    CASE_STATUS_APPROVED,
    CASE_STATUS_CLARIFICATION,
    CASE_STATUS_DRAFT,
    CASE_STATUS_FILED,
    CASE_STATUS_IN_REVIEW,
    CASE_STATUS_LAWYER_APPROVED,
    CASE_STATUS_REJECTED,
    CASE_STATUS_SUBMITTED,
    STAGE_ACCOUNTANT,
    STAGE_LAWYER,
    Case,
    CaseStatusUpdate,
)
from app.models.user import User


class WorkflowError(ValueError):
    """Raised when a transition is not allowed."""


# ---------------- helpers ----------------
def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _set_stage(case: Case, new_stage: str, cfg: StageConfig | None) -> None:
    case.current_stage = new_stage
    case.stage_entered_at = _utcnow()
    case.sla_due_at = (
        _utcnow() + timedelta(hours=cfg.sla_hours) if cfg and cfg.sla_hours else None
    )
    # Phase 33: clear the breach flag so the scanner can fire a fresh
    # notification if the new stage also overruns its SLA.
    case.sla_breach_notified_at = None


def _audit_transition(
    db: Session,
    case: Case,
    actor: User,
    *,
    action: str,
    from_status: str,
    to_status: str,
    from_stage: str,
    to_stage: str,
    comment: str,
) -> None:
    from app.services import audit_service

    audit_service.record_event(
        db,
        action=action,
        entity_type="Case",
        entity_id=case.id,
        summary=f"{action} {case.case_no}: {from_stage} -> {to_stage}",
        before={"status": from_status, "stage": from_stage},
        after={"status": to_status, "stage": to_stage},
        meta={"comment": comment[:500]} if comment else None,
        actor=actor,
    )


def _log(
    db: Session,
    case: Case,
    actor: User,
    action: str,
    *,
    from_status: str,
    to_status: str,
    from_stage: str,
    to_stage: str,
    comment: str,
) -> CaseStatusUpdate:
    entry = CaseStatusUpdate(
        case_id=case.id,
        action_type=action,
        from_status=from_status,
        to_status=to_status,
        from_stage=from_stage,
        to_stage=to_stage,
        actor_id=actor.id,
        comment=comment.strip(),
    )
    db.add(entry)
    return entry


# ---------------- transitions ----------------
def submit(db: Session, case: Case, user: User) -> Case:
    """Promote a Draft to Submitted -> Sales Manager."""
    if case.status != CASE_STATUS_DRAFT:
        raise WorkflowError("Only Draft cases can be submitted")
    if not case.cheques:
        raise WorkflowError("At least one cheque is required before submitting")
    # Phase 38: ChequeBase allows empty cheque_number during Draft
    # (so the cheque-copy upload can attach before the number is
    # known). Enforce the field is filled before the case actually
    # leaves the Accountant's hands.
    missing = [ch for ch in case.cheques if not (ch.cheque_number or "").strip()]
    if missing:
        raise WorkflowError(
            f"{len(missing)} cheque row(s) are missing a cheque number"
        )

    from_status, from_stage = case.status, case.current_stage
    first = WORKFLOW_STAGES[0]
    case.status = CASE_STATUS_SUBMITTED
    _set_stage(case, first.stage, first)
    case.submitted_at = _utcnow()

    _log(
        db,
        case,
        user,
        ACTION_SUBMIT,
        from_status=from_status,
        to_status=case.status,
        from_stage=from_stage,
        to_stage=case.current_stage,
        comment="Submitted for approval",
    )
    _audit_transition(
        db,
        case,
        user,
        action=ACTION_SUBMIT,
        from_status=from_status,
        to_status=case.status,
        from_stage=from_stage,
        to_stage=case.current_stage,
        comment="Submitted for approval",
    )
    db.commit()
    db.refresh(case)
    from app.services import notification_service

    notification_service.on_case_submitted(db, case, user)
    db.commit()
    return case


def approve(db: Session, case: Case, user: User, comment: str) -> Case:
    cfg = get_stage(case.current_stage)
    if not cfg:
        raise WorkflowError(f"Cannot approve at stage '{case.current_stage}'")
    if case.status not in (CASE_STATUS_SUBMITTED, CASE_STATUS_IN_REVIEW):
        raise WorkflowError(f"Cannot approve while status is '{case.status}'")

    from_status, from_stage = case.status, case.current_stage
    next_cfg = get_stage(cfg.next_stage) if cfg.next_stage else None

    if cfg.is_final_approval:
        # Final approval: Chairman/MD -> Lawyer, status flips to Approved
        case.status = CASE_STATUS_APPROVED
        _set_stage(case, STAGE_LAWYER, None)
    else:
        case.status = CASE_STATUS_IN_REVIEW
        _set_stage(case, cfg.next_stage or case.current_stage, next_cfg)

    _log(
        db,
        case,
        user,
        ACTION_APPROVE,
        from_status=from_status,
        to_status=case.status,
        from_stage=from_stage,
        to_stage=case.current_stage,
        comment=comment,
    )
    _audit_transition(
        db,
        case,
        user,
        action=ACTION_APPROVE,
        from_status=from_status,
        to_status=case.status,
        from_stage=from_stage,
        to_stage=case.current_stage,
        comment=comment,
    )
    db.commit()
    db.refresh(case)
    from app.services import notification_service

    notification_service.on_case_advanced(db, case, user, comment)
    db.commit()
    return case


def reject(db: Session, case: Case, user: User, comment: str) -> Case:
    if case.status in (CASE_STATUS_REJECTED, CASE_STATUS_APPROVED):
        raise WorkflowError("Case already finalised")
    if not comment.strip():
        raise WorkflowError("A reason is required when rejecting")
    from_status, from_stage = case.status, case.current_stage
    case.status = CASE_STATUS_REJECTED
    case.sla_due_at = None
    case.sla_breach_notified_at = None
    _log(
        db,
        case,
        user,
        ACTION_REJECT,
        from_status=from_status,
        to_status=case.status,
        from_stage=from_stage,
        to_stage=case.current_stage,
        comment=comment,
    )
    _audit_transition(
        db,
        case,
        user,
        action=ACTION_REJECT,
        from_status=from_status,
        to_status=case.status,
        from_stage=from_stage,
        to_stage=case.current_stage,
        comment=comment,
    )
    db.commit()
    db.refresh(case)
    from app.services import notification_service

    notification_service.on_case_rejected(db, case, user, comment)
    db.commit()
    return case


def request_clarification(db: Session, case: Case, user: User, comment: str) -> Case:
    cfg = get_stage(case.current_stage)
    if not cfg:
        raise WorkflowError(
            f"Clarification can only be requested at an approval stage; current = '{case.current_stage}'"
        )
    if not comment.strip():
        raise WorkflowError("A question is required when requesting clarification")
    from_status, from_stage = case.status, case.current_stage
    case.status = CASE_STATUS_CLARIFICATION
    _set_stage(case, STAGE_ACCOUNTANT, None)
    _log(
        db,
        case,
        user,
        ACTION_REQUEST_CLARIFICATION,
        from_status=from_status,
        to_status=case.status,
        from_stage=from_stage,
        to_stage=case.current_stage,
        comment=comment,
    )
    _audit_transition(
        db,
        case,
        user,
        action=ACTION_REQUEST_CLARIFICATION,
        from_status=from_status,
        to_status=case.status,
        from_stage=from_stage,
        to_stage=case.current_stage,
        comment=comment,
    )
    db.commit()
    db.refresh(case)
    from app.services import notification_service

    notification_service.on_case_clarification_requested(db, case, user, comment)
    db.commit()
    return case


def resubmit(db: Session, case: Case, user: User, comment: str) -> Case:
    if case.status != CASE_STATUS_CLARIFICATION:
        raise WorkflowError("Resubmit is only valid after a clarification request")
    # find the stage that last requested clarification
    last_clar = next(
        (
            t
            for t in reversed(case.timeline)
            if t.action_type == ACTION_REQUEST_CLARIFICATION
        ),
        None,
    )
    target_stage = last_clar.from_stage if last_clar else WORKFLOW_STAGES[0].stage
    cfg = get_stage(target_stage)
    if not cfg:
        target_stage = WORKFLOW_STAGES[0].stage
        cfg = WORKFLOW_STAGES[0]
    from_status, from_stage = case.status, case.current_stage
    case.status = CASE_STATUS_IN_REVIEW
    _set_stage(case, target_stage, cfg)
    _log(
        db,
        case,
        user,
        ACTION_RESUBMIT,
        from_status=from_status,
        to_status=case.status,
        from_stage=from_stage,
        to_stage=case.current_stage,
        comment=comment or "Clarification answered, resubmitting.",
    )
    _audit_transition(
        db,
        case,
        user,
        action=ACTION_RESUBMIT,
        from_status=from_status,
        to_status=case.status,
        from_stage=from_stage,
        to_stage=case.current_stage,
        comment=comment or "Clarification answered, resubmitting.",
    )
    db.commit()
    db.refresh(case)
    from app.services import notification_service

    notification_service.on_case_resubmitted(db, case, user)
    db.commit()
    return case


def lawyer_approve(db: Session, case: Case, user: User, comment: str) -> Case:
    """Explicit Lawyer sign-off after the case is Filed.

    Closes the gap that previously left the Lawyer panel saying
    "No approval action available" once the case reached the
    Filed state — the Lawyer now confirms the filing before
    closure becomes the next available action.
    """
    if case.status != CASE_STATUS_FILED:
        raise WorkflowError(
            f"Lawyer approval is only available after court filing; status = '{case.status}'"
        )
    if case.current_stage != STAGE_LAWYER:
        raise WorkflowError(
            f"Lawyer approval is only available at the Lawyer stage; current = '{case.current_stage}'"
        )
    from_status, from_stage = case.status, case.current_stage
    case.status = CASE_STATUS_LAWYER_APPROVED
    # Stay on the Lawyer stage so closure can pick up from here.
    _set_stage(case, STAGE_LAWYER, None)
    _log(
        db,
        case,
        user,
        ACTION_LAWYER_APPROVE,
        from_status=from_status,
        to_status=case.status,
        from_stage=from_stage,
        to_stage=case.current_stage,
        comment=comment or "Lawyer approved.",
    )
    _audit_transition(
        db,
        case,
        user,
        action=ACTION_LAWYER_APPROVE,
        from_status=from_status,
        to_status=case.status,
        from_stage=from_stage,
        to_stage=case.current_stage,
        comment=comment or "Lawyer approved.",
    )
    db.commit()
    db.refresh(case)
    from app.services import notification_service

    notification_service.on_lawyer_approved(db, case, user, comment)
    db.commit()
    return case


# ---------------- access helpers ----------------
def can_act(user: User, case: Case) -> bool:
    """Whether the given user can take an action at the case's current stage."""
    if user.is_super:
        return True
    perms = user.role.permissions if user.role else []
    cfg = get_stage(case.current_stage)
    allowed = allowed_division_ids(user)
    user_div_ids = set(allowed) if allowed is not None else None  # None = all
    if not cfg:
        # Accountant clarification: any user with cases:create on their own case
        if case.current_stage == STAGE_ACCOUNTANT and case.status == CASE_STATUS_CLARIFICATION:
            return has_permission(perms, "cases:create") and (
                case.created_by_id == user.id
                or user_div_ids is None
                or case.division_id in user_div_ids
            )
        # Lawyer stage with status=Filed: an explicit lawyer-approve
        # action becomes available to anyone with cases:approve:lawyer.
        if case.current_stage == STAGE_LAWYER and case.status == CASE_STATUS_FILED:
            return has_permission(perms, "cases:approve:lawyer")
        return False
    if not has_permission(perms, cfg.permission):
        return False
    # If user has division scope and case is outside it, deny.
    if user_div_ids is not None and user_div_ids:
        if case.division_id not in user_div_ids:
            return False
    return True


def inbox_for(db: Session, user: User) -> list[Case]:
    """Return cases waiting for action by this user."""
    q = db.query(Case)
    if user.is_super:
        # Super sees every in-progress case
        q = q.filter(
            Case.status.in_(
                [
                    CASE_STATUS_SUBMITTED,
                    CASE_STATUS_IN_REVIEW,
                    CASE_STATUS_CLARIFICATION,
                ]
            )
        )
        return q.order_by(Case.id.desc()).all()

    perms = user.role.permissions if user.role else []
    allowed = allowed_division_ids(user)
    actionable_stages: list[str] = []
    for cfg in WORKFLOW_STAGES:
        if has_permission(perms, cfg.permission):
            actionable_stages.append(cfg.stage)

    rows: list[Case] = []
    if actionable_stages:
        sub_q = q.filter(
            Case.status.in_([CASE_STATUS_SUBMITTED, CASE_STATUS_IN_REVIEW]),
            Case.current_stage.in_(actionable_stages),
        )
        if allowed is not None and allowed:
            sub_q = sub_q.filter(Case.division_id.in_(allowed))
        rows.extend(sub_q.all())

    # Clarifications come back to the Accountant who created them (or anyone in their division)
    if has_permission(perms, "cases:create"):
        clar_q = q.filter(Case.status == CASE_STATUS_CLARIFICATION)
        if allowed is None:
            pass  # cross-division - see every clarification
        elif allowed:
            clar_q = clar_q.filter(Case.division_id.in_(allowed))
        else:
            clar_q = clar_q.filter(Case.created_by_id == user.id)
        rows.extend(clar_q.all())

    return sorted({c.id: c for c in rows}.values(), key=lambda c: c.id, reverse=True)


def is_overdue(case: Case) -> bool:
    due = case.sla_due_at
    if not due:
        return False
    # SQLite hands back naive datetimes; assume UTC so the comparison
    # with the aware ``_utcnow()`` doesn't raise.
    if due.tzinfo is None:
        due = due.replace(tzinfo=timezone.utc)
    return due < _utcnow()


def assigned_user_field_for(case: Case) -> str | None:
    cfg = get_stage(case.current_stage)
    return cfg.user_field if cfg else None


__all__ = [
    "WorkflowError",
    "submit",
    "approve",
    "reject",
    "request_clarification",
    "resubmit",
    "lawyer_approve",
    "can_act",
    "inbox_for",
    "is_overdue",
    "assigned_user_field_for",
    "APPROVAL_STAGE_ORDER",
]

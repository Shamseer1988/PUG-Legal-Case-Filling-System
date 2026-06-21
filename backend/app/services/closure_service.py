"""Closing a case: validates settlement details, writes the closure
row, transitions the case to ``Closed`` and emits an audit entry.
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.case import (
    CASE_STATUS_APPROVED,
    CASE_STATUS_CLOSED,
    CASE_STATUS_FILED,
    CASE_STATUS_LAWYER_APPROVED,
    STAGE_CLOSED,
    Case,
    CaseStatusUpdate,
)
from app.models.closure import (
    CLOSURE_CASH_RECEIVED,
    CLOSURE_COURT_CHEQUE,
    CLOSURE_ONLINE_TRANSFER,
    CLOSURE_SETTLEMENT,
    CLOSURE_WRITEOFF,
    CaseClosure,
)
from app.models.user import User
from app.schemas.closure import ClosureCreate
from app.services import audit_service


class ClosureError(ValueError):
    """Raised when a case cannot be closed."""


CLOSABLE_STATUSES = {
    CASE_STATUS_APPROVED,
    CASE_STATUS_FILED,
    CASE_STATUS_LAWYER_APPROVED,
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _validate(payload: ClosureCreate) -> None:
    t = payload.closure_type
    if t == CLOSURE_COURT_CHEQUE:
        if not payload.court_cheque_number.strip():
            raise ClosureError("Court cheque number is required")
    elif t == CLOSURE_ONLINE_TRANSFER:
        if not payload.transfer_reference.strip():
            raise ClosureError("Transfer reference is required")
    elif t == CLOSURE_CASH_RECEIVED:
        if not payload.cash_receipt_no.strip():
            raise ClosureError("Cash receipt number is required")
    elif t == CLOSURE_SETTLEMENT:
        if not payload.settlement_agreement_ref.strip():
            raise ClosureError("Settlement agreement reference is required")
    elif t == CLOSURE_WRITEOFF:
        if not payload.writeoff_reason.strip():
            raise ClosureError("A write-off reason is required")
    if not payload.command.strip():
        raise ClosureError("A closure command / note is required")


def close_case(
    db: Session, case: Case, user: User, payload: ClosureCreate
) -> CaseClosure:
    if case.status not in CLOSABLE_STATUSES:
        raise ClosureError(
            f"Case must be Approved / Filed / Lawyer Approved before closing "
            f"(currently {case.status})"
        )
    existing = (
        db.query(CaseClosure).filter(CaseClosure.case_id == case.id).first()
    )
    if existing:
        raise ClosureError("Case has already been closed")

    _validate(payload)

    closure = CaseClosure(
        case_id=case.id,
        closed_by_id=user.id,
        closed_at=_utcnow(),
        **payload.model_dump(),
    )
    db.add(closure)

    prev_status, prev_stage = case.status, case.current_stage
    case.status = CASE_STATUS_CLOSED
    case.current_stage = STAGE_CLOSED
    case.sla_due_at = None
    db.add(
        CaseStatusUpdate(
            case_id=case.id,
            action_type="closed",
            from_status=prev_status,
            to_status=case.status,
            from_stage=prev_stage,
            to_stage=case.current_stage,
            actor_id=user.id,
            comment=f"Closed via {payload.closure_type}: {payload.command[:300]}",
        )
    )
    db.commit()
    db.refresh(closure)

    audit_service.record_event(
        db,
        action="case_closed",
        entity_type="Case",
        entity_id=case.id,
        summary=(
            f"Closed {case.case_no} via {payload.closure_type} "
            f"(settled {payload.settled_amount})"
        ),
        before={"status": prev_status, "stage": prev_stage},
        after={
            "status": case.status,
            "stage": case.current_stage,
            "closure_type": payload.closure_type,
            "settled_amount": str(payload.settled_amount),
            "settled_date": str(payload.settled_date) if payload.settled_date else None,
        },
        meta={"command": payload.command[:500]},
        actor=user,
        commit=True,
    )
    return closure


def get_closure(db: Session, case: Case) -> CaseClosure | None:
    return (
        db.query(CaseClosure).filter(CaseClosure.case_id == case.id).first()
    )

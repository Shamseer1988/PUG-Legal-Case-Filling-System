"""Business logic for court filing, hearings, and cash requests."""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.case import (
    ACTION_COMMENT,
    CASE_STATUS_APPROVED,
    CASE_STATUS_FILED,
    STAGE_LAWYER,
    Case,
    CaseStatusUpdate,
)
from app.models.court import (
    CASH_REQUEST_APPROVED,
    CASH_REQUEST_PAID,
    CASH_REQUEST_REJECTED,
    CASH_REQUEST_REQUESTED,
    CashRequest,
    CourtFiling,
    Hearing,
)
from app.models.user import User
from app.schemas.court import (
    CashRequestCreate,
    CashRequestPayPayload,
    CashRequestRejectPayload,
    CourtFilingCreate,
    CourtFilingUpdate,
    HearingCreate,
    HearingUpdate,
)
from app.services import audit_service


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CourtError(ValueError):
    """Raised when an operation is not allowed."""


def _assert_folder_with_lawyer(db: Session, case: Case) -> None:
    """Phase 41B: a case can only be marked Filed once its physical
    originals are with a Lawyer-role user. Stops the workflow from
    advancing past the point where the lawyer literally needs the
    paper to walk into court.

    Backward-compat carve-out: cases whose physical files have
    never been actively tracked (only the auto-create head row from
    case-create) bypass the gate. The check activates as soon as
    the operator records the first transfer.
    """
    from app.models.physical_document import DocumentCustodyLog, PhysicalDocument
    from app.models.user import Role, User as UserModel

    docs = (
        db.query(PhysicalDocument)
        .filter(
            PhysicalDocument.case_id == case.id,
            PhysicalDocument.is_active.is_(True),
        )
        .all()
    )
    if not docs:
        return
    lawyer_ids = {
        u.id
        for u in db.query(UserModel)
        .join(Role, UserModel.role_id == Role.id)
        .filter(Role.name == "Lawyer")
        .all()
    }
    if not lawyer_ids:
        return
    # Skip when every active doc is still on its auto-create row -
    # no real custody activity yet. Once the operator transfers
    # once, the gate engages.
    all_untouched = all(
        db.query(DocumentCustodyLog)
        .filter(DocumentCustodyLog.document_id == d.id)
        .count()
        <= 1
        for d in docs
    )
    if all_untouched:
        return
    if any(d.current_holder_user_id in lawyer_ids for d in docs):
        return
    raise CourtError(
        "Hand the physical case folder to the lawyer (Physical Files "
        "panel → Transfer) before recording the court filing."
    )


# ----------------- Court Filing -----------------
def create_court_filing(
    db: Session, case: Case, user: User, payload: CourtFilingCreate
) -> CourtFiling:
    if case.status not in (CASE_STATUS_APPROVED, CASE_STATUS_FILED):
        raise CourtError(
            "Court filing can only be recorded after the case is Approved by Chairman / MD"
        )
    if db.query(CourtFiling).filter(CourtFiling.case_id == case.id).first():
        raise CourtError("Court filing already exists for this case")
    _assert_folder_with_lawyer(db, case)

    filing = CourtFiling(
        case_id=case.id,
        filed_by_id=user.id,
        **payload.model_dump(),
    )
    db.add(filing)

    # Promote case status to Filed; keep stage at Lawyer
    prev_status, prev_stage = case.status, case.current_stage
    case.status = CASE_STATUS_FILED
    case.current_stage = STAGE_LAWYER
    db.add(
        CaseStatusUpdate(
            case_id=case.id,
            action_type="court_filed",
            from_status=prev_status,
            to_status=case.status,
            from_stage=prev_stage,
            to_stage=case.current_stage,
            actor_id=user.id,
            comment=(
                f"Filed: police #{payload.police_case_no or '-'}, "
                f"court #{payload.court_case_no or '-'}"
            ).strip(),
        )
    )
    db.commit()
    db.refresh(filing)
    audit_service.record_event(
        db,
        action="court_filed",
        entity_type="Case",
        entity_id=case.id,
        summary=f"Court filing recorded for {case.case_no}",
        after={
            "police_case_no": filing.police_case_no,
            "court_case_no": filing.court_case_no,
            "filed_court": filing.filed_court,
            "filed_date": str(filing.filed_date) if filing.filed_date else None,
        },
        actor=user,
        commit=True,
    )
    from app.services import notification_service

    notification_service.on_court_filed(db, case, user)
    db.commit()
    return filing


def update_court_filing(
    db: Session, case: Case, user: User, payload: CourtFilingUpdate
) -> CourtFiling:
    filing = db.query(CourtFiling).filter(CourtFiling.case_id == case.id).first()
    if not filing:
        raise CourtError("No court filing exists for this case")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(filing, k, v)
    db.commit()
    db.refresh(filing)
    return filing


# ----------------- Hearings -----------------
def create_hearing(db: Session, case: Case, user: User, payload: HearingCreate) -> Hearing:
    if case.status not in (CASE_STATUS_APPROVED, CASE_STATUS_FILED):
        raise CourtError("Hearings can only be added after the case has been approved")
    h = Hearing(case_id=case.id, recorded_by_id=user.id, **payload.model_dump())
    db.add(h)
    db.add(
        CaseStatusUpdate(
            case_id=case.id,
            action_type=ACTION_COMMENT,
            from_status=case.status,
            to_status=case.status,
            from_stage=case.current_stage,
            to_stage=case.current_stage,
            actor_id=user.id,
            comment=f"Hearing recorded ({payload.hearing_type}) on {payload.hearing_date:%Y-%m-%d}",
        )
    )
    db.commit()
    db.refresh(h)
    audit_service.record_event(
        db,
        action="hearing_added",
        entity_type="Case",
        entity_id=case.id,
        summary=f"Hearing on {payload.hearing_date:%Y-%m-%d} ({payload.hearing_type})",
        after={
            "hearing_id": h.id,
            "hearing_type": h.hearing_type,
            "location": h.location,
            "next_hearing_date": str(h.next_hearing_date) if h.next_hearing_date else None,
        },
        actor=user,
        commit=True,
    )
    return h


def update_hearing(db: Session, hearing: Hearing, payload: HearingUpdate) -> Hearing:
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(hearing, k, v)
    db.commit()
    db.refresh(hearing)
    return hearing


# ----------------- Cash Requests -----------------
def create_cash_request(
    db: Session, case: Case, user: User, payload: CashRequestCreate
) -> CashRequest:
    if case.status not in (CASE_STATUS_APPROVED, CASE_STATUS_FILED):
        raise CourtError(
            "Cash can only be requested for an Approved or Filed case (after Chairman/MD signoff)"
        )
    cr = CashRequest(
        case_id=case.id,
        requested_by_id=user.id,
        requested_at=_utcnow(),
        status=CASH_REQUEST_REQUESTED,
        **payload.model_dump(),
    )
    db.add(cr)
    db.commit()
    db.refresh(cr)
    audit_service.record_event(
        db,
        action="cash_request_created",
        entity_type="CashRequest",
        entity_id=cr.id,
        summary=f"Cash request {cr.amount} for {case.case_no}",
        after={"amount": str(cr.amount), "purpose": cr.purpose, "case_no": case.case_no},
        actor=user,
        commit=True,
    )
    from app.services import notification_service

    notification_service.on_cash_request_created(db, cr, case)
    db.commit()
    return cr


def approve_cash_request(
    db: Session, cr: CashRequest, user: User, comment: str
) -> CashRequest:
    if cr.status != CASH_REQUEST_REQUESTED:
        raise CourtError(f"Cannot approve when status is '{cr.status}'")
    cr.status = CASH_REQUEST_APPROVED
    cr.approved_by_id = user.id
    cr.approved_at = _utcnow()
    cr.approval_comment = comment.strip()
    db.commit()
    db.refresh(cr)
    audit_service.record_event(
        db,
        action="cash_request_approved",
        entity_type="CashRequest",
        entity_id=cr.id,
        summary=f"Approved cash request {cr.amount}",
        before={"status": CASH_REQUEST_REQUESTED},
        after={"status": cr.status, "comment": cr.approval_comment},
        actor=user,
        commit=True,
    )
    from app.services import notification_service

    case = db.get(Case, cr.case_id)
    if case:
        notification_service.on_cash_request_approved(db, cr, case)
        db.commit()
    return cr


def reject_cash_request(
    db: Session, cr: CashRequest, user: User, payload: CashRequestRejectPayload
) -> CashRequest:
    if cr.status != CASH_REQUEST_REQUESTED:
        raise CourtError(f"Cannot reject when status is '{cr.status}'")
    cr.status = CASH_REQUEST_REJECTED
    cr.approved_by_id = user.id
    cr.approved_at = _utcnow()
    cr.approval_comment = payload.comment.strip()
    db.commit()
    db.refresh(cr)
    audit_service.record_event(
        db,
        action="cash_request_rejected",
        entity_type="CashRequest",
        entity_id=cr.id,
        summary=f"Rejected cash request {cr.amount}",
        before={"status": CASH_REQUEST_REQUESTED},
        after={"status": cr.status, "comment": cr.approval_comment},
        actor=user,
        commit=True,
    )
    from app.services import notification_service

    case = db.get(Case, cr.case_id)
    if case:
        notification_service.on_cash_request_rejected(db, cr, case)
        db.commit()
    return cr


def pay_cash_request(
    db: Session, cr: CashRequest, user: User, payload: CashRequestPayPayload
) -> CashRequest:
    if cr.status != CASH_REQUEST_APPROVED:
        raise CourtError("Cash request must be approved before it can be paid")
    cr.status = CASH_REQUEST_PAID
    cr.paid_by_id = user.id
    cr.paid_at = _utcnow()
    cr.payment_reference = payload.payment_reference.strip()
    cr.receipt_attachment_id = payload.receipt_attachment_id
    db.commit()
    db.refresh(cr)
    audit_service.record_event(
        db,
        action="cash_request_paid",
        entity_type="CashRequest",
        entity_id=cr.id,
        summary=f"Paid cash request {cr.amount} (ref: {cr.payment_reference or '-'})",
        before={"status": CASH_REQUEST_APPROVED},
        after={
            "status": cr.status,
            "payment_reference": cr.payment_reference,
            "receipt_attachment_id": cr.receipt_attachment_id,
        },
        actor=user,
        commit=True,
    )
    from app.services import notification_service

    case = db.get(Case, cr.case_id)
    if case:
        notification_service.on_cash_request_paid(db, cr, case)
        db.commit()
    return cr


def spend_summary(db: Session, case_id: int) -> dict[str, object]:
    rows = (
        db.query(CashRequest.status, func.coalesce(func.sum(CashRequest.amount), 0))
        .filter(CashRequest.case_id == case_id)
        .group_by(CashRequest.status)
        .all()
    )
    by_status = {s: Decimal(str(v)) for s, v in rows}
    total_requested = sum(by_status.values(), Decimal("0"))
    return {
        "total_requested": total_requested,
        "total_approved": by_status.get(CASH_REQUEST_APPROVED, Decimal("0"))
        + by_status.get(CASH_REQUEST_PAID, Decimal("0")),
        "total_paid": by_status.get(CASH_REQUEST_PAID, Decimal("0")),
        "open_count": db.query(CashRequest)
        .filter(
            CashRequest.case_id == case_id,
            CashRequest.status.in_([CASH_REQUEST_REQUESTED, CASH_REQUEST_APPROVED]),
        )
        .count(),
    }

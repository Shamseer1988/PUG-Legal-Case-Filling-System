"""Phase 4 endpoints: court filing, hearings, cash requests, calendar."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_permission
from app.core.permissions import (
    CASES_FILE,
    CASES_READ,
    EXPENSES_APPROVE,
    EXPENSES_PAY,
    EXPENSES_REQUEST,
    HEARINGS_WRITE,
)
from app.db.session import get_db
from app.models.case import Case
from app.models.court import CashRequest, CourtFiling, Hearing
from app.models.user import User
from app.schemas.court import (
    CalendarHearing,
    CaseSpendSummary,
    CashRequestApprovePayload,
    CashRequestCreate,
    CashRequestPayPayload,
    CashRequestRead,
    CashRequestRejectPayload,
    CourtFilingCreate,
    CourtFilingRead,
    CourtFilingUpdate,
    HearingCreate,
    HearingRead,
    HearingUpdate,
)
from app.services import court_service

cases_router = APIRouter(prefix="/cases", tags=["court"])
cash_router = APIRouter(prefix="/cash-requests", tags=["court"])
hearings_router = APIRouter(prefix="/hearings", tags=["court"])


def _scoped_case_or_404(db: Session, user: User, case_id: int) -> Case:
    q = db.query(Case)
    if not user.is_super:
        perms = user.role.permissions if user.role else []
        if "*" not in perms and user.divisions:
            q = q.filter(Case.division_id.in_([d.id for d in user.divisions]))
    case = q.filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


def _name(db: Session, uid: int | None) -> str:
    if not uid:
        return ""
    u = db.get(User, uid)
    return u.full_name if u else ""


def _filing_to_read(db: Session, f: CourtFiling) -> CourtFilingRead:
    return CourtFilingRead(
        id=f.id,
        case_id=f.case_id,
        police_case_no=f.police_case_no,
        court_case_no=f.court_case_no,
        filed_court=f.filed_court,
        filed_date=f.filed_date,
        acknowledgment_attachment_id=f.acknowledgment_attachment_id,
        notes=f.notes,
        filed_by_id=f.filed_by_id,
        filed_by_name=_name(db, f.filed_by_id),
        created_at=f.created_at,
    )


def _hearing_to_read(db: Session, h: Hearing) -> HearingRead:
    return HearingRead(
        id=h.id,
        case_id=h.case_id,
        hearing_date=h.hearing_date,
        location=h.location,
        hearing_type=h.hearing_type,
        outcome=h.outcome,
        next_hearing_date=h.next_hearing_date,
        attachment_id=h.attachment_id,
        recorded_by_id=h.recorded_by_id,
        recorded_by_name=_name(db, h.recorded_by_id),
        created_at=h.created_at,
    )


def _cr_to_read(db: Session, cr: CashRequest) -> CashRequestRead:
    case = db.get(Case, cr.case_id)
    return CashRequestRead(
        id=cr.id,
        case_id=cr.case_id,
        case_no=case.case_no if case else "",
        amount=cr.amount,
        purpose=cr.purpose,
        status=cr.status,
        requested_by_id=cr.requested_by_id,
        requested_by_name=_name(db, cr.requested_by_id),
        requested_at=cr.requested_at,
        approved_by_id=cr.approved_by_id,
        approved_by_name=_name(db, cr.approved_by_id),
        approved_at=cr.approved_at,
        approval_comment=cr.approval_comment,
        paid_by_id=cr.paid_by_id,
        paid_by_name=_name(db, cr.paid_by_id),
        paid_at=cr.paid_at,
        payment_reference=cr.payment_reference,
        receipt_attachment_id=cr.receipt_attachment_id,
    )


# ===================== Court Filing =====================
@cases_router.get("/{case_id}/court-filing", response_model=CourtFilingRead | None)
def get_court_filing(
    case_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(CASES_READ)),
):
    case = _scoped_case_or_404(db, user, case_id)
    f = db.query(CourtFiling).filter(CourtFiling.case_id == case.id).first()
    return _filing_to_read(db, f) if f else None


@cases_router.post(
    "/{case_id}/court-filing", response_model=CourtFilingRead, status_code=status.HTTP_201_CREATED
)
def create_court_filing(
    case_id: int,
    payload: CourtFilingCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(CASES_FILE)),
):
    case = _scoped_case_or_404(db, user, case_id)
    try:
        f = court_service.create_court_filing(db, case, user, payload)
    except court_service.CourtError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _filing_to_read(db, f)


@cases_router.patch("/{case_id}/court-filing", response_model=CourtFilingRead)
def update_court_filing(
    case_id: int,
    payload: CourtFilingUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(CASES_FILE)),
):
    case = _scoped_case_or_404(db, user, case_id)
    try:
        f = court_service.update_court_filing(db, case, user, payload)
    except court_service.CourtError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _filing_to_read(db, f)


# ===================== Hearings =====================
@cases_router.get("/{case_id}/hearings", response_model=list[HearingRead])
def list_hearings(
    case_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(CASES_READ)),
):
    case = _scoped_case_or_404(db, user, case_id)
    rows = (
        db.query(Hearing)
        .filter(Hearing.case_id == case.id)
        .order_by(Hearing.hearing_date.desc())
        .all()
    )
    return [_hearing_to_read(db, h) for h in rows]


@cases_router.post(
    "/{case_id}/hearings", response_model=HearingRead, status_code=status.HTTP_201_CREATED
)
def create_hearing(
    case_id: int,
    payload: HearingCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(HEARINGS_WRITE)),
):
    case = _scoped_case_or_404(db, user, case_id)
    try:
        h = court_service.create_hearing(db, case, user, payload)
    except court_service.CourtError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _hearing_to_read(db, h)


@cases_router.patch("/{case_id}/hearings/{hearing_id}", response_model=HearingRead)
def update_hearing(
    case_id: int,
    hearing_id: int,
    payload: HearingUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(HEARINGS_WRITE)),
):
    case = _scoped_case_or_404(db, user, case_id)
    h = db.get(Hearing, hearing_id)
    if not h or h.case_id != case.id:
        raise HTTPException(status_code=404, detail="Hearing not found")
    h = court_service.update_hearing(db, h, payload)
    return _hearing_to_read(db, h)


@cases_router.delete(
    "/{case_id}/hearings/{hearing_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_hearing(
    case_id: int,
    hearing_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(HEARINGS_WRITE)),
):
    case = _scoped_case_or_404(db, user, case_id)
    h = db.get(Hearing, hearing_id)
    if not h or h.case_id != case.id:
        raise HTTPException(status_code=404, detail="Hearing not found")
    db.delete(h)
    db.commit()


# ===================== Cash Requests =====================
@cases_router.get("/{case_id}/cash-requests", response_model=list[CashRequestRead])
def list_case_cash_requests(
    case_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(CASES_READ)),
):
    case = _scoped_case_or_404(db, user, case_id)
    rows = (
        db.query(CashRequest)
        .filter(CashRequest.case_id == case.id)
        .order_by(CashRequest.id.desc())
        .all()
    )
    return [_cr_to_read(db, r) for r in rows]


@cases_router.get("/{case_id}/spend-summary", response_model=CaseSpendSummary)
def get_spend_summary(
    case_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(CASES_READ)),
):
    case = _scoped_case_or_404(db, user, case_id)
    return CaseSpendSummary(**court_service.spend_summary(db, case.id))


@cases_router.post(
    "/{case_id}/cash-requests",
    response_model=CashRequestRead,
    status_code=status.HTTP_201_CREATED,
)
def create_case_cash_request(
    case_id: int,
    payload: CashRequestCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(EXPENSES_REQUEST)),
):
    case = _scoped_case_or_404(db, user, case_id)
    try:
        cr = court_service.create_cash_request(db, case, user, payload)
    except court_service.CourtError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _cr_to_read(db, cr)


def _cr_or_404(db: Session, user: User, cr_id: int) -> CashRequest:
    cr = db.get(CashRequest, cr_id)
    if not cr:
        raise HTTPException(status_code=404, detail="Cash request not found")
    # Division scope via the parent case
    _scoped_case_or_404(db, user, cr.case_id)
    return cr


@cash_router.get("", response_model=list[CashRequestRead])
def list_cash_requests_inbox(
    only: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Cross-case cash request inbox. ``only`` filters by status."""
    q = db.query(CashRequest)
    if only:
        q = q.filter(CashRequest.status == only)
    if not user.is_super:
        perms = user.role.permissions if user.role else []
        if "*" not in perms and user.divisions:
            div_ids = [d.id for d in user.divisions]
            q = q.join(Case, Case.id == CashRequest.case_id).filter(Case.division_id.in_(div_ids))
    return [_cr_to_read(db, r) for r in q.order_by(CashRequest.id.desc()).limit(500).all()]


@cash_router.post("/{cr_id}/approve", response_model=CashRequestRead)
def approve_cash_request(
    cr_id: int,
    payload: CashRequestApprovePayload,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(EXPENSES_APPROVE)),
):
    cr = _cr_or_404(db, user, cr_id)
    try:
        cr = court_service.approve_cash_request(db, cr, user, payload.comment)
    except court_service.CourtError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _cr_to_read(db, cr)


@cash_router.post("/{cr_id}/reject", response_model=CashRequestRead)
def reject_cash_request(
    cr_id: int,
    payload: CashRequestRejectPayload,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(EXPENSES_APPROVE)),
):
    cr = _cr_or_404(db, user, cr_id)
    try:
        cr = court_service.reject_cash_request(db, cr, user, payload)
    except court_service.CourtError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _cr_to_read(db, cr)


@cash_router.post("/{cr_id}/pay", response_model=CashRequestRead)
def pay_cash_request(
    cr_id: int,
    payload: CashRequestPayPayload,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(EXPENSES_PAY)),
):
    cr = _cr_or_404(db, user, cr_id)
    try:
        cr = court_service.pay_cash_request(db, cr, user, payload)
    except court_service.CourtError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _cr_to_read(db, cr)


# ===================== Calendar =====================
@hearings_router.get("/calendar", response_model=list[CalendarHearing])
def calendar(
    days: int = 60,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(CASES_READ)),
):
    """Hearings + next hearings within the upcoming N days."""
    now = datetime.now(timezone.utc)
    end = now + timedelta(days=days)
    q = db.query(Hearing, Case).join(Case, Case.id == Hearing.case_id)
    if not user.is_super:
        perms = user.role.permissions if user.role else []
        if "*" not in perms and user.divisions:
            q = q.filter(Case.division_id.in_([d.id for d in user.divisions]))
    q = q.filter(
        (Hearing.hearing_date >= now) & (Hearing.hearing_date <= end)
        | (
            (Hearing.next_hearing_date.isnot(None))
            & (Hearing.next_hearing_date >= now)
            & (Hearing.next_hearing_date <= end)
        )
    )
    out: list[CalendarHearing] = []
    seen: set[tuple[int, str]] = set()
    for h, c in q.all():
        # primary hearing
        if now <= h.hearing_date <= end and (h.id, "h") not in seen:
            out.append(
                CalendarHearing(
                    id=h.id,
                    case_id=c.id,
                    case_no=c.case_no,
                    hearing_date=h.hearing_date,
                    location=h.location,
                    hearing_type=h.hearing_type,
                    next_hearing_date=h.next_hearing_date,
                )
            )
            seen.add((h.id, "h"))
        # next hearing
        if (
            h.next_hearing_date
            and now <= h.next_hearing_date <= end
            and (h.id, "n") not in seen
        ):
            out.append(
                CalendarHearing(
                    id=h.id,
                    case_id=c.id,
                    case_no=c.case_no,
                    hearing_date=h.next_hearing_date,
                    location=h.location,
                    hearing_type=f"Next: {h.hearing_type}",
                    next_hearing_date=None,
                )
            )
            seen.add((h.id, "n"))
    out.sort(key=lambda x: x.hearing_date)
    return out

"""Executive dashboard endpoints.

Every query is role-scoped using the same rule as the main case
list: super and ``*`` permission see all divisions; everyone else
sees only their mapped divisions.
"""

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.data_scope import allowed_division_ids
from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.case import Case
from app.models.court import CASH_REQUEST_PAID, CashRequest, Hearing
from app.models.masters import Division
from app.models.user import User
from app.schemas.dashboard import (
    Alert,
    DivisionRow,
    Kpis,
    StatusCount,
    TrendPoint,
    UpcomingHearing,
)
from app.services import workflow_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _scope_cases(db: Session, user: User):
    q = db.query(Case)
    allowed = allowed_division_ids(user)
    if allowed is None:
        return q
    if allowed:
        q = q.filter(Case.division_id.in_(allowed))
    return q


def _scope_cash(db: Session, user: User):
    q = db.query(CashRequest).join(Case, Case.id == CashRequest.case_id)
    allowed = allowed_division_ids(user)
    if allowed is None:
        return q
    if allowed:
        q = q.filter(Case.division_id.in_(allowed))
    return q


def _scope_hearings(db: Session, user: User):
    q = db.query(Hearing, Case).join(Case, Case.id == Hearing.case_id)
    allowed = allowed_division_ids(user)
    if allowed is None:
        return q
    if allowed:
        q = q.filter(Case.division_id.in_(allowed))
    return q


# ===================== KPIs =====================
@router.get("/kpis", response_model=Kpis)
def get_kpis(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Kpis:
    cases = _scope_cases(db, user).all()
    total = len(cases)
    open_ = sum(1 for c in cases if c.status not in ("Closed", "Rejected"))
    appfil = sum(1 for c in cases if c.status in ("Approved", "Filed"))
    rejected = sum(1 for c in cases if c.status == "Rejected")
    closed = sum(1 for c in cases if c.status == "Closed")
    # Drafts are private to the Accountant and shouldn't show up in the
    # "total legal amount" headline KPI - only Submitted-and-onwards
    # cases carry committed business value.
    total_amount = sum(
        (
            c.legal_filing_amount or Decimal("0")
            for c in cases
            if c.status != "Draft"
        ),
        Decimal("0"),
    )

    paid = (
        _scope_cash(db, user)
        .filter(CashRequest.status == CASH_REQUEST_PAID)
        .with_entities(func.coalesce(func.sum(CashRequest.amount), 0))
        .scalar()
    )

    now = datetime.now(timezone.utc)

    def _is_overdue(due: datetime | None) -> bool:
        if not due:
            return False
        # SQLite hands back naive datetimes; assume UTC so the
        # comparison with the aware ``now`` doesn't raise.
        if due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)
        return due < now

    overdue = sum(
        1
        for c in cases
        if _is_overdue(c.sla_due_at)
        and c.status in ("Submitted", "In Review")
    )

    inbox = workflow_service.inbox_for(db, user)

    return Kpis(
        total_cases=total,
        open_cases=open_,
        approved_or_filed=appfil,
        rejected_cases=rejected,
        closed_cases=closed,
        total_legal_amount=total_amount,
        total_recovered=Decimal(str(paid or 0)),
        pending_my_inbox=len(inbox),
        overdue_count=overdue,
    )


# ===================== Status breakdown =====================
@router.get("/status-breakdown", response_model=list[StatusCount])
def status_breakdown(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[StatusCount]:
    rows = (
        _scope_cases(db, user)
        .with_entities(Case.status, func.count(Case.id))
        .group_by(Case.status)
        .order_by(Case.status)
        .all()
    )
    return [StatusCount(status=s, count=int(n)) for s, n in rows]


# ===================== Trend =====================
@router.get("/trend", response_model=list[TrendPoint])
def monthly_trend(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[TrendPoint]:
    today = date.today()
    months: list[str] = []
    cursor = date(today.year, today.month, 1)
    for _ in range(12):
        months.append(f"{cursor.year:04d}-{cursor.month:02d}")
        # step back one month
        if cursor.month == 1:
            cursor = date(cursor.year - 1, 12, 1)
        else:
            cursor = date(cursor.year, cursor.month - 1, 1)
    months.reverse()

    created: dict[str, int] = defaultdict(int)
    approved: dict[str, int] = defaultdict(int)
    cases = _scope_cases(db, user).all()
    for c in cases:
        if c.created_at:
            key = f"{c.created_at.year:04d}-{c.created_at.month:02d}"
            if key in months:
                created[key] += 1
        if c.status in ("Approved", "Filed") and c.submitted_at:
            key = f"{c.submitted_at.year:04d}-{c.submitted_at.month:02d}"
            if key in months:
                approved[key] += 1

    return [
        TrendPoint(
            month=m,
            cases_created=created.get(m, 0),
            cases_approved=approved.get(m, 0),
        )
        for m in months
    ]


# ===================== Division heatmap =====================
@router.get("/division-heatmap", response_model=list[DivisionRow])
def division_heatmap(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[DivisionRow]:
    divs = {d.id: d.name for d in db.query(Division).all()}
    cases = _scope_cases(db, user).all()

    grouped: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    totals: dict[int, int] = defaultdict(int)
    amount: dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
    for c in cases:
        grouped[c.division_id][c.status] += 1
        totals[c.division_id] += 1
        amount[c.division_id] += c.legal_filing_amount or Decimal("0")

    out: list[DivisionRow] = []
    for div_id, name in divs.items():
        if div_id not in totals:
            continue
        out.append(
            DivisionRow(
                division_id=div_id,
                division_name=name,
                total=totals[div_id],
                by_status=dict(grouped[div_id]),
                total_legal_amount=amount[div_id],
            )
        )
    out.sort(key=lambda r: -r.total)
    return out


# ===================== Upcoming hearings =====================
@router.get("/upcoming-hearings", response_model=list[UpcomingHearing])
def upcoming_hearings(
    days: int = 30,
    limit: int = 10,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[UpcomingHearing]:
    now = datetime.now(timezone.utc)
    end = now + timedelta(days=days)
    rows = _scope_hearings(db, user).filter(
        (Hearing.hearing_date >= now) & (Hearing.hearing_date <= end)
        | (
            (Hearing.next_hearing_date.isnot(None))
            & (Hearing.next_hearing_date >= now)
            & (Hearing.next_hearing_date <= end)
        )
    ).all()
    out: list[UpcomingHearing] = []
    seen: set[tuple[int, str]] = set()
    for h, c in rows:
        for is_next, dt, type_label in (
            (False, h.hearing_date, h.hearing_type),
            (True, h.next_hearing_date, f"Next: {h.hearing_type}"),
        ):
            if not dt or dt < now or dt > end:
                continue
            tag = (h.id, "n" if is_next else "h")
            if tag in seen:
                continue
            seen.add(tag)
            out.append(
                UpcomingHearing(
                    case_id=c.id,
                    case_no=c.case_no,
                    hearing_date=dt.isoformat(),
                    hearing_type=type_label,
                    location=h.location or "",
                    days_until=max((dt - now).days, 0),
                )
            )
    out.sort(key=lambda x: x.hearing_date)
    return out[:limit]


# ===================== Alerts =====================
@router.get("/alerts", response_model=list[Alert])
def alerts(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Alert]:
    now = datetime.now(timezone.utc)
    cases = _scope_cases(db, user).all()
    out: list[Alert] = []

    overdue = [
        c
        for c in cases
        if c.sla_due_at
        and c.sla_due_at < now
        and c.status in ("Submitted", "In Review")
    ]
    if overdue:
        out.append(
            Alert(
                severity="danger",
                title=f"{len(overdue)} cases past SLA",
                detail="Approval stages have exceeded their configured hours.",
                link="/approvals",
                count=len(overdue),
            )
        )

    stuck = [
        c
        for c in cases
        if c.stage_entered_at
        and (now - c.stage_entered_at) > timedelta(days=7)
        and c.status in ("Submitted", "In Review", "Clarification Requested")
    ]
    if stuck:
        out.append(
            Alert(
                severity="warn",
                title=f"{len(stuck)} cases stuck > 7 days at the same stage",
                detail="Consider escalating or following up with the assigned signatory.",
                link="/approvals",
                count=len(stuck),
            )
        )

    clarif = [c for c in cases if c.status == "Clarification Requested"]
    if clarif:
        out.append(
            Alert(
                severity="warn",
                title=f"{len(clarif)} cases awaiting clarification",
                detail="The accountant has not yet resubmitted.",
                link="/cases?status=Clarification%20Requested",
                count=len(clarif),
            )
        )

    return out

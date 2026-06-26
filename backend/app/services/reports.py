"""Report registry + per-report query functions.

Each report function takes (db, user, params) and returns a dict shaped
like ``{title, subtitle, columns, rows}`` consumed by both JSON and the
Excel / PDF renderers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Callable

from sqlalchemy import false as sa_false, func
from sqlalchemy.orm import Session

from app.models.case import Case, CaseAttachment, CaseStatusUpdate, Cheque
from app.models.closure import CaseClosure
from app.models.court import CASH_REQUEST_PAID, CashRequest, CourtFiling, Hearing
from app.models.masters import Customer, Division
from app.models.user import User


# ===================== descriptor types =====================
@dataclass(frozen=True)
class ParamDef:
    name: str
    type: str  # text | date | select
    label: str
    options: tuple[str, ...] | None = None
    required: bool = False


@dataclass(frozen=True)
class ReportDef:
    key: str
    name: str
    description: str
    permission: str  # required permission to run
    params: tuple[ParamDef, ...]
    query: Callable[[Session, User, dict[str, Any]], dict[str, Any]]
    landscape: bool = True


# ===================== helpers =====================
def _user_can_see_all_divisions(user: User) -> bool:
    """True when the user has unrestricted division access.

    Super-users and anyone with the global ``*`` permission bypass
    division scoping; everyone else is filtered to their assigned
    divisions (and gets an *empty* result when they have none — never
    the full company dataset).
    """
    if user.is_super:
        return True
    perms = user.role.permissions if user.role else []
    return "*" in perms


def _scope_cases(db: Session, user: User):
    q = db.query(Case)
    if _user_can_see_all_divisions(user):
        return q
    if not user.divisions:
        # No divisions => no visibility. Force an empty result rather
        # than silently dropping the filter (which would leak the
        # entire dataset to a misconfigured account).
        return q.filter(sa_false())
    return q.filter(Case.division_id.in_([d.id for d in user.divisions]))


def _apply_common_filters(q, params: dict[str, Any]):
    """Standard ``division_id`` + ``status`` filters supported by every report."""
    div = params.get("division_id")
    if div:
        try:
            q = q.filter(Case.division_id == int(div))
        except (TypeError, ValueError):
            pass
    status = (params.get("status") or "").strip()
    if status:
        q = q.filter(Case.status == status)
    return q


def _customer_map(db: Session) -> dict[int, str]:
    return {c.id: c.name for c in db.query(Customer).all()}


def _division_map(db: Session) -> dict[int, str]:
    return {d.id: d.name for d in db.query(Division).all()}


def _parse_date(s: Any) -> date | None:
    if not s:
        return None
    if isinstance(s, date):
        return s
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


# ===================== Case Register =====================
def case_register(db: Session, user: User, params: dict[str, Any]) -> dict[str, Any]:
    date_from = _parse_date(params.get("date_from"))
    date_to = _parse_date(params.get("date_to"))

    q = _apply_common_filters(_scope_cases(db, user), params)
    if date_from:
        q = q.filter(Case.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        q = q.filter(Case.created_at <= datetime.combine(date_to, datetime.max.time()))
    cases = q.order_by(Case.id.desc()).all()

    customers = _customer_map(db)
    divisions = _division_map(db)

    rows: list[dict[str, Any]] = []
    for c in cases:
        rows.append(
            {
                "case_no": c.case_no,
                "customer": customers.get(c.customer_id, ""),
                "division": divisions.get(c.division_id, ""),
                "type": "Criminal" if c.is_criminal else "Civil" if c.is_civil else "-",
                "status": c.status,
                "stage": c.current_stage,
                "legal_amount": c.legal_filing_amount,
                "actual_due": c.actual_due_amount,
                "created_at": c.created_at,
                "submitted_at": c.submitted_at,
            }
        )

    return {
        "title": "Case Register",
        "subtitle": "All cases with applied filters",
        "columns": [
            {"key": "case_no", "label": "Case No", "type": "text"},
            {"key": "customer", "label": "Customer", "type": "text"},
            {"key": "division", "label": "Division", "type": "text"},
            {"key": "type", "label": "Type", "type": "text"},
            {"key": "status", "label": "Status", "type": "text"},
            {"key": "stage", "label": "Stage", "type": "text"},
            {"key": "actual_due", "label": "Actual Due", "type": "number"},
            {"key": "legal_amount", "label": "Legal Amount", "type": "number"},
            {"key": "created_at", "label": "Created", "type": "datetime"},
            {"key": "submitted_at", "label": "Submitted", "type": "datetime"},
        ],
        "rows": rows,
    }


# ===================== Status Summary =====================
def status_summary(db: Session, user: User, params: dict[str, Any]) -> dict[str, Any]:
    q = _apply_common_filters(_scope_cases(db, user), params)
    counts = (
        q.with_entities(
            Case.status,
            func.count(Case.id),
            func.coalesce(func.sum(Case.legal_filing_amount), 0),
        )
        .group_by(Case.status)
        .order_by(Case.status)
        .all()
    )
    rows = [
        {"status": s, "case_count": int(n), "total_legal_amount": Decimal(str(amt or 0))}
        for s, n, amt in counts
    ]
    return {
        "title": "Status Summary",
        "subtitle": "Cases grouped by status",
        "columns": [
            {"key": "status", "label": "Status", "type": "text"},
            {"key": "case_count", "label": "Cases", "type": "int"},
            {"key": "total_legal_amount", "label": "Total Legal Amount", "type": "number"},
        ],
        "rows": rows,
    }


# ===================== Aging Report =====================
def aging_report(db: Session, user: User, params: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    buckets = [
        ("0-30 days", now - timedelta(days=30), now),
        ("31-60 days", now - timedelta(days=60), now - timedelta(days=30)),
        ("61-90 days", now - timedelta(days=90), now - timedelta(days=60)),
        ("91+ days", None, now - timedelta(days=90)),
    ]
    rows: list[dict[str, Any]] = []
    for label, start, end in buckets:
        q = _apply_common_filters(_scope_cases(db, user), params)
        if start:
            # `>=` so a case exactly at the boundary (e.g. 30 days old)
            # lands in the lower bucket instead of slipping into the
            # next one.
            q = q.filter(Case.created_at >= start)
        if end:
            q = q.filter(Case.created_at < end)
        # not closed (unless user explicitly filtered for one of those)
        if not (params.get("status") or "").strip():
            q = q.filter(Case.status.notin_(["Closed", "Rejected"]))
        cases = q.all()
        rows.append(
            {
                "bucket": label,
                "case_count": len(cases),
                "total_amount": sum(
                    (c.legal_filing_amount or Decimal("0") for c in cases), Decimal("0")
                ),
            }
        )
    return {
        "title": "Aging Report",
        "subtitle": "Open cases bucketed by age (not Closed/Rejected)",
        "columns": [
            {"key": "bucket", "label": "Age Bucket", "type": "text"},
            {"key": "case_count", "label": "Open Cases", "type": "int"},
            {"key": "total_amount", "label": "Total Legal Amount", "type": "number"},
        ],
        "rows": rows,
    }


# ===================== Division-wise Summary =====================
def division_summary(db: Session, user: User, params: dict[str, Any]) -> dict[str, Any]:
    # One GROUP BY instead of one query per division. Counts are
    # produced server-side with conditional sums, then joined to the
    # division name map in Python.
    from sqlalchemy import case as sa_case

    divisions = _division_map(db)

    base = _apply_common_filters(_scope_cases(db, user), params)
    is_open = sa_case((Case.status.notin_(("Closed", "Rejected")), 1), else_=0)
    is_done = sa_case((Case.status.in_(("Approved", "Filed")), 1), else_=0)
    grouped = (
        base.with_entities(
            Case.division_id,
            func.count(Case.id).label("total"),
            func.coalesce(func.sum(is_open), 0).label("open"),
            func.coalesce(func.sum(is_done), 0).label("done"),
            func.coalesce(func.sum(Case.legal_filing_amount), 0).label("amount"),
        )
        .group_by(Case.division_id)
        .all()
    )

    # When a single division is requested, narrow the rendered output
    # (the SQL above already honours any division filter applied via
    # _apply_common_filters, so this is just a safety net).
    requested_div = params.get("division_id")
    requested_id: int | None = None
    if requested_div:
        try:
            requested_id = int(requested_div)
        except (TypeError, ValueError):
            requested_id = None

    rows: list[dict[str, Any]] = []
    for div_id, total, open_, done, amount in grouped:
        if div_id is None:
            continue
        if requested_id is not None and div_id != requested_id:
            continue
        rows.append(
            {
                "division": divisions.get(div_id, ""),
                "total_cases": int(total or 0),
                "open_cases": int(open_ or 0),
                "approved_cases": int(done or 0),
                "total_legal_amount": Decimal(str(amount or 0)),
            }
        )
    rows.sort(key=lambda r: -float(r["total_legal_amount"]))
    return {
        "title": "Division-wise Summary",
        "subtitle": "Case volume and value by division",
        "columns": [
            {"key": "division", "label": "Division", "type": "text"},
            {"key": "total_cases", "label": "Total", "type": "int"},
            {"key": "open_cases", "label": "Open", "type": "int"},
            {"key": "approved_cases", "label": "Approved / Filed", "type": "int"},
            {"key": "total_legal_amount", "label": "Total Legal Amount", "type": "number"},
        ],
        "rows": rows,
    }


# ===================== Hearing Schedule =====================
def hearing_schedule(db: Session, user: User, params: dict[str, Any]) -> dict[str, Any]:
    days = int(params.get("days") or 60)
    now = datetime.now(timezone.utc)
    end = now + timedelta(days=days)
    q = (
        db.query(Hearing, Case)
        .join(Case, Case.id == Hearing.case_id)
        .order_by(Hearing.hearing_date.asc())
    )
    if not _user_can_see_all_divisions(user):
        if not user.divisions:
            q = q.filter(sa_false())
        else:
            q = q.filter(Case.division_id.in_([d.id for d in user.divisions]))
    div = params.get("division_id")
    if div:
        try:
            q = q.filter(Case.division_id == int(div))
        except (TypeError, ValueError):
            pass
    cstatus = (params.get("status") or "").strip()
    if cstatus:
        q = q.filter(Case.status == cstatus)
    q = q.filter(
        (Hearing.hearing_date >= now) & (Hearing.hearing_date <= end)
        | (
            (Hearing.next_hearing_date.isnot(None))
            & (Hearing.next_hearing_date >= now)
            & (Hearing.next_hearing_date <= end)
        )
    )
    rows: list[dict[str, Any]] = []
    for h, c in q.all():
        if now <= h.hearing_date <= end:
            rows.append(
                {
                    "hearing_date": h.hearing_date,
                    "case_no": c.case_no,
                    "type": h.hearing_type,
                    "location": h.location,
                    "outcome": h.outcome,
                }
            )
        if h.next_hearing_date and now <= h.next_hearing_date <= end:
            rows.append(
                {
                    "hearing_date": h.next_hearing_date,
                    "case_no": c.case_no,
                    "type": f"Next: {h.hearing_type}",
                    "location": h.location,
                    "outcome": "",
                }
            )
    rows.sort(key=lambda r: r["hearing_date"])
    return {
        "title": "Hearing Schedule",
        "subtitle": f"Upcoming hearings in next {days} days",
        "columns": [
            {"key": "hearing_date", "label": "Date / Time", "type": "datetime"},
            {"key": "case_no", "label": "Case No", "type": "text"},
            {"key": "type", "label": "Type", "type": "text"},
            {"key": "location", "label": "Location", "type": "text"},
            {"key": "outcome", "label": "Outcome", "type": "text"},
        ],
        "rows": rows,
    }


# ===================== Expense Report =====================
def expense_report(db: Session, user: User, params: dict[str, Any]) -> dict[str, Any]:
    only_paid = (params.get("only_paid") or "true").lower() != "false"
    q = (
        db.query(CashRequest, Case)
        .join(Case, Case.id == CashRequest.case_id)
        .order_by(CashRequest.id.desc())
    )
    if not _user_can_see_all_divisions(user):
        if not user.divisions:
            q = q.filter(sa_false())
        else:
            q = q.filter(Case.division_id.in_([d.id for d in user.divisions]))
    div = params.get("division_id")
    if div:
        try:
            q = q.filter(Case.division_id == int(div))
        except (TypeError, ValueError):
            pass
    cstatus = (params.get("status") or "").strip()
    if cstatus:
        q = q.filter(Case.status == cstatus)
    if only_paid:
        q = q.filter(CashRequest.status == CASH_REQUEST_PAID)
    rows: list[dict[str, Any]] = []
    for cr, c in q.all():
        rows.append(
            {
                "case_no": c.case_no,
                "amount": cr.amount,
                "purpose": cr.purpose,
                "status": cr.status,
                "paid_at": cr.paid_at,
                "payment_reference": cr.payment_reference,
            }
        )
    total = sum(
        (r["amount"] for r in rows if r["status"] == CASH_REQUEST_PAID),
        Decimal("0"),
    )
    return {
        "title": "Expense Report",
        "subtitle": f"Total paid: {total:,.2f}",
        "columns": [
            {"key": "case_no", "label": "Case No", "type": "text"},
            {"key": "amount", "label": "Amount", "type": "number"},
            {"key": "purpose", "label": "Purpose", "type": "text"},
            {"key": "status", "label": "Status", "type": "text"},
            {"key": "paid_at", "label": "Paid At", "type": "datetime"},
            {"key": "payment_reference", "label": "Reference", "type": "text"},
        ],
        "rows": rows,
    }


# ===================== Case Cash Flow =====================
def case_cash_flow(db: Session, user: User, params: dict[str, Any]) -> dict[str, Any]:
    """Lifecycle of one case: every workflow event, cheque, cash request
    and the closure - in one chronological table. Each row carries
    ``attachment_id`` and ``attachment_name`` where applicable so the UI
    can deep-link.
    """
    case_no = (params.get("case_no") or "").strip()
    if not case_no:
        raise ValueError("case_no is required for the Case Cash Flow report")

    q = _scope_cases(db, user).filter(Case.case_no == case_no)
    case = q.first()
    if not case:
        return {
            "title": f"Cash Flow - {case_no}",
            "subtitle": "Case not found or out of your scope.",
            "columns": [],
            "rows": [],
            "case": None,
            "attachments": [],
        }

    actors = {
        u.id: u.full_name
        for u in db.query(User).filter(
            User.id.in_(
                {t.actor_id for t in case.timeline}
                | {case.created_by_id}
            )
        ).all()
    }

    rows: list[dict[str, Any]] = []
    # 1. Case creation
    rows.append(
        {
            "when": case.created_at,
            "phase": "Creation",
            "event": "Case created",
            "actor": actors.get(case.created_by_id, ""),
            "amount": float(case.legal_filing_amount or 0),
            "command": case.commands or "",
            "attachment_id": None,
            "attachment_name": "",
        }
    )

    # 2. Workflow timeline
    for t in case.timeline:
        rows.append(
            {
                "when": t.created_at,
                "phase": "Workflow",
                "event": f"{t.action_type}: {t.from_stage} -> {t.to_stage}",
                "actor": actors.get(t.actor_id, ""),
                "amount": 0,
                "command": t.comment or "",
                "attachment_id": None,
                "attachment_name": "",
            }
        )

    # 3. Cheques recorded on the case
    for ch in case.cheques:
        rows.append(
            {
                "when": ch.created_at,
                "phase": "Cheque",
                "event": f"Cheque {ch.cheque_number} ({ch.cheque_type})",
                "actor": "",
                "amount": float(ch.amount or 0),
                "command": ch.bounce_reason or "",
                "attachment_id": None,
                "attachment_name": "",
            }
        )

    # 4. Court filing  (batched: one round-trip for filing + hearings + cash requests)
    filing = db.query(CourtFiling).filter(CourtFiling.case_id == case.id).first()
    hearings = (
        db.query(Hearing).filter(Hearing.case_id == case.id).order_by(Hearing.id).all()
    )
    crs = (
        db.query(CashRequest)
        .filter(CashRequest.case_id == case.id)
        .order_by(CashRequest.id)
        .all()
    )
    closure = db.query(CaseClosure).filter(CaseClosure.case_id == case.id).first()
    if filing:
        rows.append(
            {
                "when": filing.created_at,
                "phase": "Court Filing",
                "event": (
                    f"Filed - Police #{filing.police_case_no or '-'}, "
                    f"Court #{filing.court_case_no or '-'}"
                ),
                "actor": actors.get(filing.filed_by_id, ""),
                "amount": 0,
                "command": filing.notes or "",
                "attachment_id": filing.acknowledgment_attachment_id,
                "attachment_name": "Govt Acknowledgement"
                if filing.acknowledgment_attachment_id
                else "",
            }
        )

    # 5. Hearings (primary date)
    for h in hearings:
        rows.append(
            {
                "when": h.hearing_date,
                "phase": "Hearing",
                "event": h.hearing_type,
                "actor": actors.get(h.recorded_by_id, ""),
                "amount": 0,
                "command": h.outcome or "",
                "attachment_id": h.attachment_id,
                "attachment_name": "Hearing attachment" if h.attachment_id else "",
            }
        )

    # 6. Cash requests
    for cr in crs:
        signed = float(cr.amount or 0)
        rows.append(
            {
                "when": cr.requested_at or cr.created_at,
                "phase": "Cash Request",
                "event": f"{cr.status} - {cr.purpose or '-'}",
                "actor": actors.get(cr.requested_by_id, ""),
                "amount": -signed if cr.status == "Paid" else 0,
                "command": cr.approval_comment or cr.payment_reference or "",
                "attachment_id": cr.receipt_attachment_id,
                "attachment_name": "Payment receipt"
                if cr.receipt_attachment_id
                else "",
            }
        )

    # 7. Closure
    if closure:
        rows.append(
            {
                "when": closure.closed_at,
                "phase": "Closure",
                "event": f"Closed via {closure.closure_type}",
                "actor": actors.get(closure.closed_by_id, ""),
                "amount": float(closure.settled_amount or 0),
                "command": closure.command or "",
                "attachment_id": None,
                "attachment_name": "",
            }
        )

    rows.sort(key=lambda r: (r["when"] or datetime.min.replace(tzinfo=timezone.utc)))

    # Attachment list (for the UI's "Download all as ZIP" + per-row links)
    attachments = [
        {
            "id": a.id,
            "filename": a.original_filename,
            "category": a.category,
            "size_bytes": a.size_bytes,
        }
        for a in case.attachments
    ]

    return {
        "title": f"Cash Flow - {case.case_no}",
        "subtitle": (
            f"Lifecycle from creation to {'closure' if closure else case.status}"
        ),
        "columns": [
            {"key": "when", "label": "When", "type": "datetime"},
            {"key": "phase", "label": "Phase", "type": "text"},
            {"key": "event", "label": "Event", "type": "text"},
            {"key": "actor", "label": "Actor", "type": "text"},
            {"key": "amount", "label": "Amount", "type": "number"},
            {"key": "command", "label": "Command / Note", "type": "text"},
            {"key": "attachment_name", "label": "Attachment", "type": "text"},
        ],
        "rows": rows,
        "case": {
            "id": case.id,
            "case_no": case.case_no,
            "status": case.status,
            "legal_filing_amount": str(case.legal_filing_amount or 0),
            "attachments_count": len(attachments),
            # Phase 20: surface closure metadata so the report UI can
            # show "Closed" pill + settlement details without a second
            # round-trip to the closure endpoint.
            "is_closed": closure is not None,
            "closure_type": closure.closure_type if closure else "",
            "closed_at": closure.closed_at if closure else None,
            "closed_by": actors.get(closure.closed_by_id, "") if closure else "",
            "settled_amount": str(closure.settled_amount) if closure else "0",
        },
        "attachments": attachments,
    }


# ===================== Registry =====================
_STATUS_OPTIONS = (
    "", "Draft", "Submitted", "In Review", "Clarification Requested",
    "Approved", "Filed", "Rejected", "Closed",
)

# A magic dynamic_source tells the UI to fetch options from a master endpoint.
_DIVISION_PARAM = ParamDef("division_id", "division_select", "Division")
_STATUS_PARAM = ParamDef("status", "select", "Status", options=_STATUS_OPTIONS)


REPORTS: dict[str, ReportDef] = {
    r.key: r
    for r in [
        ReportDef(
            key="case_register",
            name="Case Register",
            description="All cases with division / status / date filters",
            permission="cases:read",
            params=(
                _DIVISION_PARAM,
                _STATUS_PARAM,
                ParamDef("date_from", "date", "Created From"),
                ParamDef("date_to", "date", "Created To"),
            ),
            query=case_register,
        ),
        ReportDef(
            key="status_summary",
            name="Status Summary",
            description="Cases grouped by status with totals",
            permission="cases:read",
            params=(_DIVISION_PARAM,),
            query=status_summary,
            landscape=False,
        ),
        ReportDef(
            key="aging_report",
            name="Aging Report",
            description="Open cases bucketed by age",
            permission="cases:read",
            params=(_DIVISION_PARAM, _STATUS_PARAM),
            query=aging_report,
            landscape=False,
        ),
        ReportDef(
            key="division_summary",
            name="Division-wise Summary",
            description="Case volume and value by division",
            permission="cases:read",
            params=(_DIVISION_PARAM, _STATUS_PARAM),
            query=division_summary,
            landscape=False,
        ),
        ReportDef(
            key="hearing_schedule",
            name="Hearing Schedule",
            description="Upcoming hearings",
            permission="cases:read",
            params=(
                _DIVISION_PARAM,
                _STATUS_PARAM,
                ParamDef("days", "select", "Range (days)", options=("30", "60", "90", "180")),
            ),
            query=hearing_schedule,
        ),
        ReportDef(
            key="expense_report",
            name="Expense Report",
            description="Cash requests, optionally paid only",
            permission="cases:read",
            params=(
                _DIVISION_PARAM,
                _STATUS_PARAM,
                ParamDef("only_paid", "select", "Only Paid", options=("true", "false")),
            ),
            query=expense_report,
        ),
        ReportDef(
            key="case_cash_flow",
            name="Case Cash Flow (lifecycle)",
            description=(
                "Every event in one case: workflow, cheques, court filing, "
                "hearings, cash requests and closure. Each row links to its "
                "attachment; bulk-download every file as a ZIP."
            ),
            permission="cases:read",
            params=(
                ParamDef(
                    # Rendered as a searchable typeahead on the frontend
                    # so the user can pick by case_no OR customer name
                    # instead of memorising "PUG-LEGAL-YYYY-NNNN".
                    "case_no", "case_search", "Case", required=True
                ),
            ),
            query=case_cash_flow,
        ),
    ]
}


def list_reports() -> list[dict[str, Any]]:
    return [
        {
            "key": r.key,
            "name": r.name,
            "description": r.description,
            "permission": r.permission,
            "params": [
                {
                    "name": p.name,
                    "type": p.type,
                    "label": p.label,
                    "options": list(p.options) if p.options else None,
                    "required": p.required,
                }
                for p in r.params
            ],
        }
        for r in REPORTS.values()
    ]


def get_report(key: str) -> ReportDef | None:
    return REPORTS.get(key)

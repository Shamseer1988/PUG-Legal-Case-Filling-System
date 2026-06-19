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

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.case import Case, CaseStatusUpdate
from app.models.court import CASH_REQUEST_PAID, CashRequest, Hearing
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
def _scope_cases(db: Session, user: User):
    q = db.query(Case)
    if user.is_super:
        return q
    perms = user.role.permissions if user.role else []
    if "*" in perms:
        return q
    if user.divisions:
        q = q.filter(Case.division_id.in_([d.id for d in user.divisions]))
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
    status = params.get("status") or ""
    date_from = _parse_date(params.get("date_from"))
    date_to = _parse_date(params.get("date_to"))

    q = _scope_cases(db, user)
    if status:
        q = q.filter(Case.status == status)
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
    q = _scope_cases(db, user)
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
        q = _scope_cases(db, user)
        if start:
            q = q.filter(Case.created_at > start)
        if end:
            q = q.filter(Case.created_at <= end)
        # not closed
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
    rows: list[dict[str, Any]] = []
    divisions = _division_map(db)
    for div_id, div_name in divisions.items():
        q = _scope_cases(db, user).filter(Case.division_id == div_id)
        cases = q.all()
        rows.append(
            {
                "division": div_name,
                "total_cases": len(cases),
                "open_cases": sum(
                    1
                    for c in cases
                    if c.status not in ("Closed", "Rejected")
                ),
                "approved_cases": sum(1 for c in cases if c.status in ("Approved", "Filed")),
                "total_legal_amount": sum(
                    (c.legal_filing_amount or Decimal("0") for c in cases), Decimal("0")
                ),
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
    if not user.is_super:
        perms = user.role.permissions if user.role else []
        if "*" not in perms and user.divisions:
            q = q.filter(Case.division_id.in_([d.id for d in user.divisions]))
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


# ===================== Registry =====================
REPORTS: dict[str, ReportDef] = {
    r.key: r
    for r in [
        ReportDef(
            key="case_register",
            name="Case Register",
            description="All cases with status / date filters",
            permission="cases:read",
            params=(
                ParamDef("status", "select", "Status", options=(
                    "", "Draft", "Submitted", "In Review", "Clarification Requested",
                    "Approved", "Filed", "Rejected", "Closed",
                )),
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
            params=(),
            query=status_summary,
            landscape=False,
        ),
        ReportDef(
            key="aging_report",
            name="Aging Report",
            description="Open cases bucketed by age",
            permission="cases:read",
            params=(),
            query=aging_report,
            landscape=False,
        ),
        ReportDef(
            key="division_summary",
            name="Division-wise Summary",
            description="Case volume and value by division",
            permission="cases:read",
            params=(),
            query=division_summary,
            landscape=False,
        ),
        ReportDef(
            key="hearing_schedule",
            name="Hearing Schedule",
            description="Upcoming hearings",
            permission="cases:read",
            params=(
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
                ParamDef("only_paid", "select", "Only Paid", options=("true", "false")),
            ),
            query=expense_report,
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

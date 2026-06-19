"""Jinja2 renderer for the Phase 2 case-print HTML view."""

from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.orm import Session

from app.models.case import Case
from app.models.masters import Bank, Customer, Division, Lawyer, Salesman
from app.models.user import User

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"


@lru_cache
def env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        autoescape=select_autoescape(["html", "xml"]),
    )


def _user_name(db: Session, uid: int | None) -> str:
    if not uid:
        return ""
    u = db.get(User, uid)
    return u.full_name if u else ""


def _lawyer_name(db: Session, lid: int | None) -> str:
    if not lid:
        return ""
    lw = db.get(Lawyer, lid)
    return lw.name if lw else ""


def render_case_print(db: Session, case: Case) -> str:
    customer = db.get(Customer, case.customer_id) if case.customer_id else None
    division = db.get(Division, case.division_id) if case.division_id else None
    salesman = db.get(Salesman, case.salesman_id) if case.salesman_id else None
    bank = db.get(Bank, case.bank_id) if case.bank_id else None

    # Pre-load all banks referenced by cheques so the template can look them up
    bank_ids = {c.bank_id for c in case.cheques if c.bank_id}
    bank_by_id: dict[int, Bank] = {}
    if bank_ids:
        for b in db.query(Bank).filter(Bank.id.in_(bank_ids)).all():
            bank_by_id[b.id] = b

    signatory_grid = [
        {"role": "Accountant", "name": _user_name(db, case.created_by_id)},
        {"role": "Sales Manager", "name": _user_name(db, case.sales_manager_id)},
        {"role": "Division Manager", "name": _user_name(db, case.division_manager_id)},
        {"role": "Auditor", "name": _user_name(db, case.auditor_id)},
        {"role": "Finance Manager", "name": _user_name(db, case.fm_id)},
        {"role": "Executive Director", "name": _user_name(db, case.ed_id)},
        {"role": "Chairman / MD", "name": _user_name(db, case.chairman_id)},
        {"role": "Lawyer", "name": _lawyer_name(db, case.lawyer_id)},
    ]

    refs = {
        "customer": customer,
        "division": division,
        "salesman": salesman,
        "bank": bank,
        "bank_by_id": bank_by_id,
    }

    tmpl = env().get_template("case_print.html")
    return tmpl.render(
        case=case,
        refs=refs,
        signatory_grid=signatory_grid,
        now=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    )

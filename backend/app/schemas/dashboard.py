"""Executive dashboard schemas."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class Kpis(BaseModel):
    total_cases: int
    open_cases: int
    approved_or_filed: int
    rejected_cases: int
    closed_cases: int
    total_legal_amount: Decimal
    total_recovered: Decimal
    pending_my_inbox: int
    overdue_count: int


class TrendPoint(BaseModel):
    month: str  # YYYY-MM
    cases_created: int
    cases_approved: int


class StatusCount(BaseModel):
    status: str
    count: int


class DivisionRow(BaseModel):
    division_id: int
    division_name: str
    total: int
    by_status: dict[str, int]
    total_legal_amount: Decimal


class UpcomingHearing(BaseModel):
    case_id: int
    case_no: str
    hearing_date: str  # iso
    hearing_type: str
    location: str
    days_until: int


class Alert(BaseModel):
    severity: str  # warn | danger
    title: str
    detail: str
    link: str | None = None
    count: int = 1

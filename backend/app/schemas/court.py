"""Court filing, hearing and cash request schemas."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


# ---------- Court Filing ----------
class CourtFilingBase(BaseModel):
    police_case_no: str = ""
    court_case_no: str = ""
    filed_court: str = ""
    filed_date: date | None = None
    acknowledgment_attachment_id: int | None = None
    notes: str = ""


class CourtFilingCreate(CourtFilingBase):
    pass


class CourtFilingUpdate(BaseModel):
    police_case_no: str | None = None
    court_case_no: str | None = None
    filed_court: str | None = None
    filed_date: date | None = None
    acknowledgment_attachment_id: int | None = None
    notes: str | None = None


class CourtFilingRead(CourtFilingBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    case_id: int
    filed_by_id: int
    filed_by_name: str = ""
    created_at: datetime
    # Phase 21: include the acknowledgement attachment's metadata so
    # the panel can render a download chip without a second request.
    acknowledgment_attachment_filename: str = ""
    acknowledgment_attachment_size: int = 0
    # Phase 36: surface MIME so the viewer modal can pick the right
    # preview path (PDF vs image vs unsupported).
    acknowledgment_attachment_mime: str = "application/octet-stream"


# ---------- Hearing ----------
class HearingBase(BaseModel):
    hearing_date: datetime
    location: str = ""
    hearing_type: str = "Adjournment"
    outcome: str = ""
    next_hearing_date: datetime | None = None
    attachment_id: int | None = None


class HearingCreate(HearingBase):
    pass


class HearingUpdate(BaseModel):
    hearing_date: datetime | None = None
    location: str | None = None
    hearing_type: str | None = None
    outcome: str | None = None
    next_hearing_date: datetime | None = None
    attachment_id: int | None = None


class HearingRead(HearingBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    case_id: int
    recorded_by_id: int
    recorded_by_name: str = ""
    created_at: datetime


class CalendarHearing(BaseModel):
    id: int
    case_id: int
    case_no: str
    hearing_date: datetime
    location: str
    hearing_type: str
    next_hearing_date: datetime | None


# ---------- Cash Request ----------
class CashRequestBase(BaseModel):
    amount: Decimal = Field(gt=0)
    purpose: str = ""


class CashRequestCreate(CashRequestBase):
    pass


class CashRequestApprovePayload(BaseModel):
    comment: str = ""


class CashRequestRejectPayload(BaseModel):
    comment: str = Field(min_length=1)


class CashRequestPayPayload(BaseModel):
    payment_reference: str = ""
    receipt_attachment_id: int | None = None


class CashRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    case_id: int
    case_no: str = ""
    amount: Decimal
    purpose: str
    status: str

    requested_by_id: int
    requested_by_name: str = ""
    requested_at: datetime | None

    approved_by_id: int | None
    approved_by_name: str = ""
    approved_at: datetime | None
    approval_comment: str

    paid_by_id: int | None
    paid_by_name: str = ""
    paid_at: datetime | None
    payment_reference: str
    receipt_attachment_id: int | None


class CaseSpendSummary(BaseModel):
    total_requested: Decimal
    total_approved: Decimal
    total_paid: Decimal
    open_count: int

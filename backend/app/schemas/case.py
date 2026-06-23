"""Case + Cheque + Attachment schemas."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


# ---------- Cheque ----------
class ChequeBase(BaseModel):
    # Phase 38: allow blank cheque_number while the case is in
    # Draft so the user can click "Add Cheque" and immediately
    # attach a cheque-copy before they've typed the number. The
    # submit transition rejects empty numbers.
    cheque_number: str = Field(default="", max_length=50)
    bank_id: int | None = None
    bank_name_text: str = ""
    amount: Decimal = Decimal("0")
    cheque_date: date | None = None
    cheque_type: str = "Normal"
    bounce_reason: str = ""


class ChequeCreate(ChequeBase):
    pass


class ChequeRead(ChequeBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


# ---------- Attachment ----------
class AttachmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    original_filename: str
    mime_type: str
    size_bytes: int
    category: str
    uploaded_by_id: int
    created_at: datetime


# ---------- Cheque attachment (Phase 36) ----------
class ChequeAttachmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    cheque_id: int
    case_id: int
    original_filename: str
    mime_type: str
    size_bytes: int
    is_bank_return_letter: bool
    uploaded_by_id: int
    created_at: datetime


class ChequeOcrFields(BaseModel):
    """OCR auto-fill payload returned with a cheque-attachment
    upload so the form can populate the row inline."""

    success: bool
    engine: str
    cheque_number: str | None = None
    bank_id: int | None = None
    bank_name: str | None = None
    amount: str | None = None
    cheque_date: str | None = None
    cheque_type: str | None = None
    bounce_reason: str | None = None
    warnings: list[str] = []


class ChequeAttachmentUploadResult(BaseModel):
    attachment: ChequeAttachmentRead
    ocr: ChequeOcrFields


# ---------- Case ----------
class CaseBase(BaseModel):
    customer_id: int
    division_id: int
    salesman_id: int | None = None
    bank_id: int | None = None
    case_type_id: int | None = None
    customer_type: str = "Retail"
    actual_due_amount: Decimal = Decimal("0")
    legal_filing_amount: Decimal = Decimal("0")
    deposit_date: date | None = None
    is_criminal: bool = False
    is_civil: bool = False
    commands: str = ""

    sales_manager_id: int | None = None
    division_manager_id: int | None = None
    auditor_id: int | None = None
    fm_id: int | None = None
    ed_id: int | None = None
    chairman_id: int | None = None
    lawyer_id: int | None = None


class CaseCreate(CaseBase):
    cheques: list[ChequeCreate] = []


class CaseUpdate(BaseModel):
    customer_id: int | None = None
    division_id: int | None = None
    salesman_id: int | None = None
    bank_id: int | None = None
    case_type_id: int | None = None
    customer_type: str | None = None
    actual_due_amount: Decimal | None = None
    legal_filing_amount: Decimal | None = None
    deposit_date: date | None = None
    is_criminal: bool | None = None
    is_civil: bool | None = None
    commands: str | None = None
    sales_manager_id: int | None = None
    division_manager_id: int | None = None
    auditor_id: int | None = None
    fm_id: int | None = None
    ed_id: int | None = None
    chairman_id: int | None = None
    lawyer_id: int | None = None
    cheques: list[ChequeCreate] | None = None


class CaseListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    case_no: str
    customer_id: int
    division_id: int
    status: str
    current_stage: str
    legal_filing_amount: Decimal
    is_criminal: bool
    is_civil: bool
    created_at: datetime
    submitted_at: datetime | None


class CaseSearchHit(BaseModel):
    """Lightweight row for the typeahead case picker."""

    id: int
    case_no: str
    customer_name: str
    division_name: str
    legal_filing_amount: Decimal
    status: str


class CaseSearchRow(BaseModel):
    """Richer row returned by the advanced cases search.

    Carries denormalised customer + division names so the Cases page
    can render the filtered list without a second round-trip for
    each lookup.
    """

    id: int
    case_no: str
    customer_id: int
    customer_name: str
    customer_code: str
    division_id: int
    division_name: str
    status: str
    current_stage: str
    legal_filing_amount: Decimal
    is_criminal: bool
    is_civil: bool
    created_at: datetime
    submitted_at: datetime | None
    sla_due_at: datetime | None


class CaseSearchPage(BaseModel):
    """Paginated wrapper returned by ``GET /cases/search-full``."""

    items: list[CaseSearchRow]
    total: int
    limit: int
    offset: int


class CaseRead(CaseBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    case_no: str
    status: str
    current_stage: str
    submitted_at: datetime | None
    created_by_id: int
    created_at: datetime
    updated_at: datetime
    cheques: list[ChequeRead] = []
    attachments: list[AttachmentRead] = []

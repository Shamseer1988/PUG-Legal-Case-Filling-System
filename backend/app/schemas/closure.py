"""Case closure schemas."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ClosureBase(BaseModel):
    closure_type: str = Field(
        pattern="^(court_cheque|online_transfer|cash_received|settlement|writeoff|other)$"
    )
    command: str = ""
    settled_amount: Decimal = Decimal("0")
    settled_date: date | None = None

    # Court cheque
    court_cheque_number: str = ""
    court_cheque_bank: str = ""
    court_cheque_date: date | None = None

    # Online transfer
    transfer_reference: str = ""
    transfer_bank: str = ""
    transfer_account_last4: str = ""

    # Cash
    cash_receipt_no: str = ""
    cash_received_by_id: int | None = None

    # Settlement / write-off
    settlement_agreement_ref: str = ""
    writeoff_reason: str = ""

    extra: dict[str, Any] = {}


class ClosureCreate(ClosureBase):
    pass


class ClosureRead(ClosureBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    case_id: int
    closed_by_id: int
    closed_at: datetime
    closed_by_name: str = ""
    created_at: datetime

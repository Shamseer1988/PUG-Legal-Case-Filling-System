"""Case closure: how was the case settled.

Created when a case transitions to ``Closed``. Captures a free-text
command plus typed settlement details (court cheque received, online
transfer, cash, settlement, write-off, other).
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

# Settlement types - kept as strings for forward compatibility
CLOSURE_COURT_CHEQUE = "court_cheque"
CLOSURE_ONLINE_TRANSFER = "online_transfer"
CLOSURE_CASH_RECEIVED = "cash_received"
CLOSURE_SETTLEMENT = "settlement"
CLOSURE_WRITEOFF = "writeoff"
CLOSURE_OTHER = "other"

CLOSURE_TYPES = [
    CLOSURE_COURT_CHEQUE,
    CLOSURE_ONLINE_TRANSFER,
    CLOSURE_CASH_RECEIVED,
    CLOSURE_SETTLEMENT,
    CLOSURE_WRITEOFF,
    CLOSURE_OTHER,
]


class CaseClosure(Base, TimestampMixin):
    __tablename__ = "case_closures"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )

    closure_type: Mapped[str] = mapped_column(String(30), nullable=False)
    command: Mapped[str] = mapped_column(Text, default="")
    settled_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=0, nullable=False
    )
    settled_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Typed settlement details
    court_cheque_number: Mapped[str] = mapped_column(String(60), default="")
    court_cheque_bank: Mapped[str] = mapped_column(String(200), default="")
    court_cheque_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    transfer_reference: Mapped[str] = mapped_column(String(120), default="")
    transfer_bank: Mapped[str] = mapped_column(String(200), default="")
    transfer_account_last4: Mapped[str] = mapped_column(String(8), default="")

    cash_receipt_no: Mapped[str] = mapped_column(String(60), default="")
    cash_received_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    settlement_agreement_ref: Mapped[str] = mapped_column(String(120), default="")
    writeoff_reason: Mapped[str] = mapped_column(Text, default="")

    # Free-form bag for "other" or future fields
    extra: Mapped[dict] = mapped_column(JSON, default=dict)

    closed_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    closed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

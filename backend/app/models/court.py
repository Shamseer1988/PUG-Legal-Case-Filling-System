"""Court filing, hearings, and lawyer cash requests."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

# ---- Cash request statuses ----
CASH_REQUEST_REQUESTED = "Requested"
CASH_REQUEST_APPROVED = "Approved"
CASH_REQUEST_REJECTED = "Rejected"
CASH_REQUEST_PAID = "Paid"

# ---- Hearing types (free-form but seeded list shown in UI) ----
HEARING_TYPES = [
    "First Hearing",
    "Adjournment",
    "Plea",
    "Trial",
    "Cross Examination",
    "Judgment",
    "Appeal",
    "Other",
]


class CourtFiling(Base, TimestampMixin):
    """One-to-one with Case. Records the lawyer's court filing acknowledgement."""

    __tablename__ = "court_filings"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    police_case_no: Mapped[str] = mapped_column(String(60), default="")
    court_case_no: Mapped[str] = mapped_column(String(60), default="")
    filed_court: Mapped[str] = mapped_column(String(200), default="")
    filed_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    acknowledgment_attachment_id: Mapped[int | None] = mapped_column(
        ForeignKey("case_attachments.id", ondelete="SET NULL"), nullable=True
    )
    filed_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    notes: Mapped[str] = mapped_column(String(2000), default="")


class Hearing(Base, TimestampMixin):
    """A hearing event on a case."""

    __tablename__ = "hearings"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    hearing_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    location: Mapped[str] = mapped_column(String(300), default="")
    hearing_type: Mapped[str] = mapped_column(String(50), default="Adjournment")
    outcome: Mapped[str] = mapped_column(String(2000), default="")
    next_hearing_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    attachment_id: Mapped[int | None] = mapped_column(
        ForeignKey("case_attachments.id", ondelete="SET NULL"), nullable=True
    )
    recorded_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    # Phase 34: hearing reminder windows. Each timestamp is stamped
    # the first time the scheduled tick fires a reminder for that
    # window so we never spam (one ping per window per hearing).
    reminder_24h_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reminder_1h_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class CashRequest(Base, TimestampMixin):
    """Lawyer requests cash -> FM approves -> Accountant pays with receipt."""

    __tablename__ = "cash_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    purpose: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(
        String(20), default=CASH_REQUEST_REQUESTED, nullable=False, index=True
    )

    requested_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    approved_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approval_comment: Mapped[str] = mapped_column(String(500), default="")

    paid_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payment_reference: Mapped[str] = mapped_column(String(100), default="")
    receipt_attachment_id: Mapped[int | None] = mapped_column(
        ForeignKey("case_attachments.id", ondelete="SET NULL"), nullable=True
    )

    case: Mapped["object"] = relationship(  # type: ignore[type-arg]
        "Case", lazy="joined", viewonly=True
    )

"""Case, Cheque, CaseAttachment, and yearly Case-No sequence."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

# ---- Status / stage constants ----
CASE_STATUS_DRAFT = "Draft"
CASE_STATUS_SUBMITTED = "Submitted"
CASE_STATUS_IN_REVIEW = "In Review"
CASE_STATUS_CLARIFICATION = "Clarification Requested"
CASE_STATUS_APPROVED = "Approved"
CASE_STATUS_REJECTED = "Rejected"
CASE_STATUS_FILED = "Filed"  # set after court filing (Phase 4)
CASE_STATUS_LAWYER_APPROVED = "Lawyer Approved"  # Phase 20 - explicit lawyer sign-off
CASE_STATUS_CLOSED = "Closed"

STAGE_ACCOUNTANT = "Accountant"
STAGE_SALES_MGR = "Sales Manager"
STAGE_DIV_MGR = "Division Manager"
STAGE_AUDIT = "Audit"
STAGE_FM = "Finance Manager"
STAGE_ED = "Executive Director"
STAGE_CHAIRMAN = "Chairman / MD"
STAGE_LAWYER = "Lawyer"
STAGE_CLOSED = "Closed"

# Action types recorded on CaseStatusUpdate
ACTION_SUBMIT = "submit"
ACTION_APPROVE = "approve"
ACTION_REJECT = "reject"
ACTION_REQUEST_CLARIFICATION = "request_clarification"
ACTION_RESUBMIT = "resubmit"
ACTION_LAWYER_APPROVE = "lawyer_approve"
ACTION_COMMENT = "comment"


class Case(Base, TimestampMixin):
    __tablename__ = "cases"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_no: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)

    # Parties / commercials
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False
    )
    division_id: Mapped[int] = mapped_column(
        ForeignKey("divisions.id", ondelete="RESTRICT"), nullable=False
    )
    salesman_id: Mapped[int | None] = mapped_column(
        ForeignKey("salesmen.id", ondelete="SET NULL"), nullable=True
    )
    bank_id: Mapped[int | None] = mapped_column(
        ForeignKey("banks.id", ondelete="SET NULL"), nullable=True
    )
    case_type_id: Mapped[int | None] = mapped_column(
        ForeignKey("case_types.id", ondelete="SET NULL"), nullable=True
    )

    customer_type: Mapped[str] = mapped_column(String(50), default="Retail")
    actual_due_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=0, nullable=False
    )
    legal_filing_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=0, nullable=False
    )
    deposit_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Case filing checkboxes from the original paper form
    is_criminal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_civil: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    commands: Mapped[str] = mapped_column(String(2000), default="")

    # Signatory selections (set on the form before submit)
    sales_manager_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    division_manager_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    auditor_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    fm_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    ed_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    chairman_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    lawyer_id: Mapped[int | None] = mapped_column(
        ForeignKey("lawyers.id", ondelete="SET NULL"), nullable=True
    )

    # Workflow tracking
    status: Mapped[str] = mapped_column(String(40), default=CASE_STATUS_DRAFT, nullable=False)
    current_stage: Mapped[str] = mapped_column(
        String(40), default=STAGE_ACCOUNTANT, nullable=False
    )
    stage_entered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sla_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Phase 33: stamped the first time the background SLA scanner
    # fires the breach notification for the current stage. Cleared
    # in ``_set_stage`` so the next stage starts with a fresh slate.
    # Prevents duplicate notifications on every tick.
    sla_breach_notified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Phase 46: when clarification is requested from a stage other
    # than Accountant, this records which stage should answer.
    # NULL / "Accountant" means the default case-creator flow.
    clarify_from_stage: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # Authorship
    created_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    cheques: Mapped[list["Cheque"]] = relationship(
        back_populates="case",
        cascade="all, delete-orphan",
        order_by="Cheque.id",
        lazy="selectin",
    )
    attachments: Mapped[list["CaseAttachment"]] = relationship(
        back_populates="case",
        cascade="all, delete-orphan",
        order_by="CaseAttachment.id",
        lazy="selectin",
    )
    # Phase 40: joint cheque signatories - the operator picks one
    # or more CustomerPartner rows that physically sign returned
    # cheques. Submit() refuses to advance the case while this
    # list is empty (joint-sign companies must declare at least
    # one signatory).
    cheque_signatories: Mapped[list["CustomerPartner"]] = relationship(
        "CustomerPartner",
        secondary="case_cheque_signatories",
        lazy="selectin",
    )

    @property
    def cheque_signatory_partner_ids(self) -> list[int]:
        """Phase 40: surface the joint-signatory ids so the
        Pydantic ``CaseRead`` schema can pull them via
        ``from_attributes`` without a separate ORM->dict step."""
        return [p.id for p in (self.cheque_signatories or [])]

    timeline: Mapped[list["CaseStatusUpdate"]] = relationship(
        back_populates="case",
        cascade="all, delete-orphan",
        order_by="CaseStatusUpdate.id",
        lazy="selectin",
    )


class Cheque(Base, TimestampMixin):
    __tablename__ = "cheques"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )

    cheque_number: Mapped[str] = mapped_column(String(50), nullable=False)
    bank_id: Mapped[int | None] = mapped_column(
        ForeignKey("banks.id", ondelete="SET NULL"), nullable=True
    )
    bank_name_text: Mapped[str] = mapped_column(String(200), default="")  # free text fallback
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    cheque_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    cheque_type: Mapped[str] = mapped_column(String(30), default="Normal")
    # Normal | Guarantee | PDC | Post-Dated
    bounce_reason: Mapped[str] = mapped_column(String(300), default="")

    case: Mapped[Case] = relationship(back_populates="cheques")
    attachments: Mapped[list["ChequeAttachment"]] = relationship(
        back_populates="cheque",
        cascade="all, delete-orphan",
        order_by="ChequeAttachment.id",
        lazy="selectin",
    )


class ChequeAttachment(Base, TimestampMixin):
    """Phase 36: bank return acknowledgement letters and other
    cheque-specific files. The OCR output that auto-filled the
    cheque row (if any) is stored on the row for audit so we can
    explain *why* the cheque carries the values it does.
    """

    __tablename__ = "cheque_attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    cheque_id: Mapped[int] = mapped_column(
        ForeignKey("cheques.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Denormalised case_id so the ZIP and download endpoints can
    # authorise without joining through cheque every time.
    case_id: Mapped[int] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), default="application/octet-stream")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # True when the upload was processed as a bank return letter and
    # the OCR pipeline produced a usable result.
    is_bank_return_letter: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    ocr_extracted_json: Mapped[str] = mapped_column(Text, default="")
    uploaded_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    cheque: Mapped[Cheque] = relationship(back_populates="attachments")


class CaseAttachment(Base, TimestampMixin):
    __tablename__ = "case_attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), default="application/octet-stream")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    category: Mapped[str] = mapped_column(String(50), default="Supporting Document")
    uploaded_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    case: Mapped[Case] = relationship(back_populates="attachments")


class CaseStatusUpdate(Base, TimestampMixin):
    """Per-case audit / timeline entry. One row per workflow transition."""

    __tablename__ = "case_status_updates"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    action_type: Mapped[str] = mapped_column(String(30), nullable=False)
    from_status: Mapped[str] = mapped_column(String(40), nullable=False)
    to_status: Mapped[str] = mapped_column(String(40), nullable=False)
    from_stage: Mapped[str] = mapped_column(String(40), nullable=False)
    to_stage: Mapped[str] = mapped_column(String(40), nullable=False)
    actor_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    comment: Mapped[str] = mapped_column(String(2000), default="")

    case: Mapped[Case] = relationship(back_populates="timeline")
    attachments: Mapped[list["CaseTransitionAttachment"]] = relationship(
        back_populates="transition",
        cascade="all, delete-orphan",
        order_by="CaseTransitionAttachment.id",
        lazy="selectin",
    )


class CaseTransitionAttachment(Base, TimestampMixin):
    """Files attached to an approval comment (Phase 19).

    Uploaded in two phases: the user uploads files first, which creates
    rows with ``transition_id = NULL``; submitting the transition then
    binds the new ``CaseStatusUpdate`` row's ID into ``transition_id``
    via the ``attachment_ids`` payload.
    """

    __tablename__ = "case_transition_attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    transition_id: Mapped[int | None] = mapped_column(
        ForeignKey("case_status_updates.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(
        String(100), default="application/octet-stream"
    )
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    uploaded_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    transition: Mapped[CaseStatusUpdate | None] = relationship(
        back_populates="attachments"
    )


class CaseNoSequence(Base):
    """Per-year counter used to mint case numbers like PUG-LEGAL-2026-0001."""

    __tablename__ = "case_no_sequence"
    __table_args__ = (UniqueConstraint("year", name="uq_case_no_sequence_year"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    last_number: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

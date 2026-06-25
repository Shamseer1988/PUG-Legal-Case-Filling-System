"""Phase 41: physical-document chain-of-custody models.

The Legal Case Filing System tracks two parallel record sets:

- **Digital attachments** (Phase 6/19/21/...) - PDFs / JPGs uploaded
  to local storage and audited via the case-transition log.
- **Physical originals** (this module) - the paper cheques, ID
  copies, court-stamped filings etc. that physically move between
  offices, lawyers, archives.

A ``PhysicalDocument`` is one item that physically exists. Every
move (handover, return) appends to ``DocumentCustodyLog``. The
latest log row's recipient and location are denormalised back onto
the document for fast "where is X?" queries; the log is the source
of truth.
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


# Document "kind" tags so reports can group by type. Free-text is
# allowed; the constants are a recommendation for the UI dropdown.
DOC_KIND_CASE_FOLDER = "case_folder"
DOC_KIND_ORIGINAL_CHEQUE = "original_cheque"
DOC_KIND_ID_COPY = "id_copy"
DOC_KIND_CONTRACT = "contract"
DOC_KIND_COURT_FILING = "court_filing"
DOC_KIND_BANK_LETTER = "bank_letter"
DOC_KIND_OTHER = "other"
DOC_KINDS = (
    DOC_KIND_CASE_FOLDER,
    DOC_KIND_ORIGINAL_CHEQUE,
    DOC_KIND_ID_COPY,
    DOC_KIND_CONTRACT,
    DOC_KIND_COURT_FILING,
    DOC_KIND_BANK_LETTER,
    DOC_KIND_OTHER,
)


class PhysicalDocument(Base, TimestampMixin):
    """One physical asset tied to a case.

    ``current_*`` fields are denormalized from the latest custody
    log row so the case-detail view can render "Where is this
    cheque?" without joining the log every time. The log is the
    audit trail and source of truth; updaters MUST mirror both.
    """

    __tablename__ = "physical_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )

    kind: Mapped[str] = mapped_column(String(40), default=DOC_KIND_OTHER, nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="")

    # Denormalized snapshot of the latest log entry. Nullable when
    # the doc has just been created and not handed off yet.
    current_holder_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    current_location_id: Mapped[int | None] = mapped_column(
        ForeignKey("document_locations.id", ondelete="SET NULL"), nullable=True
    )
    current_location_text: Mapped[str] = mapped_column(String(300), default="")
    last_transferred_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    custody_log: Mapped[list["DocumentCustodyLog"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentCustodyLog.transferred_at.desc(), DocumentCustodyLog.id.desc()",
        lazy="selectin",
    )

    current_holder = relationship(
        "User", foreign_keys=[current_holder_user_id], lazy="joined"
    )
    current_location = relationship(
        "DocumentLocation", foreign_keys=[current_location_id], lazy="joined"
    )


class DocumentCustodyLog(Base):
    """Append-only chain-of-custody entry.

    Each handover is one row. Either ``to_user_id`` or
    ``to_location_id`` (or both) is set on every row; ``from_*`` is
    null on the first row (initial registration). ``location_text``
    holds an ad-hoc destination (courier, off-site address) when the
    master location dropdown doesn't fit.

    The signature is optional - the user picks whether to capture
    a recipient signature on the touch device. Stored relative to
    STORAGE_LOCAL_PATH under custody/<log_id>/.
    """

    __tablename__ = "document_custody_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("physical_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    transferred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: __import__("datetime").datetime.utcnow(),
        index=True,
    )

    # Who recorded the entry (the system actor, not necessarily the
    # ``from_user_id`` - e.g. an Admin can back-date a transfer on
    # behalf of an absent custodian).
    recorded_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    from_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    to_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    location_id: Mapped[int | None] = mapped_column(
        ForeignKey("document_locations.id", ondelete="SET NULL"), nullable=True
    )
    location_text: Mapped[str] = mapped_column(String(300), default="")

    note: Mapped[str] = mapped_column(Text, default="")

    # Optional signature image captured at handover.
    signature_filename: Mapped[str] = mapped_column(String(255), default="")
    signature_stored: Mapped[str] = mapped_column(String(255), default="")
    signature_mime: Mapped[str] = mapped_column(String(100), default="")
    signature_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    document: Mapped[PhysicalDocument] = relationship(back_populates="custody_log")
    recorded_by = relationship(
        "User", foreign_keys=[recorded_by_user_id], lazy="joined"
    )
    from_user = relationship("User", foreign_keys=[from_user_id], lazy="joined")
    to_user = relationship("User", foreign_keys=[to_user_id], lazy="joined")
    location = relationship(
        "DocumentLocation", foreign_keys=[location_id], lazy="joined"
    )

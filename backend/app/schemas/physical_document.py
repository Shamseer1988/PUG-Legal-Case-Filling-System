"""Phase 41: pydantic schemas for physical documents + custody log."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# ---------- Custody log entry ----------
class CustodyLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    transferred_at: datetime
    recorded_by_user_id: int | None = None
    from_user_id: int | None = None
    to_user_id: int | None = None
    location_id: int | None = None
    location_text: str = ""
    note: str = ""

    # Surface the signature metadata (filename + bytes) so the UI
    # can render a "View signature" button without a second call.
    signature_filename: str = ""
    signature_mime: str = ""
    signature_size: int = 0

    # Phase 45 acceptance flow.
    transfer_status: str = "accepted"
    accepted_at: datetime | None = None
    ack_filename: str = ""
    ack_mime: str = ""
    ack_size: int = 0

    # Pre-resolved display names so the timeline renders without
    # per-row user / location lookups on the frontend.
    from_user_name: str = ""
    to_user_name: str = ""
    location_name: str = ""
    recorded_by_name: str = ""


# ---------- Physical document ----------
class PhysicalDocumentBase(BaseModel):
    kind: str = Field(default="other", max_length=40)
    label: str = Field(min_length=1, max_length=200)
    notes: str = ""
    is_active: bool = True


class PhysicalDocumentCreate(PhysicalDocumentBase):
    # Optional initial placement so the operator can register a
    # cheque "to Cabinet A-3" in one round-trip instead of register
    # + transfer.
    initial_holder_user_id: int | None = None
    initial_location_id: int | None = None
    initial_location_text: str = ""
    initial_note: str = ""


class PhysicalDocumentUpdate(BaseModel):
    # Metadata-only edits. To MOVE a document, hit /transfer.
    kind: str | None = None
    label: str | None = None
    notes: str | None = None
    is_active: bool | None = None


class PhysicalDocumentRead(PhysicalDocumentBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    case_id: int
    current_holder_user_id: int | None = None
    current_location_id: int | None = None
    current_location_text: str = ""
    last_transferred_at: datetime | None = None

    # Display helpers populated by the API layer.
    current_holder_name: str = ""
    current_location_name: str = ""
    case_no: str = ""

    # Phase 45: pending transfer info (None when no transfer is pending).
    pending_transfer_log_id: int | None = None
    pending_transfer_to_user_id: int | None = None
    pending_transfer_to_name: str = ""


class PhysicalDocumentDetail(PhysicalDocumentRead):
    custody_log: list[CustodyLogRead] = Field(default_factory=list)


# ---------- Transfer ----------
class TransferRequest(BaseModel):
    """Record a handover from the current custodian to a new one.

    Either ``to_user_id`` or ``to_location_id`` (or both) must be
    set. ``location_text`` lets the operator type an ad-hoc
    destination (courier address, off-site). The signature payload
    is optional and uploaded separately via the file endpoint when
    a touch signature was captured.
    """

    to_user_id: int | None = None
    to_location_id: int | None = None
    location_text: str = ""
    note: str = ""
    # Optional retroactive timestamp so an Admin can back-date a
    # handover that happened before the system was switched on.
    transferred_at: datetime | None = None


# ---------- Transfer acceptance ----------
class TransferActionRequest(BaseModel):
    """Body for accept / reject actions (note is optional)."""
    note: str = ""


class PendingIncomingRead(CustodyLogRead):
    """CustodyLogRead enriched with document and case context."""
    document_label: str = ""
    case_id: int | None = None
    case_no: str = ""


# ---------- Reports ----------
class OverdueDocumentRow(BaseModel):
    document_id: int
    case_id: int
    case_no: str
    label: str
    kind: str
    holder_user_id: int | None = None
    holder_name: str = ""
    last_transferred_at: datetime | None = None
    days_out: int = 0

"""In-app notifications and outbound email log."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

# ---- EmailLog status ----
EMAIL_STATUS_QUEUED = "Queued"
EMAIL_STATUS_SENT = "Sent"
EMAIL_STATUS_FAILED = "Failed"
EMAIL_STATUS_BOUNCED = "Bounced"


class Notification(Base, TimestampMixin):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(String(2000), default="")
    link: Mapped[str] = mapped_column(String(500), default="")
    event: Mapped[str] = mapped_column(String(50), default="")
    related_case_id: Mapped[int | None] = mapped_column(
        ForeignKey("cases.id", ondelete="SET NULL"), nullable=True
    )
    is_read: Mapped[bool] = mapped_column(default=False, nullable=False, index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EmailLog(Base, TimestampMixin):
    __tablename__ = "email_log"

    id: Mapped[int] = mapped_column(primary_key=True)

    to_emails: Mapped[str] = mapped_column(String(1000), nullable=False)
    cc_emails: Mapped[str] = mapped_column(String(1000), default="")
    bcc_emails: Mapped[str] = mapped_column(String(1000), default="")
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    template_name: Mapped[str] = mapped_column(String(100), default="notification_email.html")
    body_html: Mapped[str] = mapped_column(Text, default="")
    body_text: Mapped[str] = mapped_column(Text, default="")

    status: Mapped[str] = mapped_column(
        String(20), default=EMAIL_STATUS_QUEUED, nullable=False, index=True
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str] = mapped_column(Text, default="")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Phase 25 - background worker scheduling
    # When the next delivery attempt should run. NULL = ASAP (used
    # for freshly-queued rows so the next worker tick picks them up).
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    last_attempted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    event: Mapped[str] = mapped_column(String(50), default="")
    related_case_id: Mapped[int | None] = mapped_column(
        ForeignKey("cases.id", ondelete="SET NULL"), nullable=True
    )
    related_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    attachments: Mapped[list["EmailLogAttachment"]] = relationship(
        back_populates="email_log",
        cascade="all, delete-orphan",
        order_by="EmailLogAttachment.id",
        lazy="selectin",
    )


class EmailLogAttachment(Base, TimestampMixin):
    """Phase 25: persisted email attachments.

    Each EmailLog row can carry N attachment blobs so the worker can
    retry a failed send without losing the file, and so admin resend
    re-attaches the original payload.
    """

    __tablename__ = "email_log_attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    email_log_id: Mapped[int] = mapped_column(
        ForeignKey("email_log.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(
        String(100), default="application/octet-stream"
    )
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    email_log: Mapped[EmailLog] = relationship(back_populates="attachments")

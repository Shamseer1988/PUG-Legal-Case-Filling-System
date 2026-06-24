"""Master data models: Division, Bank, Salesman, Customer, Lawyer, CaseType."""

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


# Phase 40: residency status of a customer's partner / signatory.
RESIDENCY_INSIDE = "inside_country"
RESIDENCY_OUTSIDE = "outside_country"
RESIDENCY_VISA_CANCELLED = "visa_cancelled"
RESIDENCY_UNKNOWN = "unknown"
RESIDENCY_STATUSES = (
    RESIDENCY_INSIDE,
    RESIDENCY_OUTSIDE,
    RESIDENCY_VISA_CANCELLED,
    RESIDENCY_UNKNOWN,
)


class Division(Base, TimestampMixin):
    __tablename__ = "divisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    address: Mapped[str] = mapped_column(String(500), default="")
    accountant_email: Mapped[str] = mapped_column(String(255), default="")
    manager_email: Mapped[str] = mapped_column(String(255), default="")
    sales_manager_email: Mapped[str] = mapped_column(String(255), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Bank(Base, TimestampMixin):
    __tablename__ = "banks"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Salesman(Base, TimestampMixin):
    __tablename__ = "salesmen"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(255), default="")
    phone: Mapped[str] = mapped_column(String(50), default="")
    division_id: Mapped[int | None] = mapped_column(
        ForeignKey("divisions.id", ondelete="SET NULL"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    division: Mapped[Division | None] = relationship(lazy="joined")


class Customer(Base, TimestampMixin):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    customer_type: Mapped[str] = mapped_column(String(50), default="Retail")
    phone: Mapped[str] = mapped_column(String(50), default="")
    email: Mapped[str] = mapped_column(String(255), default="")
    address: Mapped[str] = mapped_column(String(500), default="")
    division_id: Mapped[int | None] = mapped_column(
        ForeignKey("divisions.id", ondelete="SET NULL"), nullable=True
    )
    salesman_id: Mapped[int | None] = mapped_column(
        ForeignKey("salesmen.id", ondelete="SET NULL"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    division: Mapped[Division | None] = relationship(lazy="joined")
    salesman: Mapped[Salesman | None] = relationship(lazy="joined")
    # Phase 40: customer can have many partners / signatories. The
    # joint-signatory case form pulls from this list.
    partners: Mapped[list["CustomerPartner"]] = relationship(
        back_populates="customer",
        cascade="all, delete-orphan",
        order_by="CustomerPartner.id",
        lazy="selectin",
    )


class CustomerPartner(Base, TimestampMixin):
    """Phase 40: a partner / signatory linked to a Customer.

    Replaces the previous "one customer = one face" assumption.
    A single partner may wear multiple hats (cheque signatory AND
    admin contact AND authorised signatory) so the role is captured
    with independent booleans plus a free-text fallback. Joint
    cheque signing is supported because the case form picks an
    arbitrary subset of partners.
    """

    __tablename__ = "customer_partners"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    id_number: Mapped[str] = mapped_column(String(60), default="", index=True)
    id_expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    nationality: Mapped[str] = mapped_column(String(80), default="")
    residency_status: Mapped[str] = mapped_column(
        String(40), default=RESIDENCY_UNKNOWN, nullable=False
    )

    # Role flags - a partner can carry any combination.
    is_cheque_signatory: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_authorised_signatory: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    is_admin_contact: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    role_other: Mapped[str] = mapped_column(String(120), default="")

    phone: Mapped[str] = mapped_column(String(50), default="")
    email: Mapped[str] = mapped_column(String(255), default="")
    notes: Mapped[str] = mapped_column(Text, default="")

    # Optional ID copy uploaded by the operator. Path is relative
    # to STORAGE_LOCAL_PATH; storage helpers in app/services/storage.py
    # write/read under partners/<partner_id>/.
    id_document_filename: Mapped[str] = mapped_column(String(255), default="")
    id_document_stored: Mapped[str] = mapped_column(String(255), default="")
    id_document_mime: Mapped[str] = mapped_column(String(100), default="")
    id_document_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    customer: Mapped[Customer] = relationship(back_populates="partners")


class CaseChequeSignatory(Base):
    """Phase 40: join table linking a Case to one-or-more cheque
    signatory CustomerPartner rows.

    A composite primary key prevents the same partner being added
    to a case twice. Ordering is preserved via insertion order
    (the ``order_by`` on the case-side relationship).
    """

    __tablename__ = "case_cheque_signatories"

    case_id: Mapped[int] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), primary_key=True
    )
    partner_id: Mapped[int] = mapped_column(
        ForeignKey("customer_partners.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: __import__("datetime").datetime.utcnow(),
    )


class Lawyer(Base, TimestampMixin):
    __tablename__ = "lawyers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    firm: Mapped[str] = mapped_column(String(200), default="")
    email: Mapped[str] = mapped_column(String(255), default="")
    phone: Mapped[str] = mapped_column(String(50), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # "All Companies" flag — when true the lawyer is available on cases
    # across every division and the link rows are ignored. When false
    # only the divisions in ``divisions`` apply.
    is_all_divisions: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    divisions: Mapped[list["Division"]] = relationship(
        secondary="lawyer_division_map", lazy="selectin"
    )


class LawyerDivisionMap(Base):
    __tablename__ = "lawyer_division_map"

    lawyer_id: Mapped[int] = mapped_column(
        ForeignKey("lawyers.id", ondelete="CASCADE"), primary_key=True
    )
    division_id: Mapped[int] = mapped_column(
        ForeignKey("divisions.id", ondelete="CASCADE"), primary_key=True
    )


class CaseType(Base, TimestampMixin):
    __tablename__ = "case_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(String(300), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

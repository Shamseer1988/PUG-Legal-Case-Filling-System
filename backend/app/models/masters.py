"""Master data models: Division, Bank, Salesman, Customer, Lawyer, CaseType."""

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


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

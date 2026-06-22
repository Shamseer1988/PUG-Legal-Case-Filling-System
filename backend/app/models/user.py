"""User, Role and User<->Division mapping models."""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Role(Base, TimestampMixin):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(200), default="")
    permissions: Mapped[list] = mapped_column(JSON, default=list)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_super: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Phase 12 - TOTP 2FA
    totp_secret: Mapped[str] = mapped_column(String(64), default="")
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    totp_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Phase 18 - signature image (relative to STORAGE_LOCAL_PATH)
    signature_path: Mapped[str] = mapped_column(String(500), default="", nullable=False)

    # Phase 31 - preferred UI + email locale (ISO 639-1; "en" / "ar")
    locale: Mapped[str] = mapped_column(String(8), default="en", nullable=False)

    role: Mapped[Role] = relationship(lazy="joined")
    divisions: Mapped[list["Division"]] = relationship(
        secondary="user_division_map", lazy="selectin"
    )


class UserDivisionMap(Base):
    __tablename__ = "user_division_map"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    division_id: Mapped[int] = mapped_column(
        ForeignKey("divisions.id", ondelete="CASCADE"), primary_key=True
    )

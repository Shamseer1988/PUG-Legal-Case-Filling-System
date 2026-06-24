"""Phase 12: TOTP 2FA fields on users.

Revision ID: 0010_phase12_2fa
Revises: 0009_phase10_settings
Create Date: 2026-06-19
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_phase12_2fa"
down_revision: str | None = "0009_phase10_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("totp_secret", sa.String(64), nullable=False, server_default=""),
    )
    op.add_column(
        "users",
        sa.Column("totp_enabled", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "users",
        sa.Column("totp_verified_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "totp_verified_at")
    op.drop_column("users", "totp_enabled")
    op.drop_column("users", "totp_secret")

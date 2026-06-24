"""Phase 10: settings_kv.

Revision ID: 0009_phase10_settings
Revises: 0008_phase9_backup
Create Date: 2026-06-19
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_phase10_settings"
down_revision: str | None = "0008_phase9_backup"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "settings_kv",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("key", sa.String(80), nullable=False, unique=True),
        sa.Column("value", sa.Text, nullable=False, server_default=""),
        sa.Column("is_sensitive", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column(
            "updated_by_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("updated_at_explicit", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_settings_kv_key", "settings_kv", ["key"])


def downgrade() -> None:
    op.drop_index("ix_settings_kv_key", table_name="settings_kv")
    op.drop_table("settings_kv")

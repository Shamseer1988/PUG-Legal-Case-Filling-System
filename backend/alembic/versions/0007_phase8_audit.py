"""Phase 8: tamper-evident audit log.

Revision ID: 0007_phase8_audit
Revises: 0006_phase7_scheduled_reports
Create Date: 2026-06-19
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_phase8_audit"
down_revision: str | None = "0006_phase7_scheduled_reports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "actor_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("actor_email", sa.String(255), nullable=False, server_default=""),
        sa.Column("actor_role", sa.String(100), nullable=False, server_default=""),
        sa.Column("ip_address", sa.String(45), nullable=False, server_default=""),
        sa.Column("user_agent", sa.String(500), nullable=False, server_default=""),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", sa.Integer, nullable=True),
        sa.Column("summary", sa.String(500), nullable=False, server_default=""),
        sa.Column("before", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("after", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("meta", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("prev_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("row_hash", sa.String(64), nullable=False),
    )
    op.create_index("ix_audit_log_created_at", "audit_log", ["created_at"])
    op.create_index("ix_audit_log_actor_id", "audit_log", ["actor_id"])
    op.create_index("ix_audit_log_action", "audit_log", ["action"])
    op.create_index("ix_audit_log_entity_type", "audit_log", ["entity_type"])
    op.create_index("ix_audit_log_entity_id", "audit_log", ["entity_id"])
    op.create_index("ix_audit_log_row_hash", "audit_log", ["row_hash"])


def downgrade() -> None:
    for ix in (
        "ix_audit_log_row_hash",
        "ix_audit_log_entity_id",
        "ix_audit_log_entity_type",
        "ix_audit_log_action",
        "ix_audit_log_actor_id",
        "ix_audit_log_created_at",
    ):
        op.drop_index(ix, table_name="audit_log")
    op.drop_table("audit_log")

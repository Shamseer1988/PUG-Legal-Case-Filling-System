"""Phase 27: saved report filters.

Revision ID: 0016_phase27_saved_filters
Revises: 0015_phase25_email_queue
Create Date: 2026-06-21
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_phase27_saved_filters"
down_revision: str | None = "0015_phase25_email_queue"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _ts() -> list[sa.Column]:
    return [
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
    ]


def upgrade() -> None:
    op.create_table(
        "saved_report_filters",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("report_key", sa.String(50), nullable=False),
        sa.Column("params", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("is_public", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column(
            "created_by_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        *_ts(),
    )
    op.create_index(
        "ix_saved_report_filters_report_key",
        "saved_report_filters",
        ["report_key"],
    )
    op.create_index(
        "ix_saved_report_filters_is_public",
        "saved_report_filters",
        ["is_public"],
    )
    op.create_index(
        "ix_saved_report_filters_created_by_id",
        "saved_report_filters",
        ["created_by_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_saved_report_filters_created_by_id",
        table_name="saved_report_filters",
    )
    op.drop_index(
        "ix_saved_report_filters_is_public",
        table_name="saved_report_filters",
    )
    op.drop_index(
        "ix_saved_report_filters_report_key",
        table_name="saved_report_filters",
    )
    op.drop_table("saved_report_filters")

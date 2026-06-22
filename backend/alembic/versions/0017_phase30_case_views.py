"""Phase 30: case views log for audit forensics.

Revision ID: 0017_phase30_case_views
Revises: 0016_phase27_saved_filters
Create Date: 2026-06-21
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_phase30_case_views"
down_revision: str | None = "0016_phase27_saved_filters"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "case_views",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "case_id",
            sa.Integer,
            sa.ForeignKey("cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "viewed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("ip_address", sa.String(45), nullable=False, server_default=""),
    )
    op.create_index("ix_case_views_case_id", "case_views", ["case_id"])
    op.create_index("ix_case_views_user_id", "case_views", ["user_id"])
    op.create_index("ix_case_views_viewed_at", "case_views", ["viewed_at"])


def downgrade() -> None:
    op.drop_index("ix_case_views_viewed_at", table_name="case_views")
    op.drop_index("ix_case_views_user_id", table_name="case_views")
    op.drop_index("ix_case_views_case_id", table_name="case_views")
    op.drop_table("case_views")

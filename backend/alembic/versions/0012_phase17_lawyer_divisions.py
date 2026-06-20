"""Phase 17: lawyer divisions M2M + is_all_divisions flag.

Revision ID: 0012_phase17_lawyer_divisions
Revises: 0011_phase13_closure
Create Date: 2026-06-20
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_phase17_lawyer_divisions"
down_revision: str | None = "0011_phase13_closure"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "lawyers",
        sa.Column(
            "is_all_divisions",
            sa.Boolean,
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_table(
        "lawyer_division_map",
        sa.Column(
            "lawyer_id",
            sa.Integer,
            sa.ForeignKey("lawyers.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "division_id",
            sa.Integer,
            sa.ForeignKey("divisions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_index(
        "ix_lawyer_division_map_division_id",
        "lawyer_division_map",
        ["division_id"],
    )
    # All pre-existing lawyer rows had no division scope, so flip them
    # to "All Companies" — that preserves their visibility on every
    # case form rather than orphaning them with an empty list.
    op.execute("UPDATE lawyers SET is_all_divisions = TRUE")


def downgrade() -> None:
    op.drop_index(
        "ix_lawyer_division_map_division_id",
        table_name="lawyer_division_map",
    )
    op.drop_table("lawyer_division_map")
    op.drop_column("lawyers", "is_all_divisions")

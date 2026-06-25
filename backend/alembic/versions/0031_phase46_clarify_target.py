"""Phase 46: clarify_from_stage on Case.

Lets any approver ask clarification from any stage below them in the
hierarchy rather than always routing back to the Accountant.

Revision ID: 0031_phase46_clarify_target
Revises: 0030_phase45_phys_accept
Create Date: 2026-06-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0031_phase46_clarify_target"
down_revision: str | None = "0030_phase45_phys_accept"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("cases") as batch:
        batch.add_column(
            sa.Column("clarify_from_stage", sa.String(40), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("cases") as batch:
        batch.drop_column("clarify_from_stage")

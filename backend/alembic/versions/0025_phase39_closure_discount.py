"""Phase 39: case_closures.discount_amount.

Records the discount applied at closure (against the case's
``actual_due_amount`` - NOT ``legal_filing_amount``) so reports
and the audit trail can show it explicitly instead of forcing
readers to back-calculate.

Revision ID: 0025_phase39_closure_discount
Revises: 0024_phase37_user_all_divs
Create Date: 2026-06-23
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025_phase39_closure_discount"
down_revision: str | None = "0024_phase37_user_all_divs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "case_closures",
        sa.Column(
            "discount_amount",
            sa.Numeric(14, 2),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("case_closures", "discount_amount")

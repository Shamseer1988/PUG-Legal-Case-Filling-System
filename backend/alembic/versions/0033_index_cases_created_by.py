"""Index cases.created_by_id for "my cases" / inbox queries.

Migration 0002 indexed case_no, division_id and status, but every
"cases I created" lookup (the Accountant inbox, the dashboard's
recent-cases panel, etc.) filters by ``created_by_id`` and was
falling back to a sequential scan. As the cases table grows that
turns into a hot O(n) read on every login.

Uses ``IF NOT EXISTS`` so the migration is safe to re-run and to
apply on databases that have the index from a prior manual create.

Revision ID: 0033_index_cases_created_by
Revises: 0032_phase46_doc_transfer
Create Date: 2026-06-26
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0033_index_cases_created_by"
down_revision: str | None = "0032_phase46_doc_transfer"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_cases_created_by_id "
        "ON cases (created_by_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_cases_created_by_id")

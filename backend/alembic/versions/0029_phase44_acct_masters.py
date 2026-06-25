"""Phase 44: grant Accountant role division-scoped master create permission.

Adds ``masters:create_own_division`` to the Accountant system role so that
accountants can create Customers and Salesmen within their assigned division
without gaining full ``masters:write`` access.

No schema changes — this is a pure data migration that updates the JSON
permissions array in the ``roles`` table.

Revision ID: 0029_phase44_acct_masters
Revises: 0028_phase42_pgdump_backup
Create Date: 2026-06-25

Note: revision id is intentionally short. Some deployed databases were
created before alembic_version was widened to VARCHAR(64) (see env.py)
and still carry the default VARCHAR(32) cap. A longer descriptive id
would migrate fine but fail on the version-row update with
``StringDataRightTruncation``, rolling the whole batch back.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0029_phase44_acct_masters"
down_revision: str | None = "0028_phase42_pgdump_backup"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PERM = "masters:create_own_division"


def upgrade() -> None:
    # Append the new permission to the Accountant system role only when it
    # is not already present. The bind parameters are sent as VARCHAR by the
    # driver, so we cast them to ``jsonb`` explicitly inside the SQL — both
    # the ``@>`` (contains) and ``||`` (concat) operators require jsonb on
    # both sides. No PostgreSQL extensions needed.
    op.execute(
        sa.text(
            """
            UPDATE roles
            SET permissions = (permissions::jsonb || (:perm_arr)::jsonb)
            WHERE name = 'Accountant'
              AND is_system = true
              AND NOT (permissions::jsonb @> (:perm_single)::jsonb)
            """
        ).bindparams(
            perm_arr=f'["{_PERM}"]',
            perm_single=f'["{_PERM}"]',
        )
    )


def downgrade() -> None:
    # Remove the permission from the array.
    op.execute(
        sa.text(
            """
            UPDATE roles
            SET permissions = (
                SELECT json_agg(elem)::text
                FROM json_array_elements_text(permissions::json) AS elem
                WHERE elem <> :perm
            )
            WHERE name = 'Accountant'
              AND is_system = true
            """
        ).bindparams(perm=_PERM)
    )

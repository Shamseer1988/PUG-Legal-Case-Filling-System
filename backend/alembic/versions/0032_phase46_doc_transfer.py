"""Phase 46 fix: grant documents:transfer to every approval role.

The Case Folder physical file travels up the approval chain with the
case. Each receiving role (SM, DM, Auditor, FM, ED, Chairman/MD) must
be able to accept/reject the transfer and upload the signed
acknowledgment — all of which require ``documents:transfer``.

Previously only Accountant and Lawyer had this permission, so any
non-super approver hit "Missing permission: documents:transfer" on the
Accept Transfer dialog. This data migration backfills the perm on the
existing system role rows.

Revision ID: 0032_phase46_doc_transfer
Revises: 0031_phase46_clarify_target
Create Date: 2026-06-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0032_phase46_doc_transfer"
down_revision: str | None = "0031_phase46_clarify_target"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PERM = "documents:transfer"
_ROLES = (
    "Sales Manager",
    "Division Manager",
    "Auditor",
    "Finance Manager",
    "Executive Director",
    "Chairman / MD",
)


def upgrade() -> None:
    # Append documents:transfer to each approval-stage system role,
    # only when it isn't already in the JSON array. Mirrors the
    # idempotent jsonb append pattern used by migration 0029.
    for role_name in _ROLES:
        op.execute(
            sa.text(
                """
                UPDATE roles
                SET permissions = (permissions::jsonb || (:perm_arr)::jsonb)
                WHERE name = :name
                  AND is_system = true
                  AND NOT (permissions::jsonb @> (:perm_single)::jsonb)
                """
            ).bindparams(
                perm_arr=f'["{_PERM}"]',
                perm_single=f'["{_PERM}"]',
                name=role_name,
            )
        )


def downgrade() -> None:
    # COALESCE protects the column when the role held ONLY this
    # permission - PG's json_agg returns NULL on empty input, which
    # would otherwise corrupt the JSON column and crash every
    # permission check on read.
    for role_name in _ROLES:
        op.execute(
            sa.text(
                """
                UPDATE roles
                SET permissions = COALESCE(
                    (
                        SELECT json_agg(elem)::text
                        FROM json_array_elements_text(permissions::json) AS elem
                        WHERE elem <> :perm
                    ),
                    '[]'
                )
                WHERE name = :name
                  AND is_system = true
                """
            ).bindparams(perm=_PERM, name=role_name)
        )

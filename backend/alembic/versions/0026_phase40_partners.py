"""Phase 40: customer partners + joint cheque signatories on cases.

Revision ID: 0026_phase40_partners
Revises: 0025_phase39_closure_discount
Create Date: 2026-06-24
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026_phase40_partners"
down_revision: str | None = "0025_phase39_closure_discount"
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
        "customer_partners",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "customer_id",
            sa.Integer,
            sa.ForeignKey("customers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("id_number", sa.String(60), nullable=False, server_default=""),
        sa.Column("id_expiry_date", sa.Date, nullable=True),
        sa.Column("nationality", sa.String(80), nullable=False, server_default=""),
        sa.Column(
            "residency_status",
            sa.String(40),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column(
            "is_cheque_signatory",
            sa.Boolean,
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "is_authorised_signatory",
            sa.Boolean,
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "is_admin_contact",
            sa.Boolean,
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("role_other", sa.String(120), nullable=False, server_default=""),
        sa.Column("phone", sa.String(50), nullable=False, server_default=""),
        sa.Column("email", sa.String(255), nullable=False, server_default=""),
        sa.Column("notes", sa.Text, nullable=False, server_default=""),
        sa.Column(
            "id_document_filename", sa.String(255), nullable=False, server_default=""
        ),
        sa.Column(
            "id_document_stored", sa.String(255), nullable=False, server_default=""
        ),
        sa.Column(
            "id_document_mime", sa.String(100), nullable=False, server_default=""
        ),
        sa.Column(
            "id_document_size", sa.Integer, nullable=False, server_default="0"
        ),
        sa.Column(
            "is_active", sa.Boolean, nullable=False, server_default=sa.true()
        ),
        *_ts(),
    )
    op.create_index(
        "ix_customer_partners_customer_id",
        "customer_partners",
        ["customer_id"],
    )
    op.create_index(
        "ix_customer_partners_id_number",
        "customer_partners",
        ["id_number"],
    )

    op.create_table(
        "case_cheque_signatories",
        sa.Column(
            "case_id",
            sa.Integer,
            sa.ForeignKey("cases.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "partner_id",
            sa.Integer,
            sa.ForeignKey("customer_partners.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("case_cheque_signatories")
    op.drop_index(
        "ix_customer_partners_id_number", table_name="customer_partners"
    )
    op.drop_index(
        "ix_customer_partners_customer_id", table_name="customer_partners"
    )
    op.drop_table("customer_partners")

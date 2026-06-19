"""Phase 1: auth + masters tables.

Revision ID: 0001_phase1
Revises:
Create Date: 2026-06-19
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_phase1"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _ts_cols() -> list[sa.Column]:
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
        "roles",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(50), nullable=False, unique=True),
        sa.Column("description", sa.String(200), nullable=False, server_default=""),
        sa.Column("permissions", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("is_system", sa.Boolean, nullable=False, server_default=sa.false()),
        *_ts_cols(),
    )
    op.create_index("ix_roles_name", "roles", ["name"])

    op.create_table(
        "divisions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("code", sa.String(20), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("address", sa.String(500), nullable=False, server_default=""),
        sa.Column("accountant_email", sa.String(255), nullable=False, server_default=""),
        sa.Column("manager_email", sa.String(255), nullable=False, server_default=""),
        sa.Column("sales_manager_email", sa.String(255), nullable=False, server_default=""),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        *_ts_cols(),
    )
    op.create_index("ix_divisions_code", "divisions", ["code"])

    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column(
            "role_id",
            sa.Integer,
            sa.ForeignKey("roles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("is_super", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        *_ts_cols(),
    )
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "user_division_map",
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "division_id",
            sa.Integer,
            sa.ForeignKey("divisions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    op.create_table(
        "banks",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("code", sa.String(20), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        *_ts_cols(),
    )
    op.create_index("ix_banks_code", "banks", ["code"])

    op.create_table(
        "salesmen",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("code", sa.String(20), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("email", sa.String(255), nullable=False, server_default=""),
        sa.Column("phone", sa.String(50), nullable=False, server_default=""),
        sa.Column(
            "division_id",
            sa.Integer,
            sa.ForeignKey("divisions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        *_ts_cols(),
    )
    op.create_index("ix_salesmen_code", "salesmen", ["code"])

    op.create_table(
        "customers",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("code", sa.String(20), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("customer_type", sa.String(50), nullable=False, server_default="Retail"),
        sa.Column("phone", sa.String(50), nullable=False, server_default=""),
        sa.Column("email", sa.String(255), nullable=False, server_default=""),
        sa.Column("address", sa.String(500), nullable=False, server_default=""),
        sa.Column(
            "division_id",
            sa.Integer,
            sa.ForeignKey("divisions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "salesman_id",
            sa.Integer,
            sa.ForeignKey("salesmen.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        *_ts_cols(),
    )
    op.create_index("ix_customers_code", "customers", ["code"])

    op.create_table(
        "lawyers",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("firm", sa.String(200), nullable=False, server_default=""),
        sa.Column("email", sa.String(255), nullable=False, server_default=""),
        sa.Column("phone", sa.String(50), nullable=False, server_default=""),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        *_ts_cols(),
    )

    op.create_table(
        "case_types",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("code", sa.String(20), nullable=False, unique=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.String(300), nullable=False, server_default=""),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        *_ts_cols(),
    )
    op.create_index("ix_case_types_code", "case_types", ["code"])


def downgrade() -> None:
    op.drop_index("ix_case_types_code", table_name="case_types")
    op.drop_table("case_types")
    op.drop_table("lawyers")
    op.drop_index("ix_customers_code", table_name="customers")
    op.drop_table("customers")
    op.drop_index("ix_salesmen_code", table_name="salesmen")
    op.drop_table("salesmen")
    op.drop_index("ix_banks_code", table_name="banks")
    op.drop_table("banks")
    op.drop_table("user_division_map")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
    op.drop_index("ix_divisions_code", table_name="divisions")
    op.drop_table("divisions")
    op.drop_index("ix_roles_name", table_name="roles")
    op.drop_table("roles")

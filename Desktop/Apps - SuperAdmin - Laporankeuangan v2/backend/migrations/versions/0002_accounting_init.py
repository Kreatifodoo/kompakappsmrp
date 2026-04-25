"""Accounting module: accounts, journal_entries, journal_lines.

Revision ID: 0002_accounting_init
Revises: 0001_identity_init
Create Date: 2026-04-25

Notes:
- journal_entries / journal_lines are created as plain tables here.
- A follow-up migration will convert them to RANGE-partitioned tables on
  entry_date (monthly) once the partitioning helpers are in place.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_accounting_init"
down_revision: Union[str, None] = "0001_identity_init"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── accounts ─────────────────────────────────────────
    op.create_table(
        "accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code", sa.String(20), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("normal_side", sa.String(10), nullable=False),
        sa.Column(
            "parent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.id", ondelete="SET NULL"),
        ),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("is_system", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("description", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "code", name="uq_accounts_tenant_code"),
        sa.CheckConstraint(
            "type IN ('asset','liability','equity','income','expense')",
            name="ck_accounts_type",
        ),
        sa.CheckConstraint(
            "normal_side IN ('debit','credit')",
            name="ck_accounts_normal_side",
        ),
    )
    op.create_index("ix_accounts_tenant_id", "accounts", ["tenant_id"])
    op.create_index("ix_accounts_tenant_type", "accounts", ["tenant_id", "type"])
    op.create_index("ix_accounts_tenant_parent", "accounts", ["tenant_id", "parent_id"])

    # ── journal_entries ──────────────────────────────────
    op.create_table(
        "journal_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("entry_no", sa.String(30), nullable=False),
        sa.Column("entry_date", sa.Date, nullable=False),
        sa.Column("description", sa.String(500)),
        sa.Column("reference", sa.String(100)),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("source", sa.String(30)),
        sa.Column("source_id", postgresql.UUID(as_uuid=True)),
        sa.Column("created_by", postgresql.UUID(as_uuid=True)),
        sa.Column("posted_by", postgresql.UUID(as_uuid=True)),
        sa.Column("posted_at", sa.DateTime(timezone=True)),
        sa.Column("voided_by", postgresql.UUID(as_uuid=True)),
        sa.Column("voided_at", sa.DateTime(timezone=True)),
        sa.Column("void_reason", sa.String(500)),
        sa.Column("metadata", sa.JSON),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "entry_no", name="uq_journal_entries_tenant_no"),
        sa.CheckConstraint(
            "status IN ('draft','posted','void')",
            name="ck_journal_entries_status",
        ),
    )
    op.create_index("ix_journal_entries_tenant_id", "journal_entries", ["tenant_id"])
    op.create_index("ix_journal_entries_tenant_date", "journal_entries", ["tenant_id", "entry_date"])
    op.create_index("ix_journal_entries_tenant_status", "journal_entries", ["tenant_id", "status"])

    # ── journal_lines ────────────────────────────────────
    op.create_table(
        "journal_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "entry_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("journal_entries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("line_no", sa.Integer, nullable=False),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("description", sa.String(500)),
        sa.Column("debit", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("credit", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.CheckConstraint(
            "(debit >= 0 AND credit >= 0) AND (debit = 0 OR credit = 0)",
            name="ck_journal_lines_debit_xor_credit",
        ),
    )
    op.create_index("ix_journal_lines_tenant_id", "journal_lines", ["tenant_id"])
    op.create_index("ix_journal_lines_tenant_account", "journal_lines", ["tenant_id", "account_id"])
    op.create_index("ix_journal_lines_entry", "journal_lines", ["entry_id"])


def downgrade() -> None:
    op.drop_table("journal_lines")
    op.drop_table("journal_entries")
    op.drop_table("accounts")

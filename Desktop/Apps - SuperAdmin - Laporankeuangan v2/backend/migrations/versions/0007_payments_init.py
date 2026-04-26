"""Payments module: payments + payment_applications tables.

Revision ID: 0007_payments_init
Revises: 0006_account_is_cash
Create Date: 2026-04-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_payments_init"
down_revision: Union[str, None] = "0006_account_is_cash"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

POLICY_NAME = "p_tenant_isolation"


def upgrade() -> None:
    # ── payments ─────────────────────────────────────────
    op.create_table(
        "payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("payment_no", sa.String(30), nullable=False),
        sa.Column("payment_date", sa.Date, nullable=False),
        sa.Column("direction", sa.String(20), nullable=False),
        sa.Column(
            "customer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customers.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "supplier_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("suppliers.id", ondelete="RESTRICT"),
        ),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column(
            "cash_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("reference", sa.String(100)),
        sa.Column("notes", sa.String(1000)),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("journal_entry_id", postgresql.UUID(as_uuid=True)),
        sa.Column("created_by", postgresql.UUID(as_uuid=True)),
        sa.Column("posted_by", postgresql.UUID(as_uuid=True)),
        sa.Column("posted_at", sa.DateTime(timezone=True)),
        sa.Column("voided_by", postgresql.UUID(as_uuid=True)),
        sa.Column("voided_at", sa.DateTime(timezone=True)),
        sa.Column("void_reason", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "payment_no", name="uq_payments_tenant_no"),
        sa.CheckConstraint("direction IN ('receipt','disbursement')", name="ck_payments_direction"),
        sa.CheckConstraint("status IN ('draft','posted','void')", name="ck_payments_status"),
        sa.CheckConstraint(
            "(direction = 'receipt' AND customer_id IS NOT NULL AND supplier_id IS NULL) OR "
            "(direction = 'disbursement' AND supplier_id IS NOT NULL AND customer_id IS NULL)",
            name="ck_payments_party_xor",
        ),
        sa.CheckConstraint("amount > 0", name="ck_payments_amount_positive"),
    )
    op.create_index("ix_payments_tenant_id", "payments", ["tenant_id"])
    op.create_index("ix_payments_tenant_date", "payments", ["tenant_id", "payment_date"])
    op.create_index("ix_payments_tenant_status", "payments", ["tenant_id", "status"])
    op.create_index("ix_payments_customer", "payments", ["tenant_id", "customer_id"])
    op.create_index("ix_payments_supplier", "payments", ["tenant_id", "supplier_id"])

    # ── payment_applications ─────────────────────────────
    op.create_table(
        "payment_applications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "payment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("payments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "sales_invoice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sales_invoices.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "purchase_invoice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("purchase_invoices.id", ondelete="RESTRICT"),
        ),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("voided", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.CheckConstraint("amount > 0", name="ck_payment_applications_amount_positive"),
        sa.CheckConstraint(
            "(sales_invoice_id IS NOT NULL AND purchase_invoice_id IS NULL) OR "
            "(sales_invoice_id IS NULL AND purchase_invoice_id IS NOT NULL)",
            name="ck_payment_applications_invoice_xor",
        ),
    )
    op.create_index("ix_payment_applications_tenant_id", "payment_applications", ["tenant_id"])
    op.create_index("ix_payment_applications_payment", "payment_applications", ["payment_id"])
    op.create_index("ix_payment_applications_sales_invoice", "payment_applications", ["sales_invoice_id"])
    op.create_index(
        "ix_payment_applications_purchase_invoice", "payment_applications", ["purchase_invoice_id"]
    )

    # ── RLS ──────────────────────────────────────────────
    for table in ("payments", "payment_applications"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
        op.execute(
            f"""
            CREATE POLICY {POLICY_NAME} ON {table}
            USING (
                tenant_id::text = current_setting('app.current_tenant', true)
                OR current_setting('app.is_super_admin', true) = 'true'
            )
            WITH CHECK (
                tenant_id::text = current_setting('app.current_tenant', true)
                OR current_setting('app.is_super_admin', true) = 'true'
            );
            """
        )


def downgrade() -> None:
    for table in ("payment_applications", "payments"):
        op.execute(f"DROP POLICY IF EXISTS {POLICY_NAME} ON {table};")
    op.drop_table("payment_applications")
    op.drop_table("payments")

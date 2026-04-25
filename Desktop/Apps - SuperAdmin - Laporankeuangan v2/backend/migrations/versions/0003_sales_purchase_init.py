"""Sales + Purchase modules: customers, suppliers, invoices, account_mappings.

Revision ID: 0003_sales_purchase_init
Revises: 0002_accounting_init
Create Date: 2026-04-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_sales_purchase_init"
down_revision: Union[str, None] = "0002_accounting_init"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _audit_cols() -> list[sa.Column]:
    return [
        sa.Column("created_by", postgresql.UUID(as_uuid=True)),
        sa.Column("posted_by", postgresql.UUID(as_uuid=True)),
        sa.Column("posted_at", sa.DateTime(timezone=True)),
        sa.Column("voided_by", postgresql.UUID(as_uuid=True)),
        sa.Column("voided_at", sa.DateTime(timezone=True)),
        sa.Column("void_reason", sa.String(500)),
    ]


def upgrade() -> None:
    # ── account_mappings ─────────────────────────────────
    op.create_table(
        "account_mappings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("key", sa.String(50), nullable=False),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.UniqueConstraint("tenant_id", "key", name="uq_account_mappings_tenant_key"),
    )
    op.create_index("ix_account_mappings_tenant_id", "account_mappings", ["tenant_id"])

    # ── customers ────────────────────────────────────────
    op.create_table(
        "customers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code", sa.String(30), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("email", sa.String(200)),
        sa.Column("phone", sa.String(50)),
        sa.Column("address", sa.String(500)),
        sa.Column("tax_id", sa.String(50)),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.String(1000)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "code", name="uq_customers_tenant_code"),
    )
    op.create_index("ix_customers_tenant_id", "customers", ["tenant_id"])
    op.create_index("ix_customers_tenant_active", "customers", ["tenant_id", "is_active"])

    # ── suppliers ────────────────────────────────────────
    op.create_table(
        "suppliers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code", sa.String(30), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("email", sa.String(200)),
        sa.Column("phone", sa.String(50)),
        sa.Column("address", sa.String(500)),
        sa.Column("tax_id", sa.String(50)),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.String(1000)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "code", name="uq_suppliers_tenant_code"),
    )
    op.create_index("ix_suppliers_tenant_id", "suppliers", ["tenant_id"])
    op.create_index("ix_suppliers_tenant_active", "suppliers", ["tenant_id", "is_active"])

    # ── sales_invoices ───────────────────────────────────
    op.create_table(
        "sales_invoices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("invoice_no", sa.String(30), nullable=False),
        sa.Column("invoice_date", sa.Date, nullable=False),
        sa.Column("due_date", sa.Date),
        sa.Column(
            "customer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("subtotal", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("tax_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("total", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("paid_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("notes", sa.String(1000)),
        sa.Column(
            "journal_entry_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("journal_entries.id", ondelete="SET NULL"),
        ),
        *_audit_cols(),
        sa.Column("metadata", sa.JSON),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "invoice_no", name="uq_sales_invoices_tenant_no"),
        sa.CheckConstraint(
            "status IN ('draft','posted','paid','void')",
            name="ck_sales_invoices_status",
        ),
    )
    op.create_index("ix_sales_invoices_tenant_id", "sales_invoices", ["tenant_id"])
    op.create_index("ix_sales_invoices_tenant_date", "sales_invoices", ["tenant_id", "invoice_date"])
    op.create_index("ix_sales_invoices_tenant_status", "sales_invoices", ["tenant_id", "status"])
    op.create_index("ix_sales_invoices_customer", "sales_invoices", ["tenant_id", "customer_id"])

    # ── sales_invoice_lines ──────────────────────────────
    op.create_table(
        "sales_invoice_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "invoice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sales_invoices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("line_no", sa.Integer, nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("qty", sa.Numeric(18, 4), nullable=False),
        sa.Column("unit_price", sa.Numeric(18, 4), nullable=False),
        sa.Column("line_total", sa.Numeric(18, 2), nullable=False),
        sa.Column("tax_rate", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("tax_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.CheckConstraint("qty > 0", name="ck_sales_invoice_lines_qty_positive"),
        sa.CheckConstraint("unit_price >= 0", name="ck_sales_invoice_lines_price_nonneg"),
    )
    op.create_index("ix_sales_invoice_lines_tenant_id", "sales_invoice_lines", ["tenant_id"])
    op.create_index("ix_sales_invoice_lines_invoice", "sales_invoice_lines", ["invoice_id"])

    # ── purchase_invoices ────────────────────────────────
    op.create_table(
        "purchase_invoices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("invoice_no", sa.String(30), nullable=False),
        sa.Column("supplier_invoice_no", sa.String(60)),
        sa.Column("invoice_date", sa.Date, nullable=False),
        sa.Column("due_date", sa.Date),
        sa.Column(
            "supplier_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("suppliers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("subtotal", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("tax_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("total", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("paid_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("notes", sa.String(1000)),
        sa.Column(
            "journal_entry_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("journal_entries.id", ondelete="SET NULL"),
        ),
        *_audit_cols(),
        sa.Column("metadata", sa.JSON),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "invoice_no", name="uq_purchase_invoices_tenant_no"),
        sa.CheckConstraint(
            "status IN ('draft','posted','paid','void')",
            name="ck_purchase_invoices_status",
        ),
    )
    op.create_index("ix_purchase_invoices_tenant_id", "purchase_invoices", ["tenant_id"])
    op.create_index("ix_purchase_invoices_tenant_date", "purchase_invoices", ["tenant_id", "invoice_date"])
    op.create_index("ix_purchase_invoices_tenant_status", "purchase_invoices", ["tenant_id", "status"])
    op.create_index("ix_purchase_invoices_supplier", "purchase_invoices", ["tenant_id", "supplier_id"])

    # ── purchase_invoice_lines ───────────────────────────
    op.create_table(
        "purchase_invoice_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "invoice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("purchase_invoices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("line_no", sa.Integer, nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("qty", sa.Numeric(18, 4), nullable=False),
        sa.Column("unit_price", sa.Numeric(18, 4), nullable=False),
        sa.Column("line_total", sa.Numeric(18, 2), nullable=False),
        sa.Column("tax_rate", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("tax_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column(
            "expense_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.id", ondelete="RESTRICT"),
        ),
        sa.CheckConstraint("qty > 0", name="ck_purchase_invoice_lines_qty_positive"),
        sa.CheckConstraint("unit_price >= 0", name="ck_purchase_invoice_lines_price_nonneg"),
    )
    op.create_index("ix_purchase_invoice_lines_tenant_id", "purchase_invoice_lines", ["tenant_id"])
    op.create_index("ix_purchase_invoice_lines_invoice", "purchase_invoice_lines", ["invoice_id"])


def downgrade() -> None:
    op.drop_table("purchase_invoice_lines")
    op.drop_table("purchase_invoices")
    op.drop_table("sales_invoice_lines")
    op.drop_table("sales_invoices")
    op.drop_table("suppliers")
    op.drop_table("customers")
    op.drop_table("account_mappings")

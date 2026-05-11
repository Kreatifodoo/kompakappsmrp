"""Sales Orders module + tenant.fulfillment_mode flag.

Adds sales_orders + sales_order_lines tables to support ERP-style workflow:
  SO (commitment) → DO (physical delivery, in 0018) → SI (invoice) → Payment

Tenant gets fulfillment_mode column (flexible|strict). Existing tenants default
to 'flexible' (backward compat: SI auto-creates stock movement). New tenants
should default to 'strict' via app-level convention.

Revision ID: 0017_sales_orders
Revises: 0016_custom_inventory_ops
Create Date: 2026-05-11
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017_sales_orders"
down_revision: Union[str, None] = "0016_custom_inventory_ops"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

POLICY_NAME = "p_tenant_isolation"


def upgrade() -> None:
    # ── Tenant.fulfillment_mode ─────────────────────────────
    op.add_column(
        "tenants",
        sa.Column(
            "fulfillment_mode",
            sa.String(20),
            nullable=False,
            server_default="flexible",  # backward compat for existing
        ),
    )

    # ── sales_orders ────────────────────────────────────────
    op.create_table(
        "sales_orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("so_no", sa.String(30), nullable=False),
        sa.Column("order_date", sa.Date, nullable=False),
        sa.Column("expected_delivery_date", sa.Date, nullable=True),
        sa.Column(
            "customer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.String(30), nullable=False, server_default="draft"),
        sa.Column("notes", sa.String(1000), nullable=True),
        sa.Column("subtotal", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("tax", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("total", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_reason", sa.String(500), nullable=True),
        sa.UniqueConstraint("tenant_id", "so_no", name="uq_so_tenant_no"),
        sa.CheckConstraint(
            "status IN ('draft','confirmed','partially_delivered','fulfilled','cancelled')",
            name="ck_so_status",
        ),
    )
    op.create_index("ix_so_tenant_status", "sales_orders", ["tenant_id", "status"])
    op.create_index(
        "ix_so_tenant_customer_date", "sales_orders", ["tenant_id", "customer_id", "order_date"]
    )
    op.execute("ALTER TABLE sales_orders ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {POLICY_NAME} ON sales_orders "
        f"USING (tenant_id::text = current_setting('app.tenant_id', true))"
    )

    # ── sales_order_lines ───────────────────────────────────
    op.create_table(
        "sales_order_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "so_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sales_orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("line_no", sa.Integer, nullable=False),
        sa.Column(
            "item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("items.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "warehouse_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("warehouses.id", ondelete="RESTRICT"),
            nullable=True,  # nullable for service items
        ),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("qty_ordered", sa.Numeric(18, 4), nullable=False),
        sa.Column("qty_delivered", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("qty_invoiced", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("unit_price", sa.Numeric(18, 2), nullable=False),
        sa.Column("tax_rate", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("line_total", sa.Numeric(18, 2), nullable=False),
        sa.CheckConstraint("qty_ordered > 0", name="ck_sol_qty_positive"),
        sa.CheckConstraint("qty_delivered >= 0", name="ck_sol_delivered_nonneg"),
        sa.CheckConstraint("qty_invoiced >= 0", name="ck_sol_invoiced_nonneg"),
    )
    op.create_index("ix_sol_so", "sales_order_lines", ["so_id"])


def downgrade() -> None:
    op.execute(f"DROP POLICY IF EXISTS {POLICY_NAME} ON sales_orders")
    op.drop_index("ix_sol_so", table_name="sales_order_lines")
    op.drop_table("sales_order_lines")
    op.drop_index("ix_so_tenant_customer_date", table_name="sales_orders")
    op.drop_index("ix_so_tenant_status", table_name="sales_orders")
    op.drop_table("sales_orders")
    op.drop_column("tenants", "fulfillment_mode")

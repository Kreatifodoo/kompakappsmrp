"""Purchase Orders.

Mirror of Sales Orders for procurement: PO (commitment) → GR (physical receipt
in 0020) → PI (invoice) → Payment.

Revision ID: 0019_purchase_orders
Revises: 0018_delivery_orders
Create Date: 2026-05-11
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019_purchase_orders"
down_revision: Union[str, None] = "0018_delivery_orders"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

POLICY_NAME = "p_tenant_isolation"


def upgrade() -> None:
    op.create_table(
        "purchase_orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("po_no", sa.String(30), nullable=False),
        sa.Column("order_date", sa.Date, nullable=False),
        sa.Column("expected_receipt_date", sa.Date, nullable=True),
        sa.Column(
            "supplier_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("suppliers.id", ondelete="RESTRICT"),
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
        sa.UniqueConstraint("tenant_id", "po_no", name="uq_po_tenant_no"),
        sa.CheckConstraint(
            "status IN ('draft','confirmed','partially_received','fulfilled','cancelled')",
            name="ck_po_status",
        ),
    )
    op.create_index("ix_po_tenant_status", "purchase_orders", ["tenant_id", "status"])
    op.create_index(
        "ix_po_tenant_supplier_date", "purchase_orders", ["tenant_id", "supplier_id", "order_date"]
    )
    op.execute("ALTER TABLE purchase_orders ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {POLICY_NAME} ON purchase_orders "
        f"USING (tenant_id::text = current_setting('app.tenant_id', true))"
    )

    op.create_table(
        "purchase_order_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "po_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("purchase_orders.id", ondelete="CASCADE"),
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
            nullable=True,
        ),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("qty_ordered", sa.Numeric(18, 4), nullable=False),
        sa.Column("qty_received", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("qty_invoiced", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("unit_price", sa.Numeric(18, 2), nullable=False),
        sa.Column("tax_rate", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("line_total", sa.Numeric(18, 2), nullable=False),
        sa.CheckConstraint("qty_ordered > 0", name="ck_pol_qty_positive"),
        sa.CheckConstraint("qty_received >= 0", name="ck_pol_received_nonneg"),
        sa.CheckConstraint("qty_invoiced >= 0", name="ck_pol_invoiced_nonneg"),
    )
    op.create_index("ix_pol_po", "purchase_order_lines", ["po_id"])


def downgrade() -> None:
    op.execute(f"DROP POLICY IF EXISTS {POLICY_NAME} ON purchase_orders")
    op.drop_index("ix_pol_po", table_name="purchase_order_lines")
    op.drop_table("purchase_order_lines")
    op.drop_index("ix_po_tenant_supplier_date", table_name="purchase_orders")
    op.drop_index("ix_po_tenant_status", table_name="purchase_orders")
    op.drop_table("purchase_orders")

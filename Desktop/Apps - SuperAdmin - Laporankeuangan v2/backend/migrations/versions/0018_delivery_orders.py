"""Delivery Orders + link sales_invoices.do_id + new stock_movements sources.

Delivery Order = physical shipment to customer. Creates stock-out + journal
(Dr COGS / Cr Inventory) via existing inventory + accounting services.

Revision ID: 0018_delivery_orders
Revises: 0017_sales_orders
Create Date: 2026-05-11
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018_delivery_orders"
down_revision: Union[str, None] = "0017_sales_orders"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

POLICY_NAME = "p_tenant_isolation"


def upgrade() -> None:
    # ── delivery_orders ─────────────────────────────────────
    op.create_table(
        "delivery_orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("do_no", sa.String(30), nullable=False),
        sa.Column("delivery_date", sa.Date, nullable=False),
        sa.Column(
            "so_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sales_orders.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "warehouse_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("warehouses.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column(
            "journal_entry_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("journal_entries.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("notes", sa.String(1000), nullable=True),
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
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "posted_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("void_reason", sa.String(500), nullable=True),
        sa.UniqueConstraint("tenant_id", "do_no", name="uq_do_tenant_no"),
        sa.CheckConstraint("status IN ('draft','posted','void')", name="ck_do_status"),
    )
    op.create_index("ix_do_tenant_status", "delivery_orders", ["tenant_id", "status"])
    op.create_index("ix_do_so", "delivery_orders", ["so_id"])
    op.execute("ALTER TABLE delivery_orders ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {POLICY_NAME} ON delivery_orders "
        f"USING (tenant_id::text = current_setting('app.tenant_id', true))"
    )

    # ── delivery_order_lines ────────────────────────────────
    op.create_table(
        "delivery_order_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "do_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("delivery_orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "so_line_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sales_order_lines.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("items.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("qty_delivered", sa.Numeric(18, 4), nullable=False),
        # unit_cost snapshotted at post time from stock-out movement
        sa.Column("unit_cost", sa.Numeric(18, 4), nullable=True),
        sa.CheckConstraint("qty_delivered > 0", name="ck_dol_qty_positive"),
    )
    op.create_index("ix_dol_do", "delivery_order_lines", ["do_id"])

    # ── Link sales_invoices to (optional) do_id ─────────────
    op.add_column(
        "sales_invoices",
        sa.Column(
            "do_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("delivery_orders.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_si_do_id", "sales_invoices", ["do_id"])


def downgrade() -> None:
    op.drop_index("ix_si_do_id", table_name="sales_invoices")
    op.drop_column("sales_invoices", "do_id")
    op.drop_index("ix_dol_do", table_name="delivery_order_lines")
    op.drop_table("delivery_order_lines")
    op.execute(f"DROP POLICY IF EXISTS {POLICY_NAME} ON delivery_orders")
    op.drop_index("ix_do_so", table_name="delivery_orders")
    op.drop_index("ix_do_tenant_status", table_name="delivery_orders")
    op.drop_table("delivery_orders")

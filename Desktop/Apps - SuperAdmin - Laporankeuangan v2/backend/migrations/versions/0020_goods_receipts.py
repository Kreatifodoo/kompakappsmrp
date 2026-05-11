"""Goods Receipts + link purchase_invoices.gr_id.

GR = physical receipt from supplier. Creates stock-in + journal
(Dr Inventory / Cr GR-clearing).

Revision ID: 0020_goods_receipts
Revises: 0019_purchase_orders
Create Date: 2026-05-11
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0020_goods_receipts"
down_revision: Union[str, None] = "0019_purchase_orders"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

POLICY_NAME = "p_tenant_isolation"


def upgrade() -> None:
    op.create_table(
        "goods_receipts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("gr_no", sa.String(30), nullable=False),
        sa.Column("receipt_date", sa.Date, nullable=False),
        sa.Column(
            "po_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("purchase_orders.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "warehouse_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("warehouses.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        # journal_entries is partitioned — plain UUID, no FK
        sa.Column("journal_entry_id", postgresql.UUID(as_uuid=True), nullable=True),
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
        sa.UniqueConstraint("tenant_id", "gr_no", name="uq_gr_tenant_no"),
        sa.CheckConstraint("status IN ('draft','posted','void')", name="ck_gr_status"),
    )
    op.create_index("ix_gr_tenant_status", "goods_receipts", ["tenant_id", "status"])
    op.create_index("ix_gr_po", "goods_receipts", ["po_id"])
    op.execute("ALTER TABLE goods_receipts ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {POLICY_NAME} ON goods_receipts "
        f"USING (tenant_id::text = current_setting('app.tenant_id', true))"
    )

    op.create_table(
        "goods_receipt_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "gr_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("goods_receipts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "po_line_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("purchase_order_lines.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("items.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("qty_received", sa.Numeric(18, 4), nullable=False),
        sa.Column("unit_cost", sa.Numeric(18, 4), nullable=False),
        sa.CheckConstraint("qty_received > 0", name="ck_grl_qty_positive"),
    )
    op.create_index("ix_grl_gr", "goods_receipt_lines", ["gr_id"])

    # Link purchase_invoices to GR (optional)
    op.add_column(
        "purchase_invoices",
        sa.Column(
            "gr_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("goods_receipts.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_pi_gr_id", "purchase_invoices", ["gr_id"])


def downgrade() -> None:
    op.drop_index("ix_pi_gr_id", table_name="purchase_invoices")
    op.drop_column("purchase_invoices", "gr_id")
    op.drop_index("ix_grl_gr", table_name="goods_receipt_lines")
    op.drop_table("goods_receipt_lines")
    op.execute(f"DROP POLICY IF EXISTS {POLICY_NAME} ON goods_receipts")
    op.drop_index("ix_gr_po", table_name="goods_receipts")
    op.drop_index("ix_gr_tenant_status", table_name="goods_receipts")
    op.drop_table("goods_receipts")

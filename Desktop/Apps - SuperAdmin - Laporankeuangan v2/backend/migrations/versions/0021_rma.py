"""RMA (Return Merchandise Authorization).

Two flavours:
- customer_return: customer returns goods → stock-in + reverse COGS
  (Dr Inventory / Cr COGS). Sourced from a DO.
- supplier_return: we return to supplier → stock-out + reverse receipt
  (Dr GR-clearing or AP / Cr Inventory). Sourced from a GR.

Revision ID: 0021_rma
Revises: 0020_goods_receipts
Create Date: 2026-05-11
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0021_rma"
down_revision: Union[str, None] = "0020_goods_receipts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

POLICY_NAME = "p_tenant_isolation"


def upgrade() -> None:
    op.create_table(
        "rmas",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("rma_no", sa.String(30), nullable=False),
        sa.Column("rma_type", sa.String(20), nullable=False),
        sa.Column("rma_date", sa.Date, nullable=False),
        sa.Column(
            "source_do_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("delivery_orders.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "source_gr_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("goods_receipts.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "warehouse_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("warehouses.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("reason", sa.String(500), nullable=True),
        # journal_entries partitioned — plain UUID
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
        sa.UniqueConstraint("tenant_id", "rma_no", name="uq_rma_tenant_no"),
        sa.CheckConstraint(
            "rma_type IN ('customer_return','supplier_return')", name="ck_rma_type"
        ),
        sa.CheckConstraint("status IN ('draft','posted','void')", name="ck_rma_status"),
        # XOR: customer_return ↔ source_do_id; supplier_return ↔ source_gr_id
        sa.CheckConstraint(
            "(rma_type='customer_return' AND source_do_id IS NOT NULL AND source_gr_id IS NULL) "
            "OR (rma_type='supplier_return' AND source_gr_id IS NOT NULL AND source_do_id IS NULL)",
            name="ck_rma_source_xor",
        ),
    )
    op.create_index("ix_rma_tenant_status", "rmas", ["tenant_id", "status"])
    op.create_index("ix_rma_source_do", "rmas", ["source_do_id"])
    op.create_index("ix_rma_source_gr", "rmas", ["source_gr_id"])
    op.execute("ALTER TABLE rmas ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {POLICY_NAME} ON rmas "
        f"USING (tenant_id::text = current_setting('app.tenant_id', true))"
    )

    op.create_table(
        "rma_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "rma_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("rmas.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Either source_do_line_id OR source_gr_line_id — never both
        sa.Column(
            "source_do_line_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("delivery_order_lines.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "source_gr_line_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("goods_receipt_lines.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("items.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("qty_returned", sa.Numeric(18, 4), nullable=False),
        sa.Column("unit_cost", sa.Numeric(18, 4), nullable=False),
        sa.CheckConstraint("qty_returned > 0", name="ck_rmal_qty_positive"),
        sa.CheckConstraint(
            "(source_do_line_id IS NOT NULL) <> (source_gr_line_id IS NOT NULL)",
            name="ck_rmal_source_xor",
        ),
    )
    op.create_index("ix_rmal_rma", "rma_lines", ["rma_id"])


def downgrade() -> None:
    op.drop_index("ix_rmal_rma", table_name="rma_lines")
    op.drop_table("rma_lines")
    op.execute(f"DROP POLICY IF EXISTS {POLICY_NAME} ON rmas")
    op.drop_index("ix_rma_source_gr", table_name="rmas")
    op.drop_index("ix_rma_source_do", table_name="rmas")
    op.drop_index("ix_rma_tenant_status", table_name="rmas")
    op.drop_table("rmas")

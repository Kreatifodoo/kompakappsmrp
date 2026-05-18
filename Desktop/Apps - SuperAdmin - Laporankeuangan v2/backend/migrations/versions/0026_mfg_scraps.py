"""Manufacturing scrap module (Sprint M6).

Records inventory loss due to spoilage, defects, or QC reject — either
during a manufacturing run (mo_id set) or as a standalone write-off.
Each posted scrap event triggers:
  • stock_movements row (out) per line via InventoryService
  • one journal_entry: Dr mfg_scrap_loss / Cr inventory

The journal stays simple even when mo_id is set — the loss hits the
P&L immediately rather than washing through WIP. Linking to an MO is
purely informational (for the variance / efficiency reports).

Revision ID: 0026_mfg_scraps
Revises: 0025_work_centers
Create Date: 2026-05-13
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0026_mfg_scraps"
down_revision: Union[str, None] = "0025_work_centers"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

POLICY_NAME = "p_tenant_isolation"


def upgrade() -> None:
    op.create_table(
        "mfg_scraps",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("scrap_no", sa.String(30), nullable=False),
        sa.Column("scrap_date", sa.Date, nullable=False),
        sa.Column(
            "warehouse_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("warehouses.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "mo_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("manufacturing_orders.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("notes", sa.String(1000), nullable=True),
        sa.Column(
            "status", sa.String(20), nullable=False, server_default="draft"
        ),
        # journal_entries partitioned — plain UUID
        sa.Column("journal_entry_id", postgresql.UUID(as_uuid=True), nullable=True),
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
        sa.UniqueConstraint("tenant_id", "scrap_no", name="uq_scrap_tenant_no"),
        sa.CheckConstraint(
            "status IN ('draft','posted','void')", name="ck_scrap_status"
        ),
    )
    op.create_index("ix_scrap_tenant_status", "mfg_scraps", ["tenant_id", "status"])
    op.create_index("ix_scrap_mo", "mfg_scraps", ["mo_id"])
    op.execute("ALTER TABLE mfg_scraps ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {POLICY_NAME} ON mfg_scraps "
        f"USING (tenant_id::text = current_setting('app.tenant_id', true))"
    )

    op.create_table(
        "mfg_scrap_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "scrap_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("mfg_scraps.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("items.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("qty", sa.Numeric(18, 4), nullable=False),
        sa.Column(
            "unit_cost", sa.Numeric(18, 4), nullable=False, server_default="0"
        ),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.CheckConstraint("qty > 0", name="ck_scrapl_qty_positive"),
    )
    op.create_index("ix_scrapl_scrap", "mfg_scrap_lines", ["scrap_id"])

    # Extend stock_movements.source CHECK
    op.execute("ALTER TABLE stock_movements DROP CONSTRAINT IF EXISTS ck_stock_movements_source")
    op.execute(
        "ALTER TABLE stock_movements ADD CONSTRAINT ck_stock_movements_source CHECK ("
        "source IN ("
        "'manual','sales_invoice','purchase_invoice','delivery_order','goods_receipt',"
        "'customer_return','supplier_return',"
        "'inv_op_receipt','inv_op_delivery','inv_op_usage','inv_op_adjust_in','inv_op_adjust_out',"
        "'inv_op_return_receipt','inv_op_return_delivery','stock_transfer',"
        "'custom_op','delivery_order_void','goods_receipt_void',"
        "'customer_return_void','supplier_return_void','void_sales_invoice','void_purchase_invoice',"
        "'mfg_issue','mfg_receipt','mfg_issue_void','mfg_receipt_void',"
        "'mfg_scrap','mfg_scrap_void'"
        "))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE stock_movements DROP CONSTRAINT IF EXISTS ck_stock_movements_source")
    # (Re-create previous constraint without scrap sources — keep simple, ops re-run if needed)
    op.execute(
        "ALTER TABLE stock_movements ADD CONSTRAINT ck_stock_movements_source CHECK ("
        "source IN ("
        "'manual','sales_invoice','purchase_invoice','delivery_order','goods_receipt',"
        "'customer_return','supplier_return',"
        "'inv_op_receipt','inv_op_delivery','inv_op_usage','inv_op_adjust_in','inv_op_adjust_out',"
        "'inv_op_return_receipt','inv_op_return_delivery','stock_transfer',"
        "'custom_op','delivery_order_void','goods_receipt_void',"
        "'customer_return_void','supplier_return_void','void_sales_invoice','void_purchase_invoice',"
        "'mfg_issue','mfg_receipt','mfg_issue_void','mfg_receipt_void'"
        "))"
    )
    op.drop_index("ix_scrapl_scrap", table_name="mfg_scrap_lines")
    op.drop_table("mfg_scrap_lines")
    op.execute(f"DROP POLICY IF EXISTS {POLICY_NAME} ON mfg_scraps")
    op.drop_index("ix_scrap_mo", table_name="mfg_scraps")
    op.drop_index("ix_scrap_tenant_status", table_name="mfg_scraps")
    op.drop_table("mfg_scraps")

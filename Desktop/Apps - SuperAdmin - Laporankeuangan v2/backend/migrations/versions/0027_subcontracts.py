"""Subcontracting / Maklon module (Manufacturing).

Records work sent to a third-party maklon: we ship raw materials, they
process and return finished goods, we owe them a service fee.

Lifecycle: draft → issued → received | cancelled.

Postings (per status transition):
  • confirm-and-issue: stock-out raw materials @ inventory avg_cost,
    journal Dr WIP / Cr Inventory @ total raw cost.
  • receive:           stock-in finished goods @ (raw + fee), journal
    Dr Inventory-FG / Cr WIP (raw portion) / Cr AP (fee portion).
  • cancel from issued: reverse stock-out + reverse issue journal.

The fee goes straight to AP as a payable to the subcontractor; the
user clears it through the normal Payment flow. We piggyback on the
existing `wip` and `ap` mappings — no new mapping key needed.

Revision ID: 0027_subcontracts
Revises: 0026_mfg_scraps
Create Date: 2026-05-13
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0027_subcontracts"
down_revision: Union[str, None] = "0026_mfg_scraps"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

POLICY_NAME = "p_tenant_isolation"


def upgrade() -> None:
    op.create_table(
        "subcontract_orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sco_no", sa.String(30), nullable=False),
        sa.Column("sco_date", sa.Date, nullable=False),
        sa.Column(
            "supplier_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("suppliers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "output_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("items.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "warehouse_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("warehouses.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("qty_planned", sa.Numeric(18, 4), nullable=False),
        sa.Column(
            "qty_received", sa.Numeric(18, 4), nullable=False, server_default="0"
        ),
        sa.Column(
            "fee_per_unit", sa.Numeric(18, 2), nullable=False, server_default="0"
        ),
        sa.Column("fee_total", sa.Numeric(18, 2), nullable=True),
        sa.Column("expected_return_date", sa.Date, nullable=True),
        sa.Column(
            "status", sa.String(20), nullable=False, server_default="draft"
        ),
        # journal_entries partitioned — plain UUID
        sa.Column("issue_journal_entry_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("receipt_journal_entry_id", postgresql.UUID(as_uuid=True), nullable=True),
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
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_reason", sa.String(500), nullable=True),
        sa.UniqueConstraint("tenant_id", "sco_no", name="uq_sco_tenant_no"),
        sa.CheckConstraint(
            "status IN ('draft','issued','received','cancelled')", name="ck_sco_status"
        ),
        sa.CheckConstraint("qty_planned > 0", name="ck_sco_qty_planned_positive"),
        sa.CheckConstraint("fee_per_unit >= 0", name="ck_sco_fee_nonneg"),
    )
    op.create_index("ix_sco_tenant_status", "subcontract_orders", ["tenant_id", "status"])
    op.create_index("ix_sco_supplier", "subcontract_orders", ["supplier_id"])
    op.execute("ALTER TABLE subcontract_orders ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {POLICY_NAME} ON subcontract_orders "
        f"USING (tenant_id::text = current_setting('app.tenant_id', true))"
    )

    op.create_table(
        "subcontract_components",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "sco_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("subcontract_orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("items.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("qty_planned", sa.Numeric(18, 4), nullable=False),
        sa.Column(
            "qty_issued", sa.Numeric(18, 4), nullable=False, server_default="0"
        ),
        sa.Column(
            "unit_cost", sa.Numeric(18, 4), nullable=False, server_default="0"
        ),
        sa.CheckConstraint("qty_planned > 0", name="ck_scoc_qty_positive"),
    )
    op.create_index("ix_scoc_sco", "subcontract_components", ["sco_id"])

    # Extend stock_movements.source CHECK with subcontract values
    op.execute("ALTER TABLE stock_movements DROP CONSTRAINT IF EXISTS ck_stock_movements_source")
    op.execute(
        "ALTER TABLE stock_movements ADD CONSTRAINT ck_stock_movements_source CHECK ("
        "source IN ("
        "'manual','adjustment','sales_invoice','purchase_invoice','delivery_order','goods_receipt',"
        "'customer_return','supplier_return',"
        "'inv_op_receipt','inv_op_delivery','inv_op_usage','inv_op_adjust_in','inv_op_adjust_out',"
        "'inv_op_return_receipt','inv_op_return_delivery','stock_transfer','void_stock_transfer',"
        "'custom_op','delivery_order_void','goods_receipt_void',"
        "'customer_return_void','supplier_return_void','void_sales_invoice','void_purchase_invoice',"
        "'mfg_issue','mfg_receipt','mfg_issue_void','mfg_receipt_void',"
        "'mfg_scrap','mfg_scrap_void',"
        "'subcontract_issue','subcontract_receipt','subcontract_issue_void'"
        "))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE stock_movements DROP CONSTRAINT IF EXISTS ck_stock_movements_source")
    op.execute(
        "ALTER TABLE stock_movements ADD CONSTRAINT ck_stock_movements_source CHECK ("
        "source IN ("
        "'manual','adjustment','sales_invoice','purchase_invoice','delivery_order','goods_receipt',"
        "'customer_return','supplier_return',"
        "'inv_op_receipt','inv_op_delivery','inv_op_usage','inv_op_adjust_in','inv_op_adjust_out',"
        "'inv_op_return_receipt','inv_op_return_delivery','stock_transfer','void_stock_transfer',"
        "'custom_op','delivery_order_void','goods_receipt_void',"
        "'customer_return_void','supplier_return_void','void_sales_invoice','void_purchase_invoice',"
        "'mfg_issue','mfg_receipt','mfg_issue_void','mfg_receipt_void',"
        "'mfg_scrap','mfg_scrap_void'"
        "))"
    )
    op.drop_index("ix_scoc_sco", table_name="subcontract_components")
    op.drop_table("subcontract_components")
    op.execute(f"DROP POLICY IF EXISTS {POLICY_NAME} ON subcontract_orders")
    op.drop_index("ix_sco_supplier", table_name="subcontract_orders")
    op.drop_index("ix_sco_tenant_status", table_name="subcontract_orders")
    op.drop_table("subcontract_orders")

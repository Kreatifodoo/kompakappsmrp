"""Manufacturing Orders + MO Components (Sprint M2).

A Manufacturing Order (MO) is one production run for a BOM-produced item.
On completion it triggers two journal entries:
  Dr Inventory FG / Cr WIP  (FG receipt @ total cost / qty_produced)
  Dr WIP          / Cr Inventory raw  (material issue at consumption time)

stock_movements gains four new `source` string values (no CHECK constraint
on the source column — values are free-form). Documented here for grep:
  - 'mfg_issue'        raw material out into WIP
  - 'mfg_receipt'      finished goods in from WIP
  - 'mfg_issue_void'   reverse of issue (on MO cancel)
  - 'mfg_receipt_void' reverse of receipt (not used in MVP — done MO is locked)

Revision ID: 0023_mfg_orders
Revises: 0022_boms
Create Date: 2026-05-12
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0023_mfg_orders"
down_revision: Union[str, None] = "0022_boms"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

POLICY_NAME = "p_tenant_isolation"


def upgrade() -> None:
    op.create_table(
        "manufacturing_orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("mo_no", sa.String(30), nullable=False),
        sa.Column(
            "bom_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("boms.id", ondelete="RESTRICT"),
            nullable=False,
        ),
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
            nullable=False,
        ),
        sa.Column("qty_planned", sa.Numeric(18, 4), nullable=False),
        sa.Column(
            "qty_produced", sa.Numeric(18, 4), nullable=False, server_default="0"
        ),
        sa.Column("planned_start", sa.Date, nullable=True),
        sa.Column("planned_end", sa.Date, nullable=True),
        sa.Column("actual_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status", sa.String(20), nullable=False, server_default="draft"
        ),
        sa.Column(
            "backflush", sa.Boolean, nullable=False, server_default=sa.text("true")
        ),
        sa.Column("notes", sa.String(1000), nullable=True),
        # journals are partitioned (composite PK) — plain UUIDs, no FK
        sa.Column(
            "issue_journal_entry_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column(
            "receipt_journal_entry_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
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
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_reason", sa.String(500), nullable=True),
        sa.UniqueConstraint("tenant_id", "mo_no", name="uq_mo_tenant_no"),
        sa.CheckConstraint(
            "status IN ('draft','confirmed','in_progress','done','cancelled')",
            name="ck_mo_status",
        ),
        sa.CheckConstraint("qty_planned > 0", name="ck_mo_qty_planned_positive"),
    )
    op.create_index(
        "ix_mo_tenant_status", "manufacturing_orders", ["tenant_id", "status"]
    )
    op.create_index("ix_mo_bom", "manufacturing_orders", ["bom_id"])
    op.execute("ALTER TABLE manufacturing_orders ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {POLICY_NAME} ON manufacturing_orders "
        f"USING (tenant_id::text = current_setting('app.tenant_id', true))"
    )

    op.create_table(
        "mo_components",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "mo_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("manufacturing_orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "bom_line_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("bom_lines.id", ondelete="SET NULL"),
            nullable=True,
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
        sa.CheckConstraint("qty_planned > 0", name="ck_moc_qty_planned_positive"),
    )
    op.create_index("ix_moc_mo", "mo_components", ["mo_id"])


def downgrade() -> None:
    op.drop_index("ix_moc_mo", table_name="mo_components")
    op.drop_table("mo_components")
    op.execute(f"DROP POLICY IF EXISTS {POLICY_NAME} ON manufacturing_orders")
    op.drop_index("ix_mo_bom", table_name="manufacturing_orders")
    op.drop_index("ix_mo_tenant_status", table_name="manufacturing_orders")
    op.drop_table("manufacturing_orders")

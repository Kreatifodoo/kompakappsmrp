"""Lot / Batch tracking (Inventory).

MVP design:
  • Per-item opt-in: items.is_lot_tracked. Items without the flag
    continue to behave exactly as before — no lot dimension.
  • Each lot is a (tenant, item, warehouse, lot_no) row holding the
    original receipt qty, the current remaining qty, and optional
    mfg_date / expiry_date.
  • stock_movements gains a nullable lot_id. Service code populates
    it: on inflow it creates (or picks) a lot, on outflow it
    auto-FEFOs by (expiry_date NULLS LAST, mfg_date NULLS LAST,
    created_at) — oldest-expiring first.

Items.shelf_life_days is added so MO complete + GR can auto-stamp
the lot's expiry_date when the user doesn't supply one.

Revision ID: 0028_stock_lots
Revises: 0027_subcontracts
Create Date: 2026-05-13
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0028_stock_lots"
down_revision: Union[str, None] = "0027_subcontracts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

POLICY_NAME = "p_tenant_isolation"


def upgrade() -> None:
    op.add_column(
        "items",
        sa.Column(
            "is_lot_tracked", sa.Boolean,
            nullable=False, server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "items",
        sa.Column("shelf_life_days", sa.Integer, nullable=True),
    )

    op.create_table(
        "stock_lots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
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
        sa.Column("lot_no", sa.String(60), nullable=False),
        sa.Column("mfg_date", sa.Date, nullable=True),
        sa.Column("expiry_date", sa.Date, nullable=True),
        sa.Column("qty_received", sa.Numeric(18, 4), nullable=False),
        sa.Column(
            "qty_remaining", sa.Numeric(18, 4), nullable=False, server_default="0"
        ),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "tenant_id", "item_id", "warehouse_id", "lot_no",
            name="uq_lot_tenant_item_wh_no",
        ),
        sa.CheckConstraint("qty_received >= 0", name="ck_lot_received_nonneg"),
        sa.CheckConstraint("qty_remaining >= 0", name="ck_lot_remaining_nonneg"),
    )
    op.create_index(
        "ix_lot_tenant_item_wh", "stock_lots", ["tenant_id", "item_id", "warehouse_id"]
    )
    op.create_index(
        "ix_lot_expiry", "stock_lots", ["tenant_id", "expiry_date"]
    )
    op.execute("ALTER TABLE stock_lots ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {POLICY_NAME} ON stock_lots "
        f"USING (tenant_id::text = current_setting('app.tenant_id', true))"
    )

    op.add_column(
        "stock_movements",
        sa.Column(
            "lot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("stock_lots.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.create_index("ix_movement_lot", "stock_movements", ["lot_id"])


def downgrade() -> None:
    op.drop_index("ix_movement_lot", table_name="stock_movements")
    op.drop_column("stock_movements", "lot_id")
    op.execute(f"DROP POLICY IF EXISTS {POLICY_NAME} ON stock_lots")
    op.drop_index("ix_lot_expiry", table_name="stock_lots")
    op.drop_index("ix_lot_tenant_item_wh", table_name="stock_lots")
    op.drop_table("stock_lots")
    op.drop_column("items", "shelf_life_days")
    op.drop_column("items", "is_lot_tracked")

"""Inventory module: warehouses, items, stock_movements, stock_balances.

Revision ID: 0011_inventory_init
Revises: 0010_period_close
Create Date: 2026-04-27
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_inventory_init"
down_revision: Union[str, None] = "0010_period_close"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

POLICY_NAME = "p_tenant_isolation"


def upgrade() -> None:
    # ── warehouses ───────────────────────────────────────
    op.create_table(
        "warehouses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code", sa.String(30), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("is_default", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("tenant_id", "code", name="uq_warehouses_tenant_code"),
    )
    op.create_index("ix_warehouses_tenant_id", "warehouses", ["tenant_id"])
    op.create_index(
        "ix_warehouses_tenant_active", "warehouses", ["tenant_id", "is_active"]
    )

    # ── items ────────────────────────────────────────────
    op.create_table(
        "items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sku", sa.String(60), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.String(1000)),
        sa.Column("type", sa.String(20), nullable=False, server_default="stock"),
        sa.Column("unit", sa.String(20), nullable=False, server_default="pcs"),
        sa.Column(
            "default_unit_price",
            sa.Numeric(18, 2),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "default_unit_cost",
            sa.Numeric(18, 2),
            nullable=False,
            server_default="0",
        ),
        sa.Column("min_stock", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("tenant_id", "sku", name="uq_items_tenant_sku"),
        sa.CheckConstraint(
            "type IN ('stock','service','non_inventory')", name="ck_items_type"
        ),
    )
    op.create_index("ix_items_tenant_id", "items", ["tenant_id"])
    op.create_index("ix_items_tenant_active", "items", ["tenant_id", "is_active"])
    op.create_index("ix_items_tenant_type", "items", ["tenant_id", "type"])

    # ── stock_movements ──────────────────────────────────
    op.create_table(
        "stock_movements",
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
        sa.Column("movement_date", sa.Date, nullable=False),
        sa.Column("direction", sa.String(20), nullable=False),
        sa.Column("qty", sa.Numeric(18, 4), nullable=False),
        sa.Column("unit_cost", sa.Numeric(18, 4), nullable=False),
        sa.Column("total_cost", sa.Numeric(18, 2), nullable=False),
        sa.Column(
            "source", sa.String(30), nullable=False, server_default="adjustment"
        ),
        sa.Column("source_id", postgresql.UUID(as_uuid=True)),
        sa.Column("notes", sa.String(500)),
        sa.Column("qty_after", sa.Numeric(18, 4), nullable=False),
        sa.Column("avg_cost_after", sa.Numeric(18, 4), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "direction IN ('in','out','adjust_in','adjust_out')",
            name="ck_stock_movements_direction",
        ),
        sa.CheckConstraint("qty > 0", name="ck_stock_movements_qty_positive"),
        sa.CheckConstraint(
            "unit_cost >= 0", name="ck_stock_movements_unit_cost_nonneg"
        ),
    )
    op.create_index("ix_stock_movements_tenant_id", "stock_movements", ["tenant_id"])
    op.create_index(
        "ix_stock_movements_tenant_item_date",
        "stock_movements",
        ["tenant_id", "item_id", "movement_date"],
    )
    op.create_index(
        "ix_stock_movements_tenant_warehouse_date",
        "stock_movements",
        ["tenant_id", "warehouse_id", "movement_date"],
    )
    op.create_index(
        "ix_stock_movements_source",
        "stock_movements",
        ["tenant_id", "source", "source_id"],
    )

    # ── stock_balances ───────────────────────────────────
    op.create_table(
        "stock_balances",
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "warehouse_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("warehouses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("on_hand_qty", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("avg_cost", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id", "item_id", "warehouse_id", name="pk_stock_balances"
        ),
    )

    # ── RLS ──────────────────────────────────────────────
    for table in ("warehouses", "items", "stock_movements", "stock_balances"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
        op.execute(
            f"""
            CREATE POLICY {POLICY_NAME} ON {table}
            USING (
                tenant_id::text = current_setting('app.current_tenant', true)
                OR current_setting('app.is_super_admin', true) = 'true'
            )
            WITH CHECK (
                tenant_id::text = current_setting('app.current_tenant', true)
                OR current_setting('app.is_super_admin', true) = 'true'
            );
            """
        )


def downgrade() -> None:
    for table in ("stock_balances", "stock_movements", "items", "warehouses"):
        op.execute(f"DROP POLICY IF EXISTS {POLICY_NAME} ON {table};")
    op.drop_table("stock_balances")
    op.drop_table("stock_movements")
    op.drop_table("items")
    op.drop_table("warehouses")

"""Add tenants.costing_method + stock_cost_layers table.

Revision ID: 0013_costing_method
Revises: 0012_inventory_invoice_lines
Create Date: 2026-04-28

Costing methods:
- avg (default): weighted-average; layers table stays empty
- fifo: first-in first-out; outflows consume layers in received_at ASC
- lifo: last-in first-out; outflows consume layers in received_at DESC
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013_costing_method"
down_revision: Union[str, None] = "0012_inventory_invoice_lines"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

POLICY_NAME = "p_tenant_isolation"


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column(
            "costing_method",
            sa.String(10),
            nullable=False,
            server_default="avg",
        ),
    )
    op.create_check_constraint(
        "ck_tenants_costing_method",
        "tenants",
        "costing_method IN ('avg','fifo','lifo')",
    )

    op.create_table(
        "stock_cost_layers",
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
            sa.ForeignKey("items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "warehouse_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("warehouses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_movement_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("stock_movements.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("original_qty", sa.Numeric(18, 4), nullable=False),
        sa.Column("remaining_qty", sa.Numeric(18, 4), nullable=False),
        sa.Column("unit_cost", sa.Numeric(18, 4), nullable=False),
        sa.Column("is_exhausted", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("original_qty > 0", name="ck_stock_cost_layers_orig_positive"),
        sa.CheckConstraint(
            "remaining_qty >= 0 AND remaining_qty <= original_qty",
            name="ck_stock_cost_layers_remaining_bounds",
        ),
        sa.CheckConstraint("unit_cost >= 0", name="ck_stock_cost_layers_unit_cost_nonneg"),
    )
    op.create_index(
        "ix_stock_cost_layers_tenant_id", "stock_cost_layers", ["tenant_id"]
    )
    op.create_index(
        "ix_stock_cost_layers_consume",
        "stock_cost_layers",
        ["tenant_id", "item_id", "warehouse_id", "is_exhausted", "received_at"],
    )

    op.execute("ALTER TABLE stock_cost_layers ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE stock_cost_layers FORCE ROW LEVEL SECURITY;")
    op.execute(
        f"""
        CREATE POLICY {POLICY_NAME} ON stock_cost_layers
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
    op.execute(f"DROP POLICY IF EXISTS {POLICY_NAME} ON stock_cost_layers;")
    op.drop_table("stock_cost_layers")
    op.drop_constraint("ck_tenants_costing_method", "tenants", type_="check")
    op.drop_column("tenants", "costing_method")

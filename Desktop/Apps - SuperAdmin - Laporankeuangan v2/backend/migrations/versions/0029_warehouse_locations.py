"""Warehouse Locations (sub-locations within a warehouse).

Each warehouse can have N locations (rak / bin / zone). Stock balance
stays at (item, warehouse) granularity for now — locations are
organizational metadata you can attach to movements later if needed.

Revision ID: 0029_warehouse_locations
Revises: 0028_stock_lots
Create Date: 2026-05-13
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0029_warehouse_locations"
down_revision: Union[str, None] = "0028_stock_lots"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

POLICY_NAME = "p_tenant_isolation"


def upgrade() -> None:
    op.create_table(
        "warehouse_locations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "warehouse_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("warehouses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column(
            "is_active", sa.Boolean, nullable=False, server_default=sa.text("true")
        ),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("warehouse_id", "code", name="uq_wh_loc_wh_code"),
    )
    op.create_index("ix_wh_loc_wh", "warehouse_locations", ["warehouse_id"])
    op.execute("ALTER TABLE warehouse_locations ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {POLICY_NAME} ON warehouse_locations "
        f"USING (tenant_id::text = current_setting('app.tenant_id', true))"
    )


def downgrade() -> None:
    op.execute(f"DROP POLICY IF EXISTS {POLICY_NAME} ON warehouse_locations")
    op.drop_index("ix_wh_loc_wh", table_name="warehouse_locations")
    op.drop_table("warehouse_locations")

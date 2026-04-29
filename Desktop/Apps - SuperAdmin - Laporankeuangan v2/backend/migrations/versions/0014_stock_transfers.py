"""Inter-warehouse stock transfers.

Revision ID: 0014_stock_transfers
Revises: 0013_costing_method
Create Date: 2026-04-29
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014_stock_transfers"
down_revision: Union[str, None] = "0013_costing_method"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

POLICY_NAME = "p_tenant_isolation"


def upgrade() -> None:
    op.create_table(
        "stock_transfers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("transfer_no", sa.String(30), nullable=False),
        sa.Column("transfer_date", sa.Date, nullable=False),
        sa.Column(
            "source_warehouse_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("warehouses.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "destination_warehouse_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("warehouses.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="posted"),
        sa.Column("notes", sa.String(1000)),
        sa.Column("created_by", postgresql.UUID(as_uuid=True)),
        sa.Column("voided_by", postgresql.UUID(as_uuid=True)),
        sa.Column("voided_at", sa.DateTime(timezone=True)),
        sa.Column("void_reason", sa.String(500)),
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
        sa.UniqueConstraint(
            "tenant_id", "transfer_no", name="uq_stock_transfers_tenant_no"
        ),
        sa.CheckConstraint(
            "status IN ('posted','void')", name="ck_stock_transfers_status"
        ),
        sa.CheckConstraint(
            "source_warehouse_id <> destination_warehouse_id",
            name="ck_stock_transfers_distinct_warehouses",
        ),
    )
    op.create_index("ix_stock_transfers_tenant_id", "stock_transfers", ["tenant_id"])
    op.create_index(
        "ix_stock_transfers_tenant_date",
        "stock_transfers",
        ["tenant_id", "transfer_date"],
    )
    op.create_index(
        "ix_stock_transfers_tenant_status",
        "stock_transfers",
        ["tenant_id", "status"],
    )

    op.create_table(
        "stock_transfer_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "transfer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("stock_transfers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("line_no", sa.Integer, nullable=False),
        sa.Column(
            "item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("items.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("qty", sa.Numeric(18, 4), nullable=False),
        sa.Column("unit_cost", sa.Numeric(18, 4), nullable=False),
        sa.Column("notes", sa.String(500)),
        sa.CheckConstraint("qty > 0", name="ck_stock_transfer_lines_qty_positive"),
    )
    op.create_index(
        "ix_stock_transfer_lines_tenant_id", "stock_transfer_lines", ["tenant_id"]
    )
    op.create_index(
        "ix_stock_transfer_lines_transfer", "stock_transfer_lines", ["transfer_id"]
    )

    for table in ("stock_transfers", "stock_transfer_lines"):
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
    for table in ("stock_transfer_lines", "stock_transfers"):
        op.execute(f"DROP POLICY IF EXISTS {POLICY_NAME} ON {table};")
    op.drop_table("stock_transfer_lines")
    op.drop_table("stock_transfers")

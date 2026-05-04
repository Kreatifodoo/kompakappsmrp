"""Custom inventory operations table — user-defined stock operations beyond
the 7 built-in defaults (receipt/delivery/usage/adjust_in/adjust_out/return_*).

Each row defines one custom operation with its own label, direction, allowed
contra account types, default contra account, and display order. The frontend
merges these with the hardcoded built-ins on the Operasi Stok form.

Revision ID: 0016_custom_inventory_ops
Revises: 0015_pos_init
Create Date: 2026-05-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016_custom_inventory_ops"
down_revision: Union[str, None] = "0015_pos_init"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

POLICY_NAME = "p_tenant_isolation"


def upgrade() -> None:
    op.create_table(
        "custom_inventory_operations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("key", sa.String(50), nullable=False),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        # Direction must match MovementDirection enum: in/out/adjust_in/adjust_out
        sa.Column("direction", sa.String(20), nullable=False),
        # Allowed contra account types — JSON array of strings like ['expense','asset']
        sa.Column(
            "contra_account_types",
            postgresql.ARRAY(sa.String(20)),
            nullable=False,
            server_default="{expense}",
        ),
        sa.Column(
            "default_contra_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("requires_unit_cost", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("qty_label", sa.String(50), nullable=True),
        sa.Column("icon", sa.String(20), nullable=True),  # emoji or icon hint
        sa.Column("display_order", sa.Integer, nullable=False, server_default="100"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("tenant_id", "key", name="uq_custom_inv_op_tenant_key"),
    )
    op.create_index(
        "ix_custom_inv_op_tenant_active",
        "custom_inventory_operations",
        ["tenant_id", "is_active"],
    )

    # Row-level security: tenant isolation
    op.execute("ALTER TABLE custom_inventory_operations ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {POLICY_NAME} ON custom_inventory_operations "
        f"USING (tenant_id::text = current_setting('app.tenant_id', true))"
    )


def downgrade() -> None:
    op.execute(f"DROP POLICY IF EXISTS {POLICY_NAME} ON custom_inventory_operations")
    op.drop_index("ix_custom_inv_op_tenant_active", table_name="custom_inventory_operations")
    op.drop_table("custom_inventory_operations")

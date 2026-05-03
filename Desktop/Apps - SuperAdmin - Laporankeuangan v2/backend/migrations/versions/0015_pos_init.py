"""POS module: pos_sessions, pos_orders, pos_order_lines.

Revision ID: 0015_pos_init
Revises: 0014_stock_transfers
Create Date: 2026-05-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015_pos_init"
down_revision: Union[str, None] = "0014_stock_transfers"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

POLICY_NAME = "p_tenant_isolation"


def upgrade() -> None:
    # ── pos_sessions ────────────────────────────────────────────────
    op.create_table(
        "pos_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("session_no", sa.String(30), nullable=False),
        sa.Column("register_name", sa.String(100), nullable=False, server_default="Main Register"),
        sa.Column(
            "cashier_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("opening_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("closing_amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("expected_closing", sa.Numeric(18, 2), nullable=True),
        sa.Column("cash_difference", sa.Numeric(18, 2), nullable=True),
        sa.Column("total_sales", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("total_orders", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "opened_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("tenant_id", "session_no", name="uq_pos_sessions_tenant_no"),
        sa.CheckConstraint("status IN ('open','closed')", name="ck_pos_sessions_status"),
    )
    op.create_index("ix_pos_sessions_tenant_status", "pos_sessions", ["tenant_id", "status"])
    op.create_index("ix_pos_sessions_tenant_opened", "pos_sessions", ["tenant_id", "opened_at"])

    # ── pos_orders ──────────────────────────────────────────────────
    op.create_table(
        "pos_orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("pos_sessions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("order_no", sa.String(30), nullable=False),
        sa.Column("order_date", sa.Date, nullable=False),
        sa.Column("customer_name", sa.String(200), nullable=True),
        sa.Column("subtotal", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("discount_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("tax_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("total", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("payment_method", sa.String(20), nullable=False, server_default="cash"),
        sa.Column("amount_paid", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("change_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="paid"),
        sa.Column("journal_entry_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("void_reason", sa.String(500), nullable=True),
        sa.Column("voided_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("tenant_id", "order_no", name="uq_pos_orders_tenant_no"),
        sa.CheckConstraint("status IN ('paid','void')", name="ck_pos_orders_status"),
        sa.CheckConstraint(
            "payment_method IN ('cash','card','transfer','other')",
            name="ck_pos_orders_payment_method",
        ),
    )
    op.create_index("ix_pos_orders_tenant_date", "pos_orders", ["tenant_id", "order_date"])
    op.create_index("ix_pos_orders_tenant_session", "pos_orders", ["tenant_id", "session_id"])
    op.create_index("ix_pos_orders_tenant_status", "pos_orders", ["tenant_id", "status"])

    # ── pos_order_lines ─────────────────────────────────────────────
    op.create_table(
        "pos_order_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "order_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("pos_orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("line_no", sa.Integer, nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("qty", sa.Numeric(18, 4), nullable=False),
        sa.Column("unit_price", sa.Numeric(18, 4), nullable=False),
        sa.Column("discount_pct", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("discount_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("line_total", sa.Numeric(18, 2), nullable=False),
        sa.Column("tax_rate", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("tax_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("item_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("items.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("warehouse_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=True),
        sa.CheckConstraint("qty > 0", name="ck_pos_order_lines_qty_positive"),
        sa.CheckConstraint("unit_price >= 0", name="ck_pos_order_lines_price_nonneg"),
        sa.CheckConstraint(
            "discount_pct >= 0 AND discount_pct <= 100",
            name="ck_pos_order_lines_discount",
        ),
    )
    op.create_index("ix_pos_order_lines_order", "pos_order_lines", ["order_id"])
    op.create_index("ix_pos_order_lines_item", "pos_order_lines", ["tenant_id", "item_id"])

    # ── Row-Level Security ──────────────────────────────────────────
    for table in ("pos_sessions", "pos_orders", "pos_order_lines"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(
            f"CREATE POLICY {POLICY_NAME} ON {table} "
            "USING (tenant_id = current_setting('app.tenant_id')::uuid);"
        )


def downgrade() -> None:
    for table in ("pos_order_lines", "pos_orders", "pos_sessions"):
        op.execute(f"DROP POLICY IF EXISTS {POLICY_NAME} ON {table};")

    op.drop_table("pos_order_lines")
    op.drop_table("pos_orders")
    op.drop_table("pos_sessions")

"""Work Centers + BOM/MO Operations + Labor cost (Sprint M5).

Adds three tables and two MO columns. Lets a BOM optionally define a
routing of operations (e.g. cutting → assembly → QC) at a `work_center`,
each with a per-unit `time_minutes` and one-time `setup_minutes`. On MO
confirm the operations snapshot into `mo_operations` with the work
center's `cost_per_hour` frozen at that moment.

When the MO completes, total labor = sum(actual_time_min × cost_per_hour /
60) is posted as an extra journal (Dr WIP / Cr mfg_labor_applied) and
folds into the FG receipt value. Variance logic from M4 is unchanged —
variance is computed on materials only.

Revision ID: 0025_work_centers
Revises: 0024_mfg_variance
Create Date: 2026-05-12
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0025_work_centers"
down_revision: Union[str, None] = "0024_mfg_variance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

POLICY_NAME = "p_tenant_isolation"


def upgrade() -> None:
    # ── work_centers ────────────────────────────────────────
    op.create_table(
        "work_centers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column(
            "cost_per_hour", sa.Numeric(18, 2), nullable=False, server_default="0"
        ),
        sa.Column(
            "capacity_hours_per_day",
            sa.Numeric(8, 2),
            nullable=False,
            server_default="8",
        ),
        sa.Column(
            "is_active", sa.Boolean, nullable=False, server_default=sa.text("true")
        ),
        sa.Column("notes", sa.String(500), nullable=True),
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
        sa.UniqueConstraint("tenant_id", "code", name="uq_wc_tenant_code"),
        sa.CheckConstraint("cost_per_hour >= 0", name="ck_wc_cph_nonneg"),
        sa.CheckConstraint(
            "capacity_hours_per_day > 0", name="ck_wc_capacity_positive"
        ),
    )
    op.create_index("ix_wc_tenant_active", "work_centers", ["tenant_id", "is_active"])
    op.execute("ALTER TABLE work_centers ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {POLICY_NAME} ON work_centers "
        f"USING (tenant_id::text = current_setting('app.tenant_id', true))"
    )

    # ── bom_operations ──────────────────────────────────────
    op.create_table(
        "bom_operations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "bom_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("boms.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("seq", sa.Integer, nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column(
            "work_center_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("work_centers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "time_minutes", sa.Numeric(10, 2), nullable=False, server_default="0"
        ),
        sa.Column(
            "setup_minutes", sa.Numeric(10, 2), nullable=False, server_default="0"
        ),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.CheckConstraint("time_minutes >= 0", name="ck_bomop_time_nonneg"),
        sa.CheckConstraint("setup_minutes >= 0", name="ck_bomop_setup_nonneg"),
    )
    op.create_index("ix_bomop_bom", "bom_operations", ["bom_id"])

    # ── mo_operations ───────────────────────────────────────
    op.create_table(
        "mo_operations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "mo_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("manufacturing_orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "bom_operation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("bom_operations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("seq", sa.Integer, nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column(
            "work_center_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("work_centers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("planned_time_min", sa.Numeric(10, 2), nullable=False),
        sa.Column(
            "actual_time_min",
            sa.Numeric(10, 2),
            nullable=False,
            server_default="0",
        ),
        sa.Column("cost_per_hour_snapshot", sa.Numeric(18, 2), nullable=False),
        sa.Column(
            "status", sa.String(20), nullable=False, server_default="pending"
        ),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending','in_progress','done')", name="ck_moop_status"
        ),
        sa.CheckConstraint(
            "planned_time_min >= 0", name="ck_moop_planned_nonneg"
        ),
        sa.CheckConstraint("actual_time_min >= 0", name="ck_moop_actual_nonneg"),
    )
    op.create_index("ix_moop_mo", "mo_operations", ["mo_id"])

    # ── manufacturing_orders: labor columns ─────────────────
    op.add_column(
        "manufacturing_orders",
        sa.Column("labor_total_cost", sa.Numeric(18, 2), nullable=True),
    )
    op.add_column(
        "manufacturing_orders",
        sa.Column(
            "labor_journal_entry_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("manufacturing_orders", "labor_journal_entry_id")
    op.drop_column("manufacturing_orders", "labor_total_cost")
    op.drop_index("ix_moop_mo", table_name="mo_operations")
    op.drop_table("mo_operations")
    op.drop_index("ix_bomop_bom", table_name="bom_operations")
    op.drop_table("bom_operations")
    op.execute(f"DROP POLICY IF EXISTS {POLICY_NAME} ON work_centers")
    op.drop_index("ix_wc_tenant_active", table_name="work_centers")
    op.drop_table("work_centers")

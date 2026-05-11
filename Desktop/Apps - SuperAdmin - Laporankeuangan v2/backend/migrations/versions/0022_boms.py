"""BOM (Bill of Materials) master.

A BOM defines a recipe: one output item produced from N component lines,
each with a required qty and optional scrap percentage. Per-tenant, with
RLS. Exactly one BOM may be `active` per (tenant, output item) — enforced
via a partial unique index.

Status lifecycle: draft → active → obsolete. Components (`bom_lines`) are
not tenant-scoped at column level; they inherit isolation via FK to
`boms` and are always queried through the parent in the service layer.

Revision ID: 0022_boms
Revises: 0021_rma
Create Date: 2026-05-11
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0022_boms"
down_revision: Union[str, None] = "0021_rma"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

POLICY_NAME = "p_tenant_isolation"


def upgrade() -> None:
    op.create_table(
        "boms",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("bom_code", sa.String(40), nullable=False),
        sa.Column(
            "item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("items.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "qty_output", sa.Numeric(18, 4), nullable=False, server_default="1"
        ),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column(
            "status", sa.String(20), nullable=False, server_default="draft"
        ),
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
        sa.UniqueConstraint("tenant_id", "bom_code", name="uq_bom_tenant_code"),
        sa.CheckConstraint(
            "status IN ('draft','active','obsolete')", name="ck_bom_status"
        ),
        sa.CheckConstraint("qty_output > 0", name="ck_bom_qty_output_positive"),
    )
    op.create_index("ix_bom_tenant_item", "boms", ["tenant_id", "item_id"])
    # At most one ACTIVE BOM per (tenant, item)
    op.execute(
        "CREATE UNIQUE INDEX uq_bom_active_per_item "
        "ON boms (tenant_id, item_id) WHERE status = 'active'"
    )
    op.execute("ALTER TABLE boms ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {POLICY_NAME} ON boms "
        f"USING (tenant_id::text = current_setting('app.tenant_id', true))"
    )

    op.create_table(
        "bom_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "bom_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("boms.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("line_no", sa.Integer, nullable=False),
        sa.Column(
            "item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("items.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("qty_required", sa.Numeric(18, 4), nullable=False),
        sa.Column(
            "scrap_pct", sa.Numeric(5, 2), nullable=False, server_default="0"
        ),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.CheckConstraint("qty_required > 0", name="ck_boml_qty_positive"),
        sa.CheckConstraint(
            "scrap_pct >= 0 AND scrap_pct < 100", name="ck_boml_scrap_range"
        ),
    )
    op.create_index("ix_boml_bom", "bom_lines", ["bom_id"])


def downgrade() -> None:
    op.drop_index("ix_boml_bom", table_name="bom_lines")
    op.drop_table("bom_lines")
    op.execute(f"DROP POLICY IF EXISTS {POLICY_NAME} ON boms")
    op.execute("DROP INDEX IF EXISTS uq_bom_active_per_item")
    op.drop_index("ix_bom_tenant_item", table_name="boms")
    op.drop_table("boms")

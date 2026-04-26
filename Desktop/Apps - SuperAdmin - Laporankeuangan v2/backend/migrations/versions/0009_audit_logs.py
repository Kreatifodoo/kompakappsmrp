"""Audit logs table.

Revision ID: 0009_audit_logs
Revises: 0008_refund_directions
Create Date: 2026-04-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_audit_logs"
down_revision: Union[str, None] = "0008_refund_directions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

POLICY_NAME = "p_tenant_isolation"


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column("request_id", sa.String(64)),
        sa.Column("table_name", sa.String(64), nullable=False),
        sa.Column("row_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("changes", sa.JSON, nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "action IN ('create','update','delete','post','void')",
            name="ck_audit_logs_action",
        ),
    )
    op.create_index("ix_audit_logs_tenant_id", "audit_logs", ["tenant_id"])
    op.create_index(
        "ix_audit_logs_tenant_occurred", "audit_logs", ["tenant_id", "occurred_at"]
    )
    op.create_index(
        "ix_audit_logs_tenant_table_row",
        "audit_logs",
        ["tenant_id", "table_name", "row_id"],
    )
    op.create_index(
        "ix_audit_logs_tenant_user",
        "audit_logs",
        ["tenant_id", "user_id", "occurred_at"],
    )

    # RLS
    op.execute("ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE audit_logs FORCE ROW LEVEL SECURITY;")
    op.execute(
        f"""
        CREATE POLICY {POLICY_NAME} ON audit_logs
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
    op.execute(f"DROP POLICY IF EXISTS {POLICY_NAME} ON audit_logs;")
    op.drop_table("audit_logs")

"""Period closing: tenants.closed_through + period_closure_events log.

Revision ID: 0010_period_close
Revises: 0009_audit_logs
Create Date: 2026-04-27
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_period_close"
down_revision: Union[str, None] = "0009_audit_logs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("closed_through", sa.Date(), nullable=True),
    )

    op.create_table(
        "period_closure_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("through_date", sa.Date()),
        sa.Column("previous_through_date", sa.Date()),
        sa.Column("notes", sa.String(1000)),
        sa.Column(
            "performed_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "performed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "action IN ('close','reopen')", name="ck_period_closure_events_action"
        ),
    )
    op.create_index(
        "ix_period_closure_events_tenant_id", "period_closure_events", ["tenant_id"]
    )
    op.create_index(
        "ix_period_closure_events_tenant_at",
        "period_closure_events",
        ["tenant_id", "performed_at"],
    )


def downgrade() -> None:
    op.drop_table("period_closure_events")
    op.drop_column("tenants", "closed_through")

"""Add cf_section column to accounts for cash-flow statement classification.

Revision ID: 0001
Revises:
Create Date: 2026-05-03

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "accounts",
        sa.Column("cf_section", sa.String(20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("accounts", "cf_section")

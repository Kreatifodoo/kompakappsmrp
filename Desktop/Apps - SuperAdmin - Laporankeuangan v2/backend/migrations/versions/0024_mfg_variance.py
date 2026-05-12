"""Manufacturing standard cost + variance accounting (Sprint M4).

Adds opt-in standard costing per BOM line. When all components on a BOM
have `std_unit_cost` set, the MO completion journal posts FG at standard
cost with the difference vs actual going to a `mfg_variance` mapping
account (debit if unfavorable, credit if favorable). Otherwise the M2
actual-cost path is unchanged.

Schema additions (all nullable — backwards compatible):
  bom_lines.std_unit_cost                       NUMERIC(18,4) NULL
  mo_components.std_unit_cost                   NUMERIC(18,4) NULL
  manufacturing_orders.std_total_cost           NUMERIC(18,2) NULL
  manufacturing_orders.variance_amount          NUMERIC(18,2) NULL
  manufacturing_orders.variance_journal_entry_id UUID         NULL

The `variance_journal_entry_id` follows the same partitioned-journal
convention (plain UUID, no FK).

Revision ID: 0024_mfg_variance
Revises: 0023_mfg_orders
Create Date: 2026-05-12
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0024_mfg_variance"
down_revision: Union[str, None] = "0023_mfg_orders"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "bom_lines",
        sa.Column("std_unit_cost", sa.Numeric(18, 4), nullable=True),
    )
    op.add_column(
        "mo_components",
        sa.Column("std_unit_cost", sa.Numeric(18, 4), nullable=True),
    )
    op.add_column(
        "manufacturing_orders",
        sa.Column("std_total_cost", sa.Numeric(18, 2), nullable=True),
    )
    op.add_column(
        "manufacturing_orders",
        sa.Column("variance_amount", sa.Numeric(18, 2), nullable=True),
    )
    op.add_column(
        "manufacturing_orders",
        sa.Column(
            "variance_journal_entry_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("manufacturing_orders", "variance_journal_entry_id")
    op.drop_column("manufacturing_orders", "variance_amount")
    op.drop_column("manufacturing_orders", "std_total_cost")
    op.drop_column("mo_components", "std_unit_cost")
    op.drop_column("bom_lines", "std_unit_cost")

"""Wire inventory into invoice lines: item_id + warehouse_id columns.

Revision ID: 0012_inventory_invoice_lines
Revises: 0011_inventory_init
Create Date: 2026-04-28

Both columns are nullable on both invoice-line tables. Service-only
lines leave them NULL and behave exactly as before. Stock-tracked
lines reference an item.id with type='stock' and a warehouses.id;
posting the invoice creates the matching stock movement and reroutes
the relevant journal lines to the inventory / cogs accounts.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_inventory_invoice_lines"
down_revision: Union[str, None] = "0011_inventory_init"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table in ("sales_invoice_lines", "purchase_invoice_lines"):
        op.add_column(
            table,
            sa.Column(
                "item_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("items.id", ondelete="RESTRICT"),
            ),
        )
        op.add_column(
            table,
            sa.Column(
                "warehouse_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("warehouses.id", ondelete="RESTRICT"),
            ),
        )
        op.create_index(f"ix_{table}_item", table, ["item_id"])


def downgrade() -> None:
    for table in ("sales_invoice_lines", "purchase_invoice_lines"):
        op.drop_index(f"ix_{table}_item", table_name=table)
        op.drop_column(table, "warehouse_id")
        op.drop_column(table, "item_id")

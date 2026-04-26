"""Allow customer_refund and supplier_refund payment directions.

Revision ID: 0008_refund_directions
Revises: 0007_payments_init
Create Date: 2026-04-26

Drops the old direction CHECK and party-XOR-direction CHECK on payments
and recreates them to permit the two new refund directions:

- customer_refund: cash out to a customer (clears overpayment / credit)
- supplier_refund: cash in from a supplier (clears overpayment / credit)

The application-sum constraint is enforced in the application layer
(PaymentCreate model_validator) rather than as a SQL CHECK, since the
sum-vs-amount comparison spans rows in two tables.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0008_refund_directions"
down_revision: Union[str, None] = "0007_payments_init"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE payments DROP CONSTRAINT IF EXISTS ck_payments_direction;")
    op.execute("ALTER TABLE payments DROP CONSTRAINT IF EXISTS ck_payments_party_xor;")

    op.execute(
        "ALTER TABLE payments ADD CONSTRAINT ck_payments_direction "
        "CHECK (direction IN ('receipt','disbursement','customer_refund','supplier_refund'));"
    )
    op.execute(
        "ALTER TABLE payments ADD CONSTRAINT ck_payments_party_xor CHECK ("
        "(direction IN ('receipt','customer_refund') "
        "  AND customer_id IS NOT NULL AND supplier_id IS NULL) OR "
        "(direction IN ('disbursement','supplier_refund') "
        "  AND supplier_id IS NOT NULL AND customer_id IS NULL)"
        ");"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE payments DROP CONSTRAINT IF EXISTS ck_payments_direction;")
    op.execute("ALTER TABLE payments DROP CONSTRAINT IF EXISTS ck_payments_party_xor;")

    op.execute(
        "ALTER TABLE payments ADD CONSTRAINT ck_payments_direction "
        "CHECK (direction IN ('receipt','disbursement'));"
    )
    op.execute(
        "ALTER TABLE payments ADD CONSTRAINT ck_payments_party_xor CHECK ("
        "(direction = 'receipt' AND customer_id IS NOT NULL AND supplier_id IS NULL) OR "
        "(direction = 'disbursement' AND supplier_id IS NOT NULL AND customer_id IS NULL)"
        ");"
    )

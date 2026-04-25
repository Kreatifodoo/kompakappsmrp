"""Add `is_cash` flag to accounts; mark mapped cash + bank accounts.

Revision ID: 0006_account_is_cash
Revises: 0005_enable_rls
Create Date: 2026-04-26

The flag identifies cash/bank accounts so the cash-basis P&L report
can filter journals that represent actual cash movement. Defaults to
false for existing rows; the upgrade then turns it ON for any account
already mapped to `cash_default` plus any account whose code starts
with the conventional Kas/Bank prefix `11` (best-effort migration of
existing tenants).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_account_is_cash"
down_revision: Union[str, None] = "0005_enable_rls"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "accounts",
        sa.Column("is_cash", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index(
        "ix_accounts_tenant_is_cash", "accounts", ["tenant_id", "is_cash"]
    )

    # Best-effort: flip is_cash on for accounts that are clearly cash:
    # 1. Mapped to cash_default
    # 2. Code begins with "11" (the Indonesian SAK convention used by our
    #    starter COA — Kas and Bank live under 11xx).
    # Tenants with a non-conforming COA can update via PATCH /accounts/{id}.
    op.execute(
        """
        UPDATE accounts
        SET is_cash = true
        WHERE id IN (SELECT account_id FROM account_mappings WHERE key = 'cash_default')
           OR code LIKE '11%';
        """
    )


def downgrade() -> None:
    op.drop_index("ix_accounts_tenant_is_cash", table_name="accounts")
    op.drop_column("accounts", "is_cash")

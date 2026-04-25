"""Enable Postgres Row-Level Security on tenant-scoped business tables.

Revision ID: 0005_enable_rls
Revises: 0004_partition_journals
Create Date: 2026-04-26

Strategy:
- RLS is enabled on every business table that has a `tenant_id` column.
- Each gets a single policy that allows access when the row's
  `tenant_id::text` matches `current_setting('app.current_tenant', true)`,
  OR when `app.is_super_admin` is set to 'true'.
- `FORCE ROW LEVEL SECURITY` is applied so the table owner (the
  application's DB user) is also subject to the policy — otherwise the
  owner bypasses RLS by default.
- Identity tables (tenants, users, roles, permissions, role_permissions,
  tenant_users, refresh_tokens) are NOT secured here because login,
  register-tenant, and refresh flows must operate before a tenant
  context exists. Application-level authentication is authoritative
  for those tables.
- Partitioned tables (journal_entries, journal_lines): RLS on the
  partitioned table propagates to all partitions automatically.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0005_enable_rls"
down_revision: Union[str, None] = "0004_partition_journals"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SECURED_TABLES = (
    "accounts",
    "account_mappings",
    "journal_entries",
    "journal_lines",
    "customers",
    "sales_invoices",
    "sales_invoice_lines",
    "suppliers",
    "purchase_invoices",
    "purchase_invoice_lines",
)

POLICY_NAME = "p_tenant_isolation"


def _enable_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
    op.execute(
        f"""
        CREATE POLICY {POLICY_NAME} ON {table}
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


def _disable_rls(table: str) -> None:
    op.execute(f"DROP POLICY IF EXISTS {POLICY_NAME} ON {table};")
    op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
    op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")


def upgrade() -> None:
    for table in SECURED_TABLES:
        _enable_rls(table)


def downgrade() -> None:
    for table in reversed(SECURED_TABLES):
        _disable_rls(table)

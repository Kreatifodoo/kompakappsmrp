"""Convert journal_entries + journal_lines to RANGE-partitioned (monthly).

Revision ID: 0004_partition_journals
Revises: 0003_sales_purchase_init
Create Date: 2026-04-26

Strategy:
1. Save existing journal data to temp tables (preserves data if any).
2. Backfill journal_lines.entry_date from journal_entries (denormalized).
3. Drop FK constraints in sales_invoices / purchase_invoices that reference
   journal_entries.id (single-column FK no longer valid against composite PK).
4. Drop journal_lines, journal_entries.
5. Recreate as PARTITION BY RANGE (entry_date), composite PK (id, entry_date).
6. Generate monthly partitions covering [min_year - 1, max_year + 1] from the
   preserved data, defaulting to [2024, 2027] if there was no data.
7. Restore data by INSERTing from the temp tables (Postgres routes rows to
   the right partition automatically).
8. Drop temp tables.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_partition_journals"
down_revision: Union[str, None] = "0003_sales_purchase_init"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _create_monthly_partitions(table: str, year_from: int, year_to: int) -> None:
    """Issue CREATE TABLE ... PARTITION OF for every month in the range."""
    for year in range(year_from, year_to + 1):
        for month in range(1, 13):
            next_month = month + 1
            next_year = year
            if next_month == 13:
                next_month = 1
                next_year = year + 1
            partition_name = f"{table}_y{year}_m{month:02d}"
            op.execute(
                f"CREATE TABLE {partition_name} PARTITION OF {table} "
                f"FOR VALUES FROM ('{year}-{month:02d}-01') "
                f"TO ('{next_year}-{next_month:02d}-01');"
            )


def upgrade() -> None:
    # ── 1. Save existing data ────────────────────────────────
    op.execute("CREATE TEMP TABLE _je_old AS TABLE journal_entries;")
    op.execute("CREATE TEMP TABLE _jl_old AS TABLE journal_lines;")

    # ── 2. Backfill entry_date in the temp lines table ───────
    op.execute(
        "ALTER TABLE _jl_old ADD COLUMN IF NOT EXISTS entry_date date;"
    )
    op.execute(
        "UPDATE _jl_old jl SET entry_date = je.entry_date "
        "FROM _je_old je WHERE jl.entry_id = je.id;"
    )

    # Compute year range from the data; default if empty
    conn = op.get_bind()
    row = conn.execute(
        sa.text(
            "SELECT MIN(EXTRACT(YEAR FROM entry_date))::int, "
            "       MAX(EXTRACT(YEAR FROM entry_date))::int "
            "FROM _je_old;"
        )
    ).first()
    if row and row[0] is not None:
        year_from = max(2000, int(row[0]) - 1)
        year_to = int(row[1]) + 1
    else:
        year_from, year_to = 2024, 2027

    # ── 3. Drop FK constraints from sales_invoices / purchase_invoices
    #     that reference journal_entries (will not be reinstated; they
    #     would require composite (id, entry_date) on the source table).
    op.execute(
        "ALTER TABLE sales_invoices DROP CONSTRAINT IF EXISTS sales_invoices_journal_entry_id_fkey;"
    )
    op.execute(
        "ALTER TABLE purchase_invoices DROP CONSTRAINT IF EXISTS purchase_invoices_journal_entry_id_fkey;"
    )

    # ── 4. Drop the unpartitioned tables ─────────────────────
    op.execute("DROP TABLE journal_lines CASCADE;")
    op.execute("DROP TABLE journal_entries CASCADE;")

    # ── 5. Recreate journal_entries as a partitioned table ───
    op.execute(
        """
        CREATE TABLE journal_entries (
            id UUID NOT NULL,
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            entry_no VARCHAR(30) NOT NULL,
            entry_date DATE NOT NULL,
            description VARCHAR(500),
            reference VARCHAR(100),
            status VARCHAR(20) NOT NULL DEFAULT 'draft',
            source VARCHAR(30),
            source_id UUID,
            created_by UUID,
            posted_by UUID,
            posted_at TIMESTAMP WITH TIME ZONE,
            voided_by UUID,
            voided_at TIMESTAMP WITH TIME ZONE,
            void_reason VARCHAR(500),
            metadata JSON,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            CONSTRAINT pk_journal_entries PRIMARY KEY (id, entry_date),
            CONSTRAINT uq_journal_entries_tenant_no UNIQUE (tenant_id, entry_no, entry_date),
            CONSTRAINT ck_journal_entries_status CHECK (status IN ('draft','posted','void'))
        ) PARTITION BY RANGE (entry_date);
        """
    )
    op.create_index("ix_journal_entries_tenant_id", "journal_entries", ["tenant_id"])
    op.create_index(
        "ix_journal_entries_tenant_date", "journal_entries", ["tenant_id", "entry_date"]
    )
    op.create_index(
        "ix_journal_entries_tenant_status", "journal_entries", ["tenant_id", "status"]
    )

    _create_monthly_partitions("journal_entries", year_from, year_to)

    # ── 5b. Recreate journal_lines as a partitioned table ────
    op.execute(
        """
        CREATE TABLE journal_lines (
            id UUID NOT NULL,
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            entry_id UUID NOT NULL,
            entry_date DATE NOT NULL,
            line_no INTEGER NOT NULL,
            account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
            description VARCHAR(500),
            debit NUMERIC(18, 2) NOT NULL DEFAULT 0,
            credit NUMERIC(18, 2) NOT NULL DEFAULT 0,
            CONSTRAINT pk_journal_lines PRIMARY KEY (id, entry_date),
            CONSTRAINT fk_journal_lines_entry
                FOREIGN KEY (entry_id, entry_date)
                REFERENCES journal_entries(id, entry_date) ON DELETE CASCADE,
            CONSTRAINT ck_journal_lines_debit_xor_credit
                CHECK ((debit >= 0 AND credit >= 0) AND (debit = 0 OR credit = 0))
        ) PARTITION BY RANGE (entry_date);
        """
    )
    op.create_index("ix_journal_lines_tenant_id", "journal_lines", ["tenant_id"])
    op.create_index(
        "ix_journal_lines_tenant_account", "journal_lines", ["tenant_id", "account_id"]
    )
    op.create_index(
        "ix_journal_lines_tenant_date", "journal_lines", ["tenant_id", "entry_date"]
    )
    op.create_index(
        "ix_journal_lines_entry", "journal_lines", ["entry_id", "entry_date"]
    )

    _create_monthly_partitions("journal_lines", year_from, year_to)

    # ── 6. Restore data ──────────────────────────────────────
    op.execute(
        """
        INSERT INTO journal_entries (
            id, tenant_id, entry_no, entry_date, description, reference,
            status, source, source_id, created_by, posted_by, posted_at,
            voided_by, voided_at, void_reason, metadata, created_at, updated_at
        )
        SELECT
            id, tenant_id, entry_no, entry_date, description, reference,
            status, source, source_id, created_by, posted_by, posted_at,
            voided_by, voided_at, void_reason, metadata, created_at, updated_at
        FROM _je_old;
        """
    )
    op.execute(
        """
        INSERT INTO journal_lines (
            id, tenant_id, entry_id, entry_date, line_no, account_id,
            description, debit, credit
        )
        SELECT
            id, tenant_id, entry_id, entry_date, line_no, account_id,
            description, debit, credit
        FROM _jl_old;
        """
    )

    # ── 7. Cleanup ───────────────────────────────────────────
    op.execute("DROP TABLE IF EXISTS _jl_old;")
    op.execute("DROP TABLE IF EXISTS _je_old;")


def downgrade() -> None:
    # Revert to plain (un-partitioned) tables. Data preserved.
    op.execute("CREATE TEMP TABLE _je_save AS TABLE journal_entries;")
    op.execute("CREATE TEMP TABLE _jl_save AS TABLE journal_lines;")

    op.execute("DROP TABLE journal_lines CASCADE;")
    op.execute("DROP TABLE journal_entries CASCADE;")

    # Recreate as plain tables (mirrors the 0002 + 0003 columns)
    op.create_table(
        "journal_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("entry_no", sa.String(30), nullable=False),
        sa.Column("entry_date", sa.Date, nullable=False),
        sa.Column("description", sa.String(500)),
        sa.Column("reference", sa.String(100)),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("source", sa.String(30)),
        sa.Column("source_id", postgresql.UUID(as_uuid=True)),
        sa.Column("created_by", postgresql.UUID(as_uuid=True)),
        sa.Column("posted_by", postgresql.UUID(as_uuid=True)),
        sa.Column("posted_at", sa.DateTime(timezone=True)),
        sa.Column("voided_by", postgresql.UUID(as_uuid=True)),
        sa.Column("voided_at", sa.DateTime(timezone=True)),
        sa.Column("void_reason", sa.String(500)),
        sa.Column("metadata", sa.JSON),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "entry_no", name="uq_journal_entries_tenant_no"),
        sa.CheckConstraint("status IN ('draft','posted','void')", name="ck_journal_entries_status"),
    )
    op.create_index("ix_journal_entries_tenant_id", "journal_entries", ["tenant_id"])
    op.create_index("ix_journal_entries_tenant_date", "journal_entries", ["tenant_id", "entry_date"])
    op.create_index("ix_journal_entries_tenant_status", "journal_entries", ["tenant_id", "status"])

    op.create_table(
        "journal_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "entry_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("journal_entries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("line_no", sa.Integer, nullable=False),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("description", sa.String(500)),
        sa.Column("debit", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("credit", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.CheckConstraint(
            "(debit >= 0 AND credit >= 0) AND (debit = 0 OR credit = 0)",
            name="ck_journal_lines_debit_xor_credit",
        ),
    )
    op.create_index("ix_journal_lines_tenant_id", "journal_lines", ["tenant_id"])
    op.create_index("ix_journal_lines_tenant_account", "journal_lines", ["tenant_id", "account_id"])
    op.create_index("ix_journal_lines_entry", "journal_lines", ["entry_id"])

    op.execute(
        """
        INSERT INTO journal_entries
        SELECT id, tenant_id, entry_no, entry_date, description, reference,
               status, source, source_id, created_by, posted_by, posted_at,
               voided_by, voided_at, void_reason, metadata, created_at, updated_at
        FROM _je_save;
        """
    )
    op.execute(
        """
        INSERT INTO journal_lines (
            id, tenant_id, entry_id, line_no, account_id, description, debit, credit
        )
        SELECT id, tenant_id, entry_id, line_no, account_id, description, debit, credit
        FROM _jl_save;
        """
    )

    op.execute("DROP TABLE IF EXISTS _jl_save;")
    op.execute("DROP TABLE IF EXISTS _je_save;")

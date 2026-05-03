"""Accounting domain models: Account (COA), JournalEntry, JournalLine.

Design notes:
- All tables include `tenant_id` for row-level multi-tenancy + RLS.
- `journal_entries` and `journal_lines` are RANGE-partitioned by
  `entry_date` (monthly). The partition key must be part of the primary
  key, so both tables use a composite PK `(id, entry_date)`. The
  partition tables themselves are declared via Alembic migration; this
  ORM file declares the parent table shape with `postgresql_partition_by`.
- `journal_lines.entry_date` is denormalized from `journal_entries.entry_date`
  so the FK can be composite (entry_id, entry_date) and partition-pruning
  works for both tables in date-range queries (e.g. reports).
- Money is stored as NUMERIC(18, 2). Use Decimal in Python.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Account(Base):
    """Chart-of-Accounts entry. Hierarchical via parent_id."""

    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_accounts_tenant_code"),
        Index("ix_accounts_tenant_type", "tenant_id", "type"),
        Index("ix_accounts_tenant_parent", "tenant_id", "parent_id"),
        CheckConstraint(
            "type IN ('asset','liability','equity','income','expense')",
            name="ck_accounts_type",
        ),
        CheckConstraint(
            "normal_side IN ('debit','credit')",
            name="ck_accounts_normal_side",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)  # asset/liability/...
    normal_side: Mapped[str] = mapped_column(String(10), nullable=False)  # debit/credit
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="SET NULL")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Marks an account as a cash/bank account — used by cash-basis P&L
    # to identify journals that represent actual cash movement.
    is_cash: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Cash-flow statement classification for indirect method.
    # None (null) = uncategorised (account won't appear in cash-flow report).
    # 'operating'  → working capital adjustments (AR, AP, inventory, prepaid…)
    # 'investing'  → fixed assets / long-term investments
    # 'financing'  → equity + long-term debt
    # Income and expense accounts are captured via net income, not here.
    # Cash/bank accounts (is_cash=True) are the reconciling total, not here.
    cf_section: Mapped[str | None] = mapped_column(String(20), nullable=True)
    description: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class JournalEntry(Base):
    """Header of a double-entry journal transaction.

    RANGE-partitioned by `entry_date` (monthly). The partition key must
    be part of the primary key, hence the composite `(id, entry_date)` PK.
    """

    __tablename__ = "journal_entries"
    __table_args__ = (
        PrimaryKeyConstraint("id", "entry_date", name="pk_journal_entries"),
        UniqueConstraint("tenant_id", "entry_no", "entry_date", name="uq_journal_entries_tenant_no"),
        Index("ix_journal_entries_tenant_date", "tenant_id", "entry_date"),
        Index("ix_journal_entries_tenant_status", "tenant_id", "status"),
        CheckConstraint(
            "status IN ('draft','posted','void')",
            name="ck_journal_entries_status",
        ),
        {"postgresql_partition_by": "RANGE (entry_date)"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), default=uuid.uuid4, nullable=False)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entry_no: Mapped[str] = mapped_column(String(30), nullable=False)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    reference: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    source: Mapped[str | None] = mapped_column(String(30))  # manual/sale/purchase/...
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    # Audit
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    posted_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    voided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    void_reason: Mapped[str | None] = mapped_column(String(500))

    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    lines: Mapped[list["JournalLine"]] = relationship(
        back_populates="entry", cascade="all, delete-orphan", order_by="JournalLine.line_no"
    )


class JournalLine(Base):
    """Individual debit/credit line of a journal entry.

    RANGE-partitioned by `entry_date` (denormalized from JournalEntry).
    Composite FK `(entry_id, entry_date)` references the parent entry's
    composite PK, enabling partition-wise pruning when reports filter
    by date.
    """

    __tablename__ = "journal_lines"
    __table_args__ = (
        PrimaryKeyConstraint("id", "entry_date", name="pk_journal_lines"),
        ForeignKeyConstraint(
            ["entry_id", "entry_date"],
            ["journal_entries.id", "journal_entries.entry_date"],
            ondelete="CASCADE",
            name="fk_journal_lines_entry",
        ),
        Index("ix_journal_lines_tenant_account", "tenant_id", "account_id"),
        Index("ix_journal_lines_tenant_date", "tenant_id", "entry_date"),
        Index("ix_journal_lines_entry", "entry_id", "entry_date"),
        CheckConstraint(
            "(debit >= 0 AND credit >= 0) AND (debit = 0 OR credit = 0)",
            name="ck_journal_lines_debit_xor_credit",
        ),
        {"postgresql_partition_by": "RANGE (entry_date)"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), default=uuid.uuid4, nullable=False)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entry_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(String(500))
    debit: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"), nullable=False)
    credit: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"), nullable=False)

    entry: Mapped[JournalEntry] = relationship(back_populates="lines")


class AccountMapping(Base):
    """Per-tenant mapping of semantic keys to ledger accounts.

    Keys (well-known):
      ar               → Accounts Receivable
      ap               → Accounts Payable
      sales_revenue    → Sales income account
      purchase_expense → Default purchase/COGS expense account
      tax_payable      → Output tax (collected on sales)
      tax_receivable   → Input tax (paid on purchases)
      cash_default     → Default cash/bank account
    """

    __tablename__ = "account_mappings"
    __table_args__ = (UniqueConstraint("tenant_id", "key", name="uq_account_mappings_tenant_key"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    key: Mapped[str] = mapped_column(String(50), nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )

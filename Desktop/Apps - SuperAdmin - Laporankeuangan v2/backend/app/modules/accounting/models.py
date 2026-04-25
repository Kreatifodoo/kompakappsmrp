"""Accounting domain models: Account (COA), JournalEntry, JournalLine.

Design notes:
- All tables include `tenant_id` for row-level multi-tenancy + RLS.
- `journal_entries` and `journal_lines` are designed for monthly RANGE
  partitioning on `entry_date` — partitions are created via migration/DDL,
  not declared on the SQLAlchemy model itself.
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
    Index,
    Integer,
    Numeric,
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

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
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
    description: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class JournalEntry(Base):
    """Header of a double-entry journal transaction."""

    __tablename__ = "journal_entries"
    __table_args__ = (
        UniqueConstraint("tenant_id", "entry_no", name="uq_journal_entries_tenant_no"),
        Index("ix_journal_entries_tenant_date", "tenant_id", "entry_date"),
        Index("ix_journal_entries_tenant_status", "tenant_id", "status"),
        CheckConstraint(
            "status IN ('draft','posted','void')",
            name="ck_journal_entries_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
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
    """Individual debit/credit line of a journal entry."""

    __tablename__ = "journal_lines"
    __table_args__ = (
        Index("ix_journal_lines_tenant_account", "tenant_id", "account_id"),
        Index("ix_journal_lines_entry", "entry_id"),
        CheckConstraint(
            "(debit >= 0 AND credit >= 0) AND (debit = 0 OR credit = 0)",
            name="ck_journal_lines_debit_xor_credit",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("journal_entries.id", ondelete="CASCADE"),
        nullable=False,
    )
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

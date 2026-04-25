"""Purchase domain: Supplier, PurchaseInvoice, PurchaseInvoiceLine."""

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


class Supplier(Base):
    __tablename__ = "suppliers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_suppliers_tenant_code"),
        Index("ix_suppliers_tenant_active", "tenant_id", "is_active"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str | None] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(50))
    address: Mapped[str | None] = mapped_column(String(500))
    tax_id: Mapped[str | None] = mapped_column(String(50))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class PurchaseInvoice(Base):
    __tablename__ = "purchase_invoices"
    __table_args__ = (
        UniqueConstraint("tenant_id", "invoice_no", name="uq_purchase_invoices_tenant_no"),
        Index("ix_purchase_invoices_tenant_date", "tenant_id", "invoice_date"),
        Index("ix_purchase_invoices_tenant_status", "tenant_id", "status"),
        Index("ix_purchase_invoices_supplier", "tenant_id", "supplier_id"),
        CheckConstraint(
            "status IN ('draft','posted','paid','void')",
            name="ck_purchase_invoices_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    invoice_no: Mapped[str] = mapped_column(String(30), nullable=False)
    supplier_invoice_no: Mapped[str | None] = mapped_column(String(60))  # supplier's bill #
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date)
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False
    )
    subtotal: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"), nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"), nullable=False)
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    notes: Mapped[str | None] = mapped_column(String(1000))

    # Note: no FK constraint to journal_entries — that table is partitioned
    # with composite PK (id, entry_date), so a single-column FK isn't valid.
    # Application-level integrity (PurchaseService) is the source of truth.
    journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

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

    lines: Mapped[list["PurchaseInvoiceLine"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", order_by="PurchaseInvoiceLine.line_no"
    )


class PurchaseInvoiceLine(Base):
    __tablename__ = "purchase_invoice_lines"
    __table_args__ = (
        Index("ix_purchase_invoice_lines_invoice", "invoice_id"),
        CheckConstraint("qty > 0", name="ck_purchase_invoice_lines_qty_positive"),
        CheckConstraint("unit_price >= 0", name="ck_purchase_invoice_lines_price_nonneg"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("purchase_invoices.id", ondelete="CASCADE"), nullable=False
    )
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"), nullable=False)
    # Optional per-line expense account override (else uses tenant default purchase_expense)
    expense_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="RESTRICT")
    )

    invoice: Mapped[PurchaseInvoice] = relationship(back_populates="lines")

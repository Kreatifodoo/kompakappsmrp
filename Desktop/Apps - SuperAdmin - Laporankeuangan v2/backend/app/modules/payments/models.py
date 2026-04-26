"""Payments domain: Payment + PaymentApplication.

A Payment is a discrete cash movement event:
- direction='receipt': cash in from a customer (credits AR)
- direction='disbursement': cash out to a supplier (debits AP)

Each payment can apply to one or more invoices via PaymentApplication
rows. When a payment is posted, a balanced journal entry is created
in the same DB transaction (Dr Cash / Cr AR  or  Dr AP / Cr Cash) and
each linked invoice's paid_amount is incremented.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Payment(Base):
    """Header of a cash receipt or disbursement."""

    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "payment_no", name="uq_payments_tenant_no"),
        Index("ix_payments_tenant_date", "tenant_id", "payment_date"),
        Index("ix_payments_tenant_status", "tenant_id", "status"),
        Index("ix_payments_customer", "tenant_id", "customer_id"),
        Index("ix_payments_supplier", "tenant_id", "supplier_id"),
        CheckConstraint(
            "direction IN ('receipt','disbursement')",
            name="ck_payments_direction",
        ),
        CheckConstraint(
            "status IN ('draft','posted','void')",
            name="ck_payments_status",
        ),
        CheckConstraint(
            "(direction = 'receipt' AND customer_id IS NOT NULL AND supplier_id IS NULL) OR "
            "(direction = 'disbursement' AND supplier_id IS NOT NULL AND customer_id IS NULL)",
            name="ck_payments_party_xor",
        ),
        CheckConstraint("amount > 0", name="ck_payments_amount_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    payment_no: Mapped[str] = mapped_column(String(30), nullable=False)
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    direction: Mapped[str] = mapped_column(String(20), nullable=False)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT")
    )
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="RESTRICT")
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    cash_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    reference: Mapped[str | None] = mapped_column(String(100))
    notes: Mapped[str | None] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    # No FK — journal_entries is partitioned with composite PK.
    journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    # Audit
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    posted_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    voided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    void_reason: Mapped[str | None] = mapped_column(String(500))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    applications: Mapped[list["PaymentApplication"]] = relationship(
        back_populates="payment", cascade="all, delete-orphan"
    )


class PaymentApplication(Base):
    """A single (payment → invoice) attribution. Sum across applications
    must equal the payment's amount."""

    __tablename__ = "payment_applications"
    __table_args__ = (
        Index("ix_payment_applications_payment", "payment_id"),
        Index("ix_payment_applications_sales_invoice", "sales_invoice_id"),
        Index("ix_payment_applications_purchase_invoice", "purchase_invoice_id"),
        CheckConstraint("amount > 0", name="ck_payment_applications_amount_positive"),
        CheckConstraint(
            "(sales_invoice_id IS NOT NULL AND purchase_invoice_id IS NULL) OR "
            "(sales_invoice_id IS NULL AND purchase_invoice_id IS NOT NULL)",
            name="ck_payment_applications_invoice_xor",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    payment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("payments.id", ondelete="CASCADE"),
        nullable=False,
    )
    sales_invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sales_invoices.id", ondelete="RESTRICT")
    )
    purchase_invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("purchase_invoices.id", ondelete="RESTRICT")
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    voided: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    payment: Mapped[Payment] = relationship(back_populates="applications")

"""POS domain: PosSession, PosOrder, PosOrderLine.

A POS session groups all orders made on one cash-register shift.
Orders auto-post (no draft step) so the journal + stock-out happen
in the same transaction as the order creation.

Payment method mapping to GL accounts (via AccountMapping keys):
  cash       → cash_default   (debit)
  card       → pos_card       (debit, falls back to cash_default if not configured)
  transfer   → pos_transfer   (debit, falls back to cash_default if not configured)
  other      → pos_other      (debit, falls back to cash_default if not configured)
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
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class PosSession(Base):
    """A cash-register shift opened by a cashier."""

    __tablename__ = "pos_sessions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "session_no", name="uq_pos_sessions_tenant_no"),
        Index("ix_pos_sessions_tenant_status", "tenant_id", "status"),
        Index("ix_pos_sessions_tenant_opened", "tenant_id", "opened_at"),
        CheckConstraint(
            "status IN ('open','closed')",
            name="ck_pos_sessions_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_no: Mapped[str] = mapped_column(String(30), nullable=False)
    register_name: Mapped[str] = mapped_column(String(100), nullable=False, default="Main Register")
    cashier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)

    # Opening/closing cash float
    opening_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=Decimal("0"), nullable=False
    )
    closing_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    expected_closing: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    # Positive = surplus cash, negative = shortage
    cash_difference: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))

    # Session totals (accumulated from orders)
    total_sales: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=Decimal("0"), nullable=False
    )
    total_orders: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(String(500))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    orders: Mapped[list["PosOrder"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class PosOrder(Base):
    """A single POS transaction (receipt)."""

    __tablename__ = "pos_orders"
    __table_args__ = (
        UniqueConstraint("tenant_id", "order_no", name="uq_pos_orders_tenant_no"),
        Index("ix_pos_orders_tenant_date", "tenant_id", "order_date"),
        Index("ix_pos_orders_tenant_session", "tenant_id", "session_id"),
        Index("ix_pos_orders_tenant_status", "tenant_id", "status"),
        CheckConstraint(
            "status IN ('paid','void')",
            name="ck_pos_orders_status",
        ),
        CheckConstraint(
            "payment_method IN ('cash','card','transfer','other')",
            name="ck_pos_orders_payment_method",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pos_sessions.id", ondelete="RESTRICT"), nullable=False
    )
    order_no: Mapped[str] = mapped_column(String(30), nullable=False)
    order_date: Mapped[date] = mapped_column(Date, nullable=False)

    # Optional walk-in customer name (no FK required for quick sales)
    customer_name: Mapped[str | None] = mapped_column(String(200))

    subtotal: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=Decimal("0"), nullable=False
    )
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"), nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"), nullable=False)

    payment_method: Mapped[str] = mapped_column(String(20), default="cash", nullable=False)
    amount_paid: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=Decimal("0"), nullable=False
    )
    change_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=Decimal("0"), nullable=False
    )

    status: Mapped[str] = mapped_column(String(20), default="paid", nullable=False)

    journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    notes: Mapped[str | None] = mapped_column(String(500))
    void_reason: Mapped[str | None] = mapped_column(String(500))
    voided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    session: Mapped[PosSession] = relationship(back_populates="orders")
    lines: Mapped[list["PosOrderLine"]] = relationship(
        back_populates="order", cascade="all, delete-orphan", order_by="PosOrderLine.line_no"
    )


class PosOrderLine(Base):
    """A single line on a POS receipt."""

    __tablename__ = "pos_order_lines"
    __table_args__ = (
        Index("ix_pos_order_lines_order", "order_id"),
        Index("ix_pos_order_lines_item", "tenant_id", "item_id"),
        CheckConstraint("qty > 0", name="ck_pos_order_lines_qty_positive"),
        CheckConstraint("unit_price >= 0", name="ck_pos_order_lines_price_nonneg"),
        CheckConstraint("discount_pct >= 0 AND discount_pct <= 100", name="ck_pos_order_lines_discount"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pos_orders.id", ondelete="CASCADE"), nullable=False
    )
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    discount_pct: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("0"), nullable=False
    )
    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=Decimal("0"), nullable=False
    )
    line_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"), nullable=False)

    # Inventory
    item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("items.id", ondelete="RESTRICT")
    )
    warehouse_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("warehouses.id", ondelete="RESTRICT")
    )

    order: Mapped[PosOrder] = relationship(back_populates="lines")

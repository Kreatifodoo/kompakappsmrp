"""Fulfillment models: DeliveryOrder, GoodsReceipt, RMA + lines.

These are physical-movement documents. Each posted record triggers:
1. stock_movements row (via InventoryService)
2. journal_entry row (via AccountingService)

The original order doc (SO/PO) stays untouched except for derived `qty_*`
counters updated by the service layer.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
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


# ═══════════════════════════════════════════════════════════════════
# Delivery Order (sales side — outbound)
# ═══════════════════════════════════════════════════════════════════

class DeliveryOrder(Base):
    __tablename__ = "delivery_orders"
    __table_args__ = (
        UniqueConstraint("tenant_id", "do_no", name="uq_do_tenant_no"),
        Index("ix_do_tenant_status", "tenant_id", "status"),
        Index("ix_do_so", "so_id"),
        CheckConstraint("status IN ('draft','posted','void')", name="ck_do_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    do_no: Mapped[str] = mapped_column(String(30), nullable=False)
    delivery_date: Mapped[date] = mapped_column(Date, nullable=False)
    so_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sales_orders.id", ondelete="RESTRICT"), nullable=False
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("journal_entries.id", ondelete="SET NULL")
    )
    notes: Mapped[str | None] = mapped_column(String(1000))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    posted_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    void_reason: Mapped[str | None] = mapped_column(String(500))

    lines: Mapped[list["DeliveryOrderLine"]] = relationship(
        back_populates="delivery_order",
        cascade="all, delete-orphan",
    )


class DeliveryOrderLine(Base):
    __tablename__ = "delivery_order_lines"
    __table_args__ = (
        Index("ix_dol_do", "do_id"),
        CheckConstraint("qty_delivered > 0", name="ck_dol_qty_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    do_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("delivery_orders.id", ondelete="CASCADE"), nullable=False
    )
    so_line_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sales_order_lines.id", ondelete="RESTRICT"), nullable=False
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("items.id", ondelete="RESTRICT"), nullable=False
    )
    qty_delivered: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))

    delivery_order: Mapped[DeliveryOrder] = relationship(back_populates="lines")

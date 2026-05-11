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
    # journal_entries is partitioned (composite PK) — no FK, plain UUID
    journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
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


# ═══════════════════════════════════════════════════════════════════
# Goods Receipt (purchase side — inbound)
# ═══════════════════════════════════════════════════════════════════

class GoodsReceipt(Base):
    __tablename__ = "goods_receipts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "gr_no", name="uq_gr_tenant_no"),
        Index("ix_gr_tenant_status", "tenant_id", "status"),
        Index("ix_gr_po", "po_id"),
        CheckConstraint("status IN ('draft','posted','void')", name="ck_gr_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    gr_no: Mapped[str] = mapped_column(String(30), nullable=False)
    receipt_date: Mapped[date] = mapped_column(Date, nullable=False)
    po_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("purchase_orders.id", ondelete="RESTRICT"), nullable=False
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    # journal_entries partitioned — plain UUID
    journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
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

    lines: Mapped[list["GoodsReceiptLine"]] = relationship(
        back_populates="goods_receipt",
        cascade="all, delete-orphan",
    )


class GoodsReceiptLine(Base):
    __tablename__ = "goods_receipt_lines"
    __table_args__ = (
        Index("ix_grl_gr", "gr_id"),
        CheckConstraint("qty_received > 0", name="ck_grl_qty_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    gr_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("goods_receipts.id", ondelete="CASCADE"), nullable=False
    )
    po_line_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("purchase_order_lines.id", ondelete="RESTRICT"), nullable=False
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("items.id", ondelete="RESTRICT"), nullable=False
    )
    qty_received: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)

    goods_receipt: Mapped[GoodsReceipt] = relationship(back_populates="lines")


# ═══════════════════════════════════════════════════════════════════
# RMA — Return Merchandise Authorization
# ═══════════════════════════════════════════════════════════════════

class RMA(Base):
    __tablename__ = "rmas"
    __table_args__ = (
        UniqueConstraint("tenant_id", "rma_no", name="uq_rma_tenant_no"),
        Index("ix_rma_tenant_status", "tenant_id", "status"),
        Index("ix_rma_source_do", "source_do_id"),
        Index("ix_rma_source_gr", "source_gr_id"),
        CheckConstraint(
            "rma_type IN ('customer_return','supplier_return')", name="ck_rma_type"
        ),
        CheckConstraint("status IN ('draft','posted','void')", name="ck_rma_status"),
        CheckConstraint(
            "(rma_type='customer_return' AND source_do_id IS NOT NULL AND source_gr_id IS NULL) "
            "OR (rma_type='supplier_return' AND source_gr_id IS NOT NULL AND source_do_id IS NULL)",
            name="ck_rma_source_xor",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    rma_no: Mapped[str] = mapped_column(String(30), nullable=False)
    rma_type: Mapped[str] = mapped_column(String(20), nullable=False)
    rma_date: Mapped[date] = mapped_column(Date, nullable=False)
    source_do_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("delivery_orders.id", ondelete="RESTRICT")
    )
    source_gr_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("goods_receipts.id", ondelete="RESTRICT")
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    reason: Mapped[str | None] = mapped_column(String(500))
    journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
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

    lines: Mapped[list["RMALine"]] = relationship(
        back_populates="rma",
        cascade="all, delete-orphan",
    )


class RMALine(Base):
    __tablename__ = "rma_lines"
    __table_args__ = (
        Index("ix_rmal_rma", "rma_id"),
        CheckConstraint("qty_returned > 0", name="ck_rmal_qty_positive"),
        CheckConstraint(
            "(source_do_line_id IS NOT NULL) <> (source_gr_line_id IS NOT NULL)",
            name="ck_rmal_source_xor",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rma_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rmas.id", ondelete="CASCADE"), nullable=False
    )
    source_do_line_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("delivery_order_lines.id", ondelete="RESTRICT")
    )
    source_gr_line_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("goods_receipt_lines.id", ondelete="RESTRICT")
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("items.id", ondelete="RESTRICT"), nullable=False
    )
    qty_returned: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)

    rma: Mapped[RMA] = relationship(back_populates="lines")

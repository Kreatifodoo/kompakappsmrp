"""Inventory domain: Item, Warehouse, StockMovement, StockBalance.

Costing method: weighted average (v1). FIFO/LIFO are future enhancements
that would extend StockMovement with cost-layer tracking.

Quantities are NUMERIC(18, 4) to support fractional units (kg, m, hours).
Money columns stay NUMERIC(18, 2).
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
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Warehouse(Base):
    __tablename__ = "warehouses"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_warehouses_tenant_code"),
        Index("ix_warehouses_tenant_active", "tenant_id", "is_active"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Item(Base):
    __tablename__ = "items"
    __table_args__ = (
        UniqueConstraint("tenant_id", "sku", name="uq_items_tenant_sku"),
        Index("ix_items_tenant_active", "tenant_id", "is_active"),
        Index("ix_items_tenant_type", "tenant_id", "type"),
        CheckConstraint("type IN ('stock','service','non_inventory')", name="ck_items_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sku: Mapped[str] = mapped_column(String(60), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000))
    type: Mapped[str] = mapped_column(String(20), nullable=False, default="stock")
    unit: Mapped[str] = mapped_column(String(20), nullable=False, default="pcs")
    default_unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"), nullable=False)
    default_unit_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"), nullable=False)
    min_stock: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class StockMovement(Base):
    """Append-only ledger row representing a single in/out/adjustment
    on one (item, warehouse) pair. The `qty_after` and `avg_cost_after`
    columns snapshot the StockBalance state at that point — useful for
    drill-down ledger reports without re-running the full sum.
    """

    __tablename__ = "stock_movements"
    __table_args__ = (
        Index(
            "ix_stock_movements_tenant_item_date",
            "tenant_id",
            "item_id",
            "movement_date",
        ),
        Index(
            "ix_stock_movements_tenant_warehouse_date",
            "tenant_id",
            "warehouse_id",
            "movement_date",
        ),
        Index("ix_stock_movements_source", "tenant_id", "source", "source_id"),
        CheckConstraint(
            "direction IN ('in','out','adjust_in','adjust_out')",
            name="ck_stock_movements_direction",
        ),
        CheckConstraint("qty > 0", name="ck_stock_movements_qty_positive"),
        CheckConstraint("unit_cost >= 0", name="ck_stock_movements_unit_cost_nonneg"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("items.id", ondelete="RESTRICT"),
        nullable=False,
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False,
    )
    movement_date: Mapped[date] = mapped_column(Date, nullable=False)
    direction: Mapped[str] = mapped_column(String(20), nullable=False)
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    total_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="adjustment")
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    notes: Mapped[str | None] = mapped_column(String(500))
    qty_after: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    avg_cost_after: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class StockBalance(Base):
    """Running per-(tenant, item, warehouse) balance. Updated atomically
    inside post_movement() so reads on stock-on-hand are O(1)."""

    __tablename__ = "stock_balances"
    __table_args__ = (PrimaryKeyConstraint("tenant_id", "item_id", "warehouse_id", name="pk_stock_balances"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("items.id", ondelete="CASCADE"), nullable=False
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False
    )
    on_hand_qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"), nullable=False)
    avg_cost: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class StockCostLayer(Base):
    """One cost layer per stock-in receipt under FIFO/LIFO costing.

    For weighted-average tenants this table stays empty; only FIFO and
    LIFO write rows here. Each layer records the unit_cost at receipt
    and the running remaining_qty as outflows consume it. Layers are
    consumed in received_at order (asc for FIFO, desc for LIFO) and
    `is_exhausted` is denormalized to keep the consume query fast.
    """

    __tablename__ = "stock_cost_layers"
    __table_args__ = (
        Index(
            "ix_stock_cost_layers_consume",
            "tenant_id",
            "item_id",
            "warehouse_id",
            "is_exhausted",
            "received_at",
        ),
        CheckConstraint("original_qty > 0", name="ck_stock_cost_layers_orig_positive"),
        CheckConstraint(
            "remaining_qty >= 0 AND remaining_qty <= original_qty",
            name="ck_stock_cost_layers_remaining_bounds",
        ),
        CheckConstraint("unit_cost >= 0", name="ck_stock_cost_layers_unit_cost_nonneg"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("items.id", ondelete="CASCADE"), nullable=False
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False
    )
    # The IN movement that created this layer (for traceability;
    # nullable for "opening balance" layers seeded on method switch).
    source_movement_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stock_movements.id", ondelete="SET NULL")
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    original_qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    remaining_qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    is_exhausted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

"""Pydantic schemas for Inventory module."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

ItemType = Literal["stock", "service", "non_inventory"]
MovementDirection = Literal["in", "out", "adjust_in", "adjust_out"]


# ─── Warehouse ────────────────────────────────────────────
class WarehouseCreate(BaseModel):
    code: str = Field(min_length=1, max_length=30)
    name: str = Field(min_length=1, max_length=200)
    is_default: bool = False


class WarehouseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    is_default: bool | None = None
    is_active: bool | None = None


class WarehouseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str
    is_default: bool
    is_active: bool


# ─── Item ─────────────────────────────────────────────────
class ItemCreate(BaseModel):
    sku: str = Field(min_length=1, max_length=60)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    type: ItemType = "stock"
    unit: str = Field(default="pcs", min_length=1, max_length=20)
    default_unit_price: Decimal = Field(default=Decimal("0"), ge=0)
    default_unit_cost: Decimal = Field(default=Decimal("0"), ge=0)
    min_stock: Decimal = Field(default=Decimal("0"), ge=0)


class ItemUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    unit: str | None = Field(default=None, min_length=1, max_length=20)
    default_unit_price: Decimal | None = Field(default=None, ge=0)
    default_unit_cost: Decimal | None = Field(default=None, ge=0)
    min_stock: Decimal | None = Field(default=None, ge=0)
    is_active: bool | None = None


class ItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    sku: str
    name: str
    description: str | None
    type: ItemType
    unit: str
    default_unit_price: Decimal
    default_unit_cost: Decimal
    min_stock: Decimal
    is_active: bool


# ─── Stock movement ───────────────────────────────────────
class StockMovementCreate(BaseModel):
    """Manual movement: opening balance, cycle-count adjustment, or
    movements not tied to an invoice. Sales/purchase invoice posting
    creates these automatically (Phase 2)."""

    item_id: UUID
    warehouse_id: UUID
    movement_date: date
    direction: MovementDirection
    qty: Decimal = Field(gt=0)
    # For 'in' / 'adjust_in' movements: the cost per unit (will be
    # weighted-averaged into avg_cost). For 'out' / 'adjust_out' the
    # unit_cost is ignored and the current avg_cost is used; pass any
    # non-negative value or 0.
    unit_cost: Decimal = Field(default=Decimal("0"), ge=0)
    notes: str | None = Field(default=None, max_length=500)


class StockMovementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    item_id: UUID
    warehouse_id: UUID
    movement_date: date
    direction: MovementDirection
    qty: Decimal
    unit_cost: Decimal
    total_cost: Decimal
    source: str
    source_id: UUID | None
    notes: str | None
    qty_after: Decimal
    avg_cost_after: Decimal
    created_at: datetime


# ─── Stock balance + reports ──────────────────────────────
class StockBalanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    item_id: UUID
    warehouse_id: UUID
    on_hand_qty: Decimal
    avg_cost: Decimal


class StockOnHandLine(BaseModel):
    """A single item's on-hand position in one warehouse."""

    item_id: UUID
    sku: str
    name: str
    unit: str
    warehouse_id: UUID
    warehouse_code: str
    on_hand_qty: Decimal
    avg_cost: Decimal
    value: Decimal  # qty × avg_cost
    below_min_stock: bool


class StockOnHandReport(BaseModel):
    lines: list[StockOnHandLine]
    total_value: Decimal


class StockValuationReport(BaseModel):
    """Aggregated valuation across warehouses, one row per item."""

    lines: list["StockValuationLine"]
    total_value: Decimal


class StockValuationLine(BaseModel):
    item_id: UUID
    sku: str
    name: str
    unit: str
    on_hand_qty: Decimal  # summed across warehouses
    weighted_avg_cost: Decimal
    value: Decimal


StockValuationReport.model_rebuild()

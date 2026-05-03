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


# ─── Reorder report ───────────────────────────────────────
class ReorderLine(BaseModel):
    """One row in the reorder report — an item whose total on-hand
    quantity (across warehouses, or in a single warehouse when
    warehouse_id is supplied) is below its min_stock threshold."""

    item_id: UUID
    sku: str
    name: str
    unit: str
    min_stock: Decimal
    on_hand_qty: Decimal          # current total (all or filtered WH)
    shortage: Decimal             # max(0, min_stock - on_hand_qty)
    avg_cost: Decimal             # weighted avg across included warehouses
    shortage_value: Decimal       # shortage × avg_cost


class ReorderReport(BaseModel):
    """All items that need restocking, sorted by SKU."""

    as_of_today: date
    warehouse_id: UUID | None     # None = all warehouses aggregated
    lines: list[ReorderLine]
    total_shortage_value: Decimal


# ─── Slow-moving items report ──────────────────────────────
class SlowMovingLine(BaseModel):
    """One item–warehouse row flagged as slow-moving because it had no
    outflow (direction='out' or 'adjust_out') within the lookback window,
    or its last outflow was longer ago than `days` from today."""

    item_id: UUID
    sku: str
    name: str
    unit: str
    warehouse_id: UUID
    warehouse_code: str
    on_hand_qty: Decimal
    avg_cost: Decimal
    on_hand_value: Decimal              # on_hand_qty × avg_cost
    last_outflow_date: date | None      # None = never moved out
    days_since_last_outflow: int | None # None = never moved out
    period_out_qty: Decimal             # outflow qty within lookback window


class SlowMovingReport(BaseModel):
    """Items with no or minimal outflow in the lookback window."""

    as_of_today: date
    lookback_days: int                  # threshold supplied by caller
    warehouse_id: UUID | None           # None = all warehouses
    lines: list[SlowMovingLine]         # sorted by days_since_last_outflow DESC, sku
    total_on_hand_value: Decimal


# ─── Costing method ───────────────────────────────────────
CostingMethod = Literal["avg", "fifo", "lifo"]


class CostingMethodOut(BaseModel):
    method: CostingMethod


class SetCostingMethodRequest(BaseModel):
    method: CostingMethod
    # When switching avg → fifo/lifo, seed an opening cost layer per
    # existing (item, warehouse) balance using the current avg_cost. If
    # false, the switch leaves no layers and the next outflow on any
    # item with stock-on-hand will fail until layers are populated
    # manually (via stock-in receipts). Default true.
    seed_opening_layers: bool = True


# ─── Stock transfer ───────────────────────────────────────
TransferStatus = Literal["posted", "void"]


class StockTransferLineIn(BaseModel):
    item_id: UUID
    qty: Decimal = Field(gt=0)
    notes: str | None = Field(default=None, max_length=500)


class StockTransferLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    line_no: int
    item_id: UUID
    qty: Decimal
    unit_cost: Decimal
    notes: str | None


class StockTransferCreate(BaseModel):
    transfer_no: str | None = Field(default=None, max_length=30)
    transfer_date: date
    source_warehouse_id: UUID
    destination_warehouse_id: UUID
    notes: str | None = Field(default=None, max_length=1000)
    lines: list[StockTransferLineIn] = Field(min_length=1)


class StockTransferOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    transfer_no: str
    transfer_date: date
    source_warehouse_id: UUID
    destination_warehouse_id: UUID
    status: TransferStatus
    notes: str | None
    lines: list[StockTransferLineOut]


class TransferVoidRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


# ─── Cost layers ledger ───────────────────────────────────
class CostLayerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    item_id: UUID
    warehouse_id: UUID
    source_movement_id: UUID | None
    received_at: datetime
    original_qty: Decimal
    remaining_qty: Decimal
    unit_cost: Decimal
    is_exhausted: bool
    remaining_value: Decimal  # remaining_qty × unit_cost (server-computed)


class CostLayersReport(BaseModel):
    """Drill-down on an item's cost layers, used to understand the
    cost basis currently sitting on shelf under FIFO/LIFO. Empty for
    tenants on `avg` costing (layers aren't written for avg)."""

    item_id: UUID
    layers: list[CostLayerOut]
    total_remaining_qty: Decimal
    total_remaining_value: Decimal


# ─── Stock card report ───────────────────────────────────
class StockCardLine(BaseModel):
    """One row of an item's stock card — a single movement plus the
    running qty/avg/value snapshot taken at that movement."""

    movement_id: UUID
    movement_date: date
    direction: str
    qty: Decimal
    unit_cost: Decimal
    total_cost: Decimal
    source: str
    source_id: UUID | None
    notes: str | None
    qty_after: Decimal
    avg_cost_after: Decimal
    value_after: Decimal  # qty_after × avg_cost_after (server-computed)


class StockCardReport(BaseModel):
    """Per-(item, warehouse) chronological card with opening / closing
    balances and per-row running snapshot. Always per single warehouse
    so running qty + avg_cost form a coherent series."""

    item_id: UUID
    sku: str
    name: str
    unit: str
    warehouse_id: UUID
    warehouse_code: str
    date_from: date | None
    date_to: date | None
    opening_qty: Decimal
    opening_avg_cost: Decimal
    opening_value: Decimal
    lines: list[StockCardLine]
    closing_qty: Decimal
    closing_avg_cost: Decimal
    closing_value: Decimal
    period_in_qty: Decimal  # sum of qty for in + adjust_in
    period_out_qty: Decimal  # sum of qty for out + adjust_out
    period_in_value: Decimal  # sum of total_cost for in + adjust_in
    period_out_value: Decimal  # sum of total_cost for out + adjust_out

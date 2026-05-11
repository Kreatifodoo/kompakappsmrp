"""Pydantic schemas for fulfillment docs."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


DOStatus = Literal["draft", "posted", "void"]


# ─── DeliveryOrder ────────────────────────────────────────
class DeliveryOrderLineIn(BaseModel):
    so_line_id: UUID
    qty_delivered: Decimal = Field(gt=0)


class DeliveryOrderLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    so_line_id: UUID
    item_id: UUID
    qty_delivered: Decimal
    unit_cost: Decimal | None


class DeliveryOrderCreate(BaseModel):
    do_no: str | None = Field(default=None, max_length=30)
    delivery_date: date
    so_id: UUID
    warehouse_id: UUID
    notes: str | None = Field(default=None, max_length=1000)
    lines: list[DeliveryOrderLineIn] = Field(min_length=1)


class DeliveryOrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    do_no: str
    delivery_date: date
    so_id: UUID
    warehouse_id: UUID
    status: DOStatus
    journal_entry_id: UUID | None
    notes: str | None
    created_at: datetime
    posted_at: datetime | None
    voided_at: datetime | None
    void_reason: str | None
    lines: list[DeliveryOrderLineOut]


class DOVoidRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


# ─── GoodsReceipt ───────────────────────────────────────
GRStatus = Literal["draft", "posted", "void"]


class GoodsReceiptLineIn(BaseModel):
    po_line_id: UUID
    qty_received: Decimal = Field(gt=0)
    # If not provided, fall back to po_line.unit_price as receipt cost
    unit_cost: Decimal | None = Field(default=None, ge=0)


class GoodsReceiptLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    po_line_id: UUID
    item_id: UUID
    qty_received: Decimal
    unit_cost: Decimal


class GoodsReceiptCreate(BaseModel):
    gr_no: str | None = Field(default=None, max_length=30)
    receipt_date: date
    po_id: UUID
    warehouse_id: UUID
    notes: str | None = Field(default=None, max_length=1000)
    lines: list[GoodsReceiptLineIn] = Field(min_length=1)


class GoodsReceiptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    gr_no: str
    receipt_date: date
    po_id: UUID
    warehouse_id: UUID
    status: GRStatus
    journal_entry_id: UUID | None
    notes: str | None
    created_at: datetime
    posted_at: datetime | None
    voided_at: datetime | None
    void_reason: str | None
    lines: list[GoodsReceiptLineOut]


class GRVoidRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)

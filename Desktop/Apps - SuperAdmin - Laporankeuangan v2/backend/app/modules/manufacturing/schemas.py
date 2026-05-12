"""Pydantic schemas for manufacturing module (Sprint M1: BOM, M2: MO)."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


BOMStatus = Literal["draft", "active", "obsolete"]


class BOMLineIn(BaseModel):
    item_id: UUID
    qty_required: Decimal = Field(gt=0)
    scrap_pct: Decimal = Field(default=Decimal("0"), ge=0, lt=100)
    # Sprint M4: optional standard unit cost for variance accounting
    std_unit_cost: Decimal | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=500)


class BOMLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    line_no: int
    item_id: UUID
    qty_required: Decimal
    scrap_pct: Decimal
    std_unit_cost: Decimal | None
    notes: str | None


class BOMCreate(BaseModel):
    bom_code: str | None = Field(default=None, max_length=40)
    item_id: UUID
    qty_output: Decimal = Field(default=Decimal("1"), gt=0)
    version: int = Field(default=1, ge=1)
    notes: str | None = Field(default=None, max_length=1000)
    lines: list[BOMLineIn] = Field(min_length=1)


class BOMUpdate(BaseModel):
    """Allowed only on draft BOMs."""
    bom_code: str | None = Field(default=None, max_length=40)
    qty_output: Decimal | None = Field(default=None, gt=0)
    version: int | None = Field(default=None, ge=1)
    notes: str | None = Field(default=None, max_length=1000)
    lines: list[BOMLineIn] | None = None


class BOMOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    bom_code: str
    item_id: UUID
    qty_output: Decimal
    version: int
    status: BOMStatus
    notes: str | None
    created_at: datetime
    lines: list[BOMLineOut]


# ═══════════════════════════════════════════════════════════════════
# Manufacturing Order (Sprint M2)
# ═══════════════════════════════════════════════════════════════════

MOStatus = Literal["draft", "confirmed", "in_progress", "done", "cancelled"]


class MOComponentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    bom_line_id: UUID | None
    item_id: UUID
    qty_planned: Decimal
    qty_issued: Decimal
    unit_cost: Decimal
    std_unit_cost: Decimal | None


class MOCreate(BaseModel):
    mo_no: str | None = Field(default=None, max_length=30)
    # Either bom_id (explicit) OR item_id (uses the active BOM for that item)
    bom_id: UUID | None = None
    item_id: UUID | None = None
    warehouse_id: UUID
    qty_planned: Decimal = Field(gt=0)
    planned_start: date | None = None
    planned_end: date | None = None
    backflush: bool = True
    notes: str | None = Field(default=None, max_length=1000)


class MOIssueLine(BaseModel):
    component_id: UUID
    qty: Decimal = Field(gt=0)


class MOIssueRequest(BaseModel):
    lines: list[MOIssueLine] = Field(min_length=1)


class MOCompleteRequest(BaseModel):
    qty_produced: Decimal = Field(gt=0)
    complete_date: date | None = None  # default: today


class MOCancelRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class MOOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    mo_no: str
    bom_id: UUID
    item_id: UUID
    warehouse_id: UUID
    qty_planned: Decimal
    qty_produced: Decimal
    planned_start: date | None
    planned_end: date | None
    actual_start: datetime | None
    actual_end: datetime | None
    status: MOStatus
    backflush: bool
    notes: str | None
    issue_journal_entry_id: UUID | None
    receipt_journal_entry_id: UUID | None
    # Sprint M4: standard costing & variance
    std_total_cost: Decimal | None
    variance_amount: Decimal | None
    variance_journal_entry_id: UUID | None
    created_at: datetime
    confirmed_at: datetime | None
    done_at: datetime | None
    cancelled_at: datetime | None
    cancel_reason: str | None
    components: list[MOComponentOut]

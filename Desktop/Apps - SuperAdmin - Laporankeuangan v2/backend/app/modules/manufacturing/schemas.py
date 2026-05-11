"""Pydantic schemas for manufacturing module (Sprint M1: BOM)."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


BOMStatus = Literal["draft", "active", "obsolete"]


class BOMLineIn(BaseModel):
    item_id: UUID
    qty_required: Decimal = Field(gt=0)
    scrap_pct: Decimal = Field(default=Decimal("0"), ge=0, lt=100)
    notes: str | None = Field(default=None, max_length=500)


class BOMLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    line_no: int
    item_id: UUID
    qty_required: Decimal
    scrap_pct: Decimal
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

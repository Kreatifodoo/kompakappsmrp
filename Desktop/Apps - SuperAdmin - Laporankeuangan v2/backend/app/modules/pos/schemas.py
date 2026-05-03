"""POS domain Pydantic schemas."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

PaymentMethod = Literal["cash", "card", "transfer", "other"]
SessionStatus = Literal["open", "closed"]
OrderStatus = Literal["paid", "void"]


# ─── Session ──────────────────────────────────────────────────────────────────

class PosSessionOpen(BaseModel):
    """Payload to open a new POS session."""
    register_name: str = Field(default="Main Register", max_length=100)
    opening_amount: Decimal = Field(default=Decimal("0"), ge=0, description="Opening cash float")
    notes: str | None = Field(default=None, max_length=500)


class PosSessionClose(BaseModel):
    """Payload to close a POS session."""
    closing_amount: Decimal = Field(ge=0, description="Actual cash counted at close")
    notes: str | None = Field(default=None, max_length=500)


class PosSessionOut(BaseModel):
    id: UUID
    session_no: str
    register_name: str
    cashier_id: UUID
    status: SessionStatus
    opening_amount: Decimal
    closing_amount: Decimal | None
    expected_closing: Decimal | None
    cash_difference: Decimal | None
    total_sales: Decimal
    total_orders: int
    opened_at: datetime
    closed_at: datetime | None
    notes: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Order Lines ──────────────────────────────────────────────────────────────

class PosOrderLineIn(BaseModel):
    """A single line on a new POS order."""
    description: str = Field(max_length=500)
    qty: Decimal = Field(gt=0)
    unit_price: Decimal = Field(ge=0)
    discount_pct: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    tax_rate: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    item_id: UUID | None = None
    warehouse_id: UUID | None = None

    @field_validator("qty", "unit_price", "discount_pct", "tax_rate", mode="before")
    @classmethod
    def coerce_decimal(cls, v):
        return Decimal(str(v))


class PosOrderLineOut(BaseModel):
    id: UUID
    line_no: int
    description: str
    qty: Decimal
    unit_price: Decimal
    discount_pct: Decimal
    discount_amount: Decimal
    line_total: Decimal
    tax_rate: Decimal
    tax_amount: Decimal
    item_id: UUID | None
    warehouse_id: UUID | None

    model_config = {"from_attributes": True}


# ─── Order ────────────────────────────────────────────────────────────────────

class PosOrderCreate(BaseModel):
    """Payload to create and immediately post a POS order."""
    session_id: UUID
    order_date: date
    customer_name: str | None = Field(default=None, max_length=200)
    lines: list[PosOrderLineIn] = Field(min_length=1)
    payment_method: PaymentMethod = "cash"
    amount_paid: Decimal = Field(ge=0, description="Amount tendered by customer")
    notes: str | None = Field(default=None, max_length=500)

    @field_validator("amount_paid", mode="before")
    @classmethod
    def coerce_decimal(cls, v):
        return Decimal(str(v))

    @model_validator(mode="after")
    def validate_amount_paid(self):
        # We can't validate against total here (not computed yet), so we just
        # ensure amount_paid > 0.  Under-payment check happens in the service.
        if self.amount_paid < 0:
            raise ValueError("amount_paid must be >= 0")
        return self


class PosOrderOut(BaseModel):
    id: UUID
    session_id: UUID
    order_no: str
    order_date: date
    customer_name: str | None
    subtotal: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    total: Decimal
    payment_method: PaymentMethod
    amount_paid: Decimal
    change_amount: Decimal
    status: OrderStatus
    journal_entry_id: UUID | None
    notes: str | None
    void_reason: str | None
    voided_at: datetime | None
    created_by: UUID | None
    created_at: datetime
    lines: list[PosOrderLineOut]

    model_config = {"from_attributes": True}


class PosOrderVoid(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


# ─── Summary / Reports ────────────────────────────────────────────────────────

class PosSessionSummary(BaseModel):
    """Aggregated summary returned when closing (or viewing) a session."""
    session: PosSessionOut
    total_cash: Decimal
    total_card: Decimal
    total_transfer: Decimal
    total_other: Decimal
    order_count: int
    void_count: int

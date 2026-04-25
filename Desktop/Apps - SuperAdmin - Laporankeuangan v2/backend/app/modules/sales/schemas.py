"""Pydantic schemas for Sales module."""
from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

InvoiceStatus = Literal["draft", "posted", "paid", "void"]


# ─── Customer ─────────────────────────────────────────────
class CustomerCreate(BaseModel):
    code: str = Field(min_length=1, max_length=30)
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    address: str | None = Field(default=None, max_length=500)
    tax_id: str | None = Field(default=None, max_length=50)
    notes: str | None = Field(default=None, max_length=1000)


class CustomerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    address: str | None = Field(default=None, max_length=500)
    tax_id: str | None = Field(default=None, max_length=50)
    is_active: bool | None = None
    notes: str | None = Field(default=None, max_length=1000)


class CustomerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str
    email: str | None
    phone: str | None
    address: str | None
    tax_id: str | None
    is_active: bool


# ─── Sales Invoice ────────────────────────────────────────
class SalesInvoiceLineIn(BaseModel):
    description: str = Field(min_length=1, max_length=500)
    qty: Decimal = Field(gt=0)
    unit_price: Decimal = Field(ge=0)
    tax_rate: Decimal = Field(default=Decimal("0"), ge=0, le=100)


class SalesInvoiceLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    line_no: int
    description: str
    qty: Decimal
    unit_price: Decimal
    line_total: Decimal
    tax_rate: Decimal
    tax_amount: Decimal


class SalesInvoiceCreate(BaseModel):
    invoice_no: str | None = Field(default=None, max_length=30)
    invoice_date: date
    due_date: date | None = None
    customer_id: UUID
    notes: str | None = Field(default=None, max_length=1000)
    lines: list[SalesInvoiceLineIn] = Field(min_length=1)


class SalesInvoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    invoice_no: str
    invoice_date: date
    due_date: date | None
    customer_id: UUID
    subtotal: Decimal
    tax_amount: Decimal
    total: Decimal
    paid_amount: Decimal
    status: InvoiceStatus
    notes: str | None
    journal_entry_id: UUID | None
    posted_at: datetime | None
    created_at: datetime
    lines: list[SalesInvoiceLineOut]


class InvoiceVoidRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)

"""Pydantic schemas for Payments module."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

PaymentDirection = Literal["receipt", "disbursement", "customer_refund", "supplier_refund"]
PaymentStatus = Literal["draft", "posted", "void"]

CUSTOMER_DIRECTIONS = {"receipt", "customer_refund"}
SUPPLIER_DIRECTIONS = {"disbursement", "supplier_refund"}
SETTLEMENT_DIRECTIONS = {"receipt", "disbursement"}  # support invoice applications
REFUND_DIRECTIONS = {"customer_refund", "supplier_refund"}


class PaymentApplicationIn(BaseModel):
    """Apply this much of the payment to a specific invoice.
    Set sales_invoice_id (for receipts) OR purchase_invoice_id
    (for disbursements) — not both."""

    sales_invoice_id: UUID | None = None
    purchase_invoice_id: UUID | None = None
    amount: Decimal = Field(gt=0)

    @model_validator(mode="after")
    def _xor_invoice(self) -> "PaymentApplicationIn":
        if (self.sales_invoice_id is None) == (self.purchase_invoice_id is None):
            raise ValueError("Exactly one of sales_invoice_id / purchase_invoice_id must be set")
        return self


class PaymentApplicationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    sales_invoice_id: UUID | None
    purchase_invoice_id: UUID | None
    amount: Decimal


class PaymentCreate(BaseModel):
    payment_no: str | None = Field(default=None, max_length=30)
    payment_date: date
    direction: PaymentDirection
    customer_id: UUID | None = None
    supplier_id: UUID | None = None
    amount: Decimal = Field(gt=0)
    cash_account_id: UUID
    reference: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=1000)
    # Optional. For settlement (receipt/disbursement), at least one
    # application is required and sum(apps) ≤ amount (overpayment leaves
    # the difference as unallocated credit on the party's AR/AP balance).
    # For refund directions, applications are not allowed (v1).
    applications: list[PaymentApplicationIn] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate(self) -> "PaymentCreate":
        # Party / direction consistency
        if self.direction in CUSTOMER_DIRECTIONS:
            if self.customer_id is None or self.supplier_id is not None:
                raise ValueError(f"{self.direction} requires customer_id (and no supplier_id)")
        else:  # supplier directions
            if self.supplier_id is None or self.customer_id is not None:
                raise ValueError(f"{self.direction} requires supplier_id (and no customer_id)")

        if self.direction in REFUND_DIRECTIONS:
            if self.applications:
                raise ValueError(
                    f"{self.direction} does not support invoice applications "
                    "in v1 — submit refunds without applications; they clear "
                    "unallocated AR/AP credit on the party's account"
                )
            return self

        # Settlement directions: applications required + invoice type checks
        if not self.applications:
            raise ValueError(f"{self.direction} requires at least one application")

        if self.direction == "receipt":
            if any(a.purchase_invoice_id is not None for a in self.applications):
                raise ValueError("Receipts cannot apply to purchase invoices")
            if any(a.sales_invoice_id is None for a in self.applications):
                raise ValueError("Each application must specify sales_invoice_id")
        else:  # disbursement
            if any(a.sales_invoice_id is not None for a in self.applications):
                raise ValueError("Disbursements cannot apply to sales invoices")
            if any(a.purchase_invoice_id is None for a in self.applications):
                raise ValueError("Each application must specify purchase_invoice_id")

        # Allow overpayment: sum(apps) ≤ amount (difference flows to
        # unallocated AR/AP credit). Reject only sum > amount.
        total_applied = sum((a.amount for a in self.applications), Decimal("0"))
        if total_applied > self.amount:
            raise ValueError(
                f"Sum of applications ({total_applied}) cannot exceed payment amount ({self.amount})"
            )
        return self


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    payment_no: str
    payment_date: date
    direction: PaymentDirection
    customer_id: UUID | None
    supplier_id: UUID | None
    amount: Decimal
    cash_account_id: UUID
    reference: str | None
    notes: str | None
    status: PaymentStatus
    journal_entry_id: UUID | None
    posted_at: datetime | None
    created_at: datetime
    applications: list[PaymentApplicationOut]


class PaymentVoidRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)

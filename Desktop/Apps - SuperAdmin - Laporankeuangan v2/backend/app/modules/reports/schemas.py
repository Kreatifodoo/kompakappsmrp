"""Report response schemas."""

from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

AccountType = Literal["asset", "liability", "equity", "income", "expense"]


# ─── Trial Balance ────────────────────────────────────────
class TrialBalanceLine(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    account_id: UUID
    code: str
    name: str
    type: AccountType
    normal_side: Literal["debit", "credit"]
    total_debit: Decimal
    total_credit: Decimal
    balance: Decimal  # signed by normal_side: positive = on its natural side


class TrialBalance(BaseModel):
    as_of: date
    lines: list[TrialBalanceLine]
    total_debit: Decimal
    total_credit: Decimal
    balanced: bool  # total_debit == total_credit (always true for valid books)


# ─── Profit & Loss ────────────────────────────────────────
class PLLine(BaseModel):
    account_id: UUID
    code: str
    name: str
    amount: Decimal  # positive = normal direction (income → credit, expense → debit)


class ProfitLoss(BaseModel):
    date_from: date
    date_to: date
    income: list[PLLine]
    total_income: Decimal
    expense: list[PLLine]
    total_expense: Decimal
    net_profit: Decimal  # income - expense


# ─── Balance Sheet ────────────────────────────────────────
class BSLine(BaseModel):
    account_id: UUID
    code: str
    name: str
    amount: Decimal  # positive = normal direction


class BalanceSheet(BaseModel):
    as_of: date
    assets: list[BSLine]
    total_assets: Decimal
    liabilities: list[BSLine]
    total_liabilities: Decimal
    equity: list[BSLine]
    retained_earnings: Decimal  # net P/L through as_of
    total_equity: Decimal  # explicit equity + retained_earnings
    balanced: bool  # |assets - (liab + equity)| < 0.01
    imbalance: Decimal  # assets - (liab + equity); should round to 0


# ─── Aged AR / AP ─────────────────────────────────────────
class AgedBuckets(BaseModel):
    """Outstanding amount split by age bucket (in days overdue)."""

    current: Decimal  # not yet due
    days_1_30: Decimal
    days_31_60: Decimal
    days_61_90: Decimal
    days_over_90: Decimal
    total: Decimal


class AgedInvoiceLine(BaseModel):
    """A single unpaid invoice contributing to its party's buckets."""

    invoice_id: UUID
    invoice_no: str
    invoice_date: date
    due_date: date | None
    total: Decimal
    paid_amount: Decimal
    outstanding: Decimal
    days_overdue: int  # 0 if not yet due


class AgedPartyLine(BaseModel):
    """One row per customer (AR) or supplier (AP) with outstanding > 0."""

    party_id: UUID
    code: str
    name: str
    invoice_count: int
    buckets: AgedBuckets
    invoices: list[AgedInvoiceLine]


class AgedReport(BaseModel):
    as_of: date
    lines: list[AgedPartyLine]
    totals: AgedBuckets


# ─── Customer / Supplier statement ─────────────────────────
StatementLineType = Literal["invoice", "payment"]


class StatementLine(BaseModel):
    """One row of a statement: an invoice posting OR a payment application,
    with running balance after this row is applied."""

    date: date
    type: StatementLineType
    reference: str  # invoice_no or payment_no
    description: str | None
    debit: Decimal  # increases AR / decreases AP from the party's perspective
    credit: Decimal  # decreases AR / increases AP
    balance: Decimal  # running balance after this row, signed by party normal_side


class Statement(BaseModel):
    party_id: UUID
    code: str
    name: str
    date_from: date
    date_to: date
    opening_balance: Decimal  # balance just before date_from
    lines: list[StatementLine]
    closing_balance: Decimal
    period_debit_total: Decimal
    period_credit_total: Decimal

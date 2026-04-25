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

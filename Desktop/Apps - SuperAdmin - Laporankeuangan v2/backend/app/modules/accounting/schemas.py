"""Pydantic schemas for Accounting module."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

AccountType = Literal["asset", "liability", "equity", "income", "expense"]
NormalSide = Literal["debit", "credit"]
EntryStatus = Literal["draft", "posted", "void"]


# ─── Account / COA ────────────────────────────────────────
class AccountCreate(BaseModel):
    code: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=200)
    type: AccountType
    normal_side: NormalSide
    parent_id: UUID | None = None
    description: str | None = Field(default=None, max_length=500)


class AccountUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    parent_id: UUID | None = None
    is_active: bool | None = None
    is_cash: bool | None = None
    description: str | None = Field(default=None, max_length=500)


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str
    type: AccountType
    normal_side: NormalSide
    parent_id: UUID | None
    is_active: bool
    is_system: bool
    is_cash: bool
    description: str | None


# ─── Journal ──────────────────────────────────────────────
class JournalLineIn(BaseModel):
    account_id: UUID
    description: str | None = Field(default=None, max_length=500)
    debit: Decimal = Field(default=Decimal("0"), ge=0)
    credit: Decimal = Field(default=Decimal("0"), ge=0)

    @model_validator(mode="after")
    def _xor_debit_credit(self) -> "JournalLineIn":
        if self.debit > 0 and self.credit > 0:
            raise ValueError("A line cannot have both debit and credit")
        if self.debit == 0 and self.credit == 0:
            raise ValueError("A line must have a debit or credit > 0")
        return self


class JournalLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    line_no: int
    account_id: UUID
    description: str | None
    debit: Decimal
    credit: Decimal


class JournalEntryCreate(BaseModel):
    entry_no: str | None = Field(default=None, max_length=30)  # auto if None
    entry_date: date
    description: str | None = Field(default=None, max_length=500)
    reference: str | None = Field(default=None, max_length=100)
    lines: list[JournalLineIn] = Field(min_length=2)

    @model_validator(mode="after")
    def _balanced(self) -> "JournalEntryCreate":
        total_debit = sum((ln.debit for ln in self.lines), Decimal("0"))
        total_credit = sum((ln.credit for ln in self.lines), Decimal("0"))
        if total_debit != total_credit:
            raise ValueError(f"Journal not balanced: debit={total_debit} credit={total_credit}")
        return self


class JournalEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    entry_no: str
    entry_date: date
    description: str | None
    reference: str | None
    status: EntryStatus
    source: str | None
    posted_at: datetime | None
    created_at: datetime
    lines: list[JournalLineOut]


class JournalVoidRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


# ─── Account Mappings ─────────────────────────────────────
WELL_KNOWN_MAPPING_KEYS = {
    "ar",
    "ap",
    "sales_revenue",
    "purchase_expense",
    "tax_payable",
    "tax_receivable",
    "cash_default",
    "inventory",  # asset account that absorbs item-tracked stock
    "cogs",  # expense account hit on stock-out for sold items
}


class AccountMappingSet(BaseModel):
    key: str = Field(min_length=1, max_length=50)
    account_id: UUID


class AccountMappingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    account_id: UUID


# ─── Starter COA seeder ───────────────────────────────────
class StarterCOASeedResult(BaseModel):
    accounts_created: int
    accounts_skipped: int
    mappings_set: int

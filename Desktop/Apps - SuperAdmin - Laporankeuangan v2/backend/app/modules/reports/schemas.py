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


# ─── Bank reconciliation ───────────────────────────────────
class BankStatementLine(BaseModel):
    """One row from the bank's CSV/PDF, as supplied by the user.

    `amount` is signed from the perspective of OUR bank account:
    positive = money in (deposit), negative = money out (withdrawal).
    """

    date: date
    amount: Decimal
    reference: str | None = None
    description: str | None = None


class BookCashLine(BaseModel):
    """One book-side journal-line debit/credit on a cash account."""

    journal_entry_id: UUID
    entry_no: str
    entry_date: date
    amount: Decimal  # signed: + for cash debit (in), - for cash credit (out)
    description: str | None
    line_description: str | None


class BankRecMatch(BaseModel):
    book: BookCashLine
    statement: BankStatementLine


class BankReconciliationRequest(BaseModel):
    cash_account_id: UUID
    date_from: date
    date_to: date
    statement_lines: list[BankStatementLine]
    date_tolerance_days: int = 2  # ±2 days default; bank-vs-book posting lag


# ─── PPN (Indonesian VAT) report ──────────────────────────
class PPNSalesLine(BaseModel):
    """One sales (output VAT) entry for a PPN report row."""

    invoice_id: UUID
    invoice_no: str
    invoice_date: date
    customer_code: str
    customer_name: str
    customer_tax_id: str | None
    base: Decimal  # subtotal (taxable base / DPP)
    tax: Decimal  # output VAT collected (PPN Keluaran)


class PPNPurchaseLine(BaseModel):
    """One purchase (input VAT) entry."""

    invoice_id: UUID
    invoice_no: str
    supplier_invoice_no: str | None
    invoice_date: date
    supplier_code: str
    supplier_name: str
    supplier_tax_id: str | None
    base: Decimal
    tax: Decimal  # input VAT paid (PPN Masukan)


class PPNTotals(BaseModel):
    sales_base_total: Decimal
    output_vat_total: Decimal  # PPN Keluaran
    purchase_base_total: Decimal
    input_vat_total: Decimal  # PPN Masukan
    net_vat_payable: Decimal  # Output - Input (positive = payable; negative = refund)


class PPNReport(BaseModel):
    period: str  # "YYYY-MM"
    year: int
    month: int
    sales: list[PPNSalesLine]
    purchases: list[PPNPurchaseLine]
    totals: PPNTotals


class BankReconciliation(BaseModel):
    cash_account_id: UUID
    cash_account_code: str
    cash_account_name: str
    date_from: date
    date_to: date
    matched: list[BankRecMatch]
    book_only: list[BookCashLine]  # in our books, not on the statement
    statement_only: list[BankStatementLine]  # on statement, not in our books
    book_period_total: Decimal  # net signed change in books in period
    statement_period_total: Decimal  # net signed change on statement in period
    book_only_total: Decimal  # sum of unmatched book lines (signed)
    statement_only_total: Decimal  # sum of unmatched statement lines (signed)
    difference: Decimal  # book_period_total - statement_period_total


# ─── Cash Flow Statement (indirect method) ────────────────
class CashFlowLine(BaseModel):
    """One adjustment line in the cash flow statement.

    For the indirect method each line represents the period change in a
    non-cash balance-sheet account classified under operating, investing,
    or financing activities.

    `amount` is already cash-effect signed:
      positive  = cash inflow (source of cash)
      negative  = cash outflow (use of cash)

    For assets (normal_side=debit):
      amount = -(closing_balance - opening_balance)
      i.e. an asset *increase* consumes cash → negative
    For liabilities/equity (normal_side=credit):
      amount = +(closing_balance - opening_balance)
      i.e. a liability *increase* provides cash → positive
    """

    account_id: UUID
    code: str
    name: str
    opening_balance: Decimal
    closing_balance: Decimal
    amount: Decimal  # cash effect (signed as described above)


class CashFlowSection(BaseModel):
    """One of the three sections (operating / investing / financing)."""

    lines: list[CashFlowLine]
    subtotal: Decimal


class CashFlowStatement(BaseModel):
    """Indirect-method Statement of Cash Flows for a date range.

    Structure:
      A. Net income (accrual P&L for the period)
      B. Operating activities:  working-capital adjustments (cf_section='operating')
         → net_operating  = net_income + operating.subtotal
      C. Investing activities   (cf_section='investing')
      D. Financing activities   (cf_section='financing')
      Net change in cash = net_operating + investing.subtotal + financing.subtotal
      Opening cash + net_change = closing cash (reconciliation check)
    """

    date_from: date
    date_to: date

    # ── A. Profitability ─────────────────────────────────
    net_income: Decimal  # accrual net profit for [date_from, date_to]

    # ── B–D. Balance-sheet movements ─────────────────────
    operating: CashFlowSection   # working-capital adjustments
    investing: CashFlowSection   # fixed assets / long-term investments
    financing: CashFlowSection   # equity + long-term debt

    # ── Subtotals ─────────────────────────────────────────
    net_operating: Decimal       # net_income + operating.subtotal
    net_change: Decimal          # net_operating + investing + financing

    # ── Reconciliation ────────────────────────────────────
    opening_cash: Decimal        # sum of is_cash accounts before date_from
    closing_cash: Decimal        # opening_cash + net_change (reconciling total)
    book_closing_cash: Decimal   # actual sum of is_cash accounts at date_to
    reconciled: bool             # |closing_cash - book_closing_cash| < 0.01

"""Report builders: trial balance, P&L, balance sheet."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.reports.repository import ReportsRepository
from app.modules.reports.schemas import (
    AgedBuckets,
    AgedInvoiceLine,
    AgedPartyLine,
    AgedReport,
    BalanceSheet,
    BSLine,
    PLLine,
    ProfitLoss,
    TrialBalance,
    TrialBalanceLine,
)

CENT = Decimal("0.01")


def _signed_balance(total_debit: Decimal, total_credit: Decimal, normal_side: str) -> Decimal:
    """Balance signed so positive = on the account's natural side."""
    if normal_side == "debit":
        return total_debit - total_credit
    return total_credit - total_debit


class ReportsService:
    def __init__(self, session: AsyncSession, tenant_id: UUID):
        self.session = session
        self.tenant_id = tenant_id
        self.repo = ReportsRepository(session, tenant_id)

    # ─── Trial Balance ────────────────────────────────────
    async def trial_balance(self, *, as_of: date, include_zero: bool = False) -> TrialBalance:
        rows = await self.repo.aggregate_by_account(date_to=as_of)

        lines: list[TrialBalanceLine] = []
        total_debit = Decimal("0")
        total_credit = Decimal("0")
        for account, td, tc in rows:
            if not include_zero and td == 0 and tc == 0:
                continue
            lines.append(
                TrialBalanceLine(
                    account_id=account.id,
                    code=account.code,
                    name=account.name,
                    type=account.type,
                    normal_side=account.normal_side,
                    total_debit=td,
                    total_credit=tc,
                    balance=_signed_balance(td, tc, account.normal_side),
                )
            )
            total_debit += td
            total_credit += tc

        return TrialBalance(
            as_of=as_of,
            lines=lines,
            total_debit=total_debit,
            total_credit=total_credit,
            balanced=total_debit == total_credit,
        )

    # ─── Profit & Loss ────────────────────────────────────
    async def profit_loss(
        self,
        *,
        date_from: date,
        date_to: date,
        cash_basis: bool = False,
    ) -> ProfitLoss:
        # Phase 1: direct cash-basis (journals that touch cash) OR accrual
        rows = await self.repo.aggregate_by_account(
            date_from=date_from,
            date_to=date_to,
            types=["income", "expense"],
            cash_basis=cash_basis,
        )

        # account_id → (account, signed_amount_so_far)
        agg: dict = {}

        for account, td, tc in rows:
            amount = _signed_balance(td, tc, account.normal_side)
            if amount == 0:
                continue
            agg[account.id] = (account, amount)

        # Phase 2 (cash-basis only): add proportional recognition for
        # payments that settle invoices in this period. Each application
        # contributes (income_or_expense_line_amount × app_amount / invoice_total)
        if cash_basis:
            payment_rows = await self.repo.payments_with_invoice_in_period(
                date_from=date_from, date_to=date_to
            )
            for direction, invoice_id, app_amount, total, _subtotal in payment_rows:
                if total == 0:
                    continue
                ratio = app_amount / total
                source = "sales_invoice" if direction == "receipt" else "purchase_invoice"
                lines = await self.repo.income_expense_lines_for_invoice_journal(
                    invoice_id=invoice_id, invoice_source=source
                )
                for account, signed in lines:
                    contribution = (signed * ratio).quantize(CENT)
                    if contribution == 0:
                        continue
                    if account.id in agg:
                        existing_acct, existing_amount = agg[account.id]
                        agg[account.id] = (existing_acct, existing_amount + contribution)
                    else:
                        agg[account.id] = (account, contribution)

        income: list[PLLine] = []
        expense: list[PLLine] = []
        total_income = Decimal("0")
        total_expense = Decimal("0")
        for account, amount in agg.values():
            if amount == 0:
                continue
            line = PLLine(
                account_id=account.id,
                code=account.code,
                name=account.name,
                amount=amount,
            )
            if account.type == "income":
                income.append(line)
                total_income += amount
            elif account.type == "expense":
                expense.append(line)
                total_expense += amount

        income.sort(key=lambda x: x.code)
        expense.sort(key=lambda x: x.code)

        return ProfitLoss(
            date_from=date_from,
            date_to=date_to,
            income=income,
            total_income=total_income,
            expense=expense,
            total_expense=total_expense,
            net_profit=total_income - total_expense,
        )

    # ─── Balance Sheet ────────────────────────────────────
    async def balance_sheet(self, *, as_of: date) -> BalanceSheet:
        # All cumulative balances up to as_of, all account types
        rows = await self.repo.aggregate_by_account(date_to=as_of)

        assets: list[BSLine] = []
        liabilities: list[BSLine] = []
        equity: list[BSLine] = []
        total_assets = Decimal("0")
        total_liabilities = Decimal("0")
        total_equity_explicit = Decimal("0")
        retained = Decimal("0")  # cumulative net profit through as_of

        for account, td, tc in rows:
            amount = _signed_balance(td, tc, account.normal_side)
            if account.type == "asset":
                if amount != 0:
                    assets.append(
                        BSLine(
                            account_id=account.id,
                            code=account.code,
                            name=account.name,
                            amount=amount,
                        )
                    )
                    total_assets += amount
            elif account.type == "liability":
                if amount != 0:
                    liabilities.append(
                        BSLine(
                            account_id=account.id,
                            code=account.code,
                            name=account.name,
                            amount=amount,
                        )
                    )
                    total_liabilities += amount
            elif account.type == "equity":
                if amount != 0:
                    equity.append(
                        BSLine(
                            account_id=account.id,
                            code=account.code,
                            name=account.name,
                            amount=amount,
                        )
                    )
                    total_equity_explicit += amount
            elif account.type == "income":
                retained += amount  # income credit balance adds to retained
            elif account.type == "expense":
                retained -= amount  # expense debit balance reduces retained

        total_equity = total_equity_explicit + retained
        imbalance = total_assets - (total_liabilities + total_equity)

        return BalanceSheet(
            as_of=as_of,
            assets=assets,
            total_assets=total_assets,
            liabilities=liabilities,
            total_liabilities=total_liabilities,
            equity=equity,
            retained_earnings=retained,
            total_equity=total_equity,
            balanced=abs(imbalance) < CENT,
            imbalance=imbalance,
        )

    # ─── Aged AR / AP ─────────────────────────────────────
    async def aged_receivables(self, *, as_of: date) -> AgedReport:
        rows = await self.repo.open_sales_invoices(as_of=as_of)
        return self._build_aged_report(
            as_of=as_of,
            rows=[
                (
                    party.id,
                    party.code,
                    party.name,
                    invoice.id,
                    invoice.invoice_no,
                    invoice.invoice_date,
                    invoice.due_date,
                    invoice.total,
                    invoice.paid_amount,
                )
                for party, invoice in rows
            ],
        )

    async def aged_payables(self, *, as_of: date) -> AgedReport:
        rows = await self.repo.open_purchase_invoices(as_of=as_of)
        return self._build_aged_report(
            as_of=as_of,
            rows=[
                (
                    party.id,
                    party.code,
                    party.name,
                    invoice.id,
                    invoice.invoice_no,
                    invoice.invoice_date,
                    invoice.due_date,
                    invoice.total,
                    invoice.paid_amount,
                )
                for party, invoice in rows
            ],
        )

    @staticmethod
    def _bucket_for(days_overdue: int) -> str:
        """Return the AgedBuckets field name for a given overdue-day count."""
        if days_overdue <= 0:
            return "current"
        if days_overdue <= 30:
            return "days_1_30"
        if days_overdue <= 60:
            return "days_31_60"
        if days_overdue <= 90:
            return "days_61_90"
        return "days_over_90"

    def _build_aged_report(
        self,
        *,
        as_of: date,
        rows: list[tuple],  # (party_id, code, name, inv_id, inv_no, inv_date, due_date, total, paid)
    ) -> AgedReport:
        # Aggregate per party
        party_buckets: dict = {}  # party_id → {'meta': (code, name), 'invoices': [], 'b': dict[str,Decimal]}
        grand_total = {
            k: Decimal("0") for k in ("current", "days_1_30", "days_31_60", "days_61_90", "days_over_90")
        }

        for party_id, code, name, inv_id, inv_no, inv_date, due_date, total, paid in rows:
            outstanding = (total - paid).quantize(CENT)
            if outstanding <= 0:
                continue

            # Days overdue: based on due_date if present, else invoice_date
            ref_date = due_date or inv_date
            days_overdue = max(0, (as_of - ref_date).days)
            bucket_name = self._bucket_for(days_overdue)

            entry = party_buckets.setdefault(
                party_id,
                {
                    "code": code,
                    "name": name,
                    "invoices": [],
                    "b": {k: Decimal("0") for k in grand_total},
                },
            )
            entry["b"][bucket_name] += outstanding
            grand_total[bucket_name] += outstanding
            entry["invoices"].append(
                AgedInvoiceLine(
                    invoice_id=inv_id,
                    invoice_no=inv_no,
                    invoice_date=inv_date,
                    due_date=due_date,
                    total=total,
                    paid_amount=paid,
                    outstanding=outstanding,
                    days_overdue=days_overdue,
                )
            )

        lines: list[AgedPartyLine] = []
        for party_id, entry in party_buckets.items():
            buckets = AgedBuckets(
                current=entry["b"]["current"],
                days_1_30=entry["b"]["days_1_30"],
                days_31_60=entry["b"]["days_31_60"],
                days_61_90=entry["b"]["days_61_90"],
                days_over_90=entry["b"]["days_over_90"],
                total=sum(entry["b"].values(), Decimal("0")),
            )
            lines.append(
                AgedPartyLine(
                    party_id=party_id,
                    code=entry["code"],
                    name=entry["name"],
                    invoice_count=len(entry["invoices"]),
                    buckets=buckets,
                    invoices=entry["invoices"],
                )
            )

        # Sort by code for stable output
        lines.sort(key=lambda li: li.code)

        totals = AgedBuckets(
            current=grand_total["current"],
            days_1_30=grand_total["days_1_30"],
            days_31_60=grand_total["days_31_60"],
            days_61_90=grand_total["days_61_90"],
            days_over_90=grand_total["days_over_90"],
            total=sum(grand_total.values(), Decimal("0")),
        )
        return AgedReport(as_of=as_of, lines=lines, totals=totals)

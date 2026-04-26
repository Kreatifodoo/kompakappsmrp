"""Report builders: trial balance, P&L, balance sheet."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.modules.reports.repository import ReportsRepository
from app.modules.reports.schemas import (
    AgedBuckets,
    AgedInvoiceLine,
    AgedPartyLine,
    AgedReport,
    BalanceSheet,
    BankRecMatch,
    BankReconciliation,
    BankReconciliationRequest,
    BookCashLine,
    BSLine,
    PLLine,
    ProfitLoss,
    Statement,
    StatementLine,
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

    # ─── Statements (customer / supplier) ─────────────────
    async def customer_statement(
        self,
        *,
        customer_id: UUID,
        date_from: date,
        date_to: date,
    ) -> Statement:
        customer = await self.repo.get_customer(customer_id)
        if not customer:
            raise NotFoundError("Customer not found")

        invoices = await self.repo.all_sales_invoices_for_customer(customer_id)
        payments = await self.repo.all_payments_for_party(party_id=customer_id, direction="receipt")
        return self._build_statement(
            party_id=customer.id,
            code=customer.code,
            name=customer.name,
            date_from=date_from,
            date_to=date_to,
            # Both lists are pre-built tuples to keep the helper symmetric
            invoice_rows=[(inv.invoice_date, inv.invoice_no, inv.description, inv.total) for inv in invoices],
            payment_rows=[
                (p.payment_date, p.payment_no, p.reference, applied_amount) for p, applied_amount in payments
            ],
            party_normal_side="debit",  # AR is debit-normal
        )

    async def supplier_statement(
        self,
        *,
        supplier_id: UUID,
        date_from: date,
        date_to: date,
    ) -> Statement:
        supplier = await self.repo.get_supplier(supplier_id)
        if not supplier:
            raise NotFoundError("Supplier not found")

        invoices = await self.repo.all_purchase_invoices_for_supplier(supplier_id)
        payments = await self.repo.all_payments_for_party(party_id=supplier_id, direction="disbursement")
        return self._build_statement(
            party_id=supplier.id,
            code=supplier.code,
            name=supplier.name,
            date_from=date_from,
            date_to=date_to,
            invoice_rows=[
                (
                    inv.invoice_date,
                    inv.supplier_invoice_no or inv.invoice_no,
                    inv.notes,
                    inv.total,
                )
                for inv in invoices
            ],
            payment_rows=[
                (p.payment_date, p.payment_no, p.reference, applied_amount) for p, applied_amount in payments
            ],
            party_normal_side="credit",  # AP is credit-normal
        )

    def _build_statement(
        self,
        *,
        party_id: UUID,
        code: str,
        name: str,
        date_from: date,
        date_to: date,
        invoice_rows: list[tuple[date, str, str | None, Decimal]],
        payment_rows: list[tuple[date, str, str | None, Decimal]],
        party_normal_side: str,
    ) -> Statement:
        """Render a statement from invoice + payment row tuples.

        Balance is signed by the party's normal side: positive = on the
        natural side. For customers (debit-normal AR), invoices increase
        the balance, payments decrease it. For suppliers (credit-normal
        AP), invoices increase, payments decrease.
        """
        # ── Opening balance: everything before date_from ──
        opening = Decimal("0")
        for inv_date, _no, _desc, total in invoice_rows:
            if inv_date < date_from:
                opening += total
        for pay_date, _no, _ref, amount in payment_rows:
            if pay_date < date_from:
                opening -= amount

        # ── In-period rows merged + sorted ────────────────
        events: list[tuple[date, str, str, str | None, Decimal, Decimal]] = []
        # tuple: (date, type, reference, description, debit_natural, credit_natural)
        # debit_natural = increase in balance; credit_natural = decrease

        for inv_date, no, desc, total in invoice_rows:
            if date_from <= inv_date <= date_to:
                events.append((inv_date, "invoice", no, desc, total, Decimal("0")))
        for pay_date, no, ref, amount in payment_rows:
            if date_from <= pay_date <= date_to:
                events.append((pay_date, "payment", no, ref, Decimal("0"), amount))

        # Sort: by date, invoices before payments on the same date
        events.sort(key=lambda e: (e[0], 0 if e[1] == "invoice" else 1, e[2]))

        # Map natural debit/credit to absolute debit/credit columns by party side.
        # For debit-normal (customer AR): increase = debit column, decrease = credit column
        # For credit-normal (supplier AP): increase = credit column, decrease = debit column
        natural_to_debit_col = party_normal_side == "debit"

        lines: list[StatementLine] = []
        running = opening
        period_debit = Decimal("0")
        period_credit = Decimal("0")
        for ev_date, ev_type, ref, desc, increase, decrease in events:
            running = running + increase - decrease
            if natural_to_debit_col:
                debit = increase
                credit = decrease
            else:
                debit = decrease
                credit = increase
            period_debit += debit
            period_credit += credit
            lines.append(
                StatementLine(
                    date=ev_date,
                    type=ev_type,
                    reference=ref,
                    description=desc,
                    debit=debit,
                    credit=credit,
                    balance=running,
                )
            )

        return Statement(
            party_id=party_id,
            code=code,
            name=name,
            date_from=date_from,
            date_to=date_to,
            opening_balance=opening,
            lines=lines,
            closing_balance=running,
            period_debit_total=period_debit,
            period_credit_total=period_credit,
        )

    # ─── Bank reconciliation ──────────────────────────────
    async def bank_reconciliation(self, payload: BankReconciliationRequest) -> BankReconciliation:
        # Validate the cash account belongs to this tenant + is_cash=true
        from app.modules.accounting.repository import AccountingRepository

        acct_repo = AccountingRepository(self.session, self.tenant_id)
        account = await acct_repo.get_account(payload.cash_account_id)
        if account is None:
            raise NotFoundError("Cash account not found")
        if not account.is_cash:
            raise ValidationError(f"Account {account.code} is not flagged is_cash=true")

        # ── Pull book lines ───────────────────────────────
        rows = await self.repo.cash_account_lines_in_period(
            cash_account_id=payload.cash_account_id,
            date_from=payload.date_from,
            date_to=payload.date_to,
        )
        book_lines: list[BookCashLine] = []
        for entry, line in rows:
            signed = (line.debit - line.credit).quantize(CENT)
            if signed == 0:
                continue
            book_lines.append(
                BookCashLine(
                    journal_entry_id=entry.id,
                    entry_no=entry.entry_no,
                    entry_date=entry.entry_date,
                    amount=signed,
                    description=entry.description,
                    line_description=line.description,
                )
            )

        # ── Match by (amount, date within tolerance) ──────
        # Index book lines by amount → list of indices, popped greedily
        from collections import defaultdict
        from datetime import timedelta

        unmatched_book: dict = defaultdict(list)
        for idx, bl in enumerate(book_lines):
            unmatched_book[bl.amount].append(idx)

        matched: list[BankRecMatch] = []
        statement_only: list = []
        used_book_indices: set[int] = set()
        tol = timedelta(days=max(0, payload.date_tolerance_days))

        for sl in payload.statement_lines:
            sl_amt = sl.amount.quantize(CENT)
            candidates = unmatched_book.get(sl_amt, [])
            picked = None
            for cand_idx in candidates:
                if cand_idx in used_book_indices:
                    continue
                bl = book_lines[cand_idx]
                if abs((bl.entry_date - sl.date).days) <= tol.days:
                    picked = cand_idx
                    break
            if picked is None:
                statement_only.append(sl)
            else:
                used_book_indices.add(picked)
                matched.append(BankRecMatch(book=book_lines[picked], statement=sl))

        book_only = [bl for i, bl in enumerate(book_lines) if i not in used_book_indices]

        # ── Totals ────────────────────────────────────────
        book_period_total = sum((bl.amount for bl in book_lines), Decimal("0"))
        statement_period_total = sum(
            (sl.amount.quantize(CENT) for sl in payload.statement_lines), Decimal("0")
        )
        book_only_total = sum((bl.amount for bl in book_only), Decimal("0"))
        statement_only_total = sum((sl.amount.quantize(CENT) for sl in statement_only), Decimal("0"))

        return BankReconciliation(
            cash_account_id=account.id,
            cash_account_code=account.code,
            cash_account_name=account.name,
            date_from=payload.date_from,
            date_to=payload.date_to,
            matched=matched,
            book_only=book_only,
            statement_only=statement_only,
            book_period_total=book_period_total,
            statement_period_total=statement_period_total,
            book_only_total=book_only_total,
            statement_only_total=statement_only_total,
            difference=book_period_total - statement_period_total,
        )

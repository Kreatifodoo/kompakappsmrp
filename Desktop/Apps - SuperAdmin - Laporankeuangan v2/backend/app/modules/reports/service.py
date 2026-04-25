"""Report builders: trial balance, P&L, balance sheet."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.reports.repository import ReportsRepository
from app.modules.reports.schemas import (
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
    async def profit_loss(self, *, date_from: date, date_to: date) -> ProfitLoss:
        rows = await self.repo.aggregate_by_account(
            date_from=date_from, date_to=date_to, types=["income", "expense"]
        )

        income: list[PLLine] = []
        expense: list[PLLine] = []
        total_income = Decimal("0")
        total_expense = Decimal("0")

        for account, td, tc in rows:
            amount = _signed_balance(td, tc, account.normal_side)
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

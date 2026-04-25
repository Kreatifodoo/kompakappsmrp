"""Report data access — aggregates over journal_lines + accounts.

All queries:
- Scope to tenant_id at every join
- Include only `posted` journal entries (drafts and voided are excluded)
- Use the read replica via `get_read_session()` when invoked through the
  API so reports don't compete with OLTP writes
"""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.accounting.models import Account, JournalEntry, JournalLine
from app.modules.purchase.models import PurchaseInvoice, Supplier
from app.modules.sales.models import Customer, SalesInvoice


class ReportsRepository:
    def __init__(self, session: AsyncSession, tenant_id: UUID):
        self.session = session
        self.tenant_id = tenant_id

    async def aggregate_by_account(
        self,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        types: list[str] | None = None,
        cash_basis: bool = False,
    ) -> list[tuple[Account, Decimal, Decimal]]:
        """Return [(account, total_debit, total_credit)] aggregated over
        posted journal entries within the optional date window.

        Includes accounts with zero activity (LEFT JOIN), so callers can
        choose whether to filter them out.

        When `cash_basis=True`, the aggregation is restricted to journals
        whose entry has at least one line on a cash account
        (`accounts.is_cash`). Used by the cash-basis P&L variant.
        """
        # Subquery: per-account sums of debit/credit from posted journals
        je_conds = [
            JournalEntry.tenant_id == self.tenant_id,
            JournalEntry.status == "posted",
        ]
        if date_from:
            je_conds.append(JournalEntry.entry_date >= date_from)
        if date_to:
            je_conds.append(JournalEntry.entry_date <= date_to)

        line_conds = [JournalLine.tenant_id == self.tenant_id, *je_conds]
        if cash_basis:
            # Limit to journals where at least one line touches a cash account
            cash_je_ids = (
                select(JournalLine.entry_id.distinct())
                .join(Account, Account.id == JournalLine.account_id)
                .where(
                    JournalLine.tenant_id == self.tenant_id,
                    Account.is_cash.is_(True),
                )
            ).scalar_subquery()
            line_conds.append(JournalLine.entry_id.in_(cash_je_ids))

        sub = (
            select(
                JournalLine.account_id.label("account_id"),
                func.coalesce(func.sum(JournalLine.debit), 0).label("total_debit"),
                func.coalesce(func.sum(JournalLine.credit), 0).label("total_credit"),
            )
            .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
            .where(*line_conds)
            .group_by(JournalLine.account_id)
            .subquery()
        )

        acct_conds = [Account.tenant_id == self.tenant_id]
        if types:
            acct_conds.append(Account.type.in_(types))

        stmt = (
            select(
                Account,
                func.coalesce(sub.c.total_debit, 0).label("total_debit"),
                func.coalesce(sub.c.total_credit, 0).label("total_credit"),
            )
            .outerjoin(sub, sub.c.account_id == Account.id)
            .where(and_(*acct_conds))
            .order_by(Account.code)
        )

        rows = (await self.session.execute(stmt)).all()
        return [(row.Account, Decimal(row.total_debit), Decimal(row.total_credit)) for row in rows]

    # ─── Aged AR ──────────────────────────────────────────
    async def open_sales_invoices(self, *, as_of: date) -> list[tuple[Customer, SalesInvoice]]:
        """Posted sales invoices with outstanding > 0 as of the given date.
        Returned ordered by customer code, then invoice date."""
        stmt = (
            select(Customer, SalesInvoice)
            .join(SalesInvoice, SalesInvoice.customer_id == Customer.id)
            .where(
                SalesInvoice.tenant_id == self.tenant_id,
                SalesInvoice.status == "posted",
                SalesInvoice.invoice_date <= as_of,
                SalesInvoice.total > SalesInvoice.paid_amount,
            )
            .order_by(Customer.code, SalesInvoice.invoice_date)
        )
        return list((await self.session.execute(stmt)).all())

    # ─── Aged AP ──────────────────────────────────────────
    async def open_purchase_invoices(self, *, as_of: date) -> list[tuple[Supplier, PurchaseInvoice]]:
        """Posted purchase invoices with outstanding > 0 as of the given date."""
        stmt = (
            select(Supplier, PurchaseInvoice)
            .join(PurchaseInvoice, PurchaseInvoice.supplier_id == Supplier.id)
            .where(
                PurchaseInvoice.tenant_id == self.tenant_id,
                PurchaseInvoice.status == "posted",
                PurchaseInvoice.invoice_date <= as_of,
                PurchaseInvoice.total > PurchaseInvoice.paid_amount,
            )
            .order_by(Supplier.code, PurchaseInvoice.invoice_date)
        )
        return list((await self.session.execute(stmt)).all())

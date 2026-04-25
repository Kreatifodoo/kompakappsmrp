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
    ) -> list[tuple[Account, Decimal, Decimal]]:
        """Return [(account, total_debit, total_credit)] aggregated over
        posted journal entries within the optional date window.

        Includes accounts with zero activity (LEFT JOIN), so callers can
        choose whether to filter them out.
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

        sub = (
            select(
                JournalLine.account_id.label("account_id"),
                func.coalesce(func.sum(JournalLine.debit), 0).label("total_debit"),
                func.coalesce(func.sum(JournalLine.credit), 0).label("total_credit"),
            )
            .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
            .where(JournalLine.tenant_id == self.tenant_id, *je_conds)
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

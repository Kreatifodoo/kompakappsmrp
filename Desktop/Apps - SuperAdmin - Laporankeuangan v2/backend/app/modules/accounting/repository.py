"""Data access for Accounting module — all queries scoped by tenant_id."""

from datetime import date
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.accounting.models import (
    Account,
    AccountMapping,
    JournalEntry,
)


class AccountingRepository:
    def __init__(self, session: AsyncSession, tenant_id: UUID):
        self.session = session
        self.tenant_id = tenant_id

    # ── Accounts ─────────────────────────────────────────
    async def get_account(self, account_id: UUID) -> Account | None:
        stmt = select(Account).where(Account.id == account_id, Account.tenant_id == self.tenant_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_account_by_code(self, code: str) -> Account | None:
        stmt = select(Account).where(Account.code == code, Account.tenant_id == self.tenant_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_accounts_by_ids(self, ids: list[UUID]) -> list[Account]:
        if not ids:
            return []
        stmt = select(Account).where(Account.id.in_(ids), Account.tenant_id == self.tenant_id)
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_accounts(
        self,
        *,
        type_: str | None = None,
        active_only: bool = True,
    ) -> list[Account]:
        conds = [Account.tenant_id == self.tenant_id]
        if type_:
            conds.append(Account.type == type_)
        if active_only:
            conds.append(Account.is_active.is_(True))
        stmt = select(Account).where(and_(*conds)).order_by(Account.code)
        return list((await self.session.execute(stmt)).scalars().all())

    async def add_account(self, account: Account) -> Account:
        self.session.add(account)
        await self.session.flush()
        return account

    # ── Journal Entries ──────────────────────────────────
    async def get_entry(self, entry_id: UUID) -> JournalEntry | None:
        stmt = (
            select(JournalEntry)
            .options(selectinload(JournalEntry.lines))
            .where(
                JournalEntry.id == entry_id,
                JournalEntry.tenant_id == self.tenant_id,
            )
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_entries(
        self,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[JournalEntry]:
        conds = [JournalEntry.tenant_id == self.tenant_id]
        if date_from:
            conds.append(JournalEntry.entry_date >= date_from)
        if date_to:
            conds.append(JournalEntry.entry_date <= date_to)
        if status:
            conds.append(JournalEntry.status == status)
        stmt = (
            select(JournalEntry)
            .options(selectinload(JournalEntry.lines))
            .where(and_(*conds))
            .order_by(JournalEntry.entry_date.desc(), JournalEntry.entry_no.desc())
            .limit(limit)
            .offset(offset)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def add_entry(self, entry: JournalEntry) -> JournalEntry:
        self.session.add(entry)
        await self.session.flush()
        return entry

    # ── Account mappings ─────────────────────────────────
    async def get_mapping(self, key: str) -> AccountMapping | None:
        stmt = select(AccountMapping).where(
            AccountMapping.tenant_id == self.tenant_id,
            AccountMapping.key == key,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def set_mapping(self, key: str, account_id: UUID) -> AccountMapping:
        existing = await self.get_mapping(key)
        if existing:
            existing.account_id = account_id
            await self.session.flush()
            return existing
        m = AccountMapping(tenant_id=self.tenant_id, key=key, account_id=account_id)
        self.session.add(m)
        await self.session.flush()
        return m

    async def list_mappings(self) -> list[AccountMapping]:
        stmt = select(AccountMapping).where(AccountMapping.tenant_id == self.tenant_id)
        return list((await self.session.execute(stmt)).scalars().all())

    async def next_entry_no(self, year: int) -> str:
        """Generate next sequential journal number per tenant per year (JV-YYYY-#####)."""
        prefix = f"JV-{year}-"
        stmt = select(func.count(JournalEntry.id)).where(
            JournalEntry.tenant_id == self.tenant_id,
            JournalEntry.entry_no.like(f"{prefix}%"),
        )
        count = (await self.session.execute(stmt)).scalar_one() or 0
        return f"{prefix}{count + 1:05d}"

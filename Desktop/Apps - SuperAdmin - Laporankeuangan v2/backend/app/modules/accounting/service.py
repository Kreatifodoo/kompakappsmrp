"""Business logic for Accounting: COA management, journal posting."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.modules.accounting.models import Account, JournalEntry, JournalLine
from app.modules.accounting.repository import AccountingRepository
from app.modules.accounting.schemas import (
    AccountCreate,
    AccountUpdate,
    JournalEntryCreate,
)
from app.modules.accounting.starter_coa import STARTER_COA


class AccountingService:
    def __init__(self, session: AsyncSession, tenant_id: UUID, user_id: UUID):
        self.session = session
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.repo = AccountingRepository(session, tenant_id)

    # ─── Chart of Accounts ──────────────────────────────
    async def create_account(self, payload: AccountCreate) -> Account:
        if await self.repo.get_account_by_code(payload.code):
            raise ConflictError(f"Account code '{payload.code}' already exists")

        if payload.parent_id:
            parent = await self.repo.get_account(payload.parent_id)
            if not parent:
                raise NotFoundError("Parent account not found")
            if parent.type != payload.type:
                raise ValidationError("Child account type must match parent type")

        account = Account(
            tenant_id=self.tenant_id,
            code=payload.code,
            name=payload.name,
            type=payload.type,
            normal_side=payload.normal_side,
            parent_id=payload.parent_id,
            description=payload.description,
        )
        return await self.repo.add_account(account)

    # System accounts (from the starter COA) are protected against
    # structural edits. Operational toggles (active flag, cash flag) are
    # always permitted so admins can deactivate unused starter accounts
    # or flag additional cash/bank accounts for cash-basis reports.
    _SYSTEM_EDITABLE_FIELDS = frozenset({"is_active", "is_cash"})

    async def update_account(self, account_id: UUID, payload: AccountUpdate) -> Account:
        account = await self.repo.get_account(account_id)
        if not account:
            raise NotFoundError("Account not found")

        updates = payload.model_dump(exclude_unset=True)
        if account.is_system:
            disallowed = set(updates) - self._SYSTEM_EDITABLE_FIELDS
            if disallowed:
                raise ValidationError(
                    f"System accounts only allow {sorted(self._SYSTEM_EDITABLE_FIELDS)}; "
                    f"cannot modify {sorted(disallowed)}"
                )

        for field, value in updates.items():
            setattr(account, field, value)
        await self.session.flush()
        return account

    async def seed_starter_coa(self, *, overwrite_mappings: bool = False) -> dict:
        """Provision a standard COA + account mappings for this tenant.

        Idempotent: skips accounts whose code already exists. Mappings are
        created where missing; pass overwrite_mappings=True to re-bind
        existing mappings to the starter accounts.

        Returns a summary {accounts_created, accounts_skipped, mappings_set}.
        """
        # Pass 1 — create all top-level (no parent) accounts first
        # Then iterate until all are created (handles arbitrary nesting via
        # repeated passes — STARTER_COA is small)
        existing_by_code: dict[str, Account] = {}
        for a in await self.repo.list_accounts(active_only=False):
            existing_by_code[a.code] = a

        created = 0
        skipped = 0
        # Loop — each pass creates accounts whose parent is now known.
        remaining = list(STARTER_COA)
        max_passes = 10
        while remaining and max_passes > 0:
            max_passes -= 1
            still: list = []
            for sa in remaining:
                if sa.code in existing_by_code:
                    skipped += 1
                    continue
                parent_id = None
                if sa.parent_code:
                    parent = existing_by_code.get(sa.parent_code)
                    if not parent:
                        # Parent not yet created — defer
                        still.append(sa)
                        continue
                    parent_id = parent.id

                acct = Account(
                    tenant_id=self.tenant_id,
                    code=sa.code,
                    name=sa.name,
                    type=sa.type,
                    normal_side=sa.normal_side,
                    parent_id=parent_id,
                    is_system=True,
                    is_cash=sa.is_cash,
                )
                self.session.add(acct)
                await self.session.flush()
                existing_by_code[sa.code] = acct
                created += 1
            remaining = still

        if remaining:
            raise ValidationError(f"Starter COA could not resolve parents for: {[a.code for a in remaining]}")

        # Pass 2 — bind well-known mappings
        mappings_set = 0
        for sa in STARTER_COA:
            if not sa.mapping_key:
                continue
            account = existing_by_code[sa.code]
            existing_map = await self.repo.get_mapping(sa.mapping_key)
            if existing_map and not overwrite_mappings:
                continue
            await self.repo.set_mapping(sa.mapping_key, account.id)
            mappings_set += 1

        return {
            "accounts_created": created,
            "accounts_skipped": skipped,
            "mappings_set": mappings_set,
        }

    # ─── Journal Entries ────────────────────────────────
    async def create_journal(self, payload: JournalEntryCreate, *, post_now: bool = False) -> JournalEntry:
        # Validate all account_ids belong to this tenant
        account_ids = list({ln.account_id for ln in payload.lines})
        accounts = await self.repo.get_accounts_by_ids(account_ids)
        if len(accounts) != len(account_ids):
            raise ValidationError("One or more accounts do not belong to this tenant")
        inactive = [a.code for a in accounts if not a.is_active]
        if inactive:
            raise ValidationError(f"Inactive accounts cannot be used: {inactive}")

        entry_no = payload.entry_no or await self.repo.next_entry_no(payload.entry_date.year)

        entry = JournalEntry(
            tenant_id=self.tenant_id,
            entry_no=entry_no,
            entry_date=payload.entry_date,
            description=payload.description,
            reference=payload.reference,
            status="posted" if post_now else "draft",
            source="manual",
            created_by=self.user_id,
            posted_by=self.user_id if post_now else None,
            posted_at=datetime.now(UTC) if post_now else None,
        )
        for idx, line in enumerate(payload.lines, start=1):
            entry.lines.append(
                JournalLine(
                    tenant_id=self.tenant_id,
                    entry_date=payload.entry_date,  # required for partition routing
                    line_no=idx,
                    account_id=line.account_id,
                    description=line.description,
                    debit=line.debit,
                    credit=line.credit,
                )
            )
        return await self.repo.add_entry(entry)

    async def post_journal(self, entry_id: UUID) -> JournalEntry:
        entry = await self.repo.get_entry(entry_id)
        if not entry:
            raise NotFoundError("Journal entry not found")
        if entry.status == "posted":
            raise ConflictError("Journal already posted")
        if entry.status == "void":
            raise ValidationError("Voided entry cannot be posted")

        # Re-verify balance defensively
        total_debit = sum((ln.debit for ln in entry.lines), Decimal("0"))
        total_credit = sum((ln.credit for ln in entry.lines), Decimal("0"))
        if total_debit != total_credit:
            raise ValidationError(f"Journal not balanced: debit={total_debit} credit={total_credit}")

        entry.status = "posted"
        entry.posted_by = self.user_id
        entry.posted_at = datetime.now(UTC)
        await self.session.flush()
        return entry

    # ─── System-generated journals (called by Sales/Purchase) ────
    async def post_system_journal(
        self,
        *,
        entry_date,
        description: str,
        lines: list[tuple[UUID, Decimal, Decimal]],  # (account_id, debit, credit)
        source: str,
        source_id: UUID,
        reference: str | None = None,
    ) -> JournalEntry:
        """Create + post a journal entry from another module (sales/purchase/etc).

        Validates balance and that all accounts belong to the tenant.
        Runs in the same DB transaction as the caller.
        """
        if not lines or len(lines) < 2:
            raise ValidationError("System journal requires at least 2 lines")

        total_debit = sum((d for _, d, _ in lines), Decimal("0"))
        total_credit = sum((c for _, _, c in lines), Decimal("0"))
        if total_debit != total_credit:
            raise ValidationError(f"System journal not balanced: debit={total_debit} credit={total_credit}")

        account_ids = list({aid for aid, _, _ in lines})
        accounts = await self.repo.get_accounts_by_ids(account_ids)
        if len(accounts) != len(account_ids):
            raise ValidationError("System journal references unknown accounts")

        entry_no = await self.repo.next_entry_no(entry_date.year)
        entry = JournalEntry(
            tenant_id=self.tenant_id,
            entry_no=entry_no,
            entry_date=entry_date,
            description=description,
            reference=reference,
            status="posted",
            source=source,
            source_id=source_id,
            created_by=self.user_id,
            posted_by=self.user_id,
            posted_at=datetime.now(UTC),
        )
        for idx, (account_id, debit, credit) in enumerate(lines, start=1):
            entry.lines.append(
                JournalLine(
                    tenant_id=self.tenant_id,
                    entry_date=entry_date,  # required for partition routing
                    line_no=idx,
                    account_id=account_id,
                    debit=debit,
                    credit=credit,
                )
            )
        return await self.repo.add_entry(entry)

    async def void_system_journal(self, source: str, source_id: UUID, reason: str) -> JournalEntry | None:
        """Void the journal linked to a sales/purchase document. Returns None if not found."""
        from sqlalchemy import select

        stmt = select(JournalEntry).where(
            JournalEntry.tenant_id == self.tenant_id,
            JournalEntry.source == source,
            JournalEntry.source_id == source_id,
            JournalEntry.status == "posted",
        )
        entry = (await self.session.execute(stmt)).scalar_one_or_none()
        if entry is None:
            return None
        entry.status = "void"
        entry.voided_by = self.user_id
        entry.voided_at = datetime.now(UTC)
        entry.void_reason = reason
        await self.session.flush()
        return entry

    async def void_journal(self, entry_id: UUID, reason: str) -> JournalEntry:
        entry = await self.repo.get_entry(entry_id)
        if not entry:
            raise NotFoundError("Journal entry not found")
        if entry.status == "void":
            raise ConflictError("Journal already voided")

        entry.status = "void"
        entry.voided_by = self.user_id
        entry.voided_at = datetime.now(UTC)
        entry.void_reason = reason
        await self.session.flush()
        return entry

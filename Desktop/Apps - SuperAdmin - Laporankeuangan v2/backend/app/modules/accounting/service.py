"""Business logic for Accounting: COA management, journal posting."""
from datetime import datetime, timezone
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
                raise ValidationError(
                    "Child account type must match parent type"
                )

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

    async def update_account(self, account_id: UUID, payload: AccountUpdate) -> Account:
        account = await self.repo.get_account(account_id)
        if not account:
            raise NotFoundError("Account not found")
        if account.is_system:
            raise ValidationError("System accounts cannot be modified")

        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(account, field, value)
        await self.session.flush()
        return account

    # ─── Journal Entries ────────────────────────────────
    async def create_journal(
        self, payload: JournalEntryCreate, *, post_now: bool = False
    ) -> JournalEntry:
        # Validate all account_ids belong to this tenant
        account_ids = list({l.account_id for l in payload.lines})
        accounts = await self.repo.get_accounts_by_ids(account_ids)
        if len(accounts) != len(account_ids):
            raise ValidationError("One or more accounts do not belong to this tenant")
        inactive = [a.code for a in accounts if not a.is_active]
        if inactive:
            raise ValidationError(f"Inactive accounts cannot be used: {inactive}")

        entry_no = payload.entry_no or await self.repo.next_entry_no(
            payload.entry_date.year
        )

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
            posted_at=datetime.now(timezone.utc) if post_now else None,
        )
        for idx, line in enumerate(payload.lines, start=1):
            entry.lines.append(
                JournalLine(
                    tenant_id=self.tenant_id,
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
        total_debit = sum((l.debit for l in entry.lines), Decimal("0"))
        total_credit = sum((l.credit for l in entry.lines), Decimal("0"))
        if total_debit != total_credit:
            raise ValidationError(
                f"Journal not balanced: debit={total_debit} credit={total_credit}"
            )

        entry.status = "posted"
        entry.posted_by = self.user_id
        entry.posted_at = datetime.now(timezone.utc)
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
        entry.voided_at = datetime.now(timezone.utc)
        entry.void_reason = reason
        await self.session.flush()
        return entry

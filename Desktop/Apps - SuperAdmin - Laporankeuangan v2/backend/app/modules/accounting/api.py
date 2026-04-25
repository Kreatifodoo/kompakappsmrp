"""HTTP routes for Accounting: /accounts (COA), /journals."""
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_write_session
from app.core.exceptions import NotFoundError
from app.deps import CurrentUser, get_current_user, require_permission
from app.modules.accounting.repository import AccountingRepository
from app.modules.accounting.schemas import (
    WELL_KNOWN_MAPPING_KEYS,
    AccountCreate,
    AccountMappingOut,
    AccountMappingSet,
    AccountOut,
    AccountUpdate,
    JournalEntryCreate,
    JournalEntryOut,
    JournalVoidRequest,
)
from app.modules.accounting.service import AccountingService

router = APIRouter(tags=["accounting"])


# ─── Chart of Accounts ──────────────────────────────────
@router.get("/accounts", response_model=list[AccountOut])
async def list_accounts(
    type: str | None = Query(default=None),
    active_only: bool = Query(default=True),
    current: CurrentUser = Depends(require_permission("coa.read")),
    session: AsyncSession = Depends(get_write_session),
) -> list[AccountOut]:
    repo = AccountingRepository(session, current.tenant_id)
    accounts = await repo.list_accounts(type_=type, active_only=active_only)
    return [AccountOut.model_validate(a) for a in accounts]


@router.post("/accounts", response_model=AccountOut, status_code=201)
async def create_account(
    payload: AccountCreate,
    current: CurrentUser = Depends(require_permission("coa.write")),
    session: AsyncSession = Depends(get_write_session),
) -> AccountOut:
    svc = AccountingService(session, current.tenant_id, current.user_id)
    account = await svc.create_account(payload)
    return AccountOut.model_validate(account)


@router.patch("/accounts/{account_id}", response_model=AccountOut)
async def update_account(
    account_id: UUID,
    payload: AccountUpdate,
    current: CurrentUser = Depends(require_permission("coa.write")),
    session: AsyncSession = Depends(get_write_session),
) -> AccountOut:
    svc = AccountingService(session, current.tenant_id, current.user_id)
    account = await svc.update_account(account_id, payload)
    return AccountOut.model_validate(account)


# ─── Journal Entries ────────────────────────────────────
@router.get("/journals", response_model=list[JournalEntryOut])
async def list_journals(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
    current: CurrentUser = Depends(require_permission("journal.read")),
    session: AsyncSession = Depends(get_write_session),
) -> list[JournalEntryOut]:
    repo = AccountingRepository(session, current.tenant_id)
    entries = await repo.list_entries(
        date_from=date_from, date_to=date_to, status=status,
        limit=limit, offset=offset,
    )
    return [JournalEntryOut.model_validate(e) for e in entries]


@router.get("/journals/{entry_id}", response_model=JournalEntryOut)
async def get_journal(
    entry_id: UUID,
    current: CurrentUser = Depends(require_permission("journal.read")),
    session: AsyncSession = Depends(get_write_session),
) -> JournalEntryOut:
    repo = AccountingRepository(session, current.tenant_id)
    entry = await repo.get_entry(entry_id)
    if not entry:
        raise NotFoundError("Journal entry not found")
    return JournalEntryOut.model_validate(entry)


@router.post("/journals", response_model=JournalEntryOut, status_code=201)
async def create_journal(
    payload: JournalEntryCreate,
    post_now: bool = Query(default=False),
    current: CurrentUser = Depends(require_permission("journal.write")),
    session: AsyncSession = Depends(get_write_session),
) -> JournalEntryOut:
    if post_now and not current.has_permission("journal.post"):
        from app.core.exceptions import AuthorizationError
        raise AuthorizationError("Missing permission: journal.post")

    svc = AccountingService(session, current.tenant_id, current.user_id)
    entry = await svc.create_journal(payload, post_now=post_now)
    return JournalEntryOut.model_validate(entry)


@router.post("/journals/{entry_id}/post", response_model=JournalEntryOut)
async def post_journal(
    entry_id: UUID,
    current: CurrentUser = Depends(require_permission("journal.post")),
    session: AsyncSession = Depends(get_write_session),
) -> JournalEntryOut:
    svc = AccountingService(session, current.tenant_id, current.user_id)
    entry = await svc.post_journal(entry_id)
    return JournalEntryOut.model_validate(entry)


# ─── Account Mappings ───────────────────────────────────
@router.get("/account-mappings", response_model=list[AccountMappingOut])
async def list_mappings(
    current: CurrentUser = Depends(require_permission("coa.read")),
    session: AsyncSession = Depends(get_write_session),
) -> list[AccountMappingOut]:
    repo = AccountingRepository(session, current.tenant_id)
    return [AccountMappingOut.model_validate(m) for m in await repo.list_mappings()]


@router.put("/account-mappings", response_model=AccountMappingOut)
async def set_mapping(
    payload: AccountMappingSet,
    current: CurrentUser = Depends(require_permission("coa.write")),
    session: AsyncSession = Depends(get_write_session),
) -> AccountMappingOut:
    if payload.key not in WELL_KNOWN_MAPPING_KEYS:
        from app.core.exceptions import ValidationError as VE
        raise VE(
            f"Unknown mapping key '{payload.key}'. Allowed: "
            f"{sorted(WELL_KNOWN_MAPPING_KEYS)}"
        )
    repo = AccountingRepository(session, current.tenant_id)
    # Verify account belongs to tenant
    account = await repo.get_account(payload.account_id)
    if not account:
        raise NotFoundError("Account not found")
    mapping = await repo.set_mapping(payload.key, payload.account_id)
    return AccountMappingOut.model_validate(mapping)


@router.post("/journals/{entry_id}/void", response_model=JournalEntryOut)
async def void_journal(
    entry_id: UUID,
    payload: JournalVoidRequest,
    current: CurrentUser = Depends(require_permission("journal.post")),
    session: AsyncSession = Depends(get_write_session),
) -> JournalEntryOut:
    svc = AccountingService(session, current.tenant_id, current.user_id)
    entry = await svc.void_journal(entry_id, payload.reason)
    return JournalEntryOut.model_validate(entry)

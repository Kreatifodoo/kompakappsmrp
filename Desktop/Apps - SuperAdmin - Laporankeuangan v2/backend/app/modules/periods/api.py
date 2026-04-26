"""HTTP routes for period close / reopen / status."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_write_session
from app.deps import CurrentUser, require_permission
from app.modules.periods.schemas import (
    ClosePeriodRequest,
    ClosureEventOut,
    PeriodStatus,
    ReopenPeriodRequest,
)
from app.modules.periods.service import PeriodService, get_closed_through, require_admin

router = APIRouter(prefix="/periods", tags=["periods"])


@router.get("/status", response_model=PeriodStatus)
async def status(
    current: CurrentUser = Depends(require_permission("period.close")),
    session: AsyncSession = Depends(get_write_session),
) -> PeriodStatus:
    closed = await get_closed_through(session, current.tenant_id)
    return PeriodStatus(closed_through=closed, is_locked=closed is not None)


@router.post("/close", response_model=PeriodStatus)
async def close_period(
    payload: ClosePeriodRequest,
    current: CurrentUser = Depends(require_permission("period.close")),
    session: AsyncSession = Depends(get_write_session),
) -> PeriodStatus:
    require_admin(current)
    svc = PeriodService(session, current.tenant_id, current.user_id)
    tenant = await svc.close_period(payload)
    return PeriodStatus(closed_through=tenant.closed_through, is_locked=tenant.closed_through is not None)


@router.post("/reopen", response_model=PeriodStatus)
async def reopen_period(
    payload: ReopenPeriodRequest,
    current: CurrentUser = Depends(require_permission("period.close")),
    session: AsyncSession = Depends(get_write_session),
) -> PeriodStatus:
    require_admin(current)
    svc = PeriodService(session, current.tenant_id, current.user_id)
    tenant = await svc.reopen_period(payload)
    return PeriodStatus(closed_through=tenant.closed_through, is_locked=tenant.closed_through is not None)


@router.get("/events", response_model=list[ClosureEventOut])
async def list_events(
    current: CurrentUser = Depends(require_permission("period.close")),
    session: AsyncSession = Depends(get_write_session),
) -> list[ClosureEventOut]:
    svc = PeriodService(session, current.tenant_id, current.user_id)
    events = await svc.list_events()
    return [ClosureEventOut.model_validate(e) for e in events]

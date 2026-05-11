"""HTTP routes for manufacturing module (Sprint M1: BOM).

Permission scopes: mfg.read / mfg.write. Sprint M2 will add mfg.post +
mfg.cancel for Manufacturing Order lifecycle.
"""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_write_session
from app.core.exceptions import NotFoundError
from app.deps import CurrentUser, require_permission
from app.modules.manufacturing.repository import ManufacturingRepository
from app.modules.manufacturing.schemas import (
    BOMCreate,
    BOMOut,
    BOMUpdate,
    MOCancelRequest,
    MOCompleteRequest,
    MOCreate,
    MOIssueRequest,
    MOOut,
)
from app.modules.manufacturing.service import (
    BOMService,
    ManufacturingOrderService,
)

router = APIRouter(tags=["manufacturing"])


# ─── BOM ─────────────────────────────────────────────────
@router.get("/boms", response_model=list[BOMOut])
async def list_boms(
    item_id: UUID | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
    current: CurrentUser = Depends(require_permission("mfg.read")),
    session: AsyncSession = Depends(get_write_session),
) -> list[BOMOut]:
    repo = ManufacturingRepository(session, current.tenant_id)
    boms = await repo.list_boms(
        item_id=item_id, status=status, limit=limit, offset=offset
    )
    return [BOMOut.model_validate(b) for b in boms]


@router.get("/boms/{bom_id}", response_model=BOMOut)
async def get_bom(
    bom_id: UUID,
    current: CurrentUser = Depends(require_permission("mfg.read")),
    session: AsyncSession = Depends(get_write_session),
) -> BOMOut:
    repo = ManufacturingRepository(session, current.tenant_id)
    bom = await repo.get_bom(bom_id)
    if not bom:
        raise NotFoundError("BOM not found")
    return BOMOut.model_validate(bom)


@router.post("/boms", response_model=BOMOut, status_code=201)
async def create_bom(
    payload: BOMCreate,
    activate: bool = Query(default=False, description="Auto-activate after create"),
    current: CurrentUser = Depends(require_permission("mfg.write")),
    session: AsyncSession = Depends(get_write_session),
) -> BOMOut:
    svc = BOMService(session, current.tenant_id, current.user_id)
    bom = await svc.create_bom(payload)
    if activate:
        await svc.activate_bom(bom.id)
    refreshed = await svc.repo.get_bom(bom.id)
    return BOMOut.model_validate(refreshed or bom)


@router.patch("/boms/{bom_id}", response_model=BOMOut)
async def update_bom(
    bom_id: UUID,
    payload: BOMUpdate,
    current: CurrentUser = Depends(require_permission("mfg.write")),
    session: AsyncSession = Depends(get_write_session),
) -> BOMOut:
    svc = BOMService(session, current.tenant_id, current.user_id)
    bom = await svc.update_bom(bom_id, payload)
    refreshed = await svc.repo.get_bom(bom.id)
    return BOMOut.model_validate(refreshed or bom)


@router.post("/boms/{bom_id}/activate", response_model=BOMOut)
async def activate_bom(
    bom_id: UUID,
    current: CurrentUser = Depends(require_permission("mfg.write")),
    session: AsyncSession = Depends(get_write_session),
) -> BOMOut:
    svc = BOMService(session, current.tenant_id, current.user_id)
    bom = await svc.activate_bom(bom_id)
    refreshed = await svc.repo.get_bom(bom.id)
    return BOMOut.model_validate(refreshed or bom)


@router.post("/boms/{bom_id}/obsolete", response_model=BOMOut)
async def obsolete_bom(
    bom_id: UUID,
    current: CurrentUser = Depends(require_permission("mfg.write")),
    session: AsyncSession = Depends(get_write_session),
) -> BOMOut:
    svc = BOMService(session, current.tenant_id, current.user_id)
    bom = await svc.obsolete_bom(bom_id)
    refreshed = await svc.repo.get_bom(bom.id)
    return BOMOut.model_validate(refreshed or bom)


@router.delete("/boms/{bom_id}", status_code=204)
async def delete_bom(
    bom_id: UUID,
    current: CurrentUser = Depends(require_permission("mfg.write")),
    session: AsyncSession = Depends(get_write_session),
) -> None:
    svc = BOMService(session, current.tenant_id, current.user_id)
    await svc.delete_bom(bom_id)
    return None


# ─── Manufacturing Orders (Sprint M2) ────────────────────
@router.get("/manufacturing-orders", response_model=list[MOOut])
async def list_mfg_orders(
    status: str | None = Query(default=None),
    item_id: UUID | None = Query(default=None),
    bom_id: UUID | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
    current: CurrentUser = Depends(require_permission("mfg.read")),
    session: AsyncSession = Depends(get_write_session),
) -> list[MOOut]:
    repo = ManufacturingRepository(session, current.tenant_id)
    mos = await repo.list_mos(
        status=status, item_id=item_id, bom_id=bom_id,
        date_from=date_from, date_to=date_to, limit=limit, offset=offset,
    )
    return [MOOut.model_validate(m) for m in mos]


@router.get("/manufacturing-orders/{mo_id}", response_model=MOOut)
async def get_mfg_order(
    mo_id: UUID,
    current: CurrentUser = Depends(require_permission("mfg.read")),
    session: AsyncSession = Depends(get_write_session),
) -> MOOut:
    repo = ManufacturingRepository(session, current.tenant_id)
    mo = await repo.get_mo(mo_id)
    if not mo:
        raise NotFoundError("Manufacturing order not found")
    return MOOut.model_validate(mo)


@router.post("/manufacturing-orders", response_model=MOOut, status_code=201)
async def create_mfg_order(
    payload: MOCreate,
    confirm: bool = Query(default=False, description="Auto-confirm after create"),
    current: CurrentUser = Depends(require_permission("mfg.write")),
    session: AsyncSession = Depends(get_write_session),
) -> MOOut:
    svc = ManufacturingOrderService(session, current.tenant_id, current.user_id)
    mo = await svc.create_mo(payload)
    if confirm:
        await svc.confirm_mo(mo.id)
    refreshed = await svc.repo.get_mo(mo.id)
    return MOOut.model_validate(refreshed or mo)


@router.post("/manufacturing-orders/{mo_id}/confirm", response_model=MOOut)
async def confirm_mfg_order(
    mo_id: UUID,
    current: CurrentUser = Depends(require_permission("mfg.post")),
    session: AsyncSession = Depends(get_write_session),
) -> MOOut:
    svc = ManufacturingOrderService(session, current.tenant_id, current.user_id)
    mo = await svc.confirm_mo(mo_id)
    refreshed = await svc.repo.get_mo(mo.id)
    return MOOut.model_validate(refreshed or mo)


@router.post("/manufacturing-orders/{mo_id}/start", response_model=MOOut)
async def start_mfg_order(
    mo_id: UUID,
    current: CurrentUser = Depends(require_permission("mfg.post")),
    session: AsyncSession = Depends(get_write_session),
) -> MOOut:
    svc = ManufacturingOrderService(session, current.tenant_id, current.user_id)
    mo = await svc.start_mo(mo_id)
    refreshed = await svc.repo.get_mo(mo.id)
    return MOOut.model_validate(refreshed or mo)


@router.post("/manufacturing-orders/{mo_id}/issue", response_model=MOOut)
async def issue_mfg_order_materials(
    mo_id: UUID,
    payload: MOIssueRequest,
    current: CurrentUser = Depends(require_permission("mfg.post")),
    session: AsyncSession = Depends(get_write_session),
) -> MOOut:
    svc = ManufacturingOrderService(session, current.tenant_id, current.user_id)
    mo = await svc.issue_materials(mo_id, payload)
    refreshed = await svc.repo.get_mo(mo.id)
    return MOOut.model_validate(refreshed or mo)


@router.post("/manufacturing-orders/{mo_id}/complete", response_model=MOOut)
async def complete_mfg_order(
    mo_id: UUID,
    payload: MOCompleteRequest,
    current: CurrentUser = Depends(require_permission("mfg.post")),
    session: AsyncSession = Depends(get_write_session),
) -> MOOut:
    svc = ManufacturingOrderService(session, current.tenant_id, current.user_id)
    mo = await svc.complete_mo(mo_id, payload.qty_produced, payload.complete_date)
    refreshed = await svc.repo.get_mo(mo.id)
    return MOOut.model_validate(refreshed or mo)


@router.post("/manufacturing-orders/{mo_id}/cancel", response_model=MOOut)
async def cancel_mfg_order(
    mo_id: UUID,
    payload: MOCancelRequest,
    current: CurrentUser = Depends(require_permission("mfg.cancel")),
    session: AsyncSession = Depends(get_write_session),
) -> MOOut:
    svc = ManufacturingOrderService(session, current.tenant_id, current.user_id)
    mo = await svc.cancel_mo(mo_id, payload.reason)
    refreshed = await svc.repo.get_mo(mo.id)
    return MOOut.model_validate(refreshed or mo)

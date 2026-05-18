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
    MOOperationsUpdateRequest,
    MOOut,
    WorkCenterIn,
    WorkCenterOut,
    WorkCenterUpdate,
)
from app.modules.manufacturing.service import (
    BOMService,
    ManufacturingOrderService,
    WorkCenterService,
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


# ─── Work Centers (Sprint M5) ────────────────────────────
@router.get("/work-centers", response_model=list[WorkCenterOut])
async def list_work_centers(
    is_active: bool | None = Query(default=None),
    current: CurrentUser = Depends(require_permission("mfg.read")),
    session: AsyncSession = Depends(get_write_session),
) -> list[WorkCenterOut]:
    repo = ManufacturingRepository(session, current.tenant_id)
    rows = await repo.list_work_centers(is_active=is_active)
    return [WorkCenterOut.model_validate(w) for w in rows]


@router.get("/work-centers/{wc_id}", response_model=WorkCenterOut)
async def get_work_center(
    wc_id: UUID,
    current: CurrentUser = Depends(require_permission("mfg.read")),
    session: AsyncSession = Depends(get_write_session),
) -> WorkCenterOut:
    repo = ManufacturingRepository(session, current.tenant_id)
    wc = await repo.get_work_center(wc_id)
    if not wc:
        raise NotFoundError("Work center not found")
    return WorkCenterOut.model_validate(wc)


@router.post("/work-centers", response_model=WorkCenterOut, status_code=201)
async def create_work_center(
    payload: WorkCenterIn,
    current: CurrentUser = Depends(require_permission("mfg.write")),
    session: AsyncSession = Depends(get_write_session),
) -> WorkCenterOut:
    svc = WorkCenterService(session, current.tenant_id, current.user_id)
    wc = await svc.create(payload)
    return WorkCenterOut.model_validate(wc)


@router.patch("/work-centers/{wc_id}", response_model=WorkCenterOut)
async def update_work_center(
    wc_id: UUID,
    payload: WorkCenterUpdate,
    current: CurrentUser = Depends(require_permission("mfg.write")),
    session: AsyncSession = Depends(get_write_session),
) -> WorkCenterOut:
    svc = WorkCenterService(session, current.tenant_id, current.user_id)
    wc = await svc.update(wc_id, payload)
    return WorkCenterOut.model_validate(wc)


# ─── MO Operations update (Sprint M5) ────────────────────
@router.post("/manufacturing-orders/{mo_id}/operations/update", response_model=MOOut)
async def update_mo_operations(
    mo_id: UUID,
    payload: MOOperationsUpdateRequest,
    current: CurrentUser = Depends(require_permission("mfg.post")),
    session: AsyncSession = Depends(get_write_session),
) -> MOOut:
    svc = ManufacturingOrderService(session, current.tenant_id, current.user_id)
    mo = await svc.update_mo_operations(mo_id, payload)
    refreshed = await svc.repo.get_mo(mo.id)
    return MOOut.model_validate(refreshed or mo)


# ─── Scrap (Sprint M6) ───────────────────────────────────
from datetime import date as _date  # noqa: E402  (already imported, alias to avoid shadow)
from app.modules.manufacturing.schemas import (  # noqa: E402
    MfgScrapCreate,
    MfgScrapOut,
    MfgScrapVoidRequest,
)
from app.modules.manufacturing.service import ScrapService  # noqa: E402


@router.get("/mfg-scraps", response_model=list[MfgScrapOut])
async def list_scraps(
    status: str | None = Query(default=None),
    mo_id: UUID | None = Query(default=None),
    date_from: _date | None = Query(default=None),
    date_to: _date | None = Query(default=None),
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
    current: CurrentUser = Depends(require_permission("mfg.read")),
    session: AsyncSession = Depends(get_write_session),
) -> list[MfgScrapOut]:
    repo = ManufacturingRepository(session, current.tenant_id)
    rows = await repo.list_scraps(
        status=status, mo_id=mo_id,
        date_from=date_from, date_to=date_to,
        limit=limit, offset=offset,
    )
    return [MfgScrapOut.model_validate(r) for r in rows]


@router.get("/mfg-scraps/{scrap_id}", response_model=MfgScrapOut)
async def get_scrap(
    scrap_id: UUID,
    current: CurrentUser = Depends(require_permission("mfg.read")),
    session: AsyncSession = Depends(get_write_session),
) -> MfgScrapOut:
    repo = ManufacturingRepository(session, current.tenant_id)
    scrap = await repo.get_scrap(scrap_id)
    if not scrap:
        raise NotFoundError("Scrap not found")
    return MfgScrapOut.model_validate(scrap)


@router.post("/mfg-scraps", response_model=MfgScrapOut, status_code=201)
async def create_scrap(
    payload: MfgScrapCreate,
    post_now: bool = Query(default=False),
    current: CurrentUser = Depends(require_permission("mfg.write")),
    session: AsyncSession = Depends(get_write_session),
) -> MfgScrapOut:
    svc = ScrapService(session, current.tenant_id, current.user_id)
    scrap = await svc.create_scrap(payload)
    if post_now:
        await svc.post_scrap(scrap.id)
    refreshed = await svc.repo.get_scrap(scrap.id)
    return MfgScrapOut.model_validate(refreshed or scrap)


@router.post("/mfg-scraps/{scrap_id}/post", response_model=MfgScrapOut)
async def post_scrap(
    scrap_id: UUID,
    current: CurrentUser = Depends(require_permission("mfg.post")),
    session: AsyncSession = Depends(get_write_session),
) -> MfgScrapOut:
    svc = ScrapService(session, current.tenant_id, current.user_id)
    scrap = await svc.post_scrap(scrap_id)
    refreshed = await svc.repo.get_scrap(scrap.id)
    return MfgScrapOut.model_validate(refreshed or scrap)


@router.post("/mfg-scraps/{scrap_id}/void", response_model=MfgScrapOut)
async def void_scrap(
    scrap_id: UUID,
    payload: MfgScrapVoidRequest,
    current: CurrentUser = Depends(require_permission("mfg.cancel")),
    session: AsyncSession = Depends(get_write_session),
) -> MfgScrapOut:
    svc = ScrapService(session, current.tenant_id, current.user_id)
    scrap = await svc.void_scrap(scrap_id, payload.reason)
    refreshed = await svc.repo.get_scrap(scrap.id)
    return MfgScrapOut.model_validate(refreshed or scrap)

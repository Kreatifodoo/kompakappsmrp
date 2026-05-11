"""HTTP routes for manufacturing module (Sprint M1: BOM).

Permission scopes: mfg.read / mfg.write. Sprint M2 will add mfg.post +
mfg.cancel for Manufacturing Order lifecycle.
"""

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
)
from app.modules.manufacturing.service import BOMService

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

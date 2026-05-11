"""HTTP routes for fulfillment docs: DeliveryOrder (DO).
GoodsReceipt + RMA endpoints will be added in Sprint B/C.
"""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_write_session
from app.core.exceptions import NotFoundError
from app.deps import CurrentUser, require_permission
from app.modules.fulfillment.repository import FulfillmentRepository
from app.modules.fulfillment.schemas import (
    DeliveryOrderCreate,
    DeliveryOrderOut,
    DOVoidRequest,
)
from app.modules.fulfillment.service import DeliveryOrderService

router = APIRouter(tags=["fulfillment"])


# ─── Delivery Orders ────────────────────────────────────
@router.get("/delivery-orders", response_model=list[DeliveryOrderOut])
async def list_delivery_orders(
    so_id: UUID | None = Query(default=None),
    status: str | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
    current: CurrentUser = Depends(require_permission("sales.read")),
    session: AsyncSession = Depends(get_write_session),
) -> list[DeliveryOrderOut]:
    repo = FulfillmentRepository(session, current.tenant_id)
    dos = await repo.list_dos(
        so_id=so_id, status=status,
        date_from=date_from, date_to=date_to,
        limit=limit, offset=offset,
    )
    return [DeliveryOrderOut.model_validate(d) for d in dos]


@router.get("/delivery-orders/{do_id}", response_model=DeliveryOrderOut)
async def get_delivery_order(
    do_id: UUID,
    current: CurrentUser = Depends(require_permission("sales.read")),
    session: AsyncSession = Depends(get_write_session),
) -> DeliveryOrderOut:
    repo = FulfillmentRepository(session, current.tenant_id)
    do = await repo.get_do(do_id)
    if not do:
        raise NotFoundError("Delivery order not found")
    return DeliveryOrderOut.model_validate(do)


@router.post("/delivery-orders", response_model=DeliveryOrderOut, status_code=201)
async def create_delivery_order(
    payload: DeliveryOrderCreate,
    post_now: bool = Query(default=False, description="Auto-post after create"),
    current: CurrentUser = Depends(require_permission("sales.write")),
    session: AsyncSession = Depends(get_write_session),
) -> DeliveryOrderOut:
    svc = DeliveryOrderService(session, current.tenant_id, current.user_id)
    do = await svc.create_do(payload)
    if post_now:
        await svc.post_do(do.id)
    refreshed = await svc.repo.get_do(do.id)
    return DeliveryOrderOut.model_validate(refreshed or do)


@router.post("/delivery-orders/{do_id}/post", response_model=DeliveryOrderOut)
async def post_delivery_order(
    do_id: UUID,
    current: CurrentUser = Depends(require_permission("sales.post")),
    session: AsyncSession = Depends(get_write_session),
) -> DeliveryOrderOut:
    svc = DeliveryOrderService(session, current.tenant_id, current.user_id)
    do = await svc.post_do(do_id)
    refreshed = await svc.repo.get_do(do.id)
    return DeliveryOrderOut.model_validate(refreshed or do)


@router.post("/delivery-orders/{do_id}/void", response_model=DeliveryOrderOut)
async def void_delivery_order(
    do_id: UUID,
    payload: DOVoidRequest,
    current: CurrentUser = Depends(require_permission("sales.post")),
    session: AsyncSession = Depends(get_write_session),
) -> DeliveryOrderOut:
    svc = DeliveryOrderService(session, current.tenant_id, current.user_id)
    do = await svc.void_do(do_id, payload.reason)
    refreshed = await svc.repo.get_do(do.id)
    return DeliveryOrderOut.model_validate(refreshed or do)

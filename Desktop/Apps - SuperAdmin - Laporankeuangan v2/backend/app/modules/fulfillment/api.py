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


# ─── Goods Receipts ─────────────────────────────────────
from app.modules.fulfillment.schemas import (  # noqa: E402
    GoodsReceiptCreate,
    GoodsReceiptOut,
    GRVoidRequest,
)
from app.modules.fulfillment.service import GoodsReceiptService  # noqa: E402


@router.get("/goods-receipts", response_model=list[GoodsReceiptOut])
async def list_goods_receipts(
    po_id: UUID | None = Query(default=None),
    status: str | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
    current: CurrentUser = Depends(require_permission("purchase.read")),
    session: AsyncSession = Depends(get_write_session),
) -> list[GoodsReceiptOut]:
    repo = FulfillmentRepository(session, current.tenant_id)
    grs = await repo.list_grs(
        po_id=po_id, status=status, date_from=date_from, date_to=date_to,
        limit=limit, offset=offset,
    )
    return [GoodsReceiptOut.model_validate(g) for g in grs]


@router.get("/goods-receipts/{gr_id}", response_model=GoodsReceiptOut)
async def get_goods_receipt(
    gr_id: UUID,
    current: CurrentUser = Depends(require_permission("purchase.read")),
    session: AsyncSession = Depends(get_write_session),
) -> GoodsReceiptOut:
    repo = FulfillmentRepository(session, current.tenant_id)
    gr = await repo.get_gr(gr_id)
    if not gr:
        raise NotFoundError("Goods receipt not found")
    return GoodsReceiptOut.model_validate(gr)


@router.post("/goods-receipts", response_model=GoodsReceiptOut, status_code=201)
async def create_goods_receipt(
    payload: GoodsReceiptCreate,
    post_now: bool = Query(default=False),
    current: CurrentUser = Depends(require_permission("purchase.write")),
    session: AsyncSession = Depends(get_write_session),
) -> GoodsReceiptOut:
    svc = GoodsReceiptService(session, current.tenant_id, current.user_id)
    gr = await svc.create_gr(payload)
    if post_now:
        await svc.post_gr(gr.id)
    refreshed = await svc.repo.get_gr(gr.id)
    return GoodsReceiptOut.model_validate(refreshed or gr)


@router.post("/goods-receipts/{gr_id}/post", response_model=GoodsReceiptOut)
async def post_goods_receipt(
    gr_id: UUID,
    current: CurrentUser = Depends(require_permission("purchase.post")),
    session: AsyncSession = Depends(get_write_session),
) -> GoodsReceiptOut:
    svc = GoodsReceiptService(session, current.tenant_id, current.user_id)
    gr = await svc.post_gr(gr_id)
    refreshed = await svc.repo.get_gr(gr.id)
    return GoodsReceiptOut.model_validate(refreshed or gr)


@router.post("/goods-receipts/{gr_id}/void", response_model=GoodsReceiptOut)
async def void_goods_receipt(
    gr_id: UUID,
    payload: GRVoidRequest,
    current: CurrentUser = Depends(require_permission("purchase.post")),
    session: AsyncSession = Depends(get_write_session),
) -> GoodsReceiptOut:
    svc = GoodsReceiptService(session, current.tenant_id, current.user_id)
    gr = await svc.void_gr(gr_id, payload.reason)
    refreshed = await svc.repo.get_gr(gr.id)
    return GoodsReceiptOut.model_validate(refreshed or gr)


# ─── RMA ────────────────────────────────────────────────
from app.modules.fulfillment.schemas import (  # noqa: E402
    RMACreate,
    RMAOut,
    RMAVoidRequest,
)
from app.modules.fulfillment.service import RMAService  # noqa: E402


def _rma_permission(rma_type: str | None, action: str) -> str:
    # customer_return → sales, supplier_return → purchase
    if rma_type == "supplier_return":
        return f"purchase.{action}"
    return f"sales.{action}"


@router.get("/rmas", response_model=list[RMAOut])
async def list_rmas(
    rma_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    source_do_id: UUID | None = Query(default=None),
    source_gr_id: UUID | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
    current: CurrentUser = Depends(require_permission("sales.read")),
    session: AsyncSession = Depends(get_write_session),
) -> list[RMAOut]:
    repo = FulfillmentRepository(session, current.tenant_id)
    rmas = await repo.list_rmas(
        rma_type=rma_type, status=status,
        source_do_id=source_do_id, source_gr_id=source_gr_id,
        date_from=date_from, date_to=date_to,
        limit=limit, offset=offset,
    )
    return [RMAOut.model_validate(r) for r in rmas]


@router.get("/rmas/{rma_id}", response_model=RMAOut)
async def get_rma(
    rma_id: UUID,
    current: CurrentUser = Depends(require_permission("sales.read")),
    session: AsyncSession = Depends(get_write_session),
) -> RMAOut:
    repo = FulfillmentRepository(session, current.tenant_id)
    rma = await repo.get_rma(rma_id)
    if not rma:
        raise NotFoundError("RMA not found")
    return RMAOut.model_validate(rma)


@router.post("/rmas", response_model=RMAOut, status_code=201)
async def create_rma(
    payload: RMACreate,
    post_now: bool = Query(default=False),
    current: CurrentUser = Depends(require_permission("sales.write")),
    session: AsyncSession = Depends(get_write_session),
) -> RMAOut:
    svc = RMAService(session, current.tenant_id, current.user_id)
    rma = await svc.create_rma(payload)
    if post_now:
        await svc.post_rma(rma.id)
    refreshed = await svc.repo.get_rma(rma.id)
    return RMAOut.model_validate(refreshed or rma)


@router.post("/rmas/{rma_id}/post", response_model=RMAOut)
async def post_rma(
    rma_id: UUID,
    current: CurrentUser = Depends(require_permission("sales.post")),
    session: AsyncSession = Depends(get_write_session),
) -> RMAOut:
    svc = RMAService(session, current.tenant_id, current.user_id)
    rma = await svc.post_rma(rma_id)
    refreshed = await svc.repo.get_rma(rma.id)
    return RMAOut.model_validate(refreshed or rma)


@router.post("/rmas/{rma_id}/void", response_model=RMAOut)
async def void_rma(
    rma_id: UUID,
    payload: RMAVoidRequest,
    current: CurrentUser = Depends(require_permission("sales.post")),
    session: AsyncSession = Depends(get_write_session),
) -> RMAOut:
    svc = RMAService(session, current.tenant_id, current.user_id)
    rma = await svc.void_rma(rma_id, payload.reason)
    refreshed = await svc.repo.get_rma(rma.id)
    return RMAOut.model_validate(refreshed or rma)

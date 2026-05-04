"""HTTP routes for inventory: items, warehouses, stock movements, and
on-hand / valuation reports."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_read_session, get_write_session
from app.core.exceptions import NotFoundError
from app.deps import CurrentUser, require_permission
from app.modules.inventory.repository import InventoryRepository
from app.modules.inventory.schemas import (
    CostingMethodOut,
    CostLayerOut,
    CostLayersReport,
    ItemCreate,
    ItemOut,
    ItemUpdate,
    ReorderLine,
    ReorderReport,
    SetCostingMethodRequest,
    SlowMovingLine,
    SlowMovingReport,
    StockBalanceOut,
    StockCardReport,
    StockMovementCreate,
    StockMovementOut,
    StockOnHandLine,
    StockOnHandReport,
    StockTransferCreate,
    StockTransferOut,
    StockValuationLine,
    StockValuationReport,
    TransferVoidRequest,
    WarehouseCreate,
    WarehouseOut,
    WarehouseUpdate,
)
from app.modules.inventory.service import InventoryService

router = APIRouter(tags=["inventory"])


# ─── Warehouses ──────────────────────────────────────────
@router.get("/warehouses", response_model=list[WarehouseOut])
async def list_warehouses(
    active_only: bool = Query(default=True),
    current: CurrentUser = Depends(require_permission("inventory.read")),
    session: AsyncSession = Depends(get_write_session),
) -> list[WarehouseOut]:
    repo = InventoryRepository(session, current.tenant_id)
    return [WarehouseOut.model_validate(w) for w in await repo.list_warehouses(active_only=active_only)]


@router.post("/warehouses", response_model=WarehouseOut, status_code=201)
async def create_warehouse(
    payload: WarehouseCreate,
    current: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_write_session),
) -> WarehouseOut:
    svc = InventoryService(session, current.tenant_id, current.user_id)
    return WarehouseOut.model_validate(await svc.create_warehouse(payload))


@router.patch("/warehouses/{warehouse_id}", response_model=WarehouseOut)
async def update_warehouse(
    warehouse_id: UUID,
    payload: WarehouseUpdate,
    current: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_write_session),
) -> WarehouseOut:
    svc = InventoryService(session, current.tenant_id, current.user_id)
    return WarehouseOut.model_validate(await svc.update_warehouse(warehouse_id, payload))


# ─── Items ───────────────────────────────────────────────
@router.get("/items", response_model=list[ItemOut])
async def list_items(
    active_only: bool = Query(default=True),
    type: str | None = Query(default=None),  # noqa: A002
    current: CurrentUser = Depends(require_permission("inventory.read")),
    session: AsyncSession = Depends(get_write_session),
) -> list[ItemOut]:
    repo = InventoryRepository(session, current.tenant_id)
    items = await repo.list_items(active_only=active_only, type_=type)
    return [ItemOut.model_validate(i) for i in items]


@router.post("/items", response_model=ItemOut, status_code=201)
async def create_item(
    payload: ItemCreate,
    current: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_write_session),
) -> ItemOut:
    svc = InventoryService(session, current.tenant_id, current.user_id)
    return ItemOut.model_validate(await svc.create_item(payload))


@router.get("/items/{item_id}", response_model=ItemOut)
async def get_item(
    item_id: UUID,
    current: CurrentUser = Depends(require_permission("inventory.read")),
    session: AsyncSession = Depends(get_write_session),
) -> ItemOut:
    repo = InventoryRepository(session, current.tenant_id)
    item = await repo.get_item(item_id)
    if not item:
        raise NotFoundError("Item not found")
    return ItemOut.model_validate(item)


@router.patch("/items/{item_id}", response_model=ItemOut)
async def update_item(
    item_id: UUID,
    payload: ItemUpdate,
    current: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_write_session),
) -> ItemOut:
    svc = InventoryService(session, current.tenant_id, current.user_id)
    return ItemOut.model_validate(await svc.update_item(item_id, payload))


# ─── Stock movements ─────────────────────────────────────
@router.post("/stock-movements", response_model=StockMovementOut, status_code=201)
async def create_movement(
    payload: StockMovementCreate,
    current: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_write_session),
) -> StockMovementOut:
    svc = InventoryService(session, current.tenant_id, current.user_id)
    movement = await svc.post_movement(payload)
    return StockMovementOut.model_validate(movement)


@router.get("/stock-movements", response_model=list[StockMovementOut])
async def list_movements(
    item_id: UUID | None = Query(default=None),
    warehouse_id: UUID | None = Query(default=None),
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
    current: CurrentUser = Depends(require_permission("inventory.read")),
    session: AsyncSession = Depends(get_write_session),
) -> list[StockMovementOut]:
    repo = InventoryRepository(session, current.tenant_id)
    moves = await repo.list_movements(item_id=item_id, warehouse_id=warehouse_id, limit=limit, offset=offset)
    return [StockMovementOut.model_validate(m) for m in moves]


# ─── Balance / valuation reports ─────────────────────────
@router.get("/stock-balances", response_model=list[StockBalanceOut])
async def list_balances(
    item_id: UUID | None = Query(default=None),
    warehouse_id: UUID | None = Query(default=None),
    current: CurrentUser = Depends(require_permission("inventory.read")),
    session: AsyncSession = Depends(get_read_session),
) -> list[StockBalanceOut]:
    repo = InventoryRepository(session, current.tenant_id)
    rows = await repo.list_balances(item_id=item_id, warehouse_id=warehouse_id)
    return [StockBalanceOut.model_validate(r) for r in rows]


@router.get(
    "/reports/stock-on-hand",
    response_model=StockOnHandReport,
    summary="Per-warehouse on-hand quantities and values",
)
async def stock_on_hand(
    warehouse_id: UUID | None = Query(default=None),
    current: CurrentUser = Depends(require_permission("inventory.read")),
    session: AsyncSession = Depends(get_read_session),
) -> StockOnHandReport:
    repo = InventoryRepository(session, current.tenant_id)

    # Collect items + warehouses up-front so we can decorate balances
    items = {i.id: i for i in await repo.list_items(active_only=False)}
    warehouses = {w.id: w for w in await repo.list_warehouses(active_only=False)}

    balances = await repo.list_balances(warehouse_id=warehouse_id)
    lines: list[StockOnHandLine] = []
    total_value = Decimal("0")
    for bal in balances:
        if bal.on_hand_qty == 0:
            continue
        item = items.get(bal.item_id)
        wh = warehouses.get(bal.warehouse_id)
        if not item or not wh:
            continue
        value = (bal.on_hand_qty * bal.avg_cost).quantize(Decimal("0.01"))
        lines.append(
            StockOnHandLine(
                item_id=item.id,
                sku=item.sku,
                name=item.name,
                unit=item.unit,
                warehouse_id=wh.id,
                warehouse_code=wh.code,
                on_hand_qty=bal.on_hand_qty,
                avg_cost=bal.avg_cost,
                value=value,
                below_min_stock=bal.on_hand_qty < item.min_stock,
            )
        )
        total_value += value

    lines.sort(key=lambda li: (li.sku, li.warehouse_code))
    return StockOnHandReport(lines=lines, total_value=total_value)


@router.get(
    "/reports/stock-valuation",
    response_model=StockValuationReport,
    summary="Per-item valuation aggregated across warehouses",
)
async def stock_valuation(
    current: CurrentUser = Depends(require_permission("inventory.read")),
    session: AsyncSession = Depends(get_read_session),
) -> StockValuationReport:
    repo = InventoryRepository(session, current.tenant_id)
    rows = await repo.aggregate_balances_by_item()
    items = {i.id: i for i in await repo.list_items(active_only=False)}

    lines: list[StockValuationLine] = []
    total_value = Decimal("0")
    for item_id, qty, avg in rows:
        if qty == 0:
            continue
        item = items.get(item_id)
        if not item:
            continue
        value = (qty * avg).quantize(Decimal("0.01"))
        lines.append(
            StockValuationLine(
                item_id=item.id,
                sku=item.sku,
                name=item.name,
                unit=item.unit,
                on_hand_qty=qty,
                weighted_avg_cost=avg,
                value=value,
            )
        )
        total_value += value

    lines.sort(key=lambda li: li.sku)
    return StockValuationReport(lines=lines, total_value=total_value)


# ─── Costing method ──────────────────────────────────────
@router.get("/costing-method", response_model=CostingMethodOut)
async def get_costing_method(
    current: CurrentUser = Depends(require_permission("inventory.read")),
    session: AsyncSession = Depends(get_read_session),
) -> CostingMethodOut:
    from sqlalchemy import select

    from app.modules.identity.models import Tenant

    method = (
        await session.execute(select(Tenant.costing_method).where(Tenant.id == current.tenant_id))
    ).scalar_one()
    return CostingMethodOut(method=method)


@router.put(
    "/costing-method",
    response_model=CostingMethodOut,
    summary="Switch the tenant's inventory costing method (avg/fifo/lifo)",
)
async def set_costing_method(
    payload: SetCostingMethodRequest,
    current: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_write_session),
) -> CostingMethodOut:
    svc = InventoryService(session, current.tenant_id, current.user_id)
    method = await svc.set_costing_method(
        method=payload.method, seed_opening_layers=payload.seed_opening_layers
    )
    return CostingMethodOut(method=method)


# ─── Stock transfers ─────────────────────────────────────
@router.get("/stock-transfers", response_model=list[StockTransferOut])
async def list_transfers(
    status: str | None = Query(default=None),
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
    current: CurrentUser = Depends(require_permission("inventory.read")),
    session: AsyncSession = Depends(get_write_session),
) -> list[StockTransferOut]:
    repo = InventoryRepository(session, current.tenant_id)
    rows = await repo.list_transfers(status=status, limit=limit, offset=offset)
    return [StockTransferOut.model_validate(r) for r in rows]


@router.get("/stock-transfers/{transfer_id}", response_model=StockTransferOut)
async def get_transfer(
    transfer_id: UUID,
    current: CurrentUser = Depends(require_permission("inventory.read")),
    session: AsyncSession = Depends(get_write_session),
) -> StockTransferOut:
    repo = InventoryRepository(session, current.tenant_id)
    tr = await repo.get_transfer(transfer_id)
    if not tr:
        raise NotFoundError("Transfer not found")
    return StockTransferOut.model_validate(tr)


@router.post("/stock-transfers", response_model=StockTransferOut, status_code=201)
async def create_transfer(
    payload: StockTransferCreate,
    current: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_write_session),
) -> StockTransferOut:
    svc = InventoryService(session, current.tenant_id, current.user_id)
    tr = await svc.create_transfer(payload)
    # Refresh with eager-loaded lines so pydantic serialization doesn't trigger lazy load
    refreshed = await svc.repo.get_transfer(tr.id)
    return StockTransferOut.model_validate(refreshed or tr)


@router.post("/stock-transfers/{transfer_id}/void", response_model=StockTransferOut)
async def void_transfer(
    transfer_id: UUID,
    payload: TransferVoidRequest,
    current: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_write_session),
) -> StockTransferOut:
    svc = InventoryService(session, current.tenant_id, current.user_id)
    tr = await svc.void_transfer(transfer_id, payload.reason)
    return StockTransferOut.model_validate(tr)


# ─── Cost-layers ledger ──────────────────────────────────
@router.get(
    "/items/{item_id}/cost-layers",
    response_model=CostLayersReport,
    summary="Cost-layer drill-down for one item (FIFO/LIFO tenants only)",
)
async def item_cost_layers(
    item_id: UUID,
    warehouse_id: UUID | None = Query(default=None),
    include_exhausted: bool = Query(default=False, description="Include consumed layers in the response"),
    current: CurrentUser = Depends(require_permission("inventory.read")),
    session: AsyncSession = Depends(get_read_session),
) -> CostLayersReport:
    repo = InventoryRepository(session, current.tenant_id)
    item = await repo.get_item(item_id)
    if not item:
        raise NotFoundError("Item not found")

    layers = await repo.list_layers_for_item(
        item_id, warehouse_id=warehouse_id, include_exhausted=include_exhausted
    )
    out: list[CostLayerOut] = []
    total_qty = Decimal("0")
    total_value = Decimal("0")
    for la in layers:
        remaining_value = (la.remaining_qty * la.unit_cost).quantize(Decimal("0.01"))
        out.append(
            CostLayerOut(
                id=la.id,
                item_id=la.item_id,
                warehouse_id=la.warehouse_id,
                source_movement_id=la.source_movement_id,
                received_at=la.received_at,
                original_qty=la.original_qty,
                remaining_qty=la.remaining_qty,
                unit_cost=la.unit_cost,
                is_exhausted=la.is_exhausted,
                remaining_value=remaining_value,
            )
        )
        total_qty += la.remaining_qty
        total_value += remaining_value

    return CostLayersReport(
        item_id=item.id,
        layers=out,
        total_remaining_qty=total_qty,
        total_remaining_value=total_value,
    )


# ─── Stock card report ───────────────────────────────────
@router.get(
    "/items/{item_id}/stock-card",
    response_model=StockCardReport,
    summary="Per-(item, warehouse) chronological stock card with opening/closing balances",
)
async def item_stock_card(
    item_id: UUID,
    warehouse_id: UUID = Query(..., description="Warehouse to scope the card to"),
    date_from: date | None = Query(default=None, description="Inclusive start date (YYYY-MM-DD)"),
    date_to: date | None = Query(default=None, description="Inclusive end date (YYYY-MM-DD)"),
    current: CurrentUser = Depends(require_permission("inventory.read")),
    session: AsyncSession = Depends(get_read_session),
) -> StockCardReport:
    svc = InventoryService(session, current.tenant_id, current.user_id)
    return await svc.stock_card_report(
        item_id,
        warehouse_id,
        date_from=date_from,
        date_to=date_to,
    )


# ─── Reorder report ──────────────────────────────────────
@router.get(
    "/reports/reorder",
    response_model=ReorderReport,
    summary=(
        "Items whose total on-hand quantity is below min_stock. "
        "Aggregates across all warehouses unless warehouse_id is supplied."
    ),
)
async def reorder_report(
    warehouse_id: UUID | None = Query(default=None, description="Scope to a single warehouse"),
    current: CurrentUser = Depends(require_permission("inventory.read")),
    session: AsyncSession = Depends(get_read_session),
) -> ReorderReport:
    from datetime import date as _date

    repo = InventoryRepository(session, current.tenant_id)
    rows = await repo.reorder_items(warehouse_id=warehouse_id)

    lines: list[ReorderLine] = []
    total_shortage_value = Decimal("0")

    for item, on_hand_qty, avg_cost in rows:
        shortage = (item.min_stock - on_hand_qty).quantize(Decimal("0.0001"))
        shortage_value = (shortage * avg_cost).quantize(Decimal("0.01"))
        lines.append(
            ReorderLine(
                item_id=item.id,
                sku=item.sku,
                name=item.name,
                unit=item.unit,
                min_stock=item.min_stock,
                on_hand_qty=on_hand_qty,
                shortage=shortage,
                avg_cost=avg_cost,
                shortage_value=shortage_value,
            )
        )
        total_shortage_value += shortage_value

    return ReorderReport(
        as_of_today=_date.today(),
        warehouse_id=warehouse_id,
        lines=lines,
        total_shortage_value=total_shortage_value,
    )


# ─── Slow-moving items report ─────────────────────────────
@router.get(
    "/reports/slow-moving",
    response_model=SlowMovingReport,
    summary=(
        "Items with no outflow within the lookback window (default 90 days). "
        "Only rows with on_hand_qty > 0 are included."
    ),
)
async def slow_moving_report(
    days: int = Query(default=90, ge=1, le=3650, description="Lookback window in days"),
    warehouse_id: UUID | None = Query(default=None, description="Scope to a single warehouse"),
    current: CurrentUser = Depends(require_permission("inventory.read")),
    session: AsyncSession = Depends(get_read_session),
) -> SlowMovingReport:
    from datetime import date as _date
    from datetime import timedelta

    today = _date.today()
    cutoff = today - timedelta(days=days)

    repo = InventoryRepository(session, current.tenant_id)
    items = {i.id: i for i in await repo.list_items(active_only=True, type_="stock")}
    warehouses = {w.id: w for w in await repo.list_warehouses(active_only=False)}

    rows = await repo.slow_moving_items(cutoff_date=cutoff, warehouse_id=warehouse_id)

    lines: list[SlowMovingLine] = []
    total_value = Decimal("0")

    for bal, last_outflow_date, period_out_qty in rows:
        item = items.get(bal.item_id)
        wh = warehouses.get(bal.warehouse_id)
        if not item or not wh:
            continue

        # Compute days since last outflow
        if last_outflow_date is not None:
            days_since = (today - last_outflow_date).days
        else:
            days_since = None

        # Slow-moving = no outflow at all, OR last outflow older than threshold
        is_slow = last_outflow_date is None or days_since > days  # type: ignore[operator]
        if not is_slow:
            continue

        value = (bal.on_hand_qty * bal.avg_cost).quantize(Decimal("0.01"))
        lines.append(
            SlowMovingLine(
                item_id=item.id,
                sku=item.sku,
                name=item.name,
                unit=item.unit,
                warehouse_id=wh.id,
                warehouse_code=wh.code,
                on_hand_qty=bal.on_hand_qty,
                avg_cost=bal.avg_cost,
                on_hand_value=value,
                last_outflow_date=last_outflow_date,
                days_since_last_outflow=days_since,
                period_out_qty=period_out_qty,
            )
        )
        total_value += value

    # Sort: never-moved-out first (None), then oldest outflow first, then SKU
    lines.sort(
        key=lambda ln: (
            0 if ln.last_outflow_date is None else 1,
            -(ln.days_since_last_outflow or 0),
            ln.sku,
        )
    )

    return SlowMovingReport(
        as_of_today=today,
        lookback_days=days,
        warehouse_id=warehouse_id,
        lines=lines,
        total_on_hand_value=total_value,
    )

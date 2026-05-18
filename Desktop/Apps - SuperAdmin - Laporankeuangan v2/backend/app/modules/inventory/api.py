"""HTTP routes for inventory: items, warehouses, stock movements, and
on-hand / valuation reports."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_read_session, get_write_session
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
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


# ═══════════════════════════════════════════════════════════════════
# CUSTOM INVENTORY OPERATIONS
# CRUD for user-defined operation types (extends 7 built-in defaults).
# ═══════════════════════════════════════════════════════════════════

from app.modules.inventory.models import CustomInventoryOperation
from app.modules.inventory.schemas import CustomInvOpCreate, CustomInvOpOut, CustomInvOpUpdate


@router.get(
    "/custom-inventory-operations",
    response_model=list[CustomInvOpOut],
    summary="List user-defined inventory operations (custom op types)",
)
async def list_custom_inv_ops(
    active_only: bool = Query(default=False),
    current: CurrentUser = Depends(require_permission("inventory.read")),
    session: AsyncSession = Depends(get_read_session),
) -> list[CustomInvOpOut]:
    repo = InventoryRepository(session, current.tenant_id)
    rows = await repo.list_custom_ops(active_only=active_only)
    return [CustomInvOpOut.model_validate(r) for r in rows]


@router.post(
    "/custom-inventory-operations",
    response_model=CustomInvOpOut,
    status_code=201,
    summary="Create a new custom inventory operation",
)
async def create_custom_inv_op(
    payload: CustomInvOpCreate,
    current: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_write_session),
) -> CustomInvOpOut:
    repo = InventoryRepository(session, current.tenant_id)
    if await repo.get_custom_op_by_key(payload.key):
        raise ConflictError(f"Custom operation key '{payload.key}' already exists")
    if payload.default_contra_account_id:
        from app.modules.accounting.repository import AccountingRepository
        acct = await AccountingRepository(session, current.tenant_id).get_account(
            payload.default_contra_account_id
        )
        if not acct:
            raise ValidationError("default_contra_account_id not found in this tenant")

    op = CustomInventoryOperation(
        tenant_id=current.tenant_id,
        **payload.model_dump(),
    )
    op = await repo.add_custom_op(op)
    return CustomInvOpOut.model_validate(op)


@router.patch(
    "/custom-inventory-operations/{op_id}",
    response_model=CustomInvOpOut,
    summary="Update a custom inventory operation",
)
async def update_custom_inv_op(
    op_id: UUID,
    payload: CustomInvOpUpdate,
    current: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_write_session),
) -> CustomInvOpOut:
    repo = InventoryRepository(session, current.tenant_id)
    op = await repo.get_custom_op(op_id)
    if not op:
        raise NotFoundError("Custom operation not found")
    if payload.default_contra_account_id is not None:
        from app.modules.accounting.repository import AccountingRepository
        acct = await AccountingRepository(session, current.tenant_id).get_account(
            payload.default_contra_account_id
        )
        if not acct:
            raise ValidationError("default_contra_account_id not found in this tenant")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(op, k, v)
    await session.flush()
    await session.refresh(op)
    return CustomInvOpOut.model_validate(op)


@router.delete(
    "/custom-inventory-operations/{op_id}",
    status_code=204,
    summary="Soft-delete a custom inventory operation (sets is_active=false)",
)
async def delete_custom_inv_op(
    op_id: UUID,
    current: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_write_session),
) -> None:
    repo = InventoryRepository(session, current.tenant_id)
    op = await repo.get_custom_op(op_id)
    if not op:
        raise NotFoundError("Custom operation not found")
    op.is_active = False
    await session.flush()


# ─── Stock Lots / Batches (Sprint Lot) ───────────────────
from sqlalchemy import select as _sel, asc as _asc, nulls_last as _nulls_last
from datetime import date as _date2, timedelta as _td
from app.modules.inventory.models import StockLot
from app.modules.inventory.schemas import StockLotOut


@router.get("/stock-lots", response_model=list[StockLotOut])
async def list_stock_lots(
    item_id: UUID | None = Query(default=None),
    warehouse_id: UUID | None = Query(default=None),
    include_depleted: bool = Query(default=False, description="Include lots with qty_remaining=0"),
    expiring_within_days: int | None = Query(default=None, ge=0, le=3650),
    limit: int = Query(default=200, le=1000),
    current: CurrentUser = Depends(require_permission("inventory.read")),
    session: AsyncSession = Depends(get_write_session),
) -> list[StockLotOut]:
    conds = [StockLot.tenant_id == current.tenant_id]
    if item_id: conds.append(StockLot.item_id == item_id)
    if warehouse_id: conds.append(StockLot.warehouse_id == warehouse_id)
    if not include_depleted: conds.append(StockLot.qty_remaining > 0)
    if expiring_within_days is not None:
        cutoff = _date2.today() + _td(days=expiring_within_days)
        conds.append(StockLot.expiry_date != None)  # noqa: E711
        conds.append(StockLot.expiry_date <= cutoff)
    stmt = (
        _sel(StockLot).where(*conds)
        .order_by(
            _nulls_last(_asc(StockLot.expiry_date)),
            _nulls_last(_asc(StockLot.mfg_date)),
            _asc(StockLot.created_at),
        )
        .limit(limit)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [StockLotOut.model_validate(r) for r in rows]


@router.get("/stock-lots/{lot_id}", response_model=StockLotOut)
async def get_stock_lot(
    lot_id: UUID,
    current: CurrentUser = Depends(require_permission("inventory.read")),
    session: AsyncSession = Depends(get_write_session),
) -> StockLotOut:
    stmt = _sel(StockLot).where(
        StockLot.id == lot_id, StockLot.tenant_id == current.tenant_id
    )
    lot = (await session.execute(stmt)).scalar_one_or_none()
    if not lot:
        raise NotFoundError("Lot not found")
    return StockLotOut.model_validate(lot)


# ─── Lot Traceability (where-from / where-used) ──────────
@router.get("/stock-lots/{lot_id}/traceability")
async def lot_traceability(
    lot_id: UUID,
    current: CurrentUser = Depends(require_permission("inventory.read")),
    session: AsyncSession = Depends(get_write_session),
) -> dict:
    """Where-from / where-used drill-down for one lot.

    Returns the lot, all inflows (origin documents that created the
    lot), and all outflows (downstream documents that consumed the
    lot), each enriched with a human-readable source label like
    'GR-2026-00005' when we can resolve the source_id."""
    from app.modules.inventory.models import StockMovement
    from sqlalchemy import text
    from collections import defaultdict

    # Lot itself
    lot_stmt = _sel(StockLot).where(
        StockLot.id == lot_id, StockLot.tenant_id == current.tenant_id
    )
    lot = (await session.execute(lot_stmt)).scalar_one_or_none()
    if not lot:
        raise NotFoundError("Lot not found")

    # All movements on this lot
    mvm_stmt = (
        _sel(StockMovement)
        .where(
            StockMovement.tenant_id == current.tenant_id,
            StockMovement.lot_id == lot_id,
        )
        .order_by(StockMovement.movement_date.asc(), StockMovement.created_at.asc())
    )
    movements = list((await session.execute(mvm_stmt)).scalars().all())

    # Bulk-resolve source labels per source table
    by_src: dict[str, list[UUID]] = defaultdict(list)
    for m in movements:
        if m.source_id:
            by_src[m.source].append(m.source_id)

    label_map: dict[tuple[str, UUID], dict] = {}

    async def _resolve(source: str, ids: list[UUID], table: str, no_col: str, date_col: str | None = None):
        if not ids: return
        sql = f"SELECT id, {no_col}{', ' + date_col if date_col else ''} FROM {table} WHERE id = ANY(:ids)"
        rows = (await session.execute(text(sql), {"ids": list(ids)})).all()
        for r in rows:
            label_map[(source, r[0])] = {
                "doc_no": r[1],
                "date": (r[2].isoformat() if (date_col and r[2]) else None),
            }

    # Manufacturing
    await _resolve("mfg_issue",         by_src.get("mfg_issue", []),         "manufacturing_orders", "mo_no", "planned_start")
    await _resolve("mfg_receipt",       by_src.get("mfg_receipt", []),       "manufacturing_orders", "mo_no", "planned_start")
    await _resolve("mfg_issue_void",    by_src.get("mfg_issue_void", []),    "manufacturing_orders", "mo_no", "planned_start")
    await _resolve("mfg_receipt_void",  by_src.get("mfg_receipt_void", []),  "manufacturing_orders", "mo_no", "planned_start")
    await _resolve("mfg_scrap",         by_src.get("mfg_scrap", []),         "mfg_scraps",           "scrap_no", "scrap_date")
    await _resolve("mfg_scrap_void",    by_src.get("mfg_scrap_void", []),    "mfg_scraps",           "scrap_no", "scrap_date")
    await _resolve("subcontract_issue",      by_src.get("subcontract_issue", []),      "subcontract_orders", "sco_no", "sco_date")
    await _resolve("subcontract_receipt",    by_src.get("subcontract_receipt", []),    "subcontract_orders", "sco_no", "sco_date")
    await _resolve("subcontract_issue_void", by_src.get("subcontract_issue_void", []), "subcontract_orders", "sco_no", "sco_date")
    # Fulfillment
    await _resolve("delivery_order",      by_src.get("delivery_order", []),      "delivery_orders", "do_no", "delivery_date")
    await _resolve("delivery_order_void", by_src.get("delivery_order_void", []), "delivery_orders", "do_no", "delivery_date")
    await _resolve("goods_receipt",       by_src.get("goods_receipt", []),       "goods_receipts",  "gr_no", "receipt_date")
    await _resolve("goods_receipt_void",  by_src.get("goods_receipt_void", []),  "goods_receipts",  "gr_no", "receipt_date")
    await _resolve("customer_return",      by_src.get("customer_return", []),      "rmas", "rma_no", "rma_date")
    await _resolve("supplier_return",      by_src.get("supplier_return", []),      "rmas", "rma_no", "rma_date")
    await _resolve("customer_return_void", by_src.get("customer_return_void", []), "rmas", "rma_no", "rma_date")
    await _resolve("supplier_return_void", by_src.get("supplier_return_void", []), "rmas", "rma_no", "rma_date")
    # Sales / Purchase invoices
    await _resolve("sales_invoice",         by_src.get("sales_invoice", []),         "sales_invoices",    "invoice_no", "invoice_date")
    await _resolve("void_sales_invoice",    by_src.get("void_sales_invoice", []),    "sales_invoices",    "invoice_no", "invoice_date")
    await _resolve("purchase_invoice",      by_src.get("purchase_invoice", []),      "purchase_invoices", "invoice_no", "invoice_date")
    await _resolve("void_purchase_invoice", by_src.get("void_purchase_invoice", []), "purchase_invoices", "invoice_no", "invoice_date")
    # Stock transfer
    await _resolve("stock_transfer",      by_src.get("stock_transfer", []),      "stock_transfers", "transfer_no", "transfer_date")
    await _resolve("void_stock_transfer", by_src.get("void_stock_transfer", []), "stock_transfers", "transfer_no", "transfer_date")

    def _serialize(m, is_inflow: bool) -> dict:
        info = label_map.get((m.source, m.source_id)) if m.source_id else None
        return {
            "movement_id":     str(m.id),
            "direction":       m.direction,
            "is_inflow":       is_inflow,
            "movement_date":   m.movement_date.isoformat(),
            "qty":             float(m.qty),
            "unit_cost":       float(m.unit_cost),
            "total_cost":      float(m.total_cost),
            "source":          m.source,
            "source_id":       str(m.source_id) if m.source_id else None,
            "source_doc_no":   info["doc_no"] if info else None,
            "source_doc_date": info["date"] if info else None,
            "notes":           m.notes,
        }

    inflows  = [_serialize(m, True)  for m in movements if m.direction in ("in", "adjust_in")]
    outflows = [_serialize(m, False) for m in movements if m.direction in ("out", "adjust_out")]
    total_in  = sum(x["qty"] for x in inflows)
    total_out = sum(x["qty"] for x in outflows)

    return {
        "lot": StockLotOut.model_validate(lot).model_dump(mode="json"),
        "summary": {
            "total_in":       total_in,
            "total_out":      total_out,
            "remaining":      float(lot.qty_remaining),
            "movement_count": len(movements),
        },
        "inflows":  inflows,
        "outflows": outflows,
    }


# ─── Warehouse Locations ─────────────────────────────────
from app.modules.inventory.models import WarehouseLocation, Warehouse
from app.modules.inventory.schemas import (
    WarehouseLocationCreate, WarehouseLocationOut, WarehouseLocationUpdate,
)


@router.get("/warehouses/{warehouse_id}/locations", response_model=list[WarehouseLocationOut])
async def list_locations(
    warehouse_id: UUID,
    is_active: bool | None = Query(default=None),
    current: CurrentUser = Depends(require_permission("inventory.read")),
    session: AsyncSession = Depends(get_write_session),
) -> list[WarehouseLocationOut]:
    # Verify warehouse belongs to tenant
    wh_stmt = _sel(Warehouse).where(
        Warehouse.id == warehouse_id, Warehouse.tenant_id == current.tenant_id
    )
    wh = (await session.execute(wh_stmt)).scalar_one_or_none()
    if not wh:
        raise NotFoundError("Warehouse not found")
    conds = [
        WarehouseLocation.tenant_id == current.tenant_id,
        WarehouseLocation.warehouse_id == warehouse_id,
    ]
    if is_active is not None:
        conds.append(WarehouseLocation.is_active == is_active)
    stmt = _sel(WarehouseLocation).where(*conds).order_by(WarehouseLocation.code)
    rows = (await session.execute(stmt)).scalars().all()
    return [WarehouseLocationOut.model_validate(r) for r in rows]


@router.post("/warehouses/{warehouse_id}/locations", response_model=WarehouseLocationOut, status_code=201)
async def create_location(
    warehouse_id: UUID,
    payload: WarehouseLocationCreate,
    current: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_write_session),
) -> WarehouseLocationOut:
    wh_stmt = _sel(Warehouse).where(
        Warehouse.id == warehouse_id, Warehouse.tenant_id == current.tenant_id
    )
    wh = (await session.execute(wh_stmt)).scalar_one_or_none()
    if not wh:
        raise NotFoundError("Warehouse not found")
    # Reject duplicate code within the same warehouse
    dup = (await session.execute(
        _sel(WarehouseLocation).where(
            WarehouseLocation.warehouse_id == warehouse_id,
            WarehouseLocation.code == payload.code,
        )
    )).scalar_one_or_none()
    if dup:
        from app.core.exceptions import ConflictError
        raise ConflictError(f"Location code '{payload.code}' already exists in this warehouse")
    loc = WarehouseLocation(
        tenant_id=current.tenant_id,
        warehouse_id=warehouse_id,
        code=payload.code,
        name=payload.name,
        is_active=payload.is_active,
        notes=payload.notes,
    )
    session.add(loc)
    await session.flush()
    return WarehouseLocationOut.model_validate(loc)


@router.patch("/warehouses/{warehouse_id}/locations/{loc_id}", response_model=WarehouseLocationOut)
async def update_location(
    warehouse_id: UUID,
    loc_id: UUID,
    payload: WarehouseLocationUpdate,
    current: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_write_session),
) -> WarehouseLocationOut:
    stmt = _sel(WarehouseLocation).where(
        WarehouseLocation.id == loc_id,
        WarehouseLocation.warehouse_id == warehouse_id,
        WarehouseLocation.tenant_id == current.tenant_id,
    )
    loc = (await session.execute(stmt)).scalar_one_or_none()
    if not loc:
        raise NotFoundError("Location not found")
    # Dup check if code changing
    if payload.code is not None and payload.code != loc.code:
        dup = (await session.execute(
            _sel(WarehouseLocation).where(
                WarehouseLocation.warehouse_id == warehouse_id,
                WarehouseLocation.code == payload.code,
                WarehouseLocation.id != loc_id,
            )
        )).scalar_one_or_none()
        if dup:
            from app.core.exceptions import ConflictError
            raise ConflictError(f"Location code '{payload.code}' already exists")
        loc.code = payload.code
    if payload.name is not None:      loc.name = payload.name
    if payload.is_active is not None: loc.is_active = payload.is_active
    if payload.notes is not None:     loc.notes = payload.notes
    await session.flush()
    return WarehouseLocationOut.model_validate(loc)


@router.delete("/warehouses/{warehouse_id}/locations/{loc_id}", status_code=204)
async def delete_location(
    warehouse_id: UUID,
    loc_id: UUID,
    current: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_write_session),
) -> None:
    stmt = _sel(WarehouseLocation).where(
        WarehouseLocation.id == loc_id,
        WarehouseLocation.warehouse_id == warehouse_id,
        WarehouseLocation.tenant_id == current.tenant_id,
    )
    loc = (await session.execute(stmt)).scalar_one_or_none()
    if not loc:
        raise NotFoundError("Location not found")
    await session.delete(loc)
    await session.flush()
    return None

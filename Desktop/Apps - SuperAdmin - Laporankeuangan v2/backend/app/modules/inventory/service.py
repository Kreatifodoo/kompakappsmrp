"""Inventory business logic — weighted-average costing.

Costing formula on stock-in:
    new_avg = (old_qty × old_avg + in_qty × in_unit_cost) / (old_qty + in_qty)

Stock-out and adjust-out use the current avg_cost (not the supplied
unit_cost), which preserves accumulated cost basis. Adjust-in is
treated identically to a regular stock-in.
"""

from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.modules.inventory.models import Item, StockMovement, Warehouse
from app.modules.inventory.repository import InventoryRepository
from app.modules.inventory.schemas import (
    ItemCreate,
    ItemUpdate,
    StockMovementCreate,
    WarehouseCreate,
    WarehouseUpdate,
)
from app.modules.periods.service import assert_period_open

QTY_ROUNDING = Decimal("0.0001")  # 4-decimal precision for fractional units
MONEY_ROUNDING = Decimal("0.01")


def _q4(value: Decimal) -> Decimal:
    return value.quantize(QTY_ROUNDING, rounding=ROUND_HALF_UP)


def _q2(value: Decimal) -> Decimal:
    return value.quantize(MONEY_ROUNDING, rounding=ROUND_HALF_UP)


class InventoryService:
    def __init__(self, session: AsyncSession, tenant_id: UUID, user_id: UUID):
        self.session = session
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.repo = InventoryRepository(session, tenant_id)

    # ─── Warehouses ─────────────────────────────────────
    async def create_warehouse(self, payload: WarehouseCreate) -> Warehouse:
        if await self.repo.get_warehouse_by_code(payload.code):
            raise ConflictError(f"Warehouse code '{payload.code}' already exists")
        if payload.is_default:
            await self.repo.clear_default_warehouse()
        wh = Warehouse(
            tenant_id=self.tenant_id,
            code=payload.code,
            name=payload.name,
            is_default=payload.is_default,
        )
        return await self.repo.add_warehouse(wh)

    async def update_warehouse(self, warehouse_id: UUID, payload: WarehouseUpdate) -> Warehouse:
        wh = await self.repo.get_warehouse(warehouse_id)
        if not wh:
            raise NotFoundError("Warehouse not found")
        updates = payload.model_dump(exclude_unset=True)
        # If we're promoting this warehouse to default, demote the others first
        if updates.get("is_default") is True:
            await self.repo.clear_default_warehouse()
        for k, v in updates.items():
            setattr(wh, k, v)
        await self.session.flush()
        return wh

    # ─── Items ──────────────────────────────────────────
    async def create_item(self, payload: ItemCreate) -> Item:
        if await self.repo.get_item_by_sku(payload.sku):
            raise ConflictError(f"SKU '{payload.sku}' already exists")
        item = Item(tenant_id=self.tenant_id, **payload.model_dump())
        return await self.repo.add_item(item)

    async def update_item(self, item_id: UUID, payload: ItemUpdate) -> Item:
        item = await self.repo.get_item(item_id)
        if not item:
            raise NotFoundError("Item not found")
        for k, v in payload.model_dump(exclude_unset=True).items():
            setattr(item, k, v)
        await self.session.flush()
        return item

    # ─── Stock movements ────────────────────────────────
    async def post_movement(
        self,
        payload: StockMovementCreate,
        *,
        source: str = "adjustment",
        source_id: UUID | None = None,
    ) -> StockMovement:
        await assert_period_open(self.session, self.tenant_id, payload.movement_date)

        item = await self.repo.get_item(payload.item_id)
        if not item:
            raise ValidationError("Item not found in this tenant")
        if item.type != "stock":
            raise ValidationError(f"Cannot move stock for non-stock item type '{item.type}'")
        if not item.is_active:
            raise ValidationError("Inactive items cannot have stock movements")

        warehouse = await self.repo.get_warehouse(payload.warehouse_id)
        if not warehouse:
            raise ValidationError("Warehouse not found in this tenant")
        if not warehouse.is_active:
            raise ValidationError("Cannot move stock through an inactive warehouse")

        return await self._post_movement_inner(
            item=item,
            warehouse=warehouse,
            movement_date=payload.movement_date,
            direction=payload.direction,
            qty=payload.qty,
            unit_cost=payload.unit_cost,
            notes=payload.notes,
            source=source,
            source_id=source_id,
        )

    async def _post_movement_inner(
        self,
        *,
        item: Item,
        warehouse: Warehouse,
        movement_date,  # noqa: ANN001
        direction: str,
        qty: Decimal,
        unit_cost: Decimal,
        notes: str | None,
        source: str,
        source_id: UUID | None,
    ) -> StockMovement:
        bal = await self.repo.upsert_balance(item.id, warehouse.id)

        qty = _q4(qty)
        if qty <= 0:
            raise ValidationError("Movement qty must be positive")

        if direction in ("in", "adjust_in"):
            applied_unit_cost = _q4(unit_cost)
            old_qty = bal.on_hand_qty
            new_qty = _q4(old_qty + qty)
            if new_qty > 0:
                # Weighted average — keep 4 decimals for cost precision
                bal.avg_cost = _q4((old_qty * bal.avg_cost + qty * applied_unit_cost) / new_qty)
            else:
                bal.avg_cost = applied_unit_cost
            bal.on_hand_qty = new_qty
        elif direction in ("out", "adjust_out"):
            if bal.on_hand_qty < qty:
                raise ValidationError(f"Insufficient stock: on hand {bal.on_hand_qty} < requested {qty}")
            # avg_cost is unchanged; outflows are valued at current avg
            applied_unit_cost = _q4(bal.avg_cost)
            bal.on_hand_qty = _q4(bal.on_hand_qty - qty)
            # If we just zeroed out, reset avg to 0 so a fresh restock
            # picks up the new cost cleanly
            if bal.on_hand_qty == 0:
                bal.avg_cost = Decimal("0")
        else:
            raise ValidationError(f"Unknown direction '{direction}'")

        total_cost = _q2(qty * applied_unit_cost)
        movement = StockMovement(
            tenant_id=self.tenant_id,
            item_id=item.id,
            warehouse_id=warehouse.id,
            movement_date=movement_date,
            direction=direction,
            qty=qty,
            unit_cost=applied_unit_cost,
            total_cost=total_cost,
            source=source,
            source_id=source_id,
            notes=notes,
            qty_after=bal.on_hand_qty,
            avg_cost_after=bal.avg_cost,
            created_by=self.user_id,
        )
        await self.repo.add_movement(movement)
        return movement

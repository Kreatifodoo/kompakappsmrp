"""Inventory data access — tenant-scoped."""

from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.inventory.models import (
    Item,
    StockBalance,
    StockCostLayer,
    StockMovement,
    Warehouse,
)


class InventoryRepository:
    def __init__(self, session: AsyncSession, tenant_id: UUID):
        self.session = session
        self.tenant_id = tenant_id

    # ── Warehouses ───────────────────────────────────────
    async def get_warehouse(self, warehouse_id: UUID) -> Warehouse | None:
        stmt = select(Warehouse).where(Warehouse.id == warehouse_id, Warehouse.tenant_id == self.tenant_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_warehouse_by_code(self, code: str) -> Warehouse | None:
        stmt = select(Warehouse).where(Warehouse.code == code, Warehouse.tenant_id == self.tenant_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_warehouses(self, *, active_only: bool = True) -> list[Warehouse]:
        conds = [Warehouse.tenant_id == self.tenant_id]
        if active_only:
            conds.append(Warehouse.is_active.is_(True))
        stmt = select(Warehouse).where(and_(*conds)).order_by(Warehouse.code)
        return list((await self.session.execute(stmt)).scalars().all())

    async def add_warehouse(self, warehouse: Warehouse) -> Warehouse:
        self.session.add(warehouse)
        await self.session.flush()
        return warehouse

    async def clear_default_warehouse(self) -> None:
        """Used when promoting a new default — flips every other tenant
        warehouse's is_default to False so only one ever holds the flag."""
        from sqlalchemy import update

        await self.session.execute(
            update(Warehouse).where(Warehouse.tenant_id == self.tenant_id).values(is_default=False)
        )

    # ── Items ────────────────────────────────────────────
    async def get_item(self, item_id: UUID) -> Item | None:
        stmt = select(Item).where(Item.id == item_id, Item.tenant_id == self.tenant_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_item_by_sku(self, sku: str) -> Item | None:
        stmt = select(Item).where(Item.sku == sku, Item.tenant_id == self.tenant_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_items(self, *, active_only: bool = True, type_: str | None = None) -> list[Item]:
        conds = [Item.tenant_id == self.tenant_id]
        if active_only:
            conds.append(Item.is_active.is_(True))
        if type_:
            conds.append(Item.type == type_)
        stmt = select(Item).where(and_(*conds)).order_by(Item.sku)
        return list((await self.session.execute(stmt)).scalars().all())

    async def add_item(self, item: Item) -> Item:
        self.session.add(item)
        await self.session.flush()
        return item

    # ── Stock balances ───────────────────────────────────
    async def get_balance(self, item_id: UUID, warehouse_id: UUID) -> StockBalance | None:
        stmt = select(StockBalance).where(
            StockBalance.tenant_id == self.tenant_id,
            StockBalance.item_id == item_id,
            StockBalance.warehouse_id == warehouse_id,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_balances(
        self, *, item_id: UUID | None = None, warehouse_id: UUID | None = None
    ) -> list[StockBalance]:
        conds = [StockBalance.tenant_id == self.tenant_id]
        if item_id:
            conds.append(StockBalance.item_id == item_id)
        if warehouse_id:
            conds.append(StockBalance.warehouse_id == warehouse_id)
        stmt = select(StockBalance).where(and_(*conds))
        return list((await self.session.execute(stmt)).scalars().all())

    async def upsert_balance(self, item_id: UUID, warehouse_id: UUID) -> StockBalance:
        bal = await self.get_balance(item_id, warehouse_id)
        if bal is None:
            from decimal import Decimal

            bal = StockBalance(
                tenant_id=self.tenant_id,
                item_id=item_id,
                warehouse_id=warehouse_id,
                on_hand_qty=Decimal("0"),
                avg_cost=Decimal("0"),
            )
            self.session.add(bal)
            await self.session.flush()
        return bal

    # ── Stock movements ──────────────────────────────────
    async def add_movement(self, movement: StockMovement) -> StockMovement:
        self.session.add(movement)
        await self.session.flush()
        return movement

    async def list_movements_for_source(self, source: str, source_id: UUID) -> list[StockMovement]:
        """All stock movements created by a specific source document
        (e.g. a sales/purchase invoice). Used by void to find what to
        reverse."""
        stmt = select(StockMovement).where(
            StockMovement.tenant_id == self.tenant_id,
            StockMovement.source == source,
            StockMovement.source_id == source_id,
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_movements(
        self,
        *,
        item_id: UUID | None = None,
        warehouse_id: UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[StockMovement]:
        conds = [StockMovement.tenant_id == self.tenant_id]
        if item_id:
            conds.append(StockMovement.item_id == item_id)
        if warehouse_id:
            conds.append(StockMovement.warehouse_id == warehouse_id)
        stmt = (
            select(StockMovement)
            .where(and_(*conds))
            .order_by(StockMovement.movement_date.desc(), StockMovement.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def aggregate_balances_by_item(self) -> list[tuple[UUID, "Decimal", "Decimal"]]:  # noqa: F821
        """Sum on_hand and weighted-avg cost per item across warehouses,
        for the stock-valuation report.

        Returns [(item_id, total_qty, weighted_avg_cost)].
        """
        from decimal import Decimal

        stmt = (
            select(
                StockBalance.item_id,
                func.coalesce(func.sum(StockBalance.on_hand_qty), 0).label("qty"),
                func.coalesce(func.sum(StockBalance.on_hand_qty * StockBalance.avg_cost), 0).label("value"),
            )
            .where(StockBalance.tenant_id == self.tenant_id)
            .group_by(StockBalance.item_id)
        )
        rows = (await self.session.execute(stmt)).all()
        out = []
        for row in rows:
            qty = Decimal(row.qty)
            value = Decimal(row.value)
            avg = (value / qty) if qty != 0 else Decimal("0")
            out.append((row.item_id, qty, avg))
        return out

    # ── Cost layers (FIFO/LIFO) ──────────────────────────
    async def add_cost_layer(self, layer: StockCostLayer) -> StockCostLayer:
        self.session.add(layer)
        await self.session.flush()
        return layer

    async def consumable_layers(
        self, item_id: UUID, warehouse_id: UUID, *, lifo: bool
    ) -> list[StockCostLayer]:
        """Layers with remaining_qty > 0, ordered for consumption.
        FIFO → oldest first (received_at ASC); LIFO → newest first."""
        order = StockCostLayer.received_at.desc() if lifo else StockCostLayer.received_at.asc()
        tiebreak = StockCostLayer.id.desc() if lifo else StockCostLayer.id.asc()
        stmt = (
            select(StockCostLayer)
            .where(
                StockCostLayer.tenant_id == self.tenant_id,
                StockCostLayer.item_id == item_id,
                StockCostLayer.warehouse_id == warehouse_id,
                StockCostLayer.is_exhausted.is_(False),
            )
            .order_by(order, tiebreak)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_open_balances_with_avg(self) -> list[StockBalance]:
        """All non-zero balances, used to seed opening cost layers when
        a tenant switches from `avg` to FIFO/LIFO."""
        stmt = select(StockBalance).where(
            StockBalance.tenant_id == self.tenant_id,
            StockBalance.on_hand_qty > 0,
        )
        return list((await self.session.execute(stmt)).scalars().all())

"""Inventory data access — tenant-scoped."""

from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.inventory.models import (
    Item,
    StockBalance,
    StockCostLayer,
    StockMovement,
    StockTransfer,
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

    async def last_movement_before(
        self, item_id: UUID, warehouse_id: UUID, before_date
    ) -> StockMovement | None:
        """Most recent movement strictly before `before_date` for the
        given (item, warehouse). Used to seed the opening balance of
        a stock-card report — the qty_after / avg_cost_after of this
        movement IS the opening state at date_from."""
        stmt = (
            select(StockMovement)
            .where(
                StockMovement.tenant_id == self.tenant_id,
                StockMovement.item_id == item_id,
                StockMovement.warehouse_id == warehouse_id,
                StockMovement.movement_date < before_date,
            )
            .order_by(
                StockMovement.movement_date.desc(),
                StockMovement.created_at.desc(),
            )
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def movements_in_range(
        self,
        item_id: UUID,
        warehouse_id: UUID,
        *,
        date_from=None,
        date_to=None,
    ) -> list[StockMovement]:
        """Per-(item, warehouse) movements in [date_from, date_to],
        ordered chronologically. Either bound is optional."""
        conds = [
            StockMovement.tenant_id == self.tenant_id,
            StockMovement.item_id == item_id,
            StockMovement.warehouse_id == warehouse_id,
        ]
        if date_from is not None:
            conds.append(StockMovement.movement_date >= date_from)
        if date_to is not None:
            conds.append(StockMovement.movement_date <= date_to)
        stmt = (
            select(StockMovement)
            .where(and_(*conds))
            .order_by(StockMovement.movement_date, StockMovement.created_at)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_layers_for_item(
        self,
        item_id: UUID,
        *,
        warehouse_id: UUID | None = None,
        include_exhausted: bool = False,
    ) -> list[StockCostLayer]:
        """Cost-layer drill-down for one item.

        Default: only non-exhausted layers (those currently
        contributing to on-hand value). `include_exhausted=True`
        returns the full history. Always ordered by received_at ASC
        for stable presentation regardless of consumption order.
        """
        conds = [
            StockCostLayer.tenant_id == self.tenant_id,
            StockCostLayer.item_id == item_id,
        ]
        if warehouse_id is not None:
            conds.append(StockCostLayer.warehouse_id == warehouse_id)
        if not include_exhausted:
            conds.append(StockCostLayer.is_exhausted.is_(False))
        stmt = (
            select(StockCostLayer).where(and_(*conds)).order_by(StockCostLayer.received_at, StockCostLayer.id)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    # ── Stock transfers ──────────────────────────────────
    async def add_transfer(self, transfer: StockTransfer) -> StockTransfer:
        self.session.add(transfer)
        await self.session.flush()
        return transfer

    async def get_transfer(self, transfer_id: UUID) -> StockTransfer | None:
        stmt = (
            select(StockTransfer)
            .options(selectinload(StockTransfer.lines))
            .where(
                StockTransfer.id == transfer_id,
                StockTransfer.tenant_id == self.tenant_id,
            )
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_transfers(
        self, *, status: str | None = None, limit: int = 100, offset: int = 0
    ) -> list[StockTransfer]:
        conds = [StockTransfer.tenant_id == self.tenant_id]
        if status:
            conds.append(StockTransfer.status == status)
        stmt = (
            select(StockTransfer)
            .options(selectinload(StockTransfer.lines))
            .where(and_(*conds))
            .order_by(StockTransfer.transfer_date.desc(), StockTransfer.transfer_no.desc())
            .limit(limit)
            .offset(offset)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def next_transfer_no(self, year: int) -> str:
        prefix = f"TR-{year}-"
        stmt = select(func.count(StockTransfer.id)).where(
            StockTransfer.tenant_id == self.tenant_id,
            StockTransfer.transfer_no.like(f"{prefix}%"),
        )
        count = (await self.session.execute(stmt)).scalar_one() or 0
        return f"{prefix}{count + 1:05d}"

    # ── Reorder report ───────────────────────────────────
    async def reorder_items(
        self, *, warehouse_id: UUID | None = None
    ) -> list[tuple[Item, "Decimal", "Decimal"]]:  # noqa: F821
        """Items whose total on-hand is below min_stock > 0.

        Returns [(item, total_on_hand_qty, weighted_avg_cost)].
        Aggregates across all warehouses unless warehouse_id is given.
        Only stock-type, active items with min_stock > 0 are included.
        """
        from decimal import Decimal

        conds = [
            StockBalance.tenant_id == self.tenant_id,
        ]
        if warehouse_id:
            conds.append(StockBalance.warehouse_id == warehouse_id)

        # Sum qty and weighted value per item
        bal_sub = (
            select(
                StockBalance.item_id.label("item_id"),
                func.coalesce(func.sum(StockBalance.on_hand_qty), 0).label("total_qty"),
                func.coalesce(
                    func.sum(StockBalance.on_hand_qty * StockBalance.avg_cost), 0
                ).label("total_value"),
            )
            .where(and_(*conds))
            .group_by(StockBalance.item_id)
            .subquery()
        )

        stmt = (
            select(
                Item,
                func.coalesce(bal_sub.c.total_qty, 0).label("total_qty"),
                func.coalesce(bal_sub.c.total_value, 0).label("total_value"),
            )
            .outerjoin(bal_sub, bal_sub.c.item_id == Item.id)
            .where(
                Item.tenant_id == self.tenant_id,
                Item.type == "stock",
                Item.is_active.is_(True),
                Item.min_stock > 0,
                # on_hand < min_stock  (coalesce handles items with no balance row)
                func.coalesce(bal_sub.c.total_qty, 0) < Item.min_stock,
            )
            .order_by(Item.sku)
        )

        out = []
        for row in (await self.session.execute(stmt)).all():
            qty = Decimal(row.total_qty)
            value = Decimal(row.total_value)
            avg = (value / qty) if qty > 0 else Decimal("0")
            out.append((row.Item, qty, avg))
        return out

    # ── Slow-moving report ───────────────────────────────
    async def slow_moving_items(
        self,
        *,
        cutoff_date,   # movements on or after this date count as "recent"
        warehouse_id: UUID | None = None,
    ) -> list[tuple[StockBalance, "date | None", "Decimal"]]:  # noqa: F821
        """Per-(item, warehouse) rows where on_hand_qty > 0 and the item
        had no outflow (direction='out'|'adjust_out') on or after
        `cutoff_date`.

        Returns [(balance, last_outflow_date_or_None, period_out_qty)].
        `period_out_qty` is total outflow qty from cutoff_date onwards
        (will be 0 for truly slow items, but > 0 is possible if outflow
        happened just after cutoff and balance is still > 0).

        Actually we return ALL (item,warehouse) pairs with stock > 0,
        along with their last_outflow_date and period_out_qty, and let
        the caller apply the threshold filter so it can compute
        days_since_last_outflow cleanly.
        """
        from decimal import Decimal

        bal_conds = [
            StockBalance.tenant_id == self.tenant_id,
            StockBalance.on_hand_qty > 0,
        ]
        if warehouse_id:
            bal_conds.append(StockBalance.warehouse_id == warehouse_id)

        # Subquery: per (item, warehouse) — last outflow date + period qty
        mv_sub = (
            select(
                StockMovement.item_id.label("item_id"),
                StockMovement.warehouse_id.label("warehouse_id"),
                func.max(
                    func.case(
                        (
                            StockMovement.direction.in_(["out", "adjust_out"]),
                            StockMovement.movement_date,
                        ),
                        else_=None,
                    )
                ).label("last_outflow_date"),
                func.coalesce(
                    func.sum(
                        func.case(
                            (
                                and_(
                                    StockMovement.direction.in_(["out", "adjust_out"]),
                                    StockMovement.movement_date >= cutoff_date,
                                ),
                                StockMovement.qty,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("period_out_qty"),
            )
            .where(StockMovement.tenant_id == self.tenant_id)
            .group_by(StockMovement.item_id, StockMovement.warehouse_id)
            .subquery()
        )

        stmt = (
            select(
                StockBalance,
                mv_sub.c.last_outflow_date,
                func.coalesce(mv_sub.c.period_out_qty, 0).label("period_out_qty"),
            )
            .outerjoin(
                mv_sub,
                and_(
                    mv_sub.c.item_id == StockBalance.item_id,
                    mv_sub.c.warehouse_id == StockBalance.warehouse_id,
                ),
            )
            .where(and_(*bal_conds))
            .order_by(StockBalance.item_id, StockBalance.warehouse_id)
        )

        out = []
        for row in (await self.session.execute(stmt)).all():
            out.append((row.StockBalance, row.last_outflow_date, Decimal(row.period_out_qty)))
        return out

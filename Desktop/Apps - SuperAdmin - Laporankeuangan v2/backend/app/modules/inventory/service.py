"""Inventory business logic — pluggable costing method.

Per-tenant `costing_method` selects between:
- 'avg' (weighted average — default):
    new_avg = (old_qty × old_avg + in_qty × in_unit_cost) / (old_qty + in_qty)
    outflows valued at current avg_cost.
- 'fifo' (first-in first-out): each stock-in creates a cost layer.
    Outflows consume layers in received_at ASC order. Movement's
    unit_cost is the blended average of consumed layer costs.
- 'lifo' (last-in first-out): same layer mechanic, consume newest
    layers first.

For FIFO/LIFO the StockBalance.avg_cost field is kept in sync as the
qty-weighted blended cost of remaining layers — that way valuation
reports work uniformly across all three methods.
"""

from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.modules.identity.models import Tenant
from app.modules.inventory.models import (
    Item,
    StockCostLayer,
    StockMovement,
    StockTransfer,
    StockTransferLine,
    Warehouse,
)
from app.modules.inventory.repository import InventoryRepository
from app.modules.inventory.schemas import (
    ItemCreate,
    ItemUpdate,
    StockMovementCreate,
    StockTransferCreate,
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

    async def _get_costing_method(self) -> str:
        """Cached fetch of the tenant's costing_method per service instance."""
        if not hasattr(self, "_costing_method_cache"):
            stmt = select(Tenant.costing_method).where(Tenant.id == self.tenant_id)
            self._costing_method_cache = (await self.session.execute(stmt)).scalar_one()
        return self._costing_method_cache

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
        method = await self._get_costing_method()

        qty = _q4(qty)
        if qty <= 0:
            raise ValidationError("Movement qty must be positive")

        # ── Pre-flush the StockMovement row WITHOUT cost yet so layer
        # rows can FK to it. We'll fill in unit_cost / total_cost /
        # qty_after / avg_cost_after right before the final flush.
        movement = StockMovement(
            tenant_id=self.tenant_id,
            item_id=item.id,
            warehouse_id=warehouse.id,
            movement_date=movement_date,
            direction=direction,
            qty=qty,
            unit_cost=Decimal("0"),  # will be set below
            total_cost=Decimal("0"),
            source=source,
            source_id=source_id,
            notes=notes,
            qty_after=Decimal("0"),
            avg_cost_after=Decimal("0"),
            created_by=self.user_id,
        )

        if direction in ("in", "adjust_in"):
            applied_unit_cost = _q4(unit_cost)
            old_qty = bal.on_hand_qty
            new_qty = _q4(old_qty + qty)
            # Weighted-average bookkeeping is kept up to date for ALL
            # methods so valuation reports are uniform.
            if new_qty > 0:
                bal.avg_cost = _q4((old_qty * bal.avg_cost + qty * applied_unit_cost) / new_qty)
            else:
                bal.avg_cost = applied_unit_cost
            bal.on_hand_qty = new_qty
            total_cost = _q2(qty * applied_unit_cost)

            # FIFO/LIFO: also create a cost layer so future outflows can
            # consume in receipt order
            if method in ("fifo", "lifo"):
                await self.repo.add_movement(movement)  # need movement.id first
                self.session.add(
                    StockCostLayer(
                        tenant_id=self.tenant_id,
                        item_id=item.id,
                        warehouse_id=warehouse.id,
                        source_movement_id=movement.id,
                        original_qty=qty,
                        remaining_qty=qty,
                        unit_cost=applied_unit_cost,
                    )
                )
            else:
                await self.repo.add_movement(movement)

        elif direction in ("out", "adjust_out"):
            if bal.on_hand_qty < qty:
                raise ValidationError(f"Insufficient stock: on hand {bal.on_hand_qty} < requested {qty}")

            if method == "avg":
                applied_unit_cost = _q4(bal.avg_cost)
                total_cost = _q2(qty * applied_unit_cost)
                bal.on_hand_qty = _q4(bal.on_hand_qty - qty)
                if bal.on_hand_qty == 0:
                    bal.avg_cost = Decimal("0")
                await self.repo.add_movement(movement)
            else:
                # FIFO/LIFO: walk layers and consume oldest/newest first
                layers = await self.repo.consumable_layers(item.id, warehouse.id, lifo=(method == "lifo"))
                remaining_to_take = qty
                consumed_value = Decimal("0")
                for layer in layers:
                    if remaining_to_take <= 0:
                        break
                    take = min(layer.remaining_qty, remaining_to_take)
                    consumed_value += _q4(take * layer.unit_cost)
                    layer.remaining_qty = _q4(layer.remaining_qty - take)
                    if layer.remaining_qty == 0:
                        layer.is_exhausted = True
                    remaining_to_take = _q4(remaining_to_take - take)

                if remaining_to_take > 0:
                    # Defensive — would mean layers and balance disagree
                    raise ValidationError(
                        "Cost layers do not cover the on-hand qty; data integrity issue — contact support"
                    )
                applied_unit_cost = _q4(consumed_value / qty) if qty != 0 else Decimal("0")
                total_cost = _q2(consumed_value)
                bal.on_hand_qty = _q4(bal.on_hand_qty - qty)
                # Refresh avg_cost from remaining layers (qty-weighted)
                bal.avg_cost = await self._weighted_avg_from_layers(item.id, warehouse.id)
                await self.repo.add_movement(movement)
        else:
            raise ValidationError(f"Unknown direction '{direction}'")

        movement.unit_cost = applied_unit_cost
        movement.total_cost = total_cost
        movement.qty_after = bal.on_hand_qty
        movement.avg_cost_after = bal.avg_cost
        await self.session.flush()
        return movement

    async def _weighted_avg_from_layers(self, item_id: UUID, warehouse_id: UUID) -> Decimal:
        """Compute the qty-weighted blended cost of remaining FIFO/LIFO
        layers for a single (item, warehouse). Returns 0 if no remaining
        layers — caller should keep on_hand_qty consistent."""
        layers = await self.repo.consumable_layers(item_id, warehouse_id, lifo=False)
        total_qty = Decimal("0")
        total_value = Decimal("0")
        for la in layers:
            total_qty += la.remaining_qty
            total_value += la.remaining_qty * la.unit_cost
        if total_qty == 0:
            return Decimal("0")
        return _q4(total_value / total_qty)

    # ─── Costing-method switch ──────────────────────────
    async def set_costing_method(self, *, method: str, seed_opening_layers: bool = True) -> str:
        """Set the tenant's costing method.

        - 'avg' → 'fifo' or 'lifo': optionally seed one cost layer per
          existing balance (qty=on_hand, unit_cost=avg_cost) so that
          subsequent outflows have something to consume.
        - 'fifo' ↔ 'lifo': layers preserved; only consumption order
          changes for future outflows.
        - 'fifo'/'lifo' → 'avg': layers become inert (kept for history);
          on_hand_qty + avg_cost on the balance keep working.
        """
        if method not in ("avg", "fifo", "lifo"):
            raise ValidationError(f"costing_method must be one of avg/fifo/lifo (got '{method}')")
        tenant = await self.session.get(Tenant, self.tenant_id)
        if tenant is None:
            raise NotFoundError("Tenant not found")
        previous = tenant.costing_method
        if previous == method:
            return method  # no-op

        # Seed opening layers when going avg → fifo/lifo
        if previous == "avg" and method in ("fifo", "lifo") and seed_opening_layers:
            balances = await self.repo.list_open_balances_with_avg()
            for bal in balances:
                self.session.add(
                    StockCostLayer(
                        tenant_id=self.tenant_id,
                        item_id=bal.item_id,
                        warehouse_id=bal.warehouse_id,
                        source_movement_id=None,  # opening, no movement
                        original_qty=bal.on_hand_qty,
                        remaining_qty=bal.on_hand_qty,
                        unit_cost=bal.avg_cost,
                    )
                )

        tenant.costing_method = method
        # Bust the cache so subsequent posts in this session pick up
        # the new method
        if hasattr(self, "_costing_method_cache"):
            del self._costing_method_cache
        await self.session.flush()
        return method

    # ─── Stock transfers ────────────────────────────────
    async def create_transfer(self, payload: StockTransferCreate) -> StockTransfer:
        """Atomic inter-warehouse move: one stock-out from source +
        one stock-in into destination per line, in the same DB
        transaction. The IN uses the OUT's resolved unit_cost so cost
        crosses warehouses unchanged. No GL impact (Inventory account
        net-zero)."""
        await assert_period_open(self.session, self.tenant_id, payload.transfer_date)

        if payload.source_warehouse_id == payload.destination_warehouse_id:
            raise ValidationError("Source and destination warehouses must be different")

        src = await self.repo.get_warehouse(payload.source_warehouse_id)
        if not src:
            raise ValidationError("Source warehouse not found in this tenant")
        if not src.is_active:
            raise ValidationError("Source warehouse is inactive")

        dst = await self.repo.get_warehouse(payload.destination_warehouse_id)
        if not dst:
            raise ValidationError("Destination warehouse not found in this tenant")
        if not dst.is_active:
            raise ValidationError("Destination warehouse is inactive")

        transfer_no = payload.transfer_no or await self.repo.next_transfer_no(payload.transfer_date.year)

        transfer = StockTransfer(
            tenant_id=self.tenant_id,
            transfer_no=transfer_no,
            transfer_date=payload.transfer_date,
            source_warehouse_id=src.id,
            destination_warehouse_id=dst.id,
            status="posted",
            notes=payload.notes,
            created_by=self.user_id,
        )
        await self.repo.add_transfer(transfer)

        for idx, line in enumerate(payload.lines, start=1):
            item = await self.repo.get_item(line.item_id)
            if not item:
                raise ValidationError(f"Line {idx}: item {line.item_id} not found")
            if item.type != "stock":
                raise ValidationError(f"Line {idx}: only stock-type items can be transferred")
            if not item.is_active:
                raise ValidationError(f"Line {idx}: item {item.sku} is inactive")

            # OUT from source — service applies the costing method
            out_movement = await self._post_movement_inner(
                item=item,
                warehouse=src,
                movement_date=payload.transfer_date,
                direction="out",
                qty=line.qty,
                unit_cost=Decimal("0"),  # ignored on outflow
                notes=line.notes or f"Transfer {transfer_no} → {dst.code}",
                source="stock_transfer",
                source_id=transfer.id,
            )
            # IN at destination at the same blended unit_cost — preserves
            # cost basis across warehouses
            await self._post_movement_inner(
                item=item,
                warehouse=dst,
                movement_date=payload.transfer_date,
                direction="in",
                qty=line.qty,
                unit_cost=out_movement.unit_cost,
                notes=line.notes or f"Transfer {transfer_no} ← {src.code}",
                source="stock_transfer",
                source_id=transfer.id,
            )

            self.session.add(
                StockTransferLine(
                    tenant_id=self.tenant_id,
                    transfer_id=transfer.id,
                    line_no=idx,
                    item_id=item.id,
                    qty=_q4(line.qty),
                    unit_cost=out_movement.unit_cost,
                    notes=line.notes,
                )
            )

        await self.session.flush()
        return transfer

    async def void_transfer(self, transfer_id: UUID, reason: str) -> StockTransfer:
        transfer = await self.repo.get_transfer(transfer_id)
        if not transfer:
            raise NotFoundError("Transfer not found")
        if transfer.status == "void":
            raise ConflictError("Transfer already voided")
        await assert_period_open(self.session, self.tenant_id, transfer.transfer_date)

        # Reverse direction on each leg: source got an OUT → void with IN
        # at the same unit_cost. Destination got an IN → void with OUT.
        # Will raise insufficient-stock if the destination has already
        # consumed the transferred units; that's correct.
        movements = await self.repo.list_movements_for_source("stock_transfer", transfer.id)
        for m in movements:
            new_dir = "in" if m.direction == "out" else "out"
            item = await self.repo.get_item(m.item_id)
            wh = await self.repo.get_warehouse(m.warehouse_id)
            if item is None or wh is None:
                continue
            await self._post_movement_inner(
                item=item,
                warehouse=wh,
                movement_date=transfer.transfer_date,
                direction=new_dir,
                qty=m.qty,
                unit_cost=m.unit_cost,
                notes=f"Void of transfer {transfer.transfer_no}",
                source="void_stock_transfer",
                source_id=transfer.id,
            )

        from datetime import UTC
        from datetime import datetime as _datetime

        transfer.status = "void"
        transfer.voided_by = self.user_id
        transfer.voided_at = _datetime.now(UTC)
        transfer.void_reason = reason
        await self.session.flush()
        return transfer

    # ── Stock card report ────────────────────────────────
    async def stock_card_report(
        self,
        item_id: UUID,
        warehouse_id: UUID,
        *,
        date_from=None,
        date_to=None,
    ):
        """Chronological stock card for one (item, warehouse) combination.

        Returns a StockCardReport with opening/closing balances and one
        line per movement in [date_from, date_to].  The opening balance
        is derived from the most recent movement *before* date_from (its
        qty_after / avg_cost_after snapshot).  If date_from is None the
        opening balance is always 0 / 0 (full history from the start).
        """
        from app.modules.inventory.schemas import StockCardLine, StockCardReport

        item = await self.repo.get_item(item_id)
        if not item:
            raise NotFoundError("Item not found")

        warehouse = await self.repo.get_warehouse(warehouse_id)
        if not warehouse:
            raise NotFoundError("Warehouse not found")

        # ── Opening balance ───────────────────────────────────────────
        opening_qty = Decimal("0")
        opening_avg_cost = Decimal("0")

        if date_from is not None:
            prev = await self.repo.last_movement_before(item_id, warehouse_id, date_from)
            if prev is not None:
                opening_qty = prev.qty_after
                opening_avg_cost = prev.avg_cost_after

        opening_value = _q2(opening_qty * opening_avg_cost)

        # ── Period movements ──────────────────────────────────────────
        movements = await self.repo.movements_in_range(
            item_id, warehouse_id, date_from=date_from, date_to=date_to
        )

        lines: list[StockCardLine] = []
        period_in_qty = Decimal("0")
        period_out_qty = Decimal("0")
        period_in_value = Decimal("0")
        period_out_value = Decimal("0")

        for m in movements:
            value_after = _q2(m.qty_after * m.avg_cost_after)
            lines.append(
                StockCardLine(
                    movement_id=m.id,
                    movement_date=m.movement_date,
                    direction=m.direction,
                    qty=m.qty,
                    unit_cost=m.unit_cost,
                    total_cost=m.total_cost,
                    source=m.source,
                    source_id=m.source_id,
                    notes=m.notes,
                    qty_after=m.qty_after,
                    avg_cost_after=m.avg_cost_after,
                    value_after=value_after,
                )
            )
            if m.direction in ("in", "adjust_in"):
                period_in_qty += m.qty
                period_in_value += m.total_cost
            else:
                period_out_qty += m.qty
                period_out_value += m.total_cost

        # ── Closing balance ───────────────────────────────────────────
        if lines:
            closing_qty = lines[-1].qty_after
            closing_avg_cost = lines[-1].avg_cost_after
        else:
            closing_qty = opening_qty
            closing_avg_cost = opening_avg_cost

        closing_value = _q2(closing_qty * closing_avg_cost)

        return StockCardReport(
            item_id=item.id,
            sku=item.sku,
            name=item.name,
            unit=item.unit,
            warehouse_id=warehouse.id,
            warehouse_code=warehouse.code,
            date_from=date_from,
            date_to=date_to,
            opening_qty=opening_qty,
            opening_avg_cost=opening_avg_cost,
            opening_value=opening_value,
            lines=lines,
            closing_qty=closing_qty,
            closing_avg_cost=closing_avg_cost,
            closing_value=closing_value,
            period_in_qty=period_in_qty,
            period_out_qty=period_out_qty,
            period_in_value=period_in_value,
            period_out_value=period_out_value,
        )

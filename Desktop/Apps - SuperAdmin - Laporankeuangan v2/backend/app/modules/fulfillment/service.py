"""DeliveryOrder (and later: GoodsReceipt, RMA) lifecycle services.

Posting a DO:
  1. Validate SO is confirmed and qty constraints (qty_delivered ≤ qty_ordered − already_delivered)
  2. For each line: post stock-out via InventoryService with source='delivery_order'
  3. Aggregate cost from stock-out (avg_cost_after or unit_cost) → post journal
       Dr COGS  (total_cost)
       Cr Inventory (total_cost)
  4. Update SO line qty_delivered counters
  5. Recompute SO status (partially_delivered / fulfilled)
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.modules.accounting.repository import AccountingRepository
from app.modules.accounting.service import AccountingService
from app.modules.fulfillment.models import DeliveryOrder, DeliveryOrderLine
from app.modules.fulfillment.repository import FulfillmentRepository
from app.modules.fulfillment.schemas import DeliveryOrderCreate
from app.modules.inventory.repository import InventoryRepository
from app.modules.inventory.schemas import StockMovementCreate
from app.modules.inventory.service import InventoryService
from app.modules.periods.service import assert_period_open
from app.modules.sales.repository import SalesRepository
from app.modules.sales.service import SalesOrderService


CENT = Decimal("0.01")


class DeliveryOrderService:
    def __init__(self, session: AsyncSession, tenant_id: UUID, user_id: UUID):
        self.session = session
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.repo = FulfillmentRepository(session, tenant_id)
        self.sales_repo = SalesRepository(session, tenant_id)
        self.inv_repo = InventoryRepository(session, tenant_id)
        self.inv_svc = InventoryService(session, tenant_id, user_id)
        self.acct_repo = AccountingRepository(session, tenant_id)
        self.acct_svc = AccountingService(session, tenant_id, user_id)
        self.so_svc = SalesOrderService(session, tenant_id, user_id)

    # ─── Create draft DO ───────────────────────────────────
    async def create_do(self, payload: DeliveryOrderCreate) -> DeliveryOrder:
        await assert_period_open(self.session, self.tenant_id, payload.delivery_date)

        so = await self.sales_repo.get_so(payload.so_id)
        if not so:
            raise NotFoundError("Sales order not found")
        if so.status in ("draft", "cancelled"):
            raise ValidationError(
                f"Cannot create DO for SO in status '{so.status}' (must be confirmed/partially_delivered)"
            )

        warehouse = await self.inv_repo.get_warehouse(payload.warehouse_id)
        if not warehouse or not warehouse.is_active:
            raise ValidationError("Warehouse not found or inactive")

        # Validate each line against SO line counters
        so_lines = {ln.id: ln for ln in so.lines}
        line_objs: list[DeliveryOrderLine] = []
        for ln in payload.lines:
            so_line = so_lines.get(ln.so_line_id)
            if not so_line:
                raise ValidationError(f"SO line {ln.so_line_id} not in this SO")
            remaining = (so_line.qty_ordered or Decimal("0")) - (so_line.qty_delivered or Decimal("0"))
            if ln.qty_delivered > remaining:
                raise ValidationError(
                    f"Line for item {so_line.item_id}: qty {ln.qty_delivered} exceeds remaining {remaining}"
                )
            line_objs.append(DeliveryOrderLine(
                so_line_id=so_line.id,
                item_id=so_line.item_id,
                qty_delivered=ln.qty_delivered,
            ))

        do_no = payload.do_no or await self.repo.next_do_no(payload.delivery_date.year)
        do = DeliveryOrder(
            tenant_id=self.tenant_id,
            do_no=do_no,
            delivery_date=payload.delivery_date,
            so_id=so.id,
            warehouse_id=warehouse.id,
            status="draft",
            notes=payload.notes,
            created_by=self.user_id,
        )
        do.lines = line_objs
        return await self.repo.add_do(do)

    # ─── Post DO: stock-out + journal + update SO ─────────
    async def post_do(self, do_id: UUID) -> DeliveryOrder:
        do = await self.repo.get_do(do_id)
        if not do:
            raise NotFoundError("Delivery order not found")
        if do.status == "posted":
            raise ConflictError("DO already posted")
        if do.status == "void":
            raise ValidationError("Voided DO cannot be posted")
        await assert_period_open(self.session, self.tenant_id, do.delivery_date)

        # Get accounting mappings up-front
        cogs_map = await self.acct_repo.get_mapping("cogs")
        inv_map = await self.acct_repo.get_mapping("inventory")
        if not cogs_map or not inv_map:
            raise ValidationError(
                "Account mappings missing: configure 'cogs' and 'inventory' first."
            )

        total_cost = Decimal("0")
        for ln in do.lines:
            mvm = await self.inv_svc.post_movement(
                StockMovementCreate(
                    item_id=ln.item_id,
                    warehouse_id=do.warehouse_id,
                    movement_date=do.delivery_date,
                    direction="out",
                    qty=ln.qty_delivered,
                    unit_cost=Decimal("0"),
                    notes=f"DO {do.do_no} line",
                ),
                source="delivery_order",
                source_id=do.id,
            )
            ln.unit_cost = mvm.unit_cost
            total_cost += (mvm.qty * mvm.unit_cost).quantize(CENT)

        # Journal: Dr COGS / Cr Inventory at total_cost (zero if free samples)
        entry = None
        if total_cost > 0:
            entry = await self.acct_svc.post_system_journal(
                entry_date=do.delivery_date,
                description=f"Delivery {do.do_no}",
                lines=[
                    (cogs_map.account_id, total_cost, Decimal("0")),
                    (inv_map.account_id, Decimal("0"), total_cost),
                ],
                source="delivery_order",
                source_id=do.id,
            )
            do.journal_entry_id = entry.id

        do.status = "posted"
        do.posted_at = datetime.now(UTC)
        do.posted_by = self.user_id

        # Update SO line counters
        for ln in do.lines:
            so_line = await self.sales_repo.get_so_line(ln.so_line_id)
            if so_line:
                so_line.qty_delivered = (so_line.qty_delivered or Decimal("0")) + ln.qty_delivered

        await self.session.flush()

        # Recompute SO status
        await self.so_svc.recompute_fulfillment_status(do.so_id)

        # Publish event
        try:
            from app.core.events import publish
            await publish("delivery_order.posted", {
                "tenant_id": str(self.tenant_id),
                "do_id": str(do.id),
                "do_no": do.do_no,
                "so_id": str(do.so_id),
                "total_cost": float(total_cost),
            })
        except Exception:
            pass
        return do

    # ─── Void DO: reverse stock movements + reverse journal ─
    async def void_do(self, do_id: UUID, reason: str) -> DeliveryOrder:
        do = await self.repo.get_do(do_id)
        if not do:
            raise NotFoundError("Delivery order not found")
        if do.status == "void":
            raise ConflictError("DO already void")
        await assert_period_open(self.session, self.tenant_id, do.delivery_date)

        if do.status == "posted":
            # Reverse stock movements (re-stock at same unit_cost)
            for ln in do.lines:
                await self.inv_svc.post_movement(
                    StockMovementCreate(
                        item_id=ln.item_id,
                        warehouse_id=do.warehouse_id,
                        movement_date=do.delivery_date,
                        direction="in",
                        qty=ln.qty_delivered,
                        unit_cost=ln.unit_cost or Decimal("0"),
                        notes=f"Void DO {do.do_no}",
                    ),
                    source="delivery_order_void",
                    source_id=do.id,
                )
            # Void the linked journal
            if do.journal_entry_id:
                await self.acct_svc.void_system_journal(
                    "delivery_order", do.id, f"Voided: {reason}"
                )

        do.status = "void"
        do.voided_at = datetime.now(UTC)
        do.void_reason = reason

        # Revert SO line counters
        for ln in do.lines:
            so_line = await self.sales_repo.get_so_line(ln.so_line_id)
            if so_line:
                so_line.qty_delivered = max(
                    Decimal("0"),
                    (so_line.qty_delivered or Decimal("0")) - ln.qty_delivered,
                )
        await self.session.flush()

        await self.so_svc.recompute_fulfillment_status(do.so_id)

        try:
            from app.core.events import publish
            await publish("delivery_order.voided", {
                "tenant_id": str(self.tenant_id),
                "do_id": str(do.id),
                "do_no": do.do_no,
                "reason": reason,
            })
        except Exception:
            pass
        return do


# ═══════════════════════════════════════════════════════════════════
# Goods Receipt Service
# ═══════════════════════════════════════════════════════════════════

class GoodsReceiptService:
    """GR posting:
    1. Validate PO confirmed, qty constraints
    2. For each line: post stock-in (source='goods_receipt')
    3. Journal: Dr Inventory / Cr GR-clearing  (at total = sum qty × unit_cost)
    4. Update PO line qty_received counters
    5. Recompute PO status
    """

    def __init__(self, session: AsyncSession, tenant_id: UUID, user_id: UUID):
        self.session = session
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.repo = FulfillmentRepository(session, tenant_id)
        from app.modules.purchase.repository import PurchaseRepository
        from app.modules.purchase.service import PurchaseOrderService
        self.purchase_repo = PurchaseRepository(session, tenant_id)
        self.po_svc = PurchaseOrderService(session, tenant_id, user_id)
        self.inv_repo = InventoryRepository(session, tenant_id)
        self.inv_svc = InventoryService(session, tenant_id, user_id)
        self.acct_repo = AccountingRepository(session, tenant_id)
        self.acct_svc = AccountingService(session, tenant_id, user_id)

    async def create_gr(self, payload):
        from app.modules.fulfillment.models import GoodsReceipt, GoodsReceiptLine
        await assert_period_open(self.session, self.tenant_id, payload.receipt_date)

        po = await self.purchase_repo.get_po(payload.po_id)
        if not po:
            raise NotFoundError("Purchase order not found")
        if po.status in ("draft", "cancelled"):
            raise ValidationError(
                f"Cannot create GR for PO in status '{po.status}' (must be confirmed/partially_received)"
            )

        warehouse = await self.inv_repo.get_warehouse(payload.warehouse_id)
        if not warehouse or not warehouse.is_active:
            raise ValidationError("Warehouse not found or inactive")

        po_lines = {ln.id: ln for ln in po.lines}
        line_objs = []
        for ln in payload.lines:
            po_line = po_lines.get(ln.po_line_id)
            if not po_line:
                raise ValidationError(f"PO line {ln.po_line_id} not in this PO")
            remaining = (po_line.qty_ordered or Decimal("0")) - (po_line.qty_received or Decimal("0"))
            if ln.qty_received > remaining:
                raise ValidationError(
                    f"Line for item {po_line.item_id}: qty {ln.qty_received} exceeds remaining {remaining}"
                )
            unit_cost = ln.unit_cost if ln.unit_cost is not None else po_line.unit_price
            line_objs.append(GoodsReceiptLine(
                po_line_id=po_line.id,
                item_id=po_line.item_id,
                qty_received=ln.qty_received,
                unit_cost=unit_cost,
            ))

        gr_no = payload.gr_no or await self.repo.next_gr_no(payload.receipt_date.year)
        gr = GoodsReceipt(
            tenant_id=self.tenant_id,
            gr_no=gr_no,
            receipt_date=payload.receipt_date,
            po_id=po.id,
            warehouse_id=warehouse.id,
            status="draft",
            notes=payload.notes,
            created_by=self.user_id,
        )
        gr.lines = line_objs
        return await self.repo.add_gr(gr)

    async def post_gr(self, gr_id: UUID):
        gr = await self.repo.get_gr(gr_id)
        if not gr:
            raise NotFoundError("Goods receipt not found")
        if gr.status == "posted":
            raise ConflictError("GR already posted")
        if gr.status == "void":
            raise ValidationError("Voided GR cannot be posted")
        await assert_period_open(self.session, self.tenant_id, gr.receipt_date)

        inv_map = await self.acct_repo.get_mapping("inventory")
        gr_clearing_map = await self.acct_repo.get_mapping("gr_clearing")
        if not inv_map or not gr_clearing_map:
            raise ValidationError(
                "Account mappings missing: configure 'inventory' and 'gr_clearing' first."
            )

        total_cost = Decimal("0")
        for ln in gr.lines:
            await self.inv_svc.post_movement(
                StockMovementCreate(
                    item_id=ln.item_id,
                    warehouse_id=gr.warehouse_id,
                    movement_date=gr.receipt_date,
                    direction="in",
                    qty=ln.qty_received,
                    unit_cost=ln.unit_cost,
                    notes=f"GR {gr.gr_no} line",
                ),
                source="goods_receipt",
                source_id=gr.id,
            )
            total_cost += (ln.qty_received * ln.unit_cost).quantize(CENT)

        if total_cost > 0:
            entry = await self.acct_svc.post_system_journal(
                entry_date=gr.receipt_date,
                description=f"Goods Receipt {gr.gr_no}",
                lines=[
                    (inv_map.account_id, total_cost, Decimal("0")),  # Dr Inventory
                    (gr_clearing_map.account_id, Decimal("0"), total_cost),  # Cr GR-clearing
                ],
                source="goods_receipt",
                source_id=gr.id,
            )
            gr.journal_entry_id = entry.id

        gr.status = "posted"
        gr.posted_at = datetime.now(UTC)
        gr.posted_by = self.user_id

        for ln in gr.lines:
            po_line = await self.purchase_repo.get_po_line(ln.po_line_id)
            if po_line:
                po_line.qty_received = (po_line.qty_received or Decimal("0")) + ln.qty_received

        await self.session.flush()
        await self.po_svc.recompute_fulfillment_status(gr.po_id)

        try:
            from app.core.events import publish
            await publish("goods_receipt.posted", {
                "tenant_id": str(self.tenant_id),
                "gr_id": str(gr.id),
                "gr_no": gr.gr_no,
                "po_id": str(gr.po_id),
                "total_cost": float(total_cost),
            })
        except Exception:
            pass
        return gr

    async def void_gr(self, gr_id: UUID, reason: str):
        gr = await self.repo.get_gr(gr_id)
        if not gr:
            raise NotFoundError("Goods receipt not found")
        if gr.status == "void":
            raise ConflictError("GR already void")
        await assert_period_open(self.session, self.tenant_id, gr.receipt_date)

        if gr.status == "posted":
            for ln in gr.lines:
                await self.inv_svc.post_movement(
                    StockMovementCreate(
                        item_id=ln.item_id,
                        warehouse_id=gr.warehouse_id,
                        movement_date=gr.receipt_date,
                        direction="out",
                        qty=ln.qty_received,
                        unit_cost=ln.unit_cost,
                        notes=f"Void GR {gr.gr_no}",
                    ),
                    source="goods_receipt_void",
                    source_id=gr.id,
                )
            if gr.journal_entry_id:
                await self.acct_svc.void_system_journal(
                    "goods_receipt", gr.id, f"Voided: {reason}"
                )

        gr.status = "void"
        gr.voided_at = datetime.now(UTC)
        gr.void_reason = reason

        for ln in gr.lines:
            po_line = await self.purchase_repo.get_po_line(ln.po_line_id)
            if po_line:
                po_line.qty_received = max(
                    Decimal("0"),
                    (po_line.qty_received or Decimal("0")) - ln.qty_received,
                )
        await self.session.flush()
        await self.po_svc.recompute_fulfillment_status(gr.po_id)

        try:
            from app.core.events import publish
            await publish("goods_receipt.voided", {
                "tenant_id": str(self.tenant_id),
                "gr_id": str(gr.id),
                "gr_no": gr.gr_no,
                "reason": reason,
            })
        except Exception:
            pass
        return gr

"""POS business logic.

Each POS order is posted immediately (no draft state).

Journal entry pattern for a paid order
---------------------------------------
Cash sale:
    Dr  Cash / Card / Transfer account    total
        Cr  Sales Revenue                 subtotal
        Cr  Tax Payable                   tax_amount   (if > 0)

COGS (per stock-item line, same entry):
    Dr  COGS                              cogs_total
        Cr  Inventory                     cogs_total

Payment-method → GL mapping keys
----------------------------------
  cash      → cash_default
  card      → pos_card     (falls back to cash_default)
  transfer  → pos_transfer (falls back to cash_default)
  other     → pos_other    (falls back to cash_default)
"""

from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.modules.accounting.repository import AccountingRepository
from app.modules.accounting.service import AccountingService
from app.modules.inventory.repository import InventoryRepository
from app.modules.inventory.service import InventoryService
from app.modules.periods.service import assert_period_open
from app.modules.pos.models import PosOrder, PosOrderLine, PosSession
from app.modules.pos.repository import PosRepository
from app.modules.pos.schemas import (
    PosOrderCreate,
    PosSessionClose,
    PosSessionOpen,
    PosSessionSummary,
)

CENT = Decimal("0.01")
_PAYMENT_MAPPING_KEYS: dict[str, list[str]] = {
    "cash":     ["cash_default"],
    "card":     ["pos_card", "cash_default"],
    "transfer": ["pos_transfer", "cash_default"],
    "other":    ["pos_other", "cash_default"],
}


def _money(v: Decimal) -> Decimal:
    return v.quantize(CENT, rounding=ROUND_HALF_UP)


class PosService:
    def __init__(self, session: AsyncSession, tenant_id: UUID, user_id: UUID):
        self.session = session
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.repo = PosRepository(session, tenant_id)
        self.acct_repo = AccountingRepository(session, tenant_id)
        self.acct_svc = AccountingService(session, tenant_id, user_id)
        self.inv_repo = InventoryRepository(session, tenant_id)
        self.inv_svc = InventoryService(session, tenant_id, user_id)

    # ─── Helpers ──────────────────────────────────────────────────

    async def _resolve_payment_account(self, method: str) -> UUID:
        """Return account_id for the payment method, trying fallback keys."""
        for key in _PAYMENT_MAPPING_KEYS[method]:
            mapping = await self.acct_repo.get_mapping(key)
            if mapping:
                return mapping.account_id
        raise ValidationError(
            f"No account mapping found for payment method '{method}'. "
            "Please configure 'cash_default' in account mappings."
        )

    # ─── Sessions ─────────────────────────────────────────────────

    async def open_session(self, payload: PosSessionOpen) -> PosSession:
        # One open session per cashier at a time
        existing = await self.repo.get_open_session_for_cashier(self.user_id)
        if existing:
            raise ConflictError(
                f"Cashier already has an open session: {existing.session_no}. "
                "Close the current session before opening a new one."
            )
        session_no = await self.repo.next_session_no()
        pos_session = PosSession(
            tenant_id=self.tenant_id,
            session_no=session_no,
            register_name=payload.register_name,
            cashier_id=self.user_id,
            opening_amount=payload.opening_amount,
            notes=payload.notes,
            status="open",
        )
        return await self.repo.add_session(pos_session)

    async def get_session(self, session_id: UUID) -> PosSession:
        s = await self.repo.get_session(session_id)
        if not s:
            raise NotFoundError("POS session not found")
        return s

    async def list_sessions(
        self,
        *,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[PosSession]:
        return await self.repo.list_sessions(status=status, limit=limit, offset=offset)

    async def close_session(self, session_id: UUID, payload: PosSessionClose) -> PosSessionSummary:
        pos_session = await self.get_session(session_id)
        if pos_session.status == "closed":
            raise ConflictError("Session is already closed")

        # Compute expected closing: opening + all cash sales
        payment_totals = await self.repo.session_payment_totals(session_id)
        expected = pos_session.opening_amount + payment_totals["cash"]

        void_count = await self.repo.session_void_count(session_id)

        pos_session.status = "closed"
        pos_session.closing_amount = payload.closing_amount
        pos_session.expected_closing = expected
        pos_session.cash_difference = _money(payload.closing_amount - expected)
        pos_session.closed_at = datetime.now(UTC)
        if payload.notes:
            pos_session.notes = payload.notes
        await self.session.flush()
        await self.session.refresh(pos_session)

        from app.modules.pos.schemas import PosSessionOut

        return PosSessionSummary(
            session=PosSessionOut.model_validate(pos_session),
            total_cash=payment_totals["cash"],
            total_card=payment_totals["card"],
            total_transfer=payment_totals["transfer"],
            total_other=payment_totals["other"],
            order_count=pos_session.total_orders,
            void_count=void_count,
        )

    # ─── Orders ───────────────────────────────────────────────────

    async def create_order(self, payload: PosOrderCreate) -> PosOrder:
        # Validate session
        pos_session = await self.repo.get_session(payload.session_id)
        if not pos_session:
            raise NotFoundError("POS session not found")
        if pos_session.status != "open":
            raise ValidationError("Cannot add orders to a closed session")

        await assert_period_open(self.session, self.tenant_id, payload.order_date)

        # Build order lines, validate inventory
        subtotal = Decimal("0")
        discount_total = Decimal("0")
        tax_total = Decimal("0")
        built_lines: list[dict] = []

        for idx, line_in in enumerate(payload.lines, start=1):
            if line_in.item_id is not None:
                item = await self.inv_repo.get_item(line_in.item_id)
                if not item:
                    raise ValidationError(f"Line {idx}: item {line_in.item_id} not found")
                if item.type == "stock" and line_in.warehouse_id is None:
                    raise ValidationError(
                        f"Line {idx}: stock item '{item.sku}' requires warehouse_id"
                    )
                if line_in.warehouse_id is not None:
                    wh = await self.inv_repo.get_warehouse(line_in.warehouse_id)
                    if not wh:
                        raise ValidationError(
                            f"Line {idx}: warehouse {line_in.warehouse_id} not found"
                        )

            gross = _money(line_in.qty * line_in.unit_price)
            disc_amt = _money(gross * line_in.discount_pct / Decimal("100"))
            line_total = _money(gross - disc_amt)
            tax_amt = _money(line_total * line_in.tax_rate / Decimal("100"))

            subtotal += line_total
            discount_total += disc_amt
            tax_total += tax_amt

            built_lines.append(
                dict(
                    tenant_id=self.tenant_id,
                    line_no=idx,
                    description=line_in.description,
                    qty=line_in.qty,
                    unit_price=line_in.unit_price,
                    discount_pct=line_in.discount_pct,
                    discount_amount=disc_amt,
                    line_total=line_total,
                    tax_rate=line_in.tax_rate,
                    tax_amount=tax_amt,
                    item_id=line_in.item_id,
                    warehouse_id=line_in.warehouse_id,
                )
            )

        total = _money(subtotal + tax_total)

        # Validate amount_paid (must cover the total)
        if payload.amount_paid < total:
            raise ValidationError(
                f"Amount paid ({payload.amount_paid}) is less than order total ({total})"
            )
        change = _money(payload.amount_paid - total)

        order_no = await self.repo.next_order_no(payload.order_date)
        order = PosOrder(
            tenant_id=self.tenant_id,
            session_id=pos_session.id,
            order_no=order_no,
            order_date=payload.order_date,
            customer_name=payload.customer_name,
            subtotal=_money(subtotal),
            discount_amount=_money(discount_total),
            tax_amount=_money(tax_total),
            total=total,
            payment_method=payload.payment_method,
            amount_paid=payload.amount_paid,
            change_amount=change,
            status="paid",
            notes=payload.notes,
            created_by=self.user_id,
        )
        for ld in built_lines:
            order.lines.append(PosOrderLine(**ld))

        order = await self.repo.add_order(order)

        # Post journal + stock movements
        await self._post_order_journal(order, payload.payment_method)

        # Update session totals
        pos_session.total_sales = _money(pos_session.total_sales + total)
        pos_session.total_orders = pos_session.total_orders + 1
        await self.session.flush()

        return order

    async def _post_order_journal(self, order: PosOrder, payment_method: str) -> None:
        """Create journal entry: Dr Payment-Account / Cr Sales [/ Cr Tax] [Dr COGS / Cr Inv]."""
        payment_acc_id = await self._resolve_payment_account(payment_method)
        rev_mapping = await self.acct_repo.get_mapping("sales_revenue")
        if not rev_mapping:
            raise ValidationError("Account mapping 'sales_revenue' is not configured")

        lines: list[tuple[UUID, Decimal, Decimal]] = []
        # Dr Payment account (total including tax)
        lines.append((payment_acc_id, order.total, Decimal("0")))
        # Cr Sales Revenue (subtotal net of discount)
        lines.append((rev_mapping.account_id, Decimal("0"), order.subtotal))
        # Cr Tax Payable (if any tax)
        if order.tax_amount > 0:
            tax_mapping = await self.acct_repo.get_mapping("tax_payable")
            if not tax_mapping:
                raise ValidationError("Account mapping 'tax_payable' is not configured")
            lines.append((tax_mapping.account_id, Decimal("0"), order.tax_amount))

        # COGS + stock-out for each stock-type line
        cogs_total = Decimal("0")
        for ln in order.lines:
            if ln.item_id is None or ln.warehouse_id is None:
                continue
            item = await self.inv_repo.get_item(ln.item_id)
            if item is None or item.type != "stock":
                continue
            wh = await self.inv_repo.get_warehouse(ln.warehouse_id)
            if wh is None:
                continue
            movement = await self.inv_svc._post_movement_inner(
                item=item,
                warehouse=wh,
                movement_date=order.order_date,
                direction="out",
                qty=ln.qty,
                unit_cost=Decimal("0"),  # outflows use avg_cost internally
                notes=f"POS sale {order.order_no} line {ln.line_no}",
                source="pos_order",
                source_id=order.id,
            )
            cogs_total += movement.total_cost

        if cogs_total > 0:
            cogs_mapping = await self.acct_repo.get_mapping("cogs")
            inv_mapping = await self.acct_repo.get_mapping("inventory")
            if not cogs_mapping or not inv_mapping:
                raise ValidationError(
                    "Account mappings 'cogs' and 'inventory' are required for stock-item sales"
                )
            lines.append((cogs_mapping.account_id, cogs_total, Decimal("0")))
            lines.append((inv_mapping.account_id, Decimal("0"), cogs_total))

        entry = await self.acct_svc.post_system_journal(
            entry_date=order.order_date,
            description=f"POS order {order.order_no}",
            reference=order.order_no,
            lines=lines,
            source="pos_order",
            source_id=order.id,
        )
        order.journal_entry_id = entry.id
        await self.session.flush()

    async def void_order(self, order_id: UUID, reason: str) -> PosOrder:
        order = await self.repo.get_order(order_id)
        if not order:
            raise NotFoundError("POS order not found")
        if order.status == "void":
            raise ConflictError("Order is already voided")

        await assert_period_open(self.session, self.tenant_id, order.order_date)

        # Reverse journal entry
        if order.journal_entry_id:
            await self.acct_svc.void_system_journal("pos_order", order.id, f"Voided: {reason}")

        # Reverse stock-out movements
        originals = await self.inv_repo.list_movements_for_source("pos_order", order.id)
        for m in originals:
            if m.direction != "out":
                continue
            item = await self.inv_repo.get_item(m.item_id)
            wh = await self.inv_repo.get_warehouse(m.warehouse_id)
            if item is None or wh is None:
                continue
            await self.inv_svc._post_movement_inner(
                item=item,
                warehouse=wh,
                movement_date=order.order_date,
                direction="in",
                qty=m.qty,
                unit_cost=m.unit_cost,
                notes=f"Void of POS order {order.order_no}",
                source="void_pos_order",
                source_id=order.id,
            )

        # Update session totals
        pos_session = await self.repo.get_session(order.session_id)
        if pos_session and pos_session.status == "open":
            pos_session.total_sales = _money(pos_session.total_sales - order.total)
            pos_session.total_orders = max(0, pos_session.total_orders - 1)

        order.status = "void"
        order.void_reason = reason
        order.voided_by = self.user_id
        order.voided_at = datetime.now(UTC)
        await self.session.flush()
        return order

    async def get_order(self, order_id: UUID) -> PosOrder:
        o = await self.repo.get_order(order_id)
        if not o:
            raise NotFoundError("POS order not found")
        return o

    async def list_orders(
        self,
        *,
        session_id: UUID | None = None,
        order_date=None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[PosOrder]:
        return await self.repo.list_orders(
            session_id=session_id,
            order_date=order_date,
            status=status,
            limit=limit,
            offset=offset,
        )

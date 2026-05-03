"""Sales business logic.

Posting a sales invoice creates a balanced journal entry in the same
DB transaction (atomicity guaranteed by shared AsyncSession).

Journal pattern:
    Dr  Accounts Receivable     (subtotal + tax_amount)
        Cr  Sales Revenue       (subtotal)
        Cr  Tax Payable         (tax_amount, only if > 0)
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
from app.modules.sales.models import Customer, SalesInvoice, SalesInvoiceLine
from app.modules.sales.repository import SalesRepository
from app.modules.sales.schemas import (
    CustomerCreate,
    CustomerUpdate,
    SalesInvoiceCreate,
)

CENT = Decimal("0.01")


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


class SalesService:
    def __init__(self, session: AsyncSession, tenant_id: UUID, user_id: UUID):
        self.session = session
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.repo = SalesRepository(session, tenant_id)
        self.acct_repo = AccountingRepository(session, tenant_id)
        self.acct_svc = AccountingService(session, tenant_id, user_id)
        self.inv_repo = InventoryRepository(session, tenant_id)
        self.inv_svc = InventoryService(session, tenant_id, user_id)

    # ─── Customers ──────────────────────────────────────
    async def create_customer(self, payload: CustomerCreate) -> Customer:
        if await self.repo.get_customer_by_code(payload.code):
            raise ConflictError(f"Customer code '{payload.code}' already exists")
        cust = Customer(tenant_id=self.tenant_id, **payload.model_dump())
        return await self.repo.add_customer(cust)

    async def update_customer(self, customer_id: UUID, payload: CustomerUpdate) -> Customer:
        cust = await self.repo.get_customer(customer_id)
        if not cust:
            raise NotFoundError("Customer not found")
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(cust, field, value)
        await self.session.flush()
        return cust

    # ─── Invoices ───────────────────────────────────────
    async def create_invoice(self, payload: SalesInvoiceCreate, *, post_now: bool = False) -> SalesInvoice:
        await assert_period_open(self.session, self.tenant_id, payload.invoice_date)
        customer = await self.repo.get_customer(payload.customer_id)
        if not customer:
            raise ValidationError("Customer not found in this tenant")
        if not customer.is_active:
            raise ValidationError("Cannot invoice an inactive customer")

        invoice_no = payload.invoice_no or await self.repo.next_invoice_no(payload.invoice_date.year)

        subtotal = Decimal("0")
        tax_total = Decimal("0")
        invoice = SalesInvoice(
            tenant_id=self.tenant_id,
            invoice_no=invoice_no,
            invoice_date=payload.invoice_date,
            due_date=payload.due_date,
            customer_id=customer.id,
            notes=payload.notes,
            status="draft",
            created_by=self.user_id,
        )
        for idx, line in enumerate(payload.lines, start=1):
            # Inventory link validation: stock items require warehouse_id
            if line.item_id is not None:
                item = await self.inv_repo.get_item(line.item_id)
                if not item:
                    raise ValidationError(f"Line {idx}: item {line.item_id} not found in this tenant")
                if item.type == "stock" and line.warehouse_id is None:
                    raise ValidationError(f"Line {idx}: stock item {item.sku} requires warehouse_id")
                if line.warehouse_id is not None:
                    wh = await self.inv_repo.get_warehouse(line.warehouse_id)
                    if not wh:
                        raise ValidationError(f"Line {idx}: warehouse {line.warehouse_id} not found")
            line_total = _money(line.qty * line.unit_price)
            line_tax = _money(line_total * line.tax_rate / Decimal("100"))
            subtotal += line_total
            tax_total += line_tax
            invoice.lines.append(
                SalesInvoiceLine(
                    tenant_id=self.tenant_id,
                    line_no=idx,
                    description=line.description,
                    qty=line.qty,
                    unit_price=line.unit_price,
                    line_total=line_total,
                    tax_rate=line.tax_rate,
                    tax_amount=line_tax,
                    item_id=line.item_id,
                    warehouse_id=line.warehouse_id,
                )
            )

        invoice.subtotal = _money(subtotal)
        invoice.tax_amount = _money(tax_total)
        invoice.total = _money(subtotal + tax_total)

        invoice = await self.repo.add_invoice(invoice)

        if post_now:
            await self._post_internal(invoice)

        return invoice

    async def post_invoice(self, invoice_id: UUID) -> SalesInvoice:
        invoice = await self.repo.get_invoice(invoice_id)
        if not invoice:
            raise NotFoundError("Invoice not found")
        if invoice.status == "posted":
            raise ConflictError("Invoice already posted")
        if invoice.status == "void":
            raise ValidationError("Voided invoice cannot be posted")
        await assert_period_open(self.session, self.tenant_id, invoice.invoice_date)

        await self._post_internal(invoice)
        return invoice

    async def _post_internal(self, invoice: SalesInvoice) -> None:
        ar = await self.acct_repo.get_mapping("ar")
        rev = await self.acct_repo.get_mapping("sales_revenue")
        if not ar or not rev:
            raise ValidationError("Account mappings missing: configure 'ar' and 'sales_revenue'")

        lines: list[tuple[UUID, Decimal, Decimal]] = []
        # Dr AR (gross)
        lines.append((ar.account_id, invoice.total, Decimal("0")))
        # Cr Sales Revenue (subtotal)
        lines.append((rev.account_id, Decimal("0"), invoice.subtotal))
        # Cr Tax Payable (tax) — only if any
        if invoice.tax_amount > 0:
            tax = await self.acct_repo.get_mapping("tax_payable")
            if not tax:
                raise ValidationError("Account mapping missing: configure 'tax_payable' for taxed sales")
            lines.append((tax.account_id, Decimal("0"), invoice.tax_amount))

        # Inventory: for each stock-item line, create stock-out at current
        # avg_cost and accumulate COGS. If any cogs > 0 add Dr COGS / Cr
        # Inventory to the journal so AR/Sales/Tax balance independently
        # of COGS/Inventory and the whole entry stays balanced.
        cogs_total = Decimal("0")
        for ln in invoice.lines:
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
                movement_date=invoice.invoice_date,
                direction="out",
                qty=ln.qty,
                unit_cost=Decimal("0"),  # ignored for outflows (uses avg_cost)
                notes=f"Sale {invoice.invoice_no} line {ln.line_no}",
                source="sales_invoice",
                source_id=invoice.id,
            )
            cogs_total += movement.total_cost

        if cogs_total > 0:
            cogs = await self.acct_repo.get_mapping("cogs")
            inv_acc = await self.acct_repo.get_mapping("inventory")
            if not cogs or not inv_acc:
                raise ValidationError(
                    "Account mappings missing: configure 'cogs' and 'inventory' before selling stock items"
                )
            lines.append((cogs.account_id, cogs_total, Decimal("0")))
            lines.append((inv_acc.account_id, Decimal("0"), cogs_total))

        entry = await self.acct_svc.post_system_journal(
            entry_date=invoice.invoice_date,
            description=f"Sales invoice {invoice.invoice_no}",
            reference=invoice.invoice_no,
            lines=lines,
            source="sales_invoice",
            source_id=invoice.id,
        )

        invoice.journal_entry_id = entry.id
        invoice.status = "posted"
        invoice.posted_by = self.user_id
        invoice.posted_at = datetime.now(UTC)
        await self.session.flush()

        # Publish event for downstream subscribers (email, webhooks, etc.)
        try:
            customer = await self.repo.get_customer(invoice.customer_id) if invoice.customer_id else None
            from app.core.events import publish
            await publish("sales_invoice.posted", {
                "tenant_id": str(self.tenant_id),
                "invoice_id": str(invoice.id),
                "invoice_no": invoice.invoice_no,
                "total": float(invoice.total),
                "due_date": invoice.due_date.isoformat() if invoice.due_date else None,
                "customer_email": getattr(customer, "email", None) if customer else None,
                "customer_name": getattr(customer, "name", None) if customer else None,
            })
        except Exception:
            pass  # event publish is fire-and-forget; never fail the invoice post

    async def void_invoice(self, invoice_id: UUID, reason: str) -> SalesInvoice:
        invoice = await self.repo.get_invoice(invoice_id)
        if not invoice:
            raise NotFoundError("Invoice not found")
        if invoice.status == "void":
            raise ConflictError("Invoice already voided")
        if invoice.paid_amount > 0:
            raise ValidationError("Cannot void invoice with payments applied")
        await assert_period_open(self.session, self.tenant_id, invoice.invoice_date)

        if invoice.status == "posted":
            await self.acct_svc.void_system_journal("sales_invoice", invoice.id, f"Voided: {reason}")
            # Reverse every stock-out from the original posting with a
            # compensating stock-in at the same unit_cost so qty is
            # restored exactly. avg_cost will recompute via the weighted
            # average — that's the correct behavior for void-then-fix.
            originals = await self.inv_repo.list_movements_for_source("sales_invoice", invoice.id)
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
                    movement_date=invoice.invoice_date,
                    direction="in",
                    qty=m.qty,
                    unit_cost=m.unit_cost,
                    notes=f"Void of sale {invoice.invoice_no}",
                    source="void_sales_invoice",
                    source_id=invoice.id,
                )

        invoice.status = "void"
        invoice.voided_by = self.user_id
        invoice.voided_at = datetime.now(UTC)
        invoice.void_reason = reason
        await self.session.flush()
        return invoice

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

    async def void_invoice(self, invoice_id: UUID, reason: str) -> SalesInvoice:
        invoice = await self.repo.get_invoice(invoice_id)
        if not invoice:
            raise NotFoundError("Invoice not found")
        if invoice.status == "void":
            raise ConflictError("Invoice already voided")
        if invoice.paid_amount > 0:
            raise ValidationError("Cannot void invoice with payments applied")

        if invoice.status == "posted":
            await self.acct_svc.void_system_journal("sales_invoice", invoice.id, f"Voided: {reason}")

        invoice.status = "void"
        invoice.voided_by = self.user_id
        invoice.voided_at = datetime.now(UTC)
        invoice.void_reason = reason
        await self.session.flush()
        return invoice

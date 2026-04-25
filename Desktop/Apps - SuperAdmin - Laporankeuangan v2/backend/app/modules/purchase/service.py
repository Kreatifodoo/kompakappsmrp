"""Purchase business logic with auto-journal posting.

Journal pattern on post:
    Dr  Purchase Expense / line.expense_account  (each line subtotal)
    Dr  Tax Receivable                           (tax_amount, only if > 0)
        Cr  Accounts Payable                     (gross total)
"""

from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.modules.accounting.repository import AccountingRepository
from app.modules.accounting.service import AccountingService
from app.modules.purchase.models import (
    PurchaseInvoice,
    PurchaseInvoiceLine,
    Supplier,
)
from app.modules.purchase.repository import PurchaseRepository
from app.modules.purchase.schemas import (
    PurchaseInvoiceCreate,
    SupplierCreate,
    SupplierUpdate,
)

CENT = Decimal("0.01")


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


class PurchaseService:
    def __init__(self, session: AsyncSession, tenant_id: UUID, user_id: UUID):
        self.session = session
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.repo = PurchaseRepository(session, tenant_id)
        self.acct_repo = AccountingRepository(session, tenant_id)
        self.acct_svc = AccountingService(session, tenant_id, user_id)

    # ─── Suppliers ──────────────────────────────────────
    async def create_supplier(self, payload: SupplierCreate) -> Supplier:
        if await self.repo.get_supplier_by_code(payload.code):
            raise ConflictError(f"Supplier code '{payload.code}' already exists")
        s = Supplier(tenant_id=self.tenant_id, **payload.model_dump())
        return await self.repo.add_supplier(s)

    async def update_supplier(self, supplier_id: UUID, payload: SupplierUpdate) -> Supplier:
        s = await self.repo.get_supplier(supplier_id)
        if not s:
            raise NotFoundError("Supplier not found")
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(s, field, value)
        await self.session.flush()
        return s

    # ─── Invoices ───────────────────────────────────────
    async def create_invoice(
        self, payload: PurchaseInvoiceCreate, *, post_now: bool = False
    ) -> PurchaseInvoice:
        supplier = await self.repo.get_supplier(payload.supplier_id)
        if not supplier:
            raise ValidationError("Supplier not found in this tenant")
        if not supplier.is_active:
            raise ValidationError("Cannot bill an inactive supplier")

        # Validate per-line expense account overrides belong to tenant + are expense type
        override_ids = [ln.expense_account_id for ln in payload.lines if ln.expense_account_id]
        if override_ids:
            accounts = await self.acct_repo.get_accounts_by_ids(list(set(override_ids)))
            if len(accounts) != len(set(override_ids)):
                raise ValidationError("Unknown expense account override")

        invoice_no = payload.invoice_no or await self.repo.next_invoice_no(payload.invoice_date.year)

        subtotal = Decimal("0")
        tax_total = Decimal("0")
        invoice = PurchaseInvoice(
            tenant_id=self.tenant_id,
            invoice_no=invoice_no,
            supplier_invoice_no=payload.supplier_invoice_no,
            invoice_date=payload.invoice_date,
            due_date=payload.due_date,
            supplier_id=supplier.id,
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
                PurchaseInvoiceLine(
                    tenant_id=self.tenant_id,
                    line_no=idx,
                    description=line.description,
                    qty=line.qty,
                    unit_price=line.unit_price,
                    line_total=line_total,
                    tax_rate=line.tax_rate,
                    tax_amount=line_tax,
                    expense_account_id=line.expense_account_id,
                )
            )

        invoice.subtotal = _money(subtotal)
        invoice.tax_amount = _money(tax_total)
        invoice.total = _money(subtotal + tax_total)

        invoice = await self.repo.add_invoice(invoice)

        if post_now:
            await self._post_internal(invoice)

        return invoice

    async def post_invoice(self, invoice_id: UUID) -> PurchaseInvoice:
        invoice = await self.repo.get_invoice(invoice_id)
        if not invoice:
            raise NotFoundError("Invoice not found")
        if invoice.status == "posted":
            raise ConflictError("Invoice already posted")
        if invoice.status == "void":
            raise ValidationError("Voided invoice cannot be posted")
        await self._post_internal(invoice)
        return invoice

    async def _post_internal(self, invoice: PurchaseInvoice) -> None:
        ap = await self.acct_repo.get_mapping("ap")
        default_exp = await self.acct_repo.get_mapping("purchase_expense")
        if not ap or not default_exp:
            raise ValidationError("Account mappings missing: configure 'ap' and 'purchase_expense'")

        lines: list[tuple[UUID, Decimal, Decimal]] = []

        # Dr each line — to its override expense account, or the default one
        # (Aggregate by account so one combined debit per account, cleaner reports)
        debits_by_account: dict[UUID, Decimal] = {}
        for ln in invoice.lines:
            acct_id = ln.expense_account_id or default_exp.account_id
            debits_by_account[acct_id] = debits_by_account.get(acct_id, Decimal("0")) + ln.line_total

        for acct_id, amount in debits_by_account.items():
            lines.append((acct_id, amount, Decimal("0")))

        # Dr Tax Receivable (tax) — only if any
        if invoice.tax_amount > 0:
            tax = await self.acct_repo.get_mapping("tax_receivable")
            if not tax:
                raise ValidationError(
                    "Account mapping missing: configure 'tax_receivable' for taxed purchases"
                )
            lines.append((tax.account_id, invoice.tax_amount, Decimal("0")))

        # Cr AP (gross)
        lines.append((ap.account_id, Decimal("0"), invoice.total))

        entry = await self.acct_svc.post_system_journal(
            entry_date=invoice.invoice_date,
            description=f"Purchase invoice {invoice.invoice_no}",
            reference=invoice.supplier_invoice_no or invoice.invoice_no,
            lines=lines,
            source="purchase_invoice",
            source_id=invoice.id,
        )

        invoice.journal_entry_id = entry.id
        invoice.status = "posted"
        invoice.posted_by = self.user_id
        invoice.posted_at = datetime.now(UTC)
        await self.session.flush()

    async def void_invoice(self, invoice_id: UUID, reason: str) -> PurchaseInvoice:
        invoice = await self.repo.get_invoice(invoice_id)
        if not invoice:
            raise NotFoundError("Invoice not found")
        if invoice.status == "void":
            raise ConflictError("Invoice already voided")
        if invoice.paid_amount > 0:
            raise ValidationError("Cannot void invoice with payments applied")

        if invoice.status == "posted":
            await self.acct_svc.void_system_journal("purchase_invoice", invoice.id, f"Voided: {reason}")

        invoice.status = "void"
        invoice.voided_by = self.user_id
        invoice.voided_at = datetime.now(UTC)
        invoice.void_reason = reason
        await self.session.flush()
        return invoice

"""Payments business logic with auto-journal posting and invoice settlement.

Posting a payment creates a balanced journal in the same DB transaction:

    Receipt:        Dr Cash   X
                        Cr AR     X
    Disbursement:   Dr AP     X
                        Cr Cash   X

…and updates each linked invoice's `paid_amount` (status flips to
'paid' if fully settled).
"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.modules.accounting.repository import AccountingRepository
from app.modules.accounting.service import AccountingService
from app.modules.payments.models import Payment, PaymentApplication
from app.modules.payments.repository import PaymentsRepository
from app.modules.payments.schemas import PaymentCreate
from app.modules.periods.service import assert_period_open
from app.modules.purchase.repository import PurchaseRepository
from app.modules.sales.repository import SalesRepository

CENT = Decimal("0.01")


class PaymentsService:
    def __init__(self, session: AsyncSession, tenant_id: UUID, user_id: UUID):
        self.session = session
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.repo = PaymentsRepository(session, tenant_id)
        self.acct_repo = AccountingRepository(session, tenant_id)
        self.acct_svc = AccountingService(session, tenant_id, user_id)
        self.sales_repo = SalesRepository(session, tenant_id)
        self.purchase_repo = PurchaseRepository(session, tenant_id)

    async def create_payment(self, payload: PaymentCreate, *, post_now: bool = True) -> Payment:
        await assert_period_open(self.session, self.tenant_id, payload.payment_date)
        # ── Validate cash account ─────────────────────────
        cash_acct = await self.acct_repo.get_account(payload.cash_account_id)
        if not cash_acct:
            raise ValidationError("cash_account_id not found in this tenant")
        if not cash_acct.is_cash:
            raise ValidationError(f"Account {cash_acct.code} is not flagged is_cash=true")

        # ── Validate party + each application ─────────────
        # Customer-side directions (receipt + customer_refund)
        if payload.direction in ("receipt", "customer_refund"):
            customer = await self.sales_repo.get_customer(payload.customer_id)
            if not customer:
                raise ValidationError("Customer not found in this tenant")

            # Only `receipt` carries applications (refunds are unallocated)
            if payload.direction == "receipt":
                for app in payload.applications:
                    inv = await self.sales_repo.get_invoice(app.sales_invoice_id)
                    if not inv:
                        raise ValidationError(f"Sales invoice {app.sales_invoice_id} not found")
                    if inv.customer_id != customer.id:
                        raise ValidationError(
                            f"Invoice {inv.invoice_no} does not belong to customer {customer.code}"
                        )
                    if inv.status != "posted":
                        raise ValidationError(
                            f"Invoice {inv.invoice_no} is {inv.status}; "
                            f"only posted invoices can receive payment"
                        )
                    outstanding = inv.total - inv.paid_amount
                    if app.amount > outstanding:
                        raise ValidationError(
                            f"Application of {app.amount} on {inv.invoice_no} "
                            f"exceeds outstanding {outstanding}"
                        )
        else:  # supplier-side (disbursement + supplier_refund)
            supplier = await self.purchase_repo.get_supplier(payload.supplier_id)
            if not supplier:
                raise ValidationError("Supplier not found in this tenant")

            if payload.direction == "disbursement":
                for app in payload.applications:
                    inv = await self.purchase_repo.get_invoice(app.purchase_invoice_id)
                    if not inv:
                        raise ValidationError(f"Purchase invoice {app.purchase_invoice_id} not found")
                    if inv.supplier_id != supplier.id:
                        raise ValidationError(
                            f"Invoice {inv.invoice_no} does not belong to supplier {supplier.code}"
                        )
                    if inv.status != "posted":
                        raise ValidationError(f"Invoice {inv.invoice_no} is {inv.status}; cannot pay")
                    outstanding = inv.total - inv.paid_amount
                    if app.amount > outstanding:
                        raise ValidationError(
                            f"Application of {app.amount} on {inv.invoice_no} "
                            f"exceeds outstanding {outstanding}"
                        )

        # ── Build header + applications ───────────────────
        payment_no = payload.payment_no or await self.repo.next_payment_no(
            payload.payment_date.year, payload.direction
        )

        payment = Payment(
            tenant_id=self.tenant_id,
            payment_no=payment_no,
            payment_date=payload.payment_date,
            direction=payload.direction,
            customer_id=payload.customer_id,
            supplier_id=payload.supplier_id,
            amount=payload.amount,
            cash_account_id=payload.cash_account_id,
            reference=payload.reference,
            notes=payload.notes,
            status="draft",
            created_by=self.user_id,
        )
        for app in payload.applications:
            payment.applications.append(
                PaymentApplication(
                    tenant_id=self.tenant_id,
                    sales_invoice_id=app.sales_invoice_id,
                    purchase_invoice_id=app.purchase_invoice_id,
                    amount=app.amount,
                )
            )

        await self.repo.add(payment)

        if post_now:
            await self._post_internal(payment)

        return payment

    async def _post_internal(self, payment: Payment) -> None:
        # Build the 2-line balanced journal based on direction.
        # Customer-side: receipts reduce AR; refunds increase AR (reverse).
        # Supplier-side: disbursements reduce AP; refunds increase AP.
        if payment.direction in ("receipt", "customer_refund"):
            ar = await self.acct_repo.get_mapping("ar")
            if not ar:
                raise ValidationError("Account mapping missing: configure 'ar'")
            if payment.direction == "receipt":
                # Dr Cash / Cr AR
                lines = [
                    (payment.cash_account_id, payment.amount, Decimal("0")),
                    (ar.account_id, Decimal("0"), payment.amount),
                ]
                description = f"Receipt {payment.payment_no}"
            else:  # customer_refund — Dr AR / Cr Cash (reverse of receipt)
                lines = [
                    (ar.account_id, payment.amount, Decimal("0")),
                    (payment.cash_account_id, Decimal("0"), payment.amount),
                ]
                description = f"Refund to customer {payment.payment_no}"
        else:  # disbursement / supplier_refund
            ap = await self.acct_repo.get_mapping("ap")
            if not ap:
                raise ValidationError("Account mapping missing: configure 'ap'")
            if payment.direction == "disbursement":
                # Dr AP / Cr Cash
                lines = [
                    (ap.account_id, payment.amount, Decimal("0")),
                    (payment.cash_account_id, Decimal("0"), payment.amount),
                ]
                description = f"Disbursement {payment.payment_no}"
            else:  # supplier_refund — Dr Cash / Cr AP (reverse of disbursement)
                lines = [
                    (payment.cash_account_id, payment.amount, Decimal("0")),
                    (ap.account_id, Decimal("0"), payment.amount),
                ]
                description = f"Refund from supplier {payment.payment_no}"

        entry = await self.acct_svc.post_system_journal(
            entry_date=payment.payment_date,
            description=description,
            reference=payment.reference,
            lines=lines,
            source="payment",
            source_id=payment.id,
        )

        payment.journal_entry_id = entry.id
        payment.status = "posted"
        payment.posted_by = self.user_id
        payment.posted_at = datetime.now(UTC)

        # Apply to invoices + collect customer info for receipt email
        customer_email = None
        customer_name = None
        for app in payment.applications:
            if app.sales_invoice_id:
                inv = await self.sales_repo.get_invoice(app.sales_invoice_id)
                if inv and inv.customer_id and customer_email is None:
                    cust = await self.sales_repo.get_customer(inv.customer_id)
                    if cust:
                        customer_email = getattr(cust, "email", None)
                        customer_name = getattr(cust, "name", None)
            else:
                inv = await self.purchase_repo.get_invoice(app.purchase_invoice_id)
            inv.paid_amount = (inv.paid_amount + app.amount).quantize(CENT)
            if inv.paid_amount >= inv.total:
                inv.status = "paid"

        await self.session.flush()

        # Fire payment events (realtime + email + webhooks).
        try:
            from app.core.events import publish
            common = {
                "tenant_id":   str(self.tenant_id),
                "payment_id":  str(payment.id),
                "payment_no":  payment.payment_no,
                "amount":      float(payment.amount),
                "payment_date": payment.payment_date.isoformat(),
            }
            if payment.payment_type == "receipt":
                await publish("payment.received", {
                    **common,
                    "customer_email": customer_email,
                    "customer_name":  customer_name,
                })
            elif payment.payment_type == "disbursement":
                await publish("payment.disbursed", common)
        except Exception:
            pass

    async def void_payment(self, payment_id: UUID, reason: str) -> Payment:
        payment = await self.repo.get(payment_id)
        if not payment:
            raise NotFoundError("Payment not found")
        if payment.status == "void":
            raise ConflictError("Payment already voided")
        await assert_period_open(self.session, self.tenant_id, payment.payment_date)

        if payment.status == "posted":
            # Void the linked journal
            await self.acct_svc.void_system_journal("payment", payment.id, f"Voided: {reason}")
            # Reverse paid_amount on invoices
            for app in payment.applications:
                if app.voided:
                    continue
                if app.sales_invoice_id:
                    inv = await self.sales_repo.get_invoice(app.sales_invoice_id)
                else:
                    inv = await self.purchase_repo.get_invoice(app.purchase_invoice_id)
                inv.paid_amount = (inv.paid_amount - app.amount).quantize(CENT)
                if inv.paid_amount < Decimal("0"):
                    inv.paid_amount = Decimal("0")
                # Roll back paid status if needed
                if inv.status == "paid" and inv.paid_amount < inv.total:
                    inv.status = "posted"
                app.voided = True

        payment.status = "void"
        payment.voided_by = self.user_id
        payment.voided_at = datetime.now(UTC)
        payment.void_reason = reason
        await self.session.flush()
        return payment

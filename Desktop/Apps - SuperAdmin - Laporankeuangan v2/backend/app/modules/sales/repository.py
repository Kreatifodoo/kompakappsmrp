"""Sales data access layer."""

from datetime import date
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.sales.models import Customer, SalesInvoice


class SalesRepository:
    def __init__(self, session: AsyncSession, tenant_id: UUID):
        self.session = session
        self.tenant_id = tenant_id

    # ── Customers ────────────────────────────────────────
    async def get_customer(self, customer_id: UUID) -> Customer | None:
        stmt = select(Customer).where(Customer.id == customer_id, Customer.tenant_id == self.tenant_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_customer_by_code(self, code: str) -> Customer | None:
        stmt = select(Customer).where(Customer.code == code, Customer.tenant_id == self.tenant_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_customers(self, *, active_only: bool = True) -> list[Customer]:
        conds = [Customer.tenant_id == self.tenant_id]
        if active_only:
            conds.append(Customer.is_active.is_(True))
        stmt = select(Customer).where(and_(*conds)).order_by(Customer.code)
        return list((await self.session.execute(stmt)).scalars().all())

    async def add_customer(self, customer: Customer) -> Customer:
        self.session.add(customer)
        await self.session.flush()
        return customer

    # ── Sales Invoices ───────────────────────────────────
    async def get_invoice(self, invoice_id: UUID) -> SalesInvoice | None:
        stmt = (
            select(SalesInvoice)
            .options(selectinload(SalesInvoice.lines))
            .where(
                SalesInvoice.id == invoice_id,
                SalesInvoice.tenant_id == self.tenant_id,
            )
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_invoices(
        self,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        status: str | None = None,
        customer_id: UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[SalesInvoice]:
        conds = [SalesInvoice.tenant_id == self.tenant_id]
        if date_from:
            conds.append(SalesInvoice.invoice_date >= date_from)
        if date_to:
            conds.append(SalesInvoice.invoice_date <= date_to)
        if status:
            conds.append(SalesInvoice.status == status)
        if customer_id:
            conds.append(SalesInvoice.customer_id == customer_id)
        stmt = (
            select(SalesInvoice)
            .options(selectinload(SalesInvoice.lines))
            .where(and_(*conds))
            .order_by(SalesInvoice.invoice_date.desc(), SalesInvoice.invoice_no.desc())
            .limit(limit)
            .offset(offset)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def add_invoice(self, invoice: SalesInvoice) -> SalesInvoice:
        self.session.add(invoice)
        await self.session.flush()
        return invoice

    async def next_invoice_no(self, year: int) -> str:
        prefix = f"INV-{year}-"
        stmt = select(func.count(SalesInvoice.id)).where(
            SalesInvoice.tenant_id == self.tenant_id,
            SalesInvoice.invoice_no.like(f"{prefix}%"),
        )
        count = (await self.session.execute(stmt)).scalar_one() or 0
        return f"{prefix}{count + 1:05d}"

"""Purchase data access layer."""

from datetime import date
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.purchase.models import PurchaseInvoice, Supplier


class PurchaseRepository:
    def __init__(self, session: AsyncSession, tenant_id: UUID):
        self.session = session
        self.tenant_id = tenant_id

    async def get_supplier(self, supplier_id: UUID) -> Supplier | None:
        stmt = select(Supplier).where(Supplier.id == supplier_id, Supplier.tenant_id == self.tenant_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_supplier_by_code(self, code: str) -> Supplier | None:
        stmt = select(Supplier).where(Supplier.code == code, Supplier.tenant_id == self.tenant_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_suppliers(self, *, active_only: bool = True) -> list[Supplier]:
        conds = [Supplier.tenant_id == self.tenant_id]
        if active_only:
            conds.append(Supplier.is_active.is_(True))
        stmt = select(Supplier).where(and_(*conds)).order_by(Supplier.code)
        return list((await self.session.execute(stmt)).scalars().all())

    async def add_supplier(self, supplier: Supplier) -> Supplier:
        self.session.add(supplier)
        await self.session.flush()
        return supplier

    async def get_invoice(self, invoice_id: UUID) -> PurchaseInvoice | None:
        stmt = (
            select(PurchaseInvoice)
            .options(selectinload(PurchaseInvoice.lines))
            .where(
                PurchaseInvoice.id == invoice_id,
                PurchaseInvoice.tenant_id == self.tenant_id,
            )
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_invoices(
        self,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        status: str | None = None,
        supplier_id: UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[PurchaseInvoice]:
        conds = [PurchaseInvoice.tenant_id == self.tenant_id]
        if date_from:
            conds.append(PurchaseInvoice.invoice_date >= date_from)
        if date_to:
            conds.append(PurchaseInvoice.invoice_date <= date_to)
        if status:
            conds.append(PurchaseInvoice.status == status)
        if supplier_id:
            conds.append(PurchaseInvoice.supplier_id == supplier_id)
        stmt = (
            select(PurchaseInvoice)
            .options(selectinload(PurchaseInvoice.lines))
            .where(and_(*conds))
            .order_by(PurchaseInvoice.invoice_date.desc(), PurchaseInvoice.invoice_no.desc())
            .limit(limit)
            .offset(offset)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def add_invoice(self, invoice: PurchaseInvoice) -> PurchaseInvoice:
        self.session.add(invoice)
        await self.session.flush()
        return invoice

    async def next_invoice_no(self, year: int) -> str:
        prefix = f"BILL-{year}-"
        stmt = select(func.count(PurchaseInvoice.id)).where(
            PurchaseInvoice.tenant_id == self.tenant_id,
            PurchaseInvoice.invoice_no.like(f"{prefix}%"),
        )
        count = (await self.session.execute(stmt)).scalar_one() or 0
        return f"{prefix}{count + 1:05d}"

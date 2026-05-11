"""Data access for fulfillment docs (DO, GR, RMA)."""

from datetime import date
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.fulfillment.models import (
    DeliveryOrder,
    DeliveryOrderLine,
    RMA,
    RMALine,
)


class FulfillmentRepository:
    def __init__(self, session: AsyncSession, tenant_id: UUID):
        self.session = session
        self.tenant_id = tenant_id

    # ─── Delivery Orders ────────────────────────────────────
    async def list_dos(
        self,
        *,
        so_id: UUID | None = None,
        status: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[DeliveryOrder]:
        conds = [DeliveryOrder.tenant_id == self.tenant_id]
        if so_id: conds.append(DeliveryOrder.so_id == so_id)
        if status: conds.append(DeliveryOrder.status == status)
        if date_from: conds.append(DeliveryOrder.delivery_date >= date_from)
        if date_to: conds.append(DeliveryOrder.delivery_date <= date_to)
        stmt = (
            select(DeliveryOrder).where(*conds)
            .options(selectinload(DeliveryOrder.lines))
            .order_by(DeliveryOrder.delivery_date.desc(), DeliveryOrder.do_no.desc())
            .limit(limit).offset(offset)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_do(self, do_id: UUID) -> DeliveryOrder | None:
        stmt = (
            select(DeliveryOrder).where(
                DeliveryOrder.id == do_id,
                DeliveryOrder.tenant_id == self.tenant_id,
            )
            .options(selectinload(DeliveryOrder.lines))
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def add_do(self, do: DeliveryOrder) -> DeliveryOrder:
        self.session.add(do)
        await self.session.flush()
        return do

    async def next_do_no(self, year: int) -> str:
        prefix = f"DO-{year}-"
        stmt = select(func.count(DeliveryOrder.id)).where(
            DeliveryOrder.tenant_id == self.tenant_id,
            DeliveryOrder.do_no.like(f"{prefix}%"),
        )
        count = (await self.session.execute(stmt)).scalar_one() or 0
        return f"{prefix}{count + 1:05d}"


    # ─── Goods Receipts ─────────────────────────────────────
    async def list_grs(
        self,
        *,
        po_id: UUID | None = None,
        status: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list:
        from app.modules.fulfillment.models import GoodsReceipt
        conds = [GoodsReceipt.tenant_id == self.tenant_id]
        if po_id: conds.append(GoodsReceipt.po_id == po_id)
        if status: conds.append(GoodsReceipt.status == status)
        if date_from: conds.append(GoodsReceipt.receipt_date >= date_from)
        if date_to: conds.append(GoodsReceipt.receipt_date <= date_to)
        stmt = (
            select(GoodsReceipt).where(*conds)
            .options(selectinload(GoodsReceipt.lines))
            .order_by(GoodsReceipt.receipt_date.desc(), GoodsReceipt.gr_no.desc())
            .limit(limit).offset(offset)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_gr(self, gr_id: UUID):
        from app.modules.fulfillment.models import GoodsReceipt
        stmt = (
            select(GoodsReceipt).where(
                GoodsReceipt.id == gr_id,
                GoodsReceipt.tenant_id == self.tenant_id,
            )
            .options(selectinload(GoodsReceipt.lines))
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def add_gr(self, gr):
        self.session.add(gr)
        await self.session.flush()
        return gr

    async def next_gr_no(self, year: int) -> str:
        from app.modules.fulfillment.models import GoodsReceipt
        prefix = f"GR-{year}-"
        stmt = select(func.count(GoodsReceipt.id)).where(
            GoodsReceipt.tenant_id == self.tenant_id,
            GoodsReceipt.gr_no.like(f"{prefix}%"),
        )
        count = (await self.session.execute(stmt)).scalar_one() or 0
        return f"{prefix}{count + 1:05d}"

    # ─── DO/GR line lookups (for RMA source cost) ─────────
    async def get_do_line(self, do_line_id: UUID) -> DeliveryOrderLine | None:
        stmt = select(DeliveryOrderLine).where(DeliveryOrderLine.id == do_line_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_gr_line(self, gr_line_id: UUID):
        from app.modules.fulfillment.models import GoodsReceiptLine
        stmt = select(GoodsReceiptLine).where(GoodsReceiptLine.id == gr_line_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    # ─── RMA ─────────────────────────────────────────────
    async def list_rmas(
        self,
        *,
        rma_type: str | None = None,
        status: str | None = None,
        source_do_id: UUID | None = None,
        source_gr_id: UUID | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[RMA]:
        conds = [RMA.tenant_id == self.tenant_id]
        if rma_type: conds.append(RMA.rma_type == rma_type)
        if status: conds.append(RMA.status == status)
        if source_do_id: conds.append(RMA.source_do_id == source_do_id)
        if source_gr_id: conds.append(RMA.source_gr_id == source_gr_id)
        if date_from: conds.append(RMA.rma_date >= date_from)
        if date_to: conds.append(RMA.rma_date <= date_to)
        stmt = (
            select(RMA).where(*conds)
            .options(selectinload(RMA.lines))
            .order_by(RMA.rma_date.desc(), RMA.rma_no.desc())
            .limit(limit).offset(offset)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_rma(self, rma_id: UUID) -> RMA | None:
        stmt = (
            select(RMA).where(
                RMA.id == rma_id,
                RMA.tenant_id == self.tenant_id,
            )
            .options(selectinload(RMA.lines))
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def add_rma(self, rma: RMA) -> RMA:
        self.session.add(rma)
        await self.session.flush()
        return rma

    async def next_rma_no(self, year: int, rma_type: str) -> str:
        infix = "IN" if rma_type == "customer_return" else "OUT"
        prefix = f"RMA-{infix}-{year}-"
        stmt = select(func.count(RMA.id)).where(
            RMA.tenant_id == self.tenant_id,
            RMA.rma_no.like(f"{prefix}%"),
        )
        count = (await self.session.execute(stmt)).scalar_one() or 0
        return f"{prefix}{count + 1:05d}"

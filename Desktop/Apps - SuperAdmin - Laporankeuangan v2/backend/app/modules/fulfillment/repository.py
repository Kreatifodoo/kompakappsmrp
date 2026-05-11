"""Data access for fulfillment docs (DO, GR, RMA)."""

from datetime import date
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.fulfillment.models import DeliveryOrder, DeliveryOrderLine


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

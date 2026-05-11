"""Data access for Manufacturing (Sprint M1: BOM)."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from datetime import date

from app.modules.manufacturing.models import (
    BOM,
    BOMLine,
    ManufacturingOrder,
    MOComponent,
)


class ManufacturingRepository:
    def __init__(self, session: AsyncSession, tenant_id: UUID):
        self.session = session
        self.tenant_id = tenant_id

    # ─── BOM ──────────────────────────────────────────────
    async def list_boms(
        self,
        *,
        item_id: UUID | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[BOM]:
        conds = [BOM.tenant_id == self.tenant_id]
        if item_id:
            conds.append(BOM.item_id == item_id)
        if status:
            conds.append(BOM.status == status)
        stmt = (
            select(BOM)
            .where(*conds)
            .options(selectinload(BOM.lines))
            .order_by(BOM.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_bom(self, bom_id: UUID) -> BOM | None:
        stmt = (
            select(BOM)
            .where(BOM.id == bom_id, BOM.tenant_id == self.tenant_id)
            .options(selectinload(BOM.lines))
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_active_bom_for_item(self, item_id: UUID) -> BOM | None:
        stmt = (
            select(BOM)
            .where(
                BOM.tenant_id == self.tenant_id,
                BOM.item_id == item_id,
                BOM.status == "active",
            )
            .options(selectinload(BOM.lines))
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def add_bom(self, bom: BOM) -> BOM:
        self.session.add(bom)
        await self.session.flush()
        return bom

    async def next_bom_code(self, item_code: str | None = None) -> str:
        prefix = f"BOM-{item_code}-" if item_code else "BOM-"
        stmt = select(func.count(BOM.id)).where(
            BOM.tenant_id == self.tenant_id,
            BOM.bom_code.like(f"{prefix}%"),
        )
        count = (await self.session.execute(stmt)).scalar_one() or 0
        return f"{prefix}{count + 1:03d}"

    # ─── Manufacturing Order (Sprint M2) ─────────────────
    async def list_mos(
        self,
        *,
        status: str | None = None,
        item_id: UUID | None = None,
        bom_id: UUID | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ManufacturingOrder]:
        conds = [ManufacturingOrder.tenant_id == self.tenant_id]
        if status: conds.append(ManufacturingOrder.status == status)
        if item_id: conds.append(ManufacturingOrder.item_id == item_id)
        if bom_id: conds.append(ManufacturingOrder.bom_id == bom_id)
        if date_from: conds.append(ManufacturingOrder.planned_start >= date_from)
        if date_to: conds.append(ManufacturingOrder.planned_start <= date_to)
        stmt = (
            select(ManufacturingOrder).where(*conds)
            .options(selectinload(ManufacturingOrder.components))
            .order_by(ManufacturingOrder.created_at.desc())
            .limit(limit).offset(offset)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_mo(self, mo_id: UUID) -> ManufacturingOrder | None:
        stmt = (
            select(ManufacturingOrder).where(
                ManufacturingOrder.id == mo_id,
                ManufacturingOrder.tenant_id == self.tenant_id,
            )
            .options(selectinload(ManufacturingOrder.components))
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_mo_component(self, component_id: UUID) -> MOComponent | None:
        stmt = select(MOComponent).where(MOComponent.id == component_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def add_mo(self, mo: ManufacturingOrder) -> ManufacturingOrder:
        self.session.add(mo)
        await self.session.flush()
        return mo

    async def next_mo_no(self, year: int) -> str:
        prefix = f"MO-{year}-"
        stmt = select(func.count(ManufacturingOrder.id)).where(
            ManufacturingOrder.tenant_id == self.tenant_id,
            ManufacturingOrder.mo_no.like(f"{prefix}%"),
        )
        count = (await self.session.execute(stmt)).scalar_one() or 0
        return f"{prefix}{count + 1:05d}"

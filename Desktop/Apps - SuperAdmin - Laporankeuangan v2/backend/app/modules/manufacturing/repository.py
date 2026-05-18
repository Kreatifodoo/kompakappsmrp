"""Data access for Manufacturing (Sprint M1: BOM)."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from datetime import date

from app.modules.manufacturing.models import (
    BOM,
    BOMLine,
    BOMOperation,
    ManufacturingOrder,
    MOComponent,
    MOOperation,
    WorkCenter,
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
            .options(selectinload(BOM.lines), selectinload(BOM.operations))
            .order_by(BOM.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_bom(self, bom_id: UUID) -> BOM | None:
        stmt = (
            select(BOM)
            .where(BOM.id == bom_id, BOM.tenant_id == self.tenant_id)
            .options(selectinload(BOM.lines), selectinload(BOM.operations))
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
            .options(selectinload(BOM.lines), selectinload(BOM.operations))
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
            .options(
                selectinload(ManufacturingOrder.components),
                selectinload(ManufacturingOrder.operations),
            )
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
            .options(
                selectinload(ManufacturingOrder.components),
                selectinload(ManufacturingOrder.operations),
            )
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

    # ─── Work Center (Sprint M5) ────────────────────────
    async def list_work_centers(self, *, is_active: bool | None = None) -> list[WorkCenter]:
        conds = [WorkCenter.tenant_id == self.tenant_id]
        if is_active is not None:
            conds.append(WorkCenter.is_active == is_active)
        stmt = select(WorkCenter).where(*conds).order_by(WorkCenter.code)
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_work_center(self, wc_id: UUID) -> WorkCenter | None:
        stmt = select(WorkCenter).where(
            WorkCenter.id == wc_id,
            WorkCenter.tenant_id == self.tenant_id,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def add_work_center(self, wc: WorkCenter) -> WorkCenter:
        self.session.add(wc)
        await self.session.flush()
        return wc

    async def get_mo_operation(self, op_id: UUID) -> MOOperation | None:
        stmt = select(MOOperation).where(MOOperation.id == op_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    # ─── Scrap (Sprint M6) ───────────────────────────────
    async def list_scraps(
        self,
        *,
        status: str | None = None,
        mo_id: UUID | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        limit: int = 100,
        offset: int = 0,
    ):
        from app.modules.manufacturing.models import MfgScrap
        conds = [MfgScrap.tenant_id == self.tenant_id]
        if status: conds.append(MfgScrap.status == status)
        if mo_id: conds.append(MfgScrap.mo_id == mo_id)
        if date_from: conds.append(MfgScrap.scrap_date >= date_from)
        if date_to: conds.append(MfgScrap.scrap_date <= date_to)
        stmt = (
            select(MfgScrap).where(*conds)
            .options(selectinload(MfgScrap.lines))
            .order_by(MfgScrap.scrap_date.desc(), MfgScrap.scrap_no.desc())
            .limit(limit).offset(offset)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_scrap(self, scrap_id: UUID):
        from app.modules.manufacturing.models import MfgScrap
        stmt = (
            select(MfgScrap).where(
                MfgScrap.id == scrap_id,
                MfgScrap.tenant_id == self.tenant_id,
            )
            .options(selectinload(MfgScrap.lines))
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def add_scrap(self, scrap):
        self.session.add(scrap)
        await self.session.flush()
        return scrap

    async def next_scrap_no(self, year: int) -> str:
        from app.modules.manufacturing.models import MfgScrap
        prefix = f"SCR-{year}-"
        stmt = select(func.count(MfgScrap.id)).where(
            MfgScrap.tenant_id == self.tenant_id,
            MfgScrap.scrap_no.like(f"{prefix}%"),
        )
        count = (await self.session.execute(stmt)).scalar_one() or 0
        return f"{prefix}{count + 1:05d}"

    # ─── Subcontracting / Maklon ─────────────────────────
    async def list_scos(
        self,
        *,
        status: str | None = None,
        supplier_id: UUID | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        limit: int = 100,
        offset: int = 0,
    ):
        from app.modules.manufacturing.models import SubcontractOrder
        conds = [SubcontractOrder.tenant_id == self.tenant_id]
        if status: conds.append(SubcontractOrder.status == status)
        if supplier_id: conds.append(SubcontractOrder.supplier_id == supplier_id)
        if date_from: conds.append(SubcontractOrder.sco_date >= date_from)
        if date_to: conds.append(SubcontractOrder.sco_date <= date_to)
        stmt = (
            select(SubcontractOrder).where(*conds)
            .options(selectinload(SubcontractOrder.components))
            .order_by(SubcontractOrder.sco_date.desc(), SubcontractOrder.sco_no.desc())
            .limit(limit).offset(offset)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_sco(self, sco_id: UUID):
        from app.modules.manufacturing.models import SubcontractOrder
        stmt = (
            select(SubcontractOrder).where(
                SubcontractOrder.id == sco_id,
                SubcontractOrder.tenant_id == self.tenant_id,
            )
            .options(selectinload(SubcontractOrder.components))
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def add_sco(self, sco):
        self.session.add(sco)
        await self.session.flush()
        return sco

    async def next_sco_no(self, year: int) -> str:
        from app.modules.manufacturing.models import SubcontractOrder
        prefix = f"SCO-{year}-"
        stmt = select(func.count(SubcontractOrder.id)).where(
            SubcontractOrder.tenant_id == self.tenant_id,
            SubcontractOrder.sco_no.like(f"{prefix}%"),
        )
        count = (await self.session.execute(stmt)).scalar_one() or 0
        return f"{prefix}{count + 1:05d}"

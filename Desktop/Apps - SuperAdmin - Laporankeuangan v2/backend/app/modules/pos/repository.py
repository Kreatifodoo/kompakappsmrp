"""POS data-access layer."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.pos.models import PosOrder, PosOrderLine, PosSession


class PosRepository:
    def __init__(self, session: AsyncSession, tenant_id: UUID):
        self.session = session
        self.tenant_id = tenant_id

    # ─── Sessions ─────────────────────────────────────────────────

    async def get_session(self, session_id: UUID) -> PosSession | None:
        stmt = (
            select(PosSession)
            .where(PosSession.tenant_id == self.tenant_id, PosSession.id == session_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_open_session_for_cashier(self, cashier_id: UUID) -> PosSession | None:
        """Return the open session for this cashier if one exists."""
        stmt = select(PosSession).where(
            PosSession.tenant_id == self.tenant_id,
            PosSession.cashier_id == cashier_id,
            PosSession.status == "open",
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_sessions(
        self,
        *,
        status: str | None = None,
        cashier_id: UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[PosSession]:
        stmt = select(PosSession).where(PosSession.tenant_id == self.tenant_id)
        if status:
            stmt = stmt.where(PosSession.status == status)
        if cashier_id:
            stmt = stmt.where(PosSession.cashier_id == cashier_id)
        stmt = stmt.order_by(PosSession.opened_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def add_session(self, pos_session: PosSession) -> PosSession:
        self.session.add(pos_session)
        await self.session.flush()
        await self.session.refresh(pos_session)
        return pos_session

    async def next_session_no(self) -> str:
        """Generate next session number: POS-YYYYMMDD-NNN."""
        from datetime import date as _date

        today = _date.today()
        prefix = f"POS-{today.strftime('%Y%m%d')}-"
        stmt = select(func.count()).where(
            PosSession.tenant_id == self.tenant_id,
            PosSession.session_no.like(f"{prefix}%"),
        )
        result = await self.session.execute(stmt)
        count = result.scalar_one()
        return f"{prefix}{count + 1:03d}"

    # ─── Orders ───────────────────────────────────────────────────

    async def get_order(self, order_id: UUID) -> PosOrder | None:
        stmt = (
            select(PosOrder)
            .options(selectinload(PosOrder.lines))
            .where(PosOrder.tenant_id == self.tenant_id, PosOrder.id == order_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_orders(
        self,
        *,
        session_id: UUID | None = None,
        order_date: date | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[PosOrder]:
        stmt = (
            select(PosOrder)
            .options(selectinload(PosOrder.lines))
            .where(PosOrder.tenant_id == self.tenant_id)
        )
        if session_id:
            stmt = stmt.where(PosOrder.session_id == session_id)
        if order_date:
            stmt = stmt.where(PosOrder.order_date == order_date)
        if status:
            stmt = stmt.where(PosOrder.status == status)
        stmt = stmt.order_by(PosOrder.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def add_order(self, order: PosOrder) -> PosOrder:
        self.session.add(order)
        await self.session.flush()
        # Reload with lines
        return await self.get_order(order.id)  # type: ignore[return-value]

    async def next_order_no(self, order_date: date) -> str:
        """Generate next order number: SO-YYYYMMDD-NNNN."""
        prefix = f"SO-{order_date.strftime('%Y%m%d')}-"
        stmt = select(func.count()).where(
            PosOrder.tenant_id == self.tenant_id,
            PosOrder.order_no.like(f"{prefix}%"),
        )
        result = await self.session.execute(stmt)
        count = result.scalar_one()
        return f"{prefix}{count + 1:04d}"

    # ─── Session payment summary ──────────────────────────────────

    async def session_payment_totals(self, session_id: UUID) -> dict[str, Decimal]:
        """Return total sales per payment_method for the session (paid only)."""
        stmt = (
            select(PosOrder.payment_method, func.sum(PosOrder.total))
            .where(
                PosOrder.tenant_id == self.tenant_id,
                PosOrder.session_id == session_id,
                PosOrder.status == "paid",
            )
            .group_by(PosOrder.payment_method)
        )
        result = await self.session.execute(stmt)
        totals: dict[str, Decimal] = {
            "cash": Decimal("0"),
            "card": Decimal("0"),
            "transfer": Decimal("0"),
            "other": Decimal("0"),
        }
        for method, total in result.all():
            totals[method] = total or Decimal("0")
        return totals

    async def session_void_count(self, session_id: UUID) -> int:
        stmt = select(func.count()).where(
            PosOrder.tenant_id == self.tenant_id,
            PosOrder.session_id == session_id,
            PosOrder.status == "void",
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

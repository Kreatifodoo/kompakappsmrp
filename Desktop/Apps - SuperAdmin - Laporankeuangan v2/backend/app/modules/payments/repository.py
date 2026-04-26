"""Payments data access — tenant-scoped queries."""

from datetime import date
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.payments.models import Payment


class PaymentsRepository:
    def __init__(self, session: AsyncSession, tenant_id: UUID):
        self.session = session
        self.tenant_id = tenant_id

    async def get(self, payment_id: UUID) -> Payment | None:
        stmt = (
            select(Payment)
            .options(selectinload(Payment.applications))
            .where(Payment.id == payment_id, Payment.tenant_id == self.tenant_id)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list(
        self,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        direction: str | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Payment]:
        conds = [Payment.tenant_id == self.tenant_id]
        if date_from:
            conds.append(Payment.payment_date >= date_from)
        if date_to:
            conds.append(Payment.payment_date <= date_to)
        if direction:
            conds.append(Payment.direction == direction)
        if status:
            conds.append(Payment.status == status)
        stmt = (
            select(Payment)
            .options(selectinload(Payment.applications))
            .where(and_(*conds))
            .order_by(Payment.payment_date.desc(), Payment.payment_no.desc())
            .limit(limit)
            .offset(offset)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def add(self, payment: Payment) -> Payment:
        self.session.add(payment)
        await self.session.flush()
        return payment

    async def next_payment_no(self, year: int, direction: str) -> str:
        prefix = f"{'RCV' if direction == 'receipt' else 'DSB'}-{year}-"
        stmt = select(func.count(Payment.id)).where(
            Payment.tenant_id == self.tenant_id,
            Payment.payment_no.like(f"{prefix}%"),
        )
        count = (await self.session.execute(stmt)).scalar_one() or 0
        return f"{prefix}{count + 1:05d}"

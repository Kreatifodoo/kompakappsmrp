"""Period closure service + guard helper.

`assert_period_open(session, tenant_id, target_date)` is the single
chokepoint that every other service calls before doing any
state-changing write on a date-bearing entity (journal entry, invoice,
payment). The guard reads `tenants.closed_through` once per call.
"""

from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AuthorizationError,
    NotFoundError,
    PeriodClosedError,
    ValidationError,
)
from app.modules.identity.models import Tenant
from app.modules.periods.models import PeriodClosureEvent
from app.modules.periods.schemas import ClosePeriodRequest, ReopenPeriodRequest


async def get_closed_through(session: AsyncSession, tenant_id: UUID) -> date | None:
    """Return the tenant's current `closed_through` date (or None)."""
    stmt = select(Tenant.closed_through).where(Tenant.id == tenant_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def assert_period_open(session: AsyncSession, tenant_id: UUID, target_date: date) -> None:
    """Raise PeriodClosedError if `target_date` falls within a closed
    period for this tenant.

    Called by every service that creates or modifies a date-bearing
    entity. Read-only queries (reports) bypass this — closed periods
    are still queryable, just immutable.
    """
    closed = await get_closed_through(session, tenant_id)
    if closed is not None and target_date <= closed:
        raise PeriodClosedError(
            f"Cannot modify entries dated on or before {closed.isoformat()} — period is closed",
            details={"target_date": target_date.isoformat(), "closed_through": closed.isoformat()},
        )


class PeriodService:
    def __init__(self, session: AsyncSession, tenant_id: UUID, user_id: UUID):
        self.session = session
        self.tenant_id = tenant_id
        self.user_id = user_id

    async def _tenant(self) -> Tenant:
        tenant = await self.session.get(Tenant, self.tenant_id)
        if tenant is None:
            raise NotFoundError("Tenant not found")
        return tenant

    async def close_period(self, payload: ClosePeriodRequest) -> Tenant:
        tenant = await self._tenant()
        previous = tenant.closed_through
        # Closes must move forward — disallow setting closed_through
        # backward to a date earlier than the current value (that's a
        # reopen, which has its own endpoint with mandatory reason).
        if previous is not None and payload.through_date < previous:
            raise ValidationError(
                f"Closure date {payload.through_date.isoformat()} is earlier "
                f"than the current close ({previous.isoformat()}); use the "
                f"reopen endpoint to roll back"
            )
        if previous is not None and payload.through_date == previous:
            raise ValidationError(f"Period through {previous.isoformat()} is already closed")

        tenant.closed_through = payload.through_date
        self.session.add(
            PeriodClosureEvent(
                tenant_id=self.tenant_id,
                action="close",
                through_date=payload.through_date,
                previous_through_date=previous,
                notes=payload.notes,
                performed_by=self.user_id,
            )
        )
        await self.session.flush()
        return tenant

    async def reopen_period(self, payload: ReopenPeriodRequest) -> Tenant:
        tenant = await self._tenant()
        previous = tenant.closed_through
        if previous is None:
            raise ValidationError("No periods are currently closed")
        # Reopen must roll backward (or clear). Disallow rolling forward
        # (that's a normal close, not a reopen).
        if payload.new_through_date is not None and payload.new_through_date >= previous:
            raise ValidationError(
                f"Reopen target {payload.new_through_date.isoformat()} is not "
                f"before the current close ({previous.isoformat()})"
            )

        tenant.closed_through = payload.new_through_date
        self.session.add(
            PeriodClosureEvent(
                tenant_id=self.tenant_id,
                action="reopen",
                through_date=payload.new_through_date,
                previous_through_date=previous,
                notes=payload.reason,
                performed_by=self.user_id,
            )
        )
        await self.session.flush()
        return tenant

    async def list_events(self) -> list[PeriodClosureEvent]:
        stmt = (
            select(PeriodClosureEvent)
            .where(PeriodClosureEvent.tenant_id == self.tenant_id)
            .order_by(PeriodClosureEvent.performed_at.desc())
        )
        return list((await self.session.execute(stmt)).scalars().all())


# Used by API permission guard
def require_admin(current_user) -> None:  # noqa: ANN001
    """Period close/reopen requires the admin role explicitly — even if
    a custom role grants `period.close`, only admin should hold the
    keys to the books. Defense in depth alongside the permission check."""
    if current_user.role != "admin" and not current_user.is_super_admin:
        raise AuthorizationError("Period close / reopen is restricted to the admin role")

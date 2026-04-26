"""Audit log query endpoints — read-only."""

from datetime import UTC, date, datetime, time
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_read_session
from app.deps import CurrentUser, require_permission
from app.modules.audit.models import AuditLog
from app.modules.audit.schemas import AuditLogOut

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/logs", response_model=list[AuditLogOut])
async def list_audit_logs(
    table_name: str | None = Query(default=None),
    row_id: UUID | None = Query(default=None),
    user_id: UUID | None = Query(default=None),
    action: str | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
    current: CurrentUser = Depends(require_permission("audit.read")),
    session: AsyncSession = Depends(get_read_session),
) -> list[AuditLogOut]:
    """Query audit log rows. Filters compose. RLS keeps results scoped to
    the requesting tenant. Ordered by `occurred_at` desc."""
    conds = [AuditLog.tenant_id == current.tenant_id]
    if table_name:
        conds.append(AuditLog.table_name == table_name)
    if row_id:
        conds.append(AuditLog.row_id == row_id)
    if user_id:
        conds.append(AuditLog.user_id == user_id)
    if action:
        conds.append(AuditLog.action == action)
    if date_from:
        conds.append(AuditLog.occurred_at >= datetime.combine(date_from, time.min, tzinfo=UTC))
    if date_to:
        conds.append(AuditLog.occurred_at <= datetime.combine(date_to, time.max, tzinfo=UTC))

    stmt = (
        select(AuditLog).where(and_(*conds)).order_by(AuditLog.occurred_at.desc()).limit(limit).offset(offset)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [AuditLogOut.model_validate(r) for r in rows]


@router.get("/logs/{row_id}/history", response_model=list[AuditLogOut])
async def row_history(
    row_id: UUID,
    table_name: str | None = Query(
        default=None, description="Disambiguates if the same UUID exists in multiple tables (rare)"
    ),
    current: CurrentUser = Depends(require_permission("audit.read")),
    session: AsyncSession = Depends(get_read_session),
) -> list[AuditLogOut]:
    """Full chronological audit trail for a single row."""
    conds = [AuditLog.tenant_id == current.tenant_id, AuditLog.row_id == row_id]
    if table_name:
        conds.append(AuditLog.table_name == table_name)
    stmt = select(AuditLog).where(and_(*conds)).order_by(AuditLog.occurred_at.asc(), AuditLog.id.asc())
    rows = (await session.execute(stmt)).scalars().all()
    return [AuditLogOut.model_validate(r) for r in rows]

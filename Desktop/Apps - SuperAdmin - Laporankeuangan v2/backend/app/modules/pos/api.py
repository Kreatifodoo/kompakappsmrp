"""POS REST API endpoints.

Prefix: /api/v1/pos
"""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db, require_auth
from app.modules.pos.schemas import (
    PosOrderCreate,
    PosOrderOut,
    PosOrderVoid,
    PosSessionClose,
    PosSessionOpen,
    PosSessionOut,
    PosSessionSummary,
)
from app.modules.pos.service import PosService

router = APIRouter(prefix="/pos", tags=["POS"])


def _svc(
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[dict, Depends(require_auth)],
) -> PosService:
    return PosService(db, auth["tenant_id"], auth["user_id"])


# ─── Sessions ─────────────────────────────────────────────────────────────────

@router.post("/sessions", response_model=PosSessionOut, status_code=201)
async def open_session(
    payload: PosSessionOpen,
    svc: Annotated[PosService, Depends(_svc)],
):
    """Open a new POS session (cash-register shift)."""
    return await svc.open_session(payload)


@router.get("/sessions", response_model=list[PosSessionOut])
async def list_sessions(
    svc: Annotated[PosService, Depends(_svc)],
    status: str | None = Query(default=None, description="Filter by status: open | closed"),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
):
    """List POS sessions for this tenant."""
    return await svc.list_sessions(status=status, limit=limit, offset=offset)


@router.get("/sessions/{session_id}", response_model=PosSessionOut)
async def get_session(
    session_id: UUID,
    svc: Annotated[PosService, Depends(_svc)],
):
    """Get a specific POS session."""
    return await svc.get_session(session_id)


@router.post("/sessions/{session_id}/close", response_model=PosSessionSummary)
async def close_session(
    session_id: UUID,
    payload: PosSessionClose,
    svc: Annotated[PosService, Depends(_svc)],
):
    """Close a POS session and reconcile cash."""
    return await svc.close_session(session_id, payload)


# ─── Orders ───────────────────────────────────────────────────────────────────

@router.post("/orders", response_model=PosOrderOut, status_code=201)
async def create_order(
    payload: PosOrderCreate,
    svc: Annotated[PosService, Depends(_svc)],
):
    """Create and immediately post a POS order (receipt).

    Stock-type items trigger a stock-out movement and COGS journal entry
    in the same transaction.
    """
    return await svc.create_order(payload)


@router.get("/orders", response_model=list[PosOrderOut])
async def list_orders(
    svc: Annotated[PosService, Depends(_svc)],
    session_id: UUID | None = Query(default=None),
    order_date: date | None = Query(default=None),
    status: str | None = Query(default=None, description="Filter: paid | void"),
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
):
    """List POS orders."""
    return await svc.list_orders(
        session_id=session_id,
        order_date=order_date,
        status=status,
        limit=limit,
        offset=offset,
    )


@router.get("/orders/{order_id}", response_model=PosOrderOut)
async def get_order(
    order_id: UUID,
    svc: Annotated[PosService, Depends(_svc)],
):
    """Get a specific POS order with all lines."""
    return await svc.get_order(order_id)


@router.post("/orders/{order_id}/void", response_model=PosOrderOut)
async def void_order(
    order_id: UUID,
    payload: PosOrderVoid,
    svc: Annotated[PosService, Depends(_svc)],
):
    """Void a POS order. Reverses journal entry and stock movements."""
    return await svc.void_order(order_id, payload.reason)

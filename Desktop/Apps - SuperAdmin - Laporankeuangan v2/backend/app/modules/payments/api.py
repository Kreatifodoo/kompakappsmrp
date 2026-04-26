"""HTTP routes for Payments: /payments."""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_write_session
from app.core.exceptions import AuthorizationError, NotFoundError
from app.deps import CurrentUser, require_permission
from app.modules.payments.repository import PaymentsRepository
from app.modules.payments.schemas import (
    PaymentCreate,
    PaymentOut,
    PaymentVoidRequest,
)
from app.modules.payments.service import PaymentsService

router = APIRouter(tags=["payments"])


@router.get("/payments", response_model=list[PaymentOut])
async def list_payments(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    direction: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
    current: CurrentUser = Depends(require_permission("payment.read")),
    session: AsyncSession = Depends(get_write_session),
) -> list[PaymentOut]:
    repo = PaymentsRepository(session, current.tenant_id)
    payments = await repo.list(
        date_from=date_from,
        date_to=date_to,
        direction=direction,
        status=status,
        limit=limit,
        offset=offset,
    )
    return [PaymentOut.model_validate(p) for p in payments]


@router.get("/payments/{payment_id}", response_model=PaymentOut)
async def get_payment(
    payment_id: UUID,
    current: CurrentUser = Depends(require_permission("payment.read")),
    session: AsyncSession = Depends(get_write_session),
) -> PaymentOut:
    repo = PaymentsRepository(session, current.tenant_id)
    payment = await repo.get(payment_id)
    if not payment:
        raise NotFoundError("Payment not found")
    return PaymentOut.model_validate(payment)


@router.post("/payments", response_model=PaymentOut, status_code=201)
async def create_payment(
    payload: PaymentCreate,
    post_now: bool = Query(default=True),
    current: CurrentUser = Depends(require_permission("payment.write")),
    session: AsyncSession = Depends(get_write_session),
) -> PaymentOut:
    if post_now and not current.has_permission("payment.post"):
        raise AuthorizationError("Missing permission: payment.post")
    svc = PaymentsService(session, current.tenant_id, current.user_id)
    payment = await svc.create_payment(payload, post_now=post_now)
    return PaymentOut.model_validate(payment)


@router.post("/payments/{payment_id}/void", response_model=PaymentOut)
async def void_payment(
    payment_id: UUID,
    payload: PaymentVoidRequest,
    current: CurrentUser = Depends(require_permission("payment.post")),
    session: AsyncSession = Depends(get_write_session),
) -> PaymentOut:
    svc = PaymentsService(session, current.tenant_id, current.user_id)
    return PaymentOut.model_validate(await svc.void_payment(payment_id, payload.reason))

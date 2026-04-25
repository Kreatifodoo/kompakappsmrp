"""HTTP routes for Sales: /customers, /sales-invoices."""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_write_session
from app.core.exceptions import AuthorizationError, NotFoundError
from app.deps import CurrentUser, require_permission
from app.modules.sales.repository import SalesRepository
from app.modules.sales.schemas import (
    CustomerCreate,
    CustomerOut,
    CustomerUpdate,
    InvoiceVoidRequest,
    SalesInvoiceCreate,
    SalesInvoiceOut,
)
from app.modules.sales.service import SalesService

router = APIRouter(tags=["sales"])


# ─── Customers ──────────────────────────────────────────
@router.get("/customers", response_model=list[CustomerOut])
async def list_customers(
    active_only: bool = Query(default=True),
    current: CurrentUser = Depends(require_permission("sales.read")),
    session: AsyncSession = Depends(get_write_session),
) -> list[CustomerOut]:
    repo = SalesRepository(session, current.tenant_id)
    customers = await repo.list_customers(active_only=active_only)
    return [CustomerOut.model_validate(c) for c in customers]


@router.post("/customers", response_model=CustomerOut, status_code=201)
async def create_customer(
    payload: CustomerCreate,
    current: CurrentUser = Depends(require_permission("sales.write")),
    session: AsyncSession = Depends(get_write_session),
) -> CustomerOut:
    svc = SalesService(session, current.tenant_id, current.user_id)
    return CustomerOut.model_validate(await svc.create_customer(payload))


@router.patch("/customers/{customer_id}", response_model=CustomerOut)
async def update_customer(
    customer_id: UUID,
    payload: CustomerUpdate,
    current: CurrentUser = Depends(require_permission("sales.write")),
    session: AsyncSession = Depends(get_write_session),
) -> CustomerOut:
    svc = SalesService(session, current.tenant_id, current.user_id)
    return CustomerOut.model_validate(await svc.update_customer(customer_id, payload))


# ─── Sales Invoices ─────────────────────────────────────
@router.get("/sales-invoices", response_model=list[SalesInvoiceOut])
async def list_invoices(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    status: str | None = Query(default=None),
    customer_id: UUID | None = Query(default=None),
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
    current: CurrentUser = Depends(require_permission("sales.read")),
    session: AsyncSession = Depends(get_write_session),
) -> list[SalesInvoiceOut]:
    repo = SalesRepository(session, current.tenant_id)
    invoices = await repo.list_invoices(
        date_from=date_from,
        date_to=date_to,
        status=status,
        customer_id=customer_id,
        limit=limit,
        offset=offset,
    )
    return [SalesInvoiceOut.model_validate(i) for i in invoices]


@router.get("/sales-invoices/{invoice_id}", response_model=SalesInvoiceOut)
async def get_invoice(
    invoice_id: UUID,
    current: CurrentUser = Depends(require_permission("sales.read")),
    session: AsyncSession = Depends(get_write_session),
) -> SalesInvoiceOut:
    repo = SalesRepository(session, current.tenant_id)
    invoice = await repo.get_invoice(invoice_id)
    if not invoice:
        raise NotFoundError("Invoice not found")
    return SalesInvoiceOut.model_validate(invoice)


@router.post("/sales-invoices", response_model=SalesInvoiceOut, status_code=201)
async def create_invoice(
    payload: SalesInvoiceCreate,
    post_now: bool = Query(default=False),
    current: CurrentUser = Depends(require_permission("sales.write")),
    session: AsyncSession = Depends(get_write_session),
) -> SalesInvoiceOut:
    if post_now and not current.has_permission("sales.post"):
        raise AuthorizationError("Missing permission: sales.post")
    svc = SalesService(session, current.tenant_id, current.user_id)
    invoice = await svc.create_invoice(payload, post_now=post_now)
    return SalesInvoiceOut.model_validate(invoice)


@router.post("/sales-invoices/{invoice_id}/post", response_model=SalesInvoiceOut)
async def post_invoice(
    invoice_id: UUID,
    current: CurrentUser = Depends(require_permission("sales.post")),
    session: AsyncSession = Depends(get_write_session),
) -> SalesInvoiceOut:
    svc = SalesService(session, current.tenant_id, current.user_id)
    return SalesInvoiceOut.model_validate(await svc.post_invoice(invoice_id))


@router.post("/sales-invoices/{invoice_id}/void", response_model=SalesInvoiceOut)
async def void_invoice(
    invoice_id: UUID,
    payload: InvoiceVoidRequest,
    current: CurrentUser = Depends(require_permission("sales.post")),
    session: AsyncSession = Depends(get_write_session),
) -> SalesInvoiceOut:
    svc = SalesService(session, current.tenant_id, current.user_id)
    return SalesInvoiceOut.model_validate(await svc.void_invoice(invoice_id, payload.reason))

"""HTTP routes for Purchase: /suppliers, /purchase-invoices."""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_write_session
from app.core.exceptions import AuthorizationError, NotFoundError
from app.deps import CurrentUser, require_permission
from app.modules.purchase.repository import PurchaseRepository
from app.modules.purchase.schemas import (
    InvoiceVoidRequest,
    PurchaseInvoiceCreate,
    PurchaseInvoiceOut,
    SupplierCreate,
    SupplierOut,
    SupplierUpdate,
)
from app.modules.purchase.service import PurchaseService

router = APIRouter(tags=["purchase"])


# ─── Suppliers ──────────────────────────────────────────
@router.get("/suppliers", response_model=list[SupplierOut])
async def list_suppliers(
    active_only: bool = Query(default=True),
    current: CurrentUser = Depends(require_permission("purchase.read")),
    session: AsyncSession = Depends(get_write_session),
) -> list[SupplierOut]:
    repo = PurchaseRepository(session, current.tenant_id)
    return [SupplierOut.model_validate(s) for s in await repo.list_suppliers(active_only=active_only)]


@router.post("/suppliers", response_model=SupplierOut, status_code=201)
async def create_supplier(
    payload: SupplierCreate,
    current: CurrentUser = Depends(require_permission("purchase.write")),
    session: AsyncSession = Depends(get_write_session),
) -> SupplierOut:
    svc = PurchaseService(session, current.tenant_id, current.user_id)
    return SupplierOut.model_validate(await svc.create_supplier(payload))


@router.patch("/suppliers/{supplier_id}", response_model=SupplierOut)
async def update_supplier(
    supplier_id: UUID,
    payload: SupplierUpdate,
    current: CurrentUser = Depends(require_permission("purchase.write")),
    session: AsyncSession = Depends(get_write_session),
) -> SupplierOut:
    svc = PurchaseService(session, current.tenant_id, current.user_id)
    return SupplierOut.model_validate(await svc.update_supplier(supplier_id, payload))


# ─── Purchase Invoices ──────────────────────────────────
@router.get("/purchase-invoices", response_model=list[PurchaseInvoiceOut])
async def list_invoices(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    status: str | None = Query(default=None),
    supplier_id: UUID | None = Query(default=None),
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
    current: CurrentUser = Depends(require_permission("purchase.read")),
    session: AsyncSession = Depends(get_write_session),
) -> list[PurchaseInvoiceOut]:
    repo = PurchaseRepository(session, current.tenant_id)
    invoices = await repo.list_invoices(
        date_from=date_from,
        date_to=date_to,
        status=status,
        supplier_id=supplier_id,
        limit=limit,
        offset=offset,
    )
    return [PurchaseInvoiceOut.model_validate(i) for i in invoices]


@router.get("/purchase-invoices/{invoice_id}", response_model=PurchaseInvoiceOut)
async def get_invoice(
    invoice_id: UUID,
    current: CurrentUser = Depends(require_permission("purchase.read")),
    session: AsyncSession = Depends(get_write_session),
) -> PurchaseInvoiceOut:
    repo = PurchaseRepository(session, current.tenant_id)
    invoice = await repo.get_invoice(invoice_id)
    if not invoice:
        raise NotFoundError("Invoice not found")
    return PurchaseInvoiceOut.model_validate(invoice)


@router.post("/purchase-invoices", response_model=PurchaseInvoiceOut, status_code=201)
async def create_invoice(
    payload: PurchaseInvoiceCreate,
    post_now: bool = Query(default=False),
    current: CurrentUser = Depends(require_permission("purchase.write")),
    session: AsyncSession = Depends(get_write_session),
) -> PurchaseInvoiceOut:
    if post_now and not current.has_permission("purchase.post"):
        raise AuthorizationError("Missing permission: purchase.post")
    svc = PurchaseService(session, current.tenant_id, current.user_id)
    invoice = await svc.create_invoice(payload, post_now=post_now)
    return PurchaseInvoiceOut.model_validate(invoice)


@router.post("/purchase-invoices/{invoice_id}/post", response_model=PurchaseInvoiceOut)
async def post_invoice(
    invoice_id: UUID,
    current: CurrentUser = Depends(require_permission("purchase.post")),
    session: AsyncSession = Depends(get_write_session),
) -> PurchaseInvoiceOut:
    svc = PurchaseService(session, current.tenant_id, current.user_id)
    return PurchaseInvoiceOut.model_validate(await svc.post_invoice(invoice_id))


@router.post("/purchase-invoices/{invoice_id}/void", response_model=PurchaseInvoiceOut)
async def void_invoice(
    invoice_id: UUID,
    payload: InvoiceVoidRequest,
    current: CurrentUser = Depends(require_permission("purchase.post")),
    session: AsyncSession = Depends(get_write_session),
) -> PurchaseInvoiceOut:
    svc = PurchaseService(session, current.tenant_id, current.user_id)
    return PurchaseInvoiceOut.model_validate(await svc.void_invoice(invoice_id, payload.reason))

"""API v1 router aggregator."""

from fastapi import APIRouter

from app.modules.accounting.api import router as accounting_router
from app.modules.identity.api import router as identity_router
from app.modules.payments.api import router as payments_router
from app.modules.purchase.api import router as purchase_router
from app.modules.reports.api import router as reports_router
from app.modules.sales.api import router as sales_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(identity_router)
api_v1_router.include_router(accounting_router)
api_v1_router.include_router(sales_router)
api_v1_router.include_router(purchase_router)
api_v1_router.include_router(payments_router)
api_v1_router.include_router(reports_router)

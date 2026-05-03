"""API v1 router aggregator."""

from fastapi import APIRouter

from app.modules.accounting.api import router as accounting_router
from app.modules.audit.api import router as audit_router
from app.modules.identity.api import router as identity_router
from app.modules.identity.roles_api import router as roles_router
from app.modules.inventory.api import router as inventory_router
from app.modules.notifications import subscribers as _notif_subscribers  # noqa: F401  register
from app.modules.notifications.api import router as notifications_router
from app.modules.payments.api import router as payments_router
from app.modules.periods.api import router as periods_router
from app.modules.pos.api import router as pos_router
from app.modules.purchase.api import router as purchase_router
from app.modules.reports.api import router as reports_router
from app.modules.sales.api import router as sales_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(identity_router)
api_v1_router.include_router(roles_router)
api_v1_router.include_router(accounting_router)
api_v1_router.include_router(sales_router)
api_v1_router.include_router(purchase_router)
api_v1_router.include_router(payments_router)
api_v1_router.include_router(reports_router)
api_v1_router.include_router(audit_router)
api_v1_router.include_router(periods_router)
api_v1_router.include_router(inventory_router)
api_v1_router.include_router(pos_router)
api_v1_router.include_router(notifications_router)

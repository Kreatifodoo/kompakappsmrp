"""API v1 router aggregator."""
from fastapi import APIRouter

from app.modules.accounting.api import router as accounting_router
from app.modules.identity.api import router as identity_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(identity_router)
api_v1_router.include_router(accounting_router)

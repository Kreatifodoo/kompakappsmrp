"""HTTP routes for Identity: /auth/login, /auth/refresh, /auth/me, /tenants."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_write_session
from app.deps import CurrentUser, get_current_user
from app.modules.identity.repository import IdentityRepository
from app.modules.identity.schemas import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    MeResponse,
    RefreshRequest,
    RegisterTenantRequest,
    ResetPasswordRequest,
    TenantOut,
    TokenPair,
    UserOut,
)
from app.modules.identity.service import IdentityService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenPair)
async def login(
    payload: LoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_write_session),
) -> TokenPair:
    svc = IdentityService(session)
    return await svc.login(payload, ip=request.client.host if request.client else None)


@router.post("/refresh", response_model=TokenPair)
async def refresh(
    payload: RefreshRequest,
    request: Request,
    session: AsyncSession = Depends(get_write_session),
) -> TokenPair:
    svc = IdentityService(session)
    return await svc.refresh(payload.refresh_token, ip=request.client.host if request.client else None)


@router.post("/register-tenant", response_model=TenantOut, status_code=201)
async def register_tenant(
    payload: RegisterTenantRequest,
    session: AsyncSession = Depends(get_write_session),
) -> TenantOut:
    svc = IdentityService(session)
    tenant = await svc.register_tenant(payload)
    return TenantOut.model_validate(tenant)


@router.get("/me", response_model=MeResponse)
async def me(
    current: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_write_session),
) -> MeResponse:
    repo = IdentityRepository(session)
    user = await repo.get_user(current.user_id)
    tenant = await repo.get_tenant(current.tenant_id) if current.tenant_id else None
    return MeResponse(
        user=UserOut.model_validate(user),
        tenant=TenantOut.model_validate(tenant) if tenant else None,
        role=current.role,
        permissions=current.permissions,
    )


# ─── Password reset / change flow ────────────────────────
@router.post("/forgot-password", status_code=202, summary="Request password reset email (always returns success)")
async def forgot_password(
    payload: ForgotPasswordRequest,
    session: AsyncSession = Depends(get_write_session),
) -> dict:
    """Issue reset token + queue email. Always returns 202 (no email enumeration)."""
    svc = IdentityService(session)
    await svc.forgot_password(payload.email)
    return {"detail": "Jika email terdaftar, link reset password sudah dikirim."}


@router.post("/reset-password", status_code=200, summary="Reset password using JWT token from email")
async def reset_password(
    payload: ResetPasswordRequest,
    session: AsyncSession = Depends(get_write_session),
) -> dict:
    svc = IdentityService(session)
    await svc.reset_password(payload.token, payload.new_password)
    return {"detail": "Password berhasil direset. Silakan login ulang."}


@router.post("/change-password", status_code=200, summary="Change password (requires old password)")
async def change_password(
    payload: ChangePasswordRequest,
    current: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_write_session),
) -> dict:
    svc = IdentityService(session)
    await svc.change_password(current.user_id, payload.old_password, payload.new_password)
    return {"detail": "Password berhasil diubah. Login pada device lain ter-revoke."}

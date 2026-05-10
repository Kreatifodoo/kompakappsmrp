"""HTTP routes for tenant-scoped User management.

Endpoints (all require `user.write` permission for mutations,
`user.read` for list):
  GET    /users           — list users in current tenant + role + active
  POST   /users           — invite new user (creates User if email not found,
                              adds TenantUser membership). Returns temp_password.
  PATCH  /users/{user_id} — update full_name + role_id + is_active
  DELETE /users/{user_id} — soft delete (set User.is_active=False); membership
                              kept for audit trail.
"""

from __future__ import annotations

import secrets
import string
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_write_session
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.security import hash_password
from app.deps import CurrentUser, get_current_user, require_permission
from app.modules.identity.models import TenantUser, User
from app.modules.identity.repository import IdentityRepository
from app.modules.identity.schemas import (
    TenantUserInvite,
    TenantUserInviteResponse,
    TenantUserListItem,
    TenantUserUpdate,
)

router = APIRouter(prefix="/users", tags=["users"])


def _gen_temp_password() -> str:
    """Random 12-char password with letters + digits + 1 special char."""
    alphabet = string.ascii_letters + string.digits
    pwd = "".join(secrets.choice(alphabet) for _ in range(11))
    return pwd + secrets.choice("!@#$%&*")


@router.get(
    "",
    response_model=list[TenantUserListItem],
    summary="List users in the current tenant (with role + active status)",
)
async def list_tenant_users(
    current: CurrentUser = Depends(require_permission("user.read")),
    session: AsyncSession = Depends(get_write_session),
) -> list[TenantUserListItem]:
    if current.tenant_id is None:
        raise ValidationError("No tenant context")
    repo = IdentityRepository(session)
    rows = await repo.list_tenant_users(current.tenant_id)
    return [
        TenantUserListItem(
            user_id=user.id,
            email=user.email,
            full_name=user.full_name,
            is_active=user.is_active,
            is_owner=tu.is_owner,
            role_id=role.id,
            role_name=role.name,
            invited_at=tu.invited_at,
            accepted_at=tu.accepted_at,
            last_login_at=user.last_login_at,
        )
        for (user, tu, role) in rows
    ]


@router.post(
    "",
    response_model=TenantUserInviteResponse,
    status_code=201,
    summary="Invite a user to this tenant. Creates User if email new, adds membership.",
)
async def invite_user(
    payload: TenantUserInvite,
    current: CurrentUser = Depends(require_permission("user.write")),
    session: AsyncSession = Depends(get_write_session),
) -> TenantUserInviteResponse:
    if current.tenant_id is None:
        raise ValidationError("No tenant context")
    repo = IdentityRepository(session)

    # Validate role exists + belongs to this tenant or is a system role
    role = await repo.get_role(payload.role_id)
    if not role:
        raise NotFoundError("Role not found")
    if role.tenant_id is not None and role.tenant_id != current.tenant_id:
        raise ValidationError("Role does not belong to this tenant")

    # Find or create user
    user = await repo.get_user_by_email(payload.email)
    temp_password = None
    if user is None:
        # Create new user with temp password
        temp_password = payload.temp_password or _gen_temp_password()
        user = User(
            email=payload.email,
            password_hash=hash_password(temp_password),
            full_name=payload.full_name,
            is_active=True,
        )
        await repo.add_user(user)
    else:
        # Existing user — check if already a member of this tenant
        existing = await repo.get_tenant_membership(current.tenant_id, user.id)
        if existing:
            raise ConflictError(f"User {payload.email} is already a member of this tenant")
        # If user is inactive globally, reactivate (membership-add implies acceptance)
        if not user.is_active:
            user.is_active = True

    # Add membership
    membership = TenantUser(
        tenant_id=current.tenant_id,
        user_id=user.id,
        role_id=role.id,
        is_owner=False,
        accepted_at=datetime.now(UTC),
    )
    await repo.add_membership(membership)

    return TenantUserInviteResponse(
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role_name=role.name,
        temp_password=temp_password,
    )


@router.patch(
    "/{user_id}",
    response_model=TenantUserListItem,
    summary="Update user info or role within this tenant",
)
async def update_tenant_user(
    user_id: UUID,
    payload: TenantUserUpdate,
    current: CurrentUser = Depends(require_permission("user.write")),
    session: AsyncSession = Depends(get_write_session),
) -> TenantUserListItem:
    if current.tenant_id is None:
        raise ValidationError("No tenant context")
    repo = IdentityRepository(session)

    membership = await repo.get_tenant_membership(current.tenant_id, user_id)
    if membership is None:
        raise NotFoundError("User is not a member of this tenant")

    user = await repo.get_user(user_id)
    if user is None:
        raise NotFoundError("User not found")

    # Apply updates
    if payload.full_name is not None:
        user.full_name = payload.full_name
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.role_id is not None:
        if membership.is_owner:
            raise ValidationError("Cannot change role of tenant owner")
        new_role = await repo.get_role(payload.role_id)
        if not new_role:
            raise NotFoundError("Role not found")
        if new_role.tenant_id is not None and new_role.tenant_id != current.tenant_id:
            raise ValidationError("Role does not belong to this tenant")
        membership.role_id = new_role.id

    await session.flush()

    role = await repo.get_role(membership.role_id)
    return TenantUserListItem(
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        is_owner=membership.is_owner,
        role_id=role.id,
        role_name=role.name,
        invited_at=membership.invited_at,
        accepted_at=membership.accepted_at,
        last_login_at=user.last_login_at,
    )


@router.delete(
    "/{user_id}",
    status_code=204,
    summary="Deactivate user (soft delete via is_active=False)",
)
async def deactivate_user(
    user_id: UUID,
    current: CurrentUser = Depends(require_permission("user.delete")),
    session: AsyncSession = Depends(get_write_session),
) -> None:
    if current.tenant_id is None:
        raise ValidationError("No tenant context")
    repo = IdentityRepository(session)

    membership = await repo.get_tenant_membership(current.tenant_id, user_id)
    if membership is None:
        raise NotFoundError("User is not a member of this tenant")
    if membership.is_owner:
        raise ValidationError("Cannot deactivate tenant owner")
    if user_id == current.user_id:
        raise ValidationError("Cannot deactivate yourself")

    user = await repo.get_user(user_id)
    if user is None:
        raise NotFoundError("User not found")
    user.is_active = False
    # Revoke active refresh tokens — force logout immediately
    await repo.revoke_all_refresh_tokens_for_user(user.id)
    await session.flush()

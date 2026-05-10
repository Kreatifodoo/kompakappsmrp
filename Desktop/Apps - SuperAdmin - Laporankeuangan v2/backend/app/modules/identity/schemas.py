"""Pydantic schemas for Identity module HTTP layer."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
    tenant_slug: str | None = None  # Optional: pick tenant if user belongs to multiple


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds until access expires


class RefreshRequest(BaseModel):
    refresh_token: str


class RegisterTenantRequest(BaseModel):
    tenant_name: str = Field(min_length=2, max_length=200)
    tenant_slug: str = Field(min_length=3, max_length=60, pattern=r"^[a-z0-9][a-z0-9-]+$")
    owner_email: EmailStr
    owner_password: str = Field(min_length=8, max_length=128)
    owner_full_name: str = Field(min_length=2, max_length=200)


class TenantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    plan: str
    status: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    full_name: str
    is_active: bool
    is_super_admin: bool
    last_login_at: datetime | None


class MeResponse(BaseModel):
    user: UserOut
    tenant: TenantOut | None
    role: str
    permissions: list[str]


# ─── Roles & Permissions ──────────────────────────────────
class PermissionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    description: str | None


class RoleCreate(BaseModel):
    name: str = Field(min_length=2, max_length=50)
    description: str | None = Field(default=None, max_length=255)
    permission_codes: list[str] = Field(min_length=1)


class RoleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=50)
    description: str | None = Field(default=None, max_length=255)
    # If non-None, replaces the role's permission set entirely
    permission_codes: list[str] | None = None


class RoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID | None  # NULL for system roles
    name: str
    description: str | None
    is_system: bool
    permissions: list[str]  # permission codes


# ─── Password reset / change flow ─────────────────────────
class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    new_password: str = Field(min_length=8, max_length=128)


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


# ─── Tenant Users (CRUD per tenant) ───────────────────────
class TenantUserListItem(BaseModel):
    """One row in the tenant's user list — User + role + active status."""
    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    email: str
    full_name: str
    is_active: bool                  # User.is_active (global)
    is_owner: bool                   # TenantUser.is_owner
    role_id: UUID
    role_name: str
    invited_at: datetime
    accepted_at: datetime | None
    last_login_at: datetime | None


class TenantUserInvite(BaseModel):
    """Invite a new user to the current tenant. If email exists globally,
    add membership; otherwise create User + membership.

    `temp_password` defaults to a random 12-char string returned once
    in the response. The owner can then SMS/share it; user changes
    on first login. (Email-link flow can be added later via password
    reset endpoint.)
    """
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=200)
    role_id: UUID
    temp_password: str | None = Field(default=None, min_length=8, max_length=128)


class TenantUserInviteResponse(BaseModel):
    user_id: UUID
    email: str
    full_name: str
    role_name: str
    temp_password: str | None  # Returned only when newly created — for owner to share


class TenantUserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=200)
    role_id: UUID | None = None
    is_active: bool | None = None

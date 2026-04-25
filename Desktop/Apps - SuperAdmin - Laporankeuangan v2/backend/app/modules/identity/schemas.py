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

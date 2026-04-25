"""Shared FastAPI dependencies: current user, tenant, permission checks."""
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Request
from jose import JWTError

from app.core.exceptions import AuthenticationError, AuthorizationError
from app.core.security import decode_access_token


@dataclass(frozen=True)
class CurrentUser:
    user_id: UUID
    tenant_id: UUID | None
    role: str
    permissions: list[str]
    is_super_admin: bool

    def has_permission(self, perm: str) -> bool:
        if self.is_super_admin or "*" in self.permissions:
            return True
        return perm in self.permissions


async def get_current_user(request: Request) -> CurrentUser:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise AuthenticationError("Missing bearer token")
    token = auth[7:]
    try:
        payload = decode_access_token(token)
    except JWTError as exc:
        raise AuthenticationError("Invalid or expired token") from exc

    if payload.get("type") != "access":
        raise AuthenticationError("Wrong token type")

    return CurrentUser(
        user_id=UUID(payload["sub"]),
        tenant_id=UUID(payload["tid"]) if payload.get("tid") else None,
        role=payload.get("role", ""),
        permissions=payload.get("perms", []),
        is_super_admin=bool(payload.get("sa", False)),
    )


async def get_tenant_id(current: CurrentUser = Depends(get_current_user)) -> UUID:
    if current.tenant_id is None:
        raise AuthorizationError("No tenant context in token")
    return current.tenant_id


def require_permission(perm: str):
    async def checker(current: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not current.has_permission(perm):
            raise AuthorizationError(f"Missing permission: {perm}")
        return current

    return checker

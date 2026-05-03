"""Business logic for Identity: login, registration, token refresh."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    NotFoundError,
)
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.modules.identity.models import RefreshToken, Tenant, TenantUser, User
from app.modules.identity.repository import IdentityRepository
from app.modules.identity.schemas import (
    LoginRequest,
    RegisterTenantRequest,
    TokenPair,
)


class IdentityService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = IdentityRepository(session)

    # ─── Login ──────────────────────────────────────────
    async def login(self, payload: LoginRequest, *, ip: str | None = None) -> TokenPair:
        user = await self.repo.get_user_by_email(payload.email)
        if not user or not user.is_active:
            raise AuthenticationError("Invalid credentials")

        if user.locked_until and user.locked_until > datetime.now(UTC):
            raise AuthenticationError("Account locked. Try again later.")

        if not verify_password(payload.password, user.password_hash):
            await self.repo.increment_failed_login(user.id)
            raise AuthenticationError("Invalid credentials")

        # Resolve tenant: super_admin can login without tenant; others must have membership
        tenant_id, role_name, perms = await self._resolve_tenant_context(user, payload.tenant_slug)

        await self.repo.reset_failed_login(user.id)

        return await self._issue_tokens(
            user=user,
            tenant_id=tenant_id,
            role=role_name,
            perms=perms,
            ip=ip,
        )

    async def _resolve_tenant_context(
        self, user: User, tenant_slug: str | None
    ) -> tuple[UUID | None, str, list[str]]:
        if user.is_super_admin and tenant_slug is None:
            return None, "super_admin", ["*"]

        memberships = await self.repo.list_user_memberships(user.id)
        if not memberships:
            raise AuthorizationError("User has no tenant access")

        if tenant_slug:
            membership = next((m for m in memberships if m.tenant.slug == tenant_slug), None)
            if not membership:
                raise AuthorizationError(f"No access to tenant '{tenant_slug}'")
        elif len(memberships) == 1:
            membership = memberships[0]
        else:
            # Multiple tenants — client must specify
            raise AuthorizationError(
                "Multiple tenants — specify 'tenant_slug'",
            )

        role = await self.repo.get_role(membership.role_id)
        if not role:
            raise NotFoundError("Role not found")
        perms = await self.repo.get_permissions_for_role(role.id)
        return membership.tenant_id, role.name, perms

    # ─── Register Tenant (signup) ────────────────────────
    async def register_tenant(self, payload: RegisterTenantRequest) -> Tenant:
        if await self.repo.get_tenant_by_slug(payload.tenant_slug):
            raise ConflictError(f"Tenant slug '{payload.tenant_slug}' already taken")

        if await self.repo.get_user_by_email(payload.owner_email):
            raise ConflictError(f"Email '{payload.owner_email}' already registered")

        tenant = Tenant(name=payload.tenant_name, slug=payload.tenant_slug)
        await self.repo.add_tenant(tenant)

        user = User(
            email=payload.owner_email,
            password_hash=hash_password(payload.owner_password),
            full_name=payload.owner_full_name,
        )
        await self.repo.add_user(user)

        owner_role = await self.repo.get_role_by_name("admin", tenant_id=None)
        if not owner_role:
            raise NotFoundError("System role 'admin' not seeded")

        await self.repo.add_membership(
            TenantUser(
                tenant_id=tenant.id,
                user_id=user.id,
                role_id=owner_role.id,
                is_owner=True,
                accepted_at=datetime.now(UTC),
            )
        )

        from app.core.events import publish
        await publish("tenant.registered", {
            "tenant_id": str(tenant.id),
            "tenant_name": tenant.name,
            "owner_email": user.email,
            "owner_name": user.full_name,
        })
        return tenant

    # ─── Refresh ────────────────────────────────────────
    async def refresh(self, raw_token: str, *, ip: str | None = None) -> TokenPair:
        token_hash = hash_refresh_token(raw_token)
        rt = await self.repo.get_refresh_token_by_hash(token_hash)
        if not rt or rt.expires_at < datetime.now(UTC):
            raise AuthenticationError("Invalid or expired refresh token")

        user = await self.repo.get_user(rt.user_id)
        if not user or not user.is_active:
            raise AuthenticationError("User inactive")

        # Token rotation: revoke old, issue new
        await self.repo.revoke_refresh_token(rt)

        # Reload tenant context (single membership inferred)
        tenant_id, role_name, perms = await self._resolve_tenant_context(user, None)

        return await self._issue_tokens(user=user, tenant_id=tenant_id, role=role_name, perms=perms, ip=ip)

    # ─── Helpers ────────────────────────────────────────
    async def _issue_tokens(
        self,
        *,
        user: User,
        tenant_id: UUID | None,
        role: str,
        perms: list[str],
        ip: str | None,
    ) -> TokenPair:
        access = create_access_token(
            user_id=str(user.id),
            tenant_id=str(tenant_id) if tenant_id else None,
            role=role,
            permissions=perms,
            is_super_admin=user.is_super_admin,
        )
        raw_refresh, hashed, expires_at = create_refresh_token()
        await self.repo.add_refresh_token(
            RefreshToken(
                user_id=user.id,
                token_hash=hashed,
                expires_at=expires_at,
                ip_address=ip,
            )
        )

        from app.config import settings as app_settings

        return TokenPair(
            access_token=access,
            refresh_token=raw_refresh,
            expires_in=app_settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

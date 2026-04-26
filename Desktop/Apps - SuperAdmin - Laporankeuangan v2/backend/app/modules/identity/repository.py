"""Data access layer for Identity module."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.identity.models import (
    Permission,
    RefreshToken,
    Role,
    RolePermission,
    Tenant,
    TenantUser,
    User,
)


class IdentityRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    # ── Users ────────────────────────────────────────────────
    async def get_user_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_user(self, user_id: UUID) -> User | None:
        return await self.session.get(User, user_id)

    async def add_user(self, user: User) -> User:
        self.session.add(user)
        await self.session.flush()
        return user

    async def increment_failed_login(self, user_id: UUID) -> None:
        user = await self.get_user(user_id)
        if not user:
            return
        user.failed_login_count += 1
        if user.failed_login_count >= 5:
            user.locked_until = datetime.now(UTC).replace(microsecond=0)
        await self.session.flush()

    async def reset_failed_login(self, user_id: UUID) -> None:
        user = await self.get_user(user_id)
        if not user:
            return
        user.failed_login_count = 0
        user.locked_until = None
        user.last_login_at = datetime.now(UTC)
        await self.session.flush()

    # ── Tenants ──────────────────────────────────────────────
    async def get_tenant_by_slug(self, slug: str) -> Tenant | None:
        stmt = select(Tenant).where(Tenant.slug == slug, Tenant.deleted_at.is_(None))
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_tenant(self, tenant_id: UUID) -> Tenant | None:
        return await self.session.get(Tenant, tenant_id)

    async def add_tenant(self, tenant: Tenant) -> Tenant:
        self.session.add(tenant)
        await self.session.flush()
        return tenant

    # ── Memberships ──────────────────────────────────────────
    async def get_membership(self, user_id: UUID, tenant_id: UUID) -> TenantUser | None:
        stmt = (
            select(TenantUser)
            .options(selectinload(TenantUser.tenant))
            .where(TenantUser.user_id == user_id, TenantUser.tenant_id == tenant_id)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_user_memberships(self, user_id: UUID) -> list[TenantUser]:
        stmt = (
            select(TenantUser).options(selectinload(TenantUser.tenant)).where(TenantUser.user_id == user_id)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def add_membership(self, membership: TenantUser) -> TenantUser:
        self.session.add(membership)
        await self.session.flush()
        return membership

    # ── Roles & Permissions ──────────────────────────────────
    async def get_role(self, role_id: UUID) -> Role | None:
        return await self.session.get(Role, role_id)

    async def get_role_by_name(self, name: str, tenant_id: UUID | None) -> Role | None:
        stmt = select(Role).where(Role.name == name, Role.tenant_id == tenant_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_permissions_for_role(self, role_id: UUID) -> list[str]:
        stmt = (
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == role_id)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_permissions(self) -> list[Permission]:
        stmt = select(Permission).order_by(Permission.code)
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_permissions_by_codes(self, codes: list[str]) -> list[Permission]:
        if not codes:
            return []
        stmt = select(Permission).where(Permission.code.in_(codes))
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_roles_for_tenant(self, tenant_id: UUID) -> list[Role]:
        """All roles available to a tenant: system roles (tenant_id IS NULL)
        + this tenant's own custom roles."""
        from sqlalchemy import or_

        stmt = (
            select(Role)
            .where(or_(Role.tenant_id.is_(None), Role.tenant_id == tenant_id))
            .order_by(Role.is_system.desc(), Role.name)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def add_role(self, role: Role) -> Role:
        self.session.add(role)
        await self.session.flush()
        return role

    async def replace_role_permissions(self, role_id: UUID, permission_ids: list[UUID]) -> None:
        """Wipe and re-attach the role's permission set in one go."""
        await self.session.execute(RolePermission.__table__.delete().where(RolePermission.role_id == role_id))
        for pid in permission_ids:
            self.session.add(RolePermission(role_id=role_id, permission_id=pid))
        await self.session.flush()

    async def delete_role(self, role: Role) -> None:
        await self.session.delete(role)
        await self.session.flush()

    async def count_users_with_role(self, role_id: UUID) -> int:
        from sqlalchemy import func as _f

        from app.modules.identity.models import TenantUser

        stmt = select(_f.count(TenantUser.user_id)).where(TenantUser.role_id == role_id)
        return (await self.session.execute(stmt)).scalar_one() or 0

    # ── Refresh tokens ───────────────────────────────────────
    async def add_refresh_token(self, rt: RefreshToken) -> RefreshToken:
        self.session.add(rt)
        await self.session.flush()
        return rt

    async def get_refresh_token_by_hash(self, token_hash: str) -> RefreshToken | None:
        stmt = select(RefreshToken).where(
            RefreshToken.token_hash == token_hash, RefreshToken.revoked_at.is_(None)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def revoke_refresh_token(self, rt: RefreshToken) -> None:
        rt.revoked_at = datetime.now(UTC)
        await self.session.flush()

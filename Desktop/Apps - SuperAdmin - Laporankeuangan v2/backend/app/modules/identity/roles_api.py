"""Role + permission management — admin-only.

System roles (tenant_id IS NULL) are read-only here. Tenant-scoped
roles can be created, updated, and deleted by tenants holding the
`role.manage` permission.
"""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_write_session
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.deps import CurrentUser, require_permission
from app.modules.identity.models import Role
from app.modules.identity.repository import IdentityRepository
from app.modules.identity.schemas import (
    PermissionOut,
    RoleCreate,
    RoleOut,
    RoleUpdate,
)

router = APIRouter(tags=["roles"])


async def _to_role_out(repo: IdentityRepository, role: Role) -> RoleOut:
    perms = await repo.get_permissions_for_role(role.id)
    return RoleOut(
        id=role.id,
        tenant_id=role.tenant_id,
        name=role.name,
        description=role.description,
        is_system=role.is_system,
        permissions=sorted(perms),
    )


@router.get(
    "/permissions",
    response_model=list[PermissionOut],
    summary="List all permission codes available in this system",
)
async def list_permissions(
    current: CurrentUser = Depends(require_permission("role.manage")),
    session: AsyncSession = Depends(get_write_session),
) -> list[PermissionOut]:
    repo = IdentityRepository(session)
    perms = await repo.list_permissions()
    return [PermissionOut.model_validate(p) for p in perms]


@router.get(
    "/roles",
    response_model=list[RoleOut],
    summary="List system + tenant-scoped roles available to this tenant",
)
async def list_roles(
    current: CurrentUser = Depends(require_permission("role.manage")),
    session: AsyncSession = Depends(get_write_session),
) -> list[RoleOut]:
    repo = IdentityRepository(session)
    roles = await repo.list_roles_for_tenant(current.tenant_id)
    return [await _to_role_out(repo, r) for r in roles]


@router.get("/roles/{role_id}", response_model=RoleOut)
async def get_role(
    role_id: UUID,
    current: CurrentUser = Depends(require_permission("role.manage")),
    session: AsyncSession = Depends(get_write_session),
) -> RoleOut:
    repo = IdentityRepository(session)
    role = await repo.get_role(role_id)
    if not role or (role.tenant_id is not None and role.tenant_id != current.tenant_id):
        raise NotFoundError("Role not found")
    return await _to_role_out(repo, role)


@router.post("/roles", response_model=RoleOut, status_code=201)
async def create_role(
    payload: RoleCreate,
    current: CurrentUser = Depends(require_permission("role.manage")),
    session: AsyncSession = Depends(get_write_session),
) -> RoleOut:
    repo = IdentityRepository(session)

    # Block creating a tenant role with the same name as an existing system
    # role (e.g. "admin") OR a duplicate within this tenant
    if await repo.get_role_by_name(payload.name, tenant_id=None):
        raise ConflictError(f"Role name '{payload.name}' is reserved by a system role")
    if await repo.get_role_by_name(payload.name, tenant_id=current.tenant_id):
        raise ConflictError(f"Role '{payload.name}' already exists in this tenant")

    perms = await repo.get_permissions_by_codes(payload.permission_codes)
    perm_codes = {p.code for p in perms}
    missing = set(payload.permission_codes) - perm_codes
    if missing:
        raise ValidationError(f"Unknown permission codes: {sorted(missing)}")

    role = Role(
        tenant_id=current.tenant_id,
        name=payload.name,
        description=payload.description,
        is_system=False,
    )
    role = await repo.add_role(role)
    await repo.replace_role_permissions(role.id, [p.id for p in perms])
    return await _to_role_out(repo, role)


@router.patch("/roles/{role_id}", response_model=RoleOut)
async def update_role(
    role_id: UUID,
    payload: RoleUpdate,
    current: CurrentUser = Depends(require_permission("role.manage")),
    session: AsyncSession = Depends(get_write_session),
) -> RoleOut:
    repo = IdentityRepository(session)
    role = await repo.get_role(role_id)
    if not role or (role.tenant_id is not None and role.tenant_id != current.tenant_id):
        raise NotFoundError("Role not found")
    if role.is_system or role.tenant_id is None:
        raise ValidationError("System roles cannot be modified")

    if payload.name is not None and payload.name != role.name:
        # Disallow taking a system role's name
        if await repo.get_role_by_name(payload.name, tenant_id=None):
            raise ConflictError(f"Role name '{payload.name}' is reserved by a system role")
        # Disallow conflicting with an existing tenant role
        existing = await repo.get_role_by_name(payload.name, tenant_id=current.tenant_id)
        if existing and existing.id != role.id:
            raise ConflictError(f"Role '{payload.name}' already exists in this tenant")
        role.name = payload.name

    if payload.description is not None:
        role.description = payload.description

    if payload.permission_codes is not None:
        if not payload.permission_codes:
            raise ValidationError("A role must have at least one permission")
        perms = await repo.get_permissions_by_codes(payload.permission_codes)
        perm_codes = {p.code for p in perms}
        missing = set(payload.permission_codes) - perm_codes
        if missing:
            raise ValidationError(f"Unknown permission codes: {sorted(missing)}")
        await repo.replace_role_permissions(role.id, [p.id for p in perms])

    await session.flush()
    return await _to_role_out(repo, role)


@router.delete("/roles/{role_id}", status_code=204)
async def delete_role(
    role_id: UUID,
    current: CurrentUser = Depends(require_permission("role.manage")),
    session: AsyncSession = Depends(get_write_session),
) -> None:
    repo = IdentityRepository(session)
    role = await repo.get_role(role_id)
    if not role or (role.tenant_id is not None and role.tenant_id != current.tenant_id):
        raise NotFoundError("Role not found")
    if role.is_system or role.tenant_id is None:
        raise ValidationError("System roles cannot be deleted")

    in_use = await repo.count_users_with_role(role.id)
    if in_use > 0:
        raise ConflictError(
            f"Role '{role.name}' is still assigned to {in_use} user(s); reassign them before deleting"
        )

    await repo.delete_role(role)

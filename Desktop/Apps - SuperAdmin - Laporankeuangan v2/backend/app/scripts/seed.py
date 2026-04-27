"""Seed system roles and permissions.

Run:
    python -m app.scripts.seed
"""

import asyncio

from sqlalchemy import select

from app.core.database import transaction
from app.modules.identity.models import Permission, Role, RolePermission

# ── Permission catalog ─────────────────────────────────────
PERMISSIONS: list[tuple[str, str]] = [
    # Identity
    ("user.read", "View users"),
    ("user.write", "Create/update users"),
    ("user.delete", "Delete users"),
    ("role.manage", "Manage roles & permissions"),
    # Accounting
    ("coa.read", "View chart of accounts"),
    ("coa.write", "Create/update accounts"),
    ("journal.read", "View journal entries"),
    ("journal.write", "Create/update journal entries"),
    ("journal.post", "Post journal entries"),
    # Sales / Purchase
    ("sales.read", "View sales (incl. customers + invoices)"),
    ("sales.write", "Create/update customers + sales invoices"),
    ("sales.post", "Post / void sales invoices (creates journals)"),
    ("purchase.read", "View purchases (incl. suppliers + invoices)"),
    ("purchase.write", "Create/update suppliers + purchase invoices"),
    ("purchase.post", "Post / void purchase invoices (creates journals)"),
    # Payments
    ("payment.read", "View payments (cash receipts + disbursements)"),
    ("payment.write", "Create payments (drafts)"),
    ("payment.post", "Post / void payments (creates journals + settles invoices)"),
    # Audit
    ("audit.read", "View audit logs"),
    # Periods
    ("period.close", "Close / reopen accounting periods"),
    # Inventory
    ("inventory.read", "View items, warehouses, stock balances"),
    ("inventory.write", "Create/update items, warehouses, manual stock movements"),
    # Reports
    ("report.read", "View reports"),
    ("report.export", "Export reports"),
    # Tenant admin
    ("tenant.settings", "Manage tenant settings"),
    ("tenant.billing", "Manage billing"),
]

# ── System role definitions ─────────────────────────────────
ROLES: dict[str, list[str]] = {
    "admin": [code for code, _ in PERMISSIONS],
    "accountant": [
        "coa.read",
        "coa.write",
        "journal.read",
        "journal.write",
        "journal.post",
        "sales.read",
        "sales.write",
        "sales.post",
        "purchase.read",
        "purchase.write",
        "purchase.post",
        "payment.read",
        "payment.write",
        "payment.post",
        "report.read",
        "report.export",
        "audit.read",
        "period.close",
        "inventory.read",
        "inventory.write",
    ],
    "staff": [
        "coa.read",
        "journal.read",
        "journal.write",
        "sales.read",
        "sales.write",
        "purchase.read",
        "purchase.write",
        "payment.read",
        "payment.write",
        "report.read",
        "inventory.read",
        "inventory.write",
    ],
    "viewer": [
        "coa.read",
        "journal.read",
        "sales.read",
        "purchase.read",
        "report.read",
        "inventory.read",
    ],
}


async def seed() -> None:
    async with transaction() as session:
        # Permissions
        existing_perms = {p.code: p for p in (await session.execute(select(Permission))).scalars().all()}
        for code, desc in PERMISSIONS:
            if code not in existing_perms:
                p = Permission(code=code, description=desc)
                session.add(p)
                existing_perms[code] = p
        await session.flush()

        # System roles (tenant_id IS NULL)
        existing_roles = {
            r.name: r
            for r in (
                await session.execute(select(Role).where(Role.tenant_id.is_(None), Role.is_system.is_(True)))
            )
            .scalars()
            .all()
        }

        for role_name, perm_codes in ROLES.items():
            role = existing_roles.get(role_name)
            if role is None:
                role = Role(
                    tenant_id=None,
                    name=role_name,
                    description=f"System role: {role_name}",
                    is_system=True,
                )
                session.add(role)
                await session.flush()

            # Wipe + re-attach permissions (idempotent)
            await session.execute(RolePermission.__table__.delete().where(RolePermission.role_id == role.id))
            for code in perm_codes:
                perm = existing_perms[code]
                session.add(RolePermission(role_id=role.id, permission_id=perm.id))

        print(f"Seeded {len(PERMISSIONS)} permissions and {len(ROLES)} system roles.")


if __name__ == "__main__":
    asyncio.run(seed())

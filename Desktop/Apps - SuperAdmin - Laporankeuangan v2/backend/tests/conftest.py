"""Test fixtures.

Strategy:
- Dedicated Postgres database (TEST_DB_URL env, default `kompak_test`).
- Once per session: drop+create the schema via Base.metadata, install citext.
- Per test (autouse): TRUNCATE all tables, then re-seed system roles +
  permissions. This is fast (no bcrypt, just inserts) and guarantees
  perfect isolation regardless of test order.
- HTTP via httpx ASGITransport — direct against the FastAPI app.
"""

from __future__ import annotations

import os

# Set required env vars BEFORE any app imports (Settings reads eagerly)
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-at-least-32-characters-long-OK")
DEFAULT_TEST_DB_URL = "postgresql+asyncpg://kompak:kompak_dev@localhost:5432/kompak_test"
TEST_DB_URL = os.getenv("TEST_DB_URL", DEFAULT_TEST_DB_URL)
os.environ["DB_PRIMARY_URL"] = TEST_DB_URL
os.environ.setdefault("APP_ENV", "test")

from collections.abc import AsyncGenerator  # noqa: E402

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Import all models so Base.metadata is fully populated
from app.core.database import Base, get_read_session, get_write_session  # noqa: E402
from app.modules.accounting import models as _accounting  # noqa: F401, E402
from app.modules.identity import models as _identity  # noqa: F401, E402
from app.modules.purchase import models as _purchase  # noqa: F401, E402
from app.modules.sales import models as _sales  # noqa: F401, E402

# Tables to wipe between tests (in order ignoring FKs — we use TRUNCATE
# with the full set, so order is irrelevant).
ALL_TABLES = [
    "refresh_tokens",
    "tenant_users",
    "role_permissions",
    "roles",
    "permissions",
    "account_mappings",
    "journal_lines",
    "journal_entries",
    "sales_invoice_lines",
    "sales_invoices",
    "customers",
    "purchase_invoice_lines",
    "purchase_invoices",
    "suppliers",
    "accounts",
    "users",
    "tenants",
]


async def _create_journal_partitions(conn, year_from: int = 2024, year_to: int = 2030) -> None:
    """Create monthly partitions for journal_entries and journal_lines.

    Mirrors what migration 0004 does in production. Tests use Base.metadata
    (not Alembic), so we have to create partitions manually after create_all.
    """
    for table in ("journal_entries", "journal_lines"):
        for year in range(year_from, year_to + 1):
            for month in range(1, 13):
                next_year, next_month = (year, month + 1) if month < 12 else (year + 1, 1)
                name = f"{table}_y{year}_m{month:02d}"
                await conn.execute(
                    text(
                        f"CREATE TABLE IF NOT EXISTS {name} PARTITION OF {table} "
                        f"FOR VALUES FROM ('{year}-{month:02d}-01') "
                        f"TO ('{next_year}-{next_month:02d}-01')"
                    )
                )


# ── Engine + schema (session-scoped) ──────────────────────
@pytest_asyncio.fixture(scope="session")
async def engine():
    eng = create_async_engine(TEST_DB_URL, echo=False, future=True)
    async with eng.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS citext"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        await _create_journal_partitions(conn)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest_asyncio.fixture(scope="session")
async def session_factory(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def _seed_system_roles(session_factory) -> None:
    from app.modules.identity.models import Permission, Role, RolePermission
    from app.scripts.seed import PERMISSIONS, ROLES

    async with session_factory() as s:
        for code, desc in PERMISSIONS:
            s.add(Permission(code=code, description=desc))
        await s.flush()
        perms_by_code = {p.code: p for p in (await s.execute(select(Permission))).scalars().all()}
        for role_name, codes in ROLES.items():
            role = Role(
                tenant_id=None,
                name=role_name,
                description=f"System role: {role_name}",
                is_system=True,
            )
            s.add(role)
            await s.flush()
            for code in codes:
                s.add(RolePermission(role_id=role.id, permission_id=perms_by_code[code].id))
        await s.commit()


# ── Per-test reset (autouse) ──────────────────────────────
@pytest_asyncio.fixture(autouse=True)
async def _reset_db(session_factory):
    async with session_factory() as s:
        await s.execute(text(f"TRUNCATE TABLE {', '.join(ALL_TABLES)} RESTART IDENTITY CASCADE"))
        await s.commit()
    await _seed_system_roles(session_factory)
    yield


# ── HTTP client with overridden DB dep ────────────────────
@pytest_asyncio.fixture
async def client(session_factory) -> AsyncGenerator[AsyncClient, None]:
    from app.main import app

    async def _override_write():
        async with session_factory() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    async def _override_read():
        async with session_factory() as s:
            yield s

    app.dependency_overrides[get_write_session] = _override_write
    app.dependency_overrides[get_read_session] = _override_read
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


# ── High-level helpers ────────────────────────────────────
@pytest_asyncio.fixture
async def tenant_token(client: AsyncClient) -> dict:
    """Register a tenant + login, return access/refresh tokens + auth headers."""
    payload = {
        "tenant_name": "Acme Corp",
        "tenant_slug": "acme",
        "owner_email": "owner@acme.test",
        "owner_password": "Passw0rd!",
        "owner_full_name": "Owner User",
    }
    r = await client.post("/api/v1/auth/register-tenant", json=payload)
    assert r.status_code == 201, r.text

    r = await client.post(
        "/api/v1/auth/login",
        json={
            "email": payload["owner_email"],
            "password": payload["owner_password"],
            "tenant_slug": payload["tenant_slug"],
        },
    )
    assert r.status_code == 200, r.text
    tokens = r.json()
    return {
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "tenant_slug": payload["tenant_slug"],
        "headers": {"Authorization": f"Bearer {tokens['access_token']}"},
    }


@pytest_asyncio.fixture
async def seeded_tenant(client: AsyncClient, tenant_token: dict) -> dict:
    """Tenant with starter COA + account mappings already provisioned."""
    r = await client.post("/api/v1/accounts/seed-starter-coa", headers=tenant_token["headers"])
    assert r.status_code == 200, r.text
    return tenant_token

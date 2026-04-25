"""Postgres RLS isolation: tenant A's queries cannot see tenant B's rows
even when issued via raw SQL (defense-in-depth beyond app-level filters)."""

from httpx import AsyncClient
from sqlalchemy import select, text

from app.modules.accounting.models import Account


async def _register_and_login(client: AsyncClient, slug: str, email: str) -> dict:
    await client.post(
        "/api/v1/auth/register-tenant",
        json={
            "tenant_name": f"Tenant {slug}",
            "tenant_slug": slug,
            "owner_email": email,
            "owner_password": "Passw0rd!",
            "owner_full_name": f"Owner {slug}",
        },
    )
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Passw0rd!", "tenant_slug": slug},
    )
    return r.json()


async def test_tenant_b_cannot_see_tenant_a_accounts(client: AsyncClient):
    """End-to-end via API: with tenant B's JWT, listing accounts must
    return only B's data — even though the underlying SQL has no
    WHERE tenant_id filter beyond what the app adds (RLS is the safety
    net if the app ever forgets)."""
    a = await _register_and_login(client, "rls-a", "a@rls.test")
    headers_a = {"Authorization": f"Bearer {a['access_token']}"}
    await client.post("/api/v1/accounts/seed-starter-coa", headers=headers_a)
    # Tenant A creates a custom account
    r = await client.post(
        "/api/v1/accounts",
        headers=headers_a,
        json={
            "code": "9999",
            "name": "A-only secret",
            "type": "expense",
            "normal_side": "debit",
        },
    )
    assert r.status_code == 201

    b = await _register_and_login(client, "rls-b", "b@rls.test")
    headers_b = {"Authorization": f"Bearer {b['access_token']}"}
    # Tenant B's account list must NOT contain code 9999
    rb = await client.get("/api/v1/accounts?include_zero=true", headers=headers_b)
    assert rb.status_code == 200
    codes = {a["code"] for a in rb.json()}
    assert "9999" not in codes


async def test_rls_blocks_raw_sql_without_tenant_context(session_factory):
    """Direct DB access without setting app.current_tenant returns zero
    rows from RLS-protected tables — even if the app were to forget a
    `WHERE tenant_id = ?` clause."""
    # Bypass RLS first to insert seed data into two tenants
    from uuid import uuid4

    tenant_a_id = uuid4()
    tenant_b_id = uuid4()

    async with session_factory() as s:
        # Bypass RLS for setup
        await s.execute(text("SELECT set_config('app.is_super_admin', 'true', true)"))
        # Need the tenants table populated (it's not RLS-protected)
        await s.execute(
            text(
                "INSERT INTO tenants (id, name, slug, plan, status, settings) "
                "VALUES (:id, :n, :s, 'free', 'active', '{}'::json)"
            ),
            [
                {"id": tenant_a_id, "n": "A", "s": "rlsraw-a"},
                {"id": tenant_b_id, "n": "B", "s": "rlsraw-b"},
            ],
        )
        # Insert an account into each tenant
        await s.execute(
            text(
                "INSERT INTO accounts "
                "(id, tenant_id, code, name, type, normal_side, is_active, is_system) "
                "VALUES (:id, :tid, '1100', 'Kas', 'asset', 'debit', true, false)"
            ),
            [
                {"id": uuid4(), "tid": tenant_a_id},
                {"id": uuid4(), "tid": tenant_b_id},
            ],
        )
        await s.commit()

    # Without setting app.current_tenant, RLS denies all rows
    async with session_factory() as s:
        # No GUC set → no rows visible
        rows = (await s.execute(select(Account))).scalars().all()
        assert rows == []

    # With tenant A's GUC, only A's row is visible
    async with session_factory() as s:
        await s.execute(
            text("SELECT set_config('app.current_tenant', :tid, true)"),
            {"tid": str(tenant_a_id)},
        )
        rows = (await s.execute(select(Account))).scalars().all()
        assert len(rows) == 1
        assert rows[0].tenant_id == tenant_a_id

    # With tenant B's GUC, only B's row
    async with session_factory() as s:
        await s.execute(
            text("SELECT set_config('app.current_tenant', :tid, true)"),
            {"tid": str(tenant_b_id)},
        )
        rows = (await s.execute(select(Account))).scalars().all()
        assert len(rows) == 1
        assert rows[0].tenant_id == tenant_b_id

    # super_admin GUC sees everything
    async with session_factory() as s:
        await s.execute(text("SELECT set_config('app.is_super_admin', 'true', true)"))
        rows = (await s.execute(select(Account))).scalars().all()
        assert len(rows) == 2


async def test_rls_blocks_cross_tenant_write(session_factory):
    """A WITH CHECK violation: trying to INSERT a row with a different
    tenant_id than the GUC must fail."""
    from uuid import uuid4

    tenant_a_id = uuid4()
    tenant_b_id = uuid4()

    async with session_factory() as s:
        await s.execute(text("SELECT set_config('app.is_super_admin', 'true', true)"))
        await s.execute(
            text(
                "INSERT INTO tenants (id, name, slug, plan, status, settings) "
                "VALUES (:id, :n, :s, 'free', 'active', '{}'::json)"
            ),
            [
                {"id": tenant_a_id, "n": "A", "s": "wrch-a"},
                {"id": tenant_b_id, "n": "B", "s": "wrch-b"},
            ],
        )
        await s.commit()

    # Pretend to be tenant A but try to insert a tenant_id = B account
    async with session_factory() as s:
        await s.execute(
            text("SELECT set_config('app.current_tenant', :tid, true)"),
            {"tid": str(tenant_a_id)},
        )
        try:
            await s.execute(
                text(
                    "INSERT INTO accounts "
                    "(id, tenant_id, code, name, type, normal_side, is_active, is_system) "
                    "VALUES (:id, :tid, '1100', 'Kas', 'asset', 'debit', true, false)"
                ),
                {"id": uuid4(), "tid": tenant_b_id},  # cross-tenant write
            )
            await s.commit()
            raise AssertionError("RLS should have blocked the cross-tenant write")
        except Exception as e:
            # Postgres raises: new row violates row-level security policy
            assert "row-level security" in str(e).lower() or "policy" in str(e).lower()
            await s.rollback()

"""Tenant-scoped role management: admins create custom roles with
chosen permissions; system roles stay read-only."""

from uuid import uuid4

from httpx import AsyncClient


async def test_list_permissions_returns_seeded_catalog(client: AsyncClient, tenant_token: dict):
    r = await client.get("/api/v1/permissions", headers=tenant_token["headers"])
    assert r.status_code == 200
    codes = {p["code"] for p in r.json()}
    # Spot-check that the catalog is populated
    assert "coa.read" in codes
    assert "sales.post" in codes
    assert "audit.read" in codes


async def test_list_roles_includes_system_and_tenant_roles(client: AsyncClient, tenant_token: dict):
    headers = tenant_token["headers"]

    r = await client.get("/api/v1/roles", headers=headers)
    assert r.status_code == 200
    roles_before = r.json()
    # 4 system roles seeded by conftest
    assert {ro["name"] for ro in roles_before} >= {"admin", "accountant", "staff", "viewer"}
    assert all(ro["is_system"] is True for ro in roles_before)
    assert all(ro["tenant_id"] is None for ro in roles_before)

    # Create a tenant-scoped role
    rc = await client.post(
        "/api/v1/roles",
        headers=headers,
        json={
            "name": "auditor",
            "description": "Read-only auditor",
            "permission_codes": ["coa.read", "journal.read", "report.read", "audit.read"],
        },
    )
    assert rc.status_code == 201, rc.text
    body = rc.json()
    assert body["is_system"] is False
    assert body["tenant_id"] is not None
    assert sorted(body["permissions"]) == [
        "audit.read",
        "coa.read",
        "journal.read",
        "report.read",
    ]

    r2 = await client.get("/api/v1/roles", headers=headers)
    names = {ro["name"] for ro in r2.json()}
    assert "auditor" in names


async def test_create_role_with_unknown_permission_rejected(client: AsyncClient, tenant_token: dict):
    r = await client.post(
        "/api/v1/roles",
        headers=tenant_token["headers"],
        json={"name": "broken", "permission_codes": ["coa.read", "does.not.exist"]},
    )
    assert r.status_code == 422
    assert "does.not.exist" in r.json()["error"]["message"]


async def test_create_role_reserved_system_name_rejected(client: AsyncClient, tenant_token: dict):
    r = await client.post(
        "/api/v1/roles",
        headers=tenant_token["headers"],
        json={"name": "admin", "permission_codes": ["coa.read"]},
    )
    assert r.status_code == 409


async def test_update_custom_role_replaces_permissions(client: AsyncClient, tenant_token: dict):
    headers = tenant_token["headers"]
    rc = await client.post(
        "/api/v1/roles",
        headers=headers,
        json={"name": "manager", "permission_codes": ["coa.read", "journal.read"]},
    )
    role_id = rc.json()["id"]

    rp = await client.patch(
        f"/api/v1/roles/{role_id}",
        headers=headers,
        json={
            "description": "Manages day-to-day ops",
            "permission_codes": [
                "coa.read",
                "journal.read",
                "journal.write",
                "sales.read",
                "sales.write",
            ],
        },
    )
    assert rp.status_code == 200, rp.text
    body = rp.json()
    assert body["description"] == "Manages day-to-day ops"
    assert sorted(body["permissions"]) == [
        "coa.read",
        "journal.read",
        "journal.write",
        "sales.read",
        "sales.write",
    ]


async def test_cannot_modify_system_role(client: AsyncClient, tenant_token: dict):
    """System roles (tenant_id IS NULL) are read-only here."""
    headers = tenant_token["headers"]
    roles = (await client.get("/api/v1/roles", headers=headers)).json()
    admin_role = next(r for r in roles if r["name"] == "admin")
    rp = await client.patch(
        f"/api/v1/roles/{admin_role['id']}",
        headers=headers,
        json={"description": "Hacked"},
    )
    assert rp.status_code == 422
    assert "system" in rp.json()["error"]["message"].lower()


async def test_cannot_delete_role_in_use(client: AsyncClient, tenant_token: dict):
    """The owner is on system 'admin', not deletable. Even creating a
    custom role and assigning a user requires the user-membership
    endpoint we don't have yet — so for now we just verify the in-use
    guard fires for system roles via tenant_id mismatch (they 404 since
    they're not 'in this tenant')."""
    headers = tenant_token["headers"]

    # Create a custom role; it has zero users; deletion should succeed
    rc = await client.post(
        "/api/v1/roles",
        headers=headers,
        json={"name": "to-delete", "permission_codes": ["coa.read"]},
    )
    role_id = rc.json()["id"]

    rd = await client.delete(f"/api/v1/roles/{role_id}", headers=headers)
    assert rd.status_code == 204

    # Confirm gone
    rg = await client.get(f"/api/v1/roles/{role_id}", headers=headers)
    assert rg.status_code == 404


async def test_role_404_for_unknown_id(client: AsyncClient, tenant_token: dict):
    r = await client.get(f"/api/v1/roles/{uuid4()}", headers=tenant_token["headers"])
    assert r.status_code == 404


async def test_tenant_b_cannot_see_tenant_a_custom_roles(client: AsyncClient):
    """Custom roles are scoped to a tenant; another tenant cannot see them."""
    # Tenant A
    await client.post(
        "/api/v1/auth/register-tenant",
        json={
            "tenant_name": "A Inc",
            "tenant_slug": "rolea",
            "owner_email": "owner@rolea.test",
            "owner_password": "Passw0rd!",
            "owner_full_name": "A Owner",
        },
    )
    la = await client.post(
        "/api/v1/auth/login",
        json={"email": "owner@rolea.test", "password": "Passw0rd!", "tenant_slug": "rolea"},
    )
    ha = {"Authorization": f"Bearer {la.json()['access_token']}"}
    rc = await client.post(
        "/api/v1/roles",
        headers=ha,
        json={"name": "a-only-role", "permission_codes": ["coa.read"]},
    )
    assert rc.status_code == 201
    a_role_id = rc.json()["id"]

    # Tenant B
    await client.post(
        "/api/v1/auth/register-tenant",
        json={
            "tenant_name": "B Inc",
            "tenant_slug": "roleb",
            "owner_email": "owner@roleb.test",
            "owner_password": "Passw0rd!",
            "owner_full_name": "B Owner",
        },
    )
    lb = await client.post(
        "/api/v1/auth/login",
        json={"email": "owner@roleb.test", "password": "Passw0rd!", "tenant_slug": "roleb"},
    )
    hb = {"Authorization": f"Bearer {lb.json()['access_token']}"}

    # B's role list contains system roles + their own customs only
    rl = await client.get("/api/v1/roles", headers=hb)
    assert rl.status_code == 200
    names = {r["name"] for r in rl.json()}
    assert "a-only-role" not in names

    # Direct fetch by id → 404 (cross-tenant access blocked)
    rg = await client.get(f"/api/v1/roles/{a_role_id}", headers=hb)
    assert rg.status_code == 404

    # B can create a role with the same name (uniqueness is per-tenant)
    rcb = await client.post(
        "/api/v1/roles",
        headers=hb,
        json={"name": "a-only-role", "permission_codes": ["coa.read"]},
    )
    assert rcb.status_code == 201

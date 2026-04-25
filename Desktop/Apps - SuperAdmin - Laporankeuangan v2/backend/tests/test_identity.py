"""Identity flow: register → login → me → refresh."""

from httpx import AsyncClient


async def test_register_tenant_creates_owner_membership(client: AsyncClient):
    r = await client.post(
        "/api/v1/auth/register-tenant",
        json={
            "tenant_name": "Acme",
            "tenant_slug": "acme",
            "owner_email": "owner@acme.test",
            "owner_password": "StrongP@ss1",
            "owner_full_name": "Owner",
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["slug"] == "acme"
    assert body["status"] == "active"


async def test_register_duplicate_slug_conflicts(client: AsyncClient):
    payload = {
        "tenant_name": "Acme",
        "tenant_slug": "acme",
        "owner_email": "first@acme.test",
        "owner_password": "StrongP@ss1",
        "owner_full_name": "First",
    }
    r1 = await client.post("/api/v1/auth/register-tenant", json=payload)
    assert r1.status_code == 201

    payload["owner_email"] = "second@acme.test"
    r2 = await client.post("/api/v1/auth/register-tenant", json=payload)
    assert r2.status_code == 409
    assert r2.json()["error"]["code"] == "conflict"


async def test_login_returns_token_pair(tenant_token: dict):
    assert tenant_token["access_token"]
    assert tenant_token["refresh_token"]


async def test_login_wrong_password_returns_401(client: AsyncClient, tenant_token: dict):
    r = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "owner@acme.test",
            "password": "wrong-password",
            "tenant_slug": "acme",
        },
    )
    assert r.status_code == 401


async def test_me_returns_user_tenant_role_perms(client: AsyncClient, tenant_token: dict):
    r = await client.get("/api/v1/auth/me", headers=tenant_token["headers"])
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["email"].lower() == "owner@acme.test"
    assert body["tenant"]["slug"] == "acme"
    assert body["role"] == "admin"
    # Owner is on system 'admin' role with full permission set
    assert "coa.write" in body["permissions"]
    assert "sales.post" in body["permissions"]


async def test_me_without_token_returns_401(client: AsyncClient):
    r = await client.get("/api/v1/auth/me")
    assert r.status_code == 401


async def test_refresh_rotates_token(client: AsyncClient, tenant_token: dict):
    r = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tenant_token["refresh_token"]},
    )
    assert r.status_code == 200
    new_tokens = r.json()
    assert new_tokens["refresh_token"] != tenant_token["refresh_token"]

    # Old token should now be revoked
    r2 = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tenant_token["refresh_token"]},
    )
    assert r2.status_code == 401

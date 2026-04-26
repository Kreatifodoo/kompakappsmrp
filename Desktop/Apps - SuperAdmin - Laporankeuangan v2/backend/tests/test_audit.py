"""Audit log: every write to a tracked table emits an audit row with
who, what, before/after, and request correlation."""

from httpx import AsyncClient


async def _list_audit(client: AsyncClient, headers: dict, **params) -> list[dict]:
    r = await client.get("/api/v1/audit/logs", headers=headers, params=params)
    assert r.status_code == 200, r.text
    return r.json()


async def test_create_emits_create_audit(client: AsyncClient, seeded_tenant: dict):
    headers = seeded_tenant["headers"]
    rc = await client.post("/api/v1/customers", headers=headers, json={"code": "C001", "name": "Audit Cust"})
    assert rc.status_code == 201
    cust_id = rc.json()["id"]

    rows = await _list_audit(client, headers, table_name="customers", row_id=cust_id)
    assert len(rows) == 1
    log = rows[0]
    assert log["action"] == "create"
    assert log["table_name"] == "customers"
    assert log["row_id"] == cust_id
    # changes carries a snapshot of all columns
    assert log["changes"]["code"] == "C001"
    assert log["changes"]["name"] == "Audit Cust"
    # User attribution from the JWT
    assert log["user_id"] is not None


async def test_update_records_field_diffs(client: AsyncClient, seeded_tenant: dict):
    headers = seeded_tenant["headers"]
    rc = await client.post("/api/v1/customers", headers=headers, json={"code": "C002", "name": "Old Name"})
    cust_id = rc.json()["id"]

    rp = await client.patch(
        f"/api/v1/customers/{cust_id}",
        headers=headers,
        json={"name": "New Name", "email": "new@example.com"},
    )
    assert rp.status_code == 200

    rows = await _list_audit(client, headers, table_name="customers", row_id=cust_id)
    # Most recent first; first row is the update, second is the create
    assert len(rows) == 2
    update_log = rows[0]
    assert update_log["action"] == "update"
    assert update_log["changes"]["name"] == {"old": "Old Name", "new": "New Name"}
    assert update_log["changes"]["email"] == {"old": None, "new": "new@example.com"}
    # Unchanged fields are not in the diff
    assert "code" not in update_log["changes"]


async def test_post_action_classified_as_post(client: AsyncClient, seeded_tenant: dict):
    """A status transition draft → posted should be tagged 'post'."""
    headers = seeded_tenant["headers"]
    rc = await client.post("/api/v1/customers", headers=headers, json={"code": "C003", "name": "X"})
    cust_id = rc.json()["id"]

    # Create draft, then post separately
    rs = await client.post(
        "/api/v1/sales-invoices",
        headers=headers,
        json={
            "invoice_date": "2026-04-01",
            "customer_id": cust_id,
            "lines": [{"description": "x", "qty": "1", "unit_price": "100"}],
        },
    )
    inv_id = rs.json()["id"]

    rp = await client.post(f"/api/v1/sales-invoices/{inv_id}/post", headers=headers)
    assert rp.status_code == 200

    rows = await _list_audit(client, headers, table_name="sales_invoices", row_id=inv_id)
    actions = [r["action"] for r in rows]
    # Most recent first: post, then create
    assert actions[0] == "post"
    assert actions[-1] == "create"
    post_log = rows[0]
    assert post_log["changes"]["status"] == {"old": "draft", "new": "posted"}


async def test_void_action_classified_as_void(client: AsyncClient, seeded_tenant: dict):
    headers = seeded_tenant["headers"]
    rc = await client.post("/api/v1/customers", headers=headers, json={"code": "C-V", "name": "V"})
    cust_id = rc.json()["id"]
    rs = await client.post(
        "/api/v1/sales-invoices?post_now=true",
        headers=headers,
        json={
            "invoice_date": "2026-04-01",
            "customer_id": cust_id,
            "lines": [{"description": "x", "qty": "1", "unit_price": "50"}],
        },
    )
    inv_id = rs.json()["id"]

    rv = await client.post(
        f"/api/v1/sales-invoices/{inv_id}/void",
        headers=headers,
        json={"reason": "test"},
    )
    assert rv.status_code == 200

    rows = await _list_audit(client, headers, table_name="sales_invoices", row_id=inv_id)
    assert rows[0]["action"] == "void"
    assert rows[0]["changes"]["status"] == {"old": "posted", "new": "void"}


async def test_row_history_returns_full_chronological_trail(client: AsyncClient, seeded_tenant: dict):
    headers = seeded_tenant["headers"]
    rc = await client.post("/api/v1/customers", headers=headers, json={"code": "C-H", "name": "First"})
    cust_id = rc.json()["id"]
    await client.patch(
        f"/api/v1/customers/{cust_id}",
        headers=headers,
        json={"name": "Second"},
    )
    await client.patch(
        f"/api/v1/customers/{cust_id}",
        headers=headers,
        json={"name": "Third"},
    )

    r = await client.get(
        f"/api/v1/audit/logs/{cust_id}/history?table_name=customers",
        headers=headers,
    )
    assert r.status_code == 200
    rows = r.json()
    # Returned ascending: create → update → update
    assert [r["action"] for r in rows] == ["create", "update", "update"]
    assert rows[1]["changes"]["name"]["new"] == "Second"
    assert rows[2]["changes"]["name"]["new"] == "Third"


async def test_audit_logs_filtered_by_tenant_via_rls(client: AsyncClient, seeded_tenant: dict):
    """Tenant A's audit logs must not appear in tenant B's query results."""
    # Tenant A activity
    await client.post(
        "/api/v1/customers",
        headers=seeded_tenant["headers"],
        json={"code": "ATEN", "name": "A's Cust"},
    )
    a_logs = await _list_audit(client, seeded_tenant["headers"])
    assert len(a_logs) >= 1
    a_table_set = {log["table_name"] for log in a_logs}

    # Register a second tenant + login
    payload = {
        "tenant_name": "Other Inc",
        "tenant_slug": "other",
        "owner_email": "other@audit.test",
        "owner_password": "Passw0rd!",
        "owner_full_name": "Other Owner",
    }
    rr = await client.post("/api/v1/auth/register-tenant", json=payload)
    assert rr.status_code == 201
    rl = await client.post(
        "/api/v1/auth/login",
        json={
            "email": payload["owner_email"],
            "password": payload["owner_password"],
            "tenant_slug": payload["tenant_slug"],
        },
    )
    other_headers = {"Authorization": f"Bearer {rl.json()['access_token']}"}

    # Tenant B sees only its own logs (none for customers — A made one but
    # tenant_id filtering plus RLS keep it private).
    b_logs = await _list_audit(client, other_headers, table_name="customers")
    assert b_logs == []
    # B should see no audit logs about A's tables
    assert "customers" not in {log["table_name"] for log in b_logs}
    # Sanity: A still sees its own customer create
    assert "customers" in a_table_set

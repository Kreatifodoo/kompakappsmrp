"""Period closing: lock past months, enforce on every state-changing
write, allow auditable reopen."""

from httpx import AsyncClient


async def _customer(client: AsyncClient, headers: dict, code: str) -> str:
    r = await client.post("/api/v1/customers", headers=headers, json={"code": code, "name": f"Cust {code}"})
    assert r.status_code == 201
    return r.json()["id"]


async def _close_period(client: AsyncClient, headers: dict, through: str) -> dict:
    r = await client.post("/api/v1/periods/close", headers=headers, json={"through_date": through})
    assert r.status_code == 200, r.text
    return r.json()


# ─── Status / close / reopen lifecycle ─────────────────────
async def test_status_starts_unlocked(client: AsyncClient, seeded_tenant: dict):
    r = await client.get("/api/v1/periods/status", headers=seeded_tenant["headers"])
    assert r.status_code == 200
    body = r.json()
    assert body["closed_through"] is None
    assert body["is_locked"] is False


async def test_close_then_reopen(client: AsyncClient, seeded_tenant: dict):
    headers = seeded_tenant["headers"]
    c = await _close_period(client, headers, "2026-01-31")
    assert c["closed_through"] == "2026-01-31"
    assert c["is_locked"] is True

    # Reopen entirely
    r = await client.post(
        "/api/v1/periods/reopen",
        headers=headers,
        json={"reason": "Found a journal error in January"},
    )
    assert r.status_code == 200
    assert r.json()["closed_through"] is None

    # Events log shows both actions, most recent first
    re = await client.get("/api/v1/periods/events", headers=headers)
    events = re.json()
    assert len(events) == 2
    assert events[0]["action"] == "reopen"
    assert events[1]["action"] == "close"
    assert events[1]["through_date"] == "2026-01-31"


async def test_close_must_move_forward(client: AsyncClient, seeded_tenant: dict):
    headers = seeded_tenant["headers"]
    await _close_period(client, headers, "2026-01-31")

    # Same date again → 422 (already closed)
    r1 = await client.post(
        "/api/v1/periods/close",
        headers=headers,
        json={"through_date": "2026-01-31"},
    )
    assert r1.status_code == 422

    # Earlier date → 422 (must use reopen)
    r2 = await client.post(
        "/api/v1/periods/close",
        headers=headers,
        json={"through_date": "2025-12-31"},
    )
    assert r2.status_code == 422


async def test_reopen_requires_reason(client: AsyncClient, seeded_tenant: dict):
    headers = seeded_tenant["headers"]
    await _close_period(client, headers, "2026-01-31")
    r = await client.post("/api/v1/periods/reopen", headers=headers, json={})
    # Pydantic enforces reason min_length=1
    assert r.status_code == 422


# ─── Write enforcement on closed periods ───────────────────
async def test_create_invoice_in_closed_period_rejected(client: AsyncClient, seeded_tenant: dict):
    headers = seeded_tenant["headers"]
    cust = await _customer(client, headers, "C-LOCKED")
    await _close_period(client, headers, "2026-01-31")

    r = await client.post(
        "/api/v1/sales-invoices",
        headers=headers,
        json={
            "invoice_date": "2026-01-15",  # in closed period
            "customer_id": cust,
            "lines": [{"description": "x", "qty": "1", "unit_price": "100"}],
        },
    )
    assert r.status_code == 422
    body = r.json()
    assert body["error"]["code"] == "period_closed"
    assert "closed_through" in body["error"]["details"]


async def test_create_invoice_after_close_date_works(client: AsyncClient, seeded_tenant: dict):
    headers = seeded_tenant["headers"]
    cust = await _customer(client, headers, "C-OPEN")
    await _close_period(client, headers, "2026-01-31")

    r = await client.post(
        "/api/v1/sales-invoices",
        headers=headers,
        json={
            "invoice_date": "2026-02-01",  # after the close
            "customer_id": cust,
            "lines": [{"description": "x", "qty": "1", "unit_price": "100"}],
        },
    )
    assert r.status_code == 201


async def test_void_invoice_in_closed_period_rejected(client: AsyncClient, seeded_tenant: dict):
    headers = seeded_tenant["headers"]
    cust = await _customer(client, headers, "C-VOID")
    # Post in February (still open)
    rs = await client.post(
        "/api/v1/sales-invoices?post_now=true",
        headers=headers,
        json={
            "invoice_date": "2026-02-10",
            "customer_id": cust,
            "lines": [{"description": "x", "qty": "1", "unit_price": "200"}],
        },
    )
    inv_id = rs.json()["id"]

    # Close through Feb — now voiding the Feb invoice should fail
    await _close_period(client, headers, "2026-02-28")

    r = await client.post(
        f"/api/v1/sales-invoices/{inv_id}/void",
        headers=headers,
        json={"reason": "test"},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "period_closed"


async def test_post_journal_in_closed_period_rejected(client: AsyncClient, seeded_tenant: dict):
    headers = seeded_tenant["headers"]
    racc = await client.get("/api/v1/accounts?include_zero=true", headers=headers)
    by_code = {a["code"]: a["id"] for a in racc.json()}
    await _close_period(client, headers, "2026-01-31")

    r = await client.post(
        "/api/v1/journals?post_now=true",
        headers=headers,
        json={
            "entry_date": "2026-01-15",
            "description": "Late entry",
            "lines": [
                {"account_id": by_code["1110"], "debit": "100", "credit": "0"},
                {"account_id": by_code["3100"], "debit": "0", "credit": "100"},
            ],
        },
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "period_closed"


async def test_payment_in_closed_period_rejected(client: AsyncClient, seeded_tenant: dict):
    headers = seeded_tenant["headers"]
    cust = await _customer(client, headers, "C-PAY")

    rs = await client.post(
        "/api/v1/sales-invoices?post_now=true",
        headers=headers,
        json={
            "invoice_date": "2026-02-01",
            "customer_id": cust,
            "lines": [{"description": "x", "qty": "1", "unit_price": "500"}],
        },
    )
    inv_id = rs.json()["id"]

    await _close_period(client, headers, "2026-02-28")

    racc = await client.get("/api/v1/accounts?include_zero=true", headers=headers)
    cash = next(a["id"] for a in racc.json() if a["code"] == "1110")

    # Try a payment dated within the closed period
    r = await client.post(
        "/api/v1/payments",
        headers=headers,
        json={
            "payment_date": "2026-02-25",
            "direction": "receipt",
            "customer_id": cust,
            "amount": "500",
            "cash_account_id": cash,
            "applications": [{"sales_invoice_id": inv_id, "amount": "500"}],
        },
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "period_closed"

    # After reopening, the same payment goes through
    rr = await client.post(
        "/api/v1/periods/reopen",
        headers=headers,
        json={"reason": "Late receipt arrived"},
    )
    assert rr.status_code == 200
    r2 = await client.post(
        "/api/v1/payments",
        headers=headers,
        json={
            "payment_date": "2026-02-25",
            "direction": "receipt",
            "customer_id": cust,
            "amount": "500",
            "cash_account_id": cash,
            "applications": [{"sales_invoice_id": inv_id, "amount": "500"}],
        },
    )
    assert r2.status_code == 201

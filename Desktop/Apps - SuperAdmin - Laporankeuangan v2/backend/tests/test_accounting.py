"""Accounting: starter COA, accounts, journals."""
from httpx import AsyncClient


async def test_seed_starter_coa_creates_accounts_and_mappings(
    client: AsyncClient, tenant_token: dict
):
    r = await client.post(
        "/api/v1/accounts/seed-starter-coa", headers=tenant_token["headers"]
    )
    assert r.status_code == 200
    body = r.json()
    assert body["accounts_created"] >= 30
    assert body["accounts_skipped"] == 0
    assert body["mappings_set"] == 7

    # Re-running is idempotent
    r2 = await client.post(
        "/api/v1/accounts/seed-starter-coa", headers=tenant_token["headers"]
    )
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2["accounts_created"] == 0
    assert body2["accounts_skipped"] >= 30
    assert body2["mappings_set"] == 0  # already bound

    # All 7 well-known mappings present
    rm = await client.get("/api/v1/account-mappings", headers=tenant_token["headers"])
    assert rm.status_code == 200
    keys = {m["key"] for m in rm.json()}
    assert keys == {
        "ar", "ap", "sales_revenue", "purchase_expense",
        "tax_payable", "tax_receivable", "cash_default",
    }


async def test_create_custom_account(client: AsyncClient, seeded_tenant: dict):
    r = await client.post(
        "/api/v1/accounts",
        headers=seeded_tenant["headers"],
        json={
            "code": "5999",
            "name": "Custom Expense",
            "type": "expense",
            "normal_side": "debit",
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["code"] == "5999"
    assert body["is_system"] is False


async def test_duplicate_account_code_conflicts(
    client: AsyncClient, seeded_tenant: dict
):
    payload = {
        "code": "5999", "name": "X", "type": "expense", "normal_side": "debit",
    }
    r1 = await client.post(
        "/api/v1/accounts", headers=seeded_tenant["headers"], json=payload
    )
    assert r1.status_code == 201

    r2 = await client.post(
        "/api/v1/accounts", headers=seeded_tenant["headers"], json=payload
    )
    assert r2.status_code == 409


async def _account_id_by_code(client: AsyncClient, headers: dict, code: str) -> str:
    r = await client.get("/api/v1/accounts", headers=headers)
    assert r.status_code == 200
    return next(a["id"] for a in r.json() if a["code"] == code)


async def test_create_balanced_journal_succeeds(
    client: AsyncClient, seeded_tenant: dict
):
    cash = await _account_id_by_code(client, seeded_tenant["headers"], "1110")
    capital = await _account_id_by_code(client, seeded_tenant["headers"], "3100")

    r = await client.post(
        "/api/v1/journals?post_now=true",
        headers=seeded_tenant["headers"],
        json={
            "entry_date": "2026-01-15",
            "description": "Initial capital",
            "lines": [
                {"account_id": cash, "debit": "1000.00", "credit": "0"},
                {"account_id": capital, "debit": "0", "credit": "1000.00"},
            ],
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "posted"
    assert body["posted_at"] is not None
    assert body["entry_no"].startswith("JV-2026-")


async def test_unbalanced_journal_rejected(
    client: AsyncClient, seeded_tenant: dict
):
    cash = await _account_id_by_code(client, seeded_tenant["headers"], "1110")
    capital = await _account_id_by_code(client, seeded_tenant["headers"], "3100")

    r = await client.post(
        "/api/v1/journals",
        headers=seeded_tenant["headers"],
        json={
            "entry_date": "2026-01-15",
            "description": "Bad",
            "lines": [
                {"account_id": cash, "debit": "1000.00", "credit": "0"},
                {"account_id": capital, "debit": "0", "credit": "999.00"},
            ],
        },
    )
    assert r.status_code == 422  # FastAPI's pydantic validation error

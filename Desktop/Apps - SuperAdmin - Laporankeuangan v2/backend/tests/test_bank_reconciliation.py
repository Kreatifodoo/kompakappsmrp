"""Bank reconciliation: match a supplied bank statement against the
book journal lines on a cash account."""

from decimal import Decimal

from httpx import AsyncClient


async def _kas_id(client: AsyncClient, headers: dict) -> str:
    r = await client.get("/api/v1/accounts?include_zero=true", headers=headers)
    return next(a["id"] for a in r.json() if a["code"] == "1110")


async def _capital_id(client: AsyncClient, headers: dict) -> str:
    r = await client.get("/api/v1/accounts?include_zero=true", headers=headers)
    return next(a["id"] for a in r.json() if a["code"] == "3100")


async def _post_journal(
    client: AsyncClient,
    headers: dict,
    *,
    date_: str,
    cash_id: str,
    other_id: str,
    cash_debit: str,
) -> str:
    """Helper to post a manual 2-line journal involving the cash account.
    Pass cash_debit='100' for a deposit (Dr Cash 100/Cr Other 100), or
    pass with negative semantics by swapping with cash_credit (use a
    separate helper for outflow)."""
    r = await client.post(
        "/api/v1/journals?post_now=true",
        headers=headers,
        json={
            "entry_date": date_,
            "description": f"Test {date_}",
            "lines": [
                {"account_id": cash_id, "debit": cash_debit, "credit": "0"},
                {"account_id": other_id, "debit": "0", "credit": cash_debit},
            ],
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _post_outflow(
    client: AsyncClient,
    headers: dict,
    *,
    date_: str,
    cash_id: str,
    other_id: str,
    cash_credit: str,
) -> str:
    r = await client.post(
        "/api/v1/journals?post_now=true",
        headers=headers,
        json={
            "entry_date": date_,
            "description": f"Outflow {date_}",
            "lines": [
                {"account_id": cash_id, "debit": "0", "credit": cash_credit},
                {"account_id": other_id, "debit": cash_credit, "credit": "0"},
            ],
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def test_bank_rec_matches_book_lines_to_statement(client: AsyncClient, seeded_tenant: dict):
    """3 book entries, 3 statement lines — all matching by amount + date."""
    headers = seeded_tenant["headers"]
    cash_id = await _kas_id(client, headers)
    capital_id = await _capital_id(client, headers)

    await _post_journal(
        client, headers, date_="2026-05-01", cash_id=cash_id, other_id=capital_id, cash_debit="500"
    )
    await _post_outflow(
        client, headers, date_="2026-05-05", cash_id=cash_id, other_id=capital_id, cash_credit="200"
    )
    await _post_journal(
        client, headers, date_="2026-05-10", cash_id=cash_id, other_id=capital_id, cash_debit="700"
    )

    r = await client.post(
        "/api/v1/reports/bank-reconciliation",
        headers=headers,
        json={
            "cash_account_id": cash_id,
            "date_from": "2026-05-01",
            "date_to": "2026-05-31",
            "statement_lines": [
                {"date": "2026-05-01", "amount": "500", "reference": "DEP-1"},
                {"date": "2026-05-05", "amount": "-200", "reference": "WD-1"},
                {"date": "2026-05-10", "amount": "700", "reference": "DEP-2"},
            ],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()

    assert len(body["matched"]) == 3
    assert body["book_only"] == []
    assert body["statement_only"] == []
    assert Decimal(body["book_period_total"]) == Decimal("1000.00")  # 500 - 200 + 700
    assert Decimal(body["statement_period_total"]) == Decimal("1000.00")
    assert Decimal(body["difference"]) == Decimal("0")


async def test_bank_rec_book_only_when_statement_missing(client: AsyncClient, seeded_tenant: dict):
    """Book has 2 entries; statement only shows one → book_only contains
    the missing one (e.g. cheque written but not yet cleared)."""
    headers = seeded_tenant["headers"]
    cash_id = await _kas_id(client, headers)
    capital_id = await _capital_id(client, headers)

    await _post_journal(
        client, headers, date_="2026-05-01", cash_id=cash_id, other_id=capital_id, cash_debit="500"
    )
    await _post_journal(
        client, headers, date_="2026-05-15", cash_id=cash_id, other_id=capital_id, cash_debit="300"
    )

    r = await client.post(
        "/api/v1/reports/bank-reconciliation",
        headers=headers,
        json={
            "cash_account_id": cash_id,
            "date_from": "2026-05-01",
            "date_to": "2026-05-31",
            "statement_lines": [
                {"date": "2026-05-01", "amount": "500"},
                # 300 missing from statement
            ],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["matched"]) == 1
    assert len(body["book_only"]) == 1
    assert Decimal(body["book_only"][0]["amount"]) == Decimal("300.00")
    assert Decimal(body["book_only_total"]) == Decimal("300.00")
    assert Decimal(body["difference"]) == Decimal("300.00")  # 800 - 500


async def test_bank_rec_statement_only_for_bank_charges(client: AsyncClient, seeded_tenant: dict):
    """Statement contains a bank fee not in our books yet."""
    headers = seeded_tenant["headers"]
    cash_id = await _kas_id(client, headers)
    capital_id = await _capital_id(client, headers)

    await _post_journal(
        client, headers, date_="2026-05-01", cash_id=cash_id, other_id=capital_id, cash_debit="500"
    )

    r = await client.post(
        "/api/v1/reports/bank-reconciliation",
        headers=headers,
        json={
            "cash_account_id": cash_id,
            "date_from": "2026-05-01",
            "date_to": "2026-05-31",
            "statement_lines": [
                {"date": "2026-05-01", "amount": "500"},
                {"date": "2026-05-31", "amount": "-15", "description": "Bank fee"},
            ],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["matched"]) == 1
    assert len(body["statement_only"]) == 1
    assert Decimal(body["statement_only"][0]["amount"]) == Decimal("-15.00")
    assert Decimal(body["statement_only_total"]) == Decimal("-15.00")
    # Books = 500, statement = 485 → difference = 15
    assert Decimal(body["difference"]) == Decimal("15.00")


async def test_bank_rec_date_tolerance_matches_close_dates(client: AsyncClient, seeded_tenant: dict):
    """A 2-day posting lag still matches under the default tolerance."""
    headers = seeded_tenant["headers"]
    cash_id = await _kas_id(client, headers)
    capital_id = await _capital_id(client, headers)

    # Book recorded on 2026-05-10; bank posted on 2026-05-12 (2 days later)
    await _post_journal(
        client, headers, date_="2026-05-10", cash_id=cash_id, other_id=capital_id, cash_debit="123"
    )

    r = await client.post(
        "/api/v1/reports/bank-reconciliation",
        headers=headers,
        json={
            "cash_account_id": cash_id,
            "date_from": "2026-05-01",
            "date_to": "2026-05-31",
            "statement_lines": [{"date": "2026-05-12", "amount": "123"}],
        },
    )
    body = r.json()
    assert len(body["matched"]) == 1

    # With 0-day tolerance the same lines would NOT match
    r2 = await client.post(
        "/api/v1/reports/bank-reconciliation",
        headers=headers,
        json={
            "cash_account_id": cash_id,
            "date_from": "2026-05-01",
            "date_to": "2026-05-31",
            "statement_lines": [{"date": "2026-05-12", "amount": "123"}],
            "date_tolerance_days": 0,
        },
    )
    body2 = r2.json()
    assert len(body2["matched"]) == 0
    assert len(body2["book_only"]) == 1
    assert len(body2["statement_only"]) == 1


async def test_bank_rec_rejects_non_cash_account(client: AsyncClient, seeded_tenant: dict):
    """Validates the chosen account has is_cash=true."""
    headers = seeded_tenant["headers"]
    # AR (1200) is not flagged is_cash
    r = await client.get("/api/v1/accounts?include_zero=true", headers=headers)
    ar_id = next(a["id"] for a in r.json() if a["code"] == "1200")

    rr = await client.post(
        "/api/v1/reports/bank-reconciliation",
        headers=headers,
        json={
            "cash_account_id": ar_id,
            "date_from": "2026-05-01",
            "date_to": "2026-05-31",
            "statement_lines": [],
        },
    )
    assert rr.status_code == 422
    assert "is_cash" in rr.json()["error"]["message"].lower()

"""Customer / supplier statements: chronological invoice + payment ledger
with opening / closing balances and running balance per row."""

from decimal import Decimal

from httpx import AsyncClient


async def _customer(client: AsyncClient, headers: dict, code: str) -> str:
    r = await client.post("/api/v1/customers", headers=headers, json={"code": code, "name": f"Cust {code}"})
    assert r.status_code == 201
    return r.json()["id"]


async def _supplier(client: AsyncClient, headers: dict, code: str) -> str:
    r = await client.post("/api/v1/suppliers", headers=headers, json={"code": code, "name": f"Vend {code}"})
    assert r.status_code == 201
    return r.json()["id"]


async def _post_si(client: AsyncClient, headers: dict, customer_id: str, amount: str, d: str) -> str:
    r = await client.post(
        "/api/v1/sales-invoices?post_now=true",
        headers=headers,
        json={
            "invoice_date": d,
            "customer_id": customer_id,
            "lines": [{"description": "x", "qty": "1", "unit_price": amount}],
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _post_pi(client: AsyncClient, headers: dict, supplier_id: str, amount: str, d: str) -> str:
    r = await client.post(
        "/api/v1/purchase-invoices?post_now=true",
        headers=headers,
        json={
            "invoice_date": d,
            "supplier_id": supplier_id,
            "lines": [{"description": "x", "qty": "1", "unit_price": amount}],
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _kas_id(client: AsyncClient, headers: dict) -> str:
    r = await client.get("/api/v1/accounts?include_zero=true", headers=headers)
    return next(a["id"] for a in r.json() if a["code"] == "1110")


async def _receipt(
    client: AsyncClient,
    headers: dict,
    customer_id: str,
    invoice_id: str,
    amount: str,
    d: str,
) -> None:
    cash = await _kas_id(client, headers)
    r = await client.post(
        "/api/v1/payments",
        headers=headers,
        json={
            "payment_date": d,
            "direction": "receipt",
            "customer_id": customer_id,
            "amount": amount,
            "cash_account_id": cash,
            "applications": [{"sales_invoice_id": invoice_id, "amount": amount}],
        },
    )
    assert r.status_code == 201, r.text


async def _disbursement(
    client: AsyncClient,
    headers: dict,
    supplier_id: str,
    invoice_id: str,
    amount: str,
    d: str,
) -> None:
    cash = await _kas_id(client, headers)
    r = await client.post(
        "/api/v1/payments",
        headers=headers,
        json={
            "payment_date": d,
            "direction": "disbursement",
            "supplier_id": supplier_id,
            "amount": amount,
            "cash_account_id": cash,
            "applications": [{"purchase_invoice_id": invoice_id, "amount": amount}],
        },
    )
    assert r.status_code == 201, r.text


# ─── Customer statement ────────────────────────────────────
async def test_customer_statement_running_balance(client: AsyncClient, seeded_tenant: dict):
    """Multi-event statement: 2 invoices + 1 partial payment.
    Verify opening balance, per-row running balance, closing balance."""
    headers = seeded_tenant["headers"]
    cust = await _customer(client, headers, "C001")

    # Pre-period: a 200 invoice posted in Feb (before the period we'll request)
    await _post_si(client, headers, cust, "200", "2026-02-15")
    # In period (March-April):
    inv_a = await _post_si(client, headers, cust, "1000", "2026-03-10")
    await _post_si(client, headers, cust, "500", "2026-04-05")
    # Receipt of 600 against inv_a in late March
    await _receipt(client, headers, cust, inv_a, "600", "2026-03-25")

    r = await client.get(
        f"/api/v1/reports/customer-statement/{cust}?date_from=2026-03-01&date_to=2026-04-30",
        headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()

    # Opening balance = pre-period 200 invoice → 200
    assert Decimal(body["opening_balance"]) == Decimal("200.00")

    # 3 in-period rows: invoice 1000 (3/10), payment 600 (3/25), invoice 500 (4/5)
    assert len(body["lines"]) == 3
    rows = body["lines"]
    assert rows[0]["type"] == "invoice"
    assert Decimal(rows[0]["debit"]) == Decimal("1000.00")
    assert Decimal(rows[0]["balance"]) == Decimal("1200.00")  # 200 + 1000

    assert rows[1]["type"] == "payment"
    assert Decimal(rows[1]["credit"]) == Decimal("600.00")
    assert Decimal(rows[1]["balance"]) == Decimal("600.00")  # 1200 - 600

    assert rows[2]["type"] == "invoice"
    assert Decimal(rows[2]["debit"]) == Decimal("500.00")
    assert Decimal(rows[2]["balance"]) == Decimal("1100.00")  # 600 + 500

    # Period totals
    assert Decimal(body["period_debit_total"]) == Decimal("1500.00")
    assert Decimal(body["period_credit_total"]) == Decimal("600.00")
    assert Decimal(body["closing_balance"]) == Decimal("1100.00")


async def test_customer_statement_excludes_voided(client: AsyncClient, seeded_tenant: dict):
    headers = seeded_tenant["headers"]
    cust = await _customer(client, headers, "C002")
    inv_id = await _post_si(client, headers, cust, "999", "2026-03-01")
    rv = await client.post(
        f"/api/v1/sales-invoices/{inv_id}/void",
        headers=headers,
        json={"reason": "test"},
    )
    assert rv.status_code == 200

    r = await client.get(
        f"/api/v1/reports/customer-statement/{cust}?date_from=2026-01-01&date_to=2026-12-31",
        headers=headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["lines"] == []
    assert Decimal(body["opening_balance"]) == Decimal("0")
    assert Decimal(body["closing_balance"]) == Decimal("0")


async def test_customer_statement_unknown_customer_404(client: AsyncClient, seeded_tenant: dict):
    from uuid import uuid4

    r = await client.get(
        f"/api/v1/reports/customer-statement/{uuid4()}?date_from=2026-01-01&date_to=2026-12-31",
        headers=seeded_tenant["headers"],
    )
    assert r.status_code == 404


# ─── Supplier statement ────────────────────────────────────
async def test_supplier_statement_running_balance(client: AsyncClient, seeded_tenant: dict):
    """Mirror of the customer test: invoices increase balance, payments
    decrease it, but balance is signed by AP's credit-normal side."""
    headers = seeded_tenant["headers"]
    sup = await _supplier(client, headers, "S001")

    inv_a = await _post_pi(client, headers, sup, "800", "2026-03-05")
    await _disbursement(client, headers, sup, inv_a, "300", "2026-03-15")
    await _post_pi(client, headers, sup, "400", "2026-03-20")

    r = await client.get(
        f"/api/v1/reports/supplier-statement/{sup}?date_from=2026-03-01&date_to=2026-03-31",
        headers=headers,
    )
    assert r.status_code == 200
    body = r.json()

    assert Decimal(body["opening_balance"]) == Decimal("0")
    assert len(body["lines"]) == 3
    rows = body["lines"]

    # Invoice on 3/5 → balance becomes 800
    assert rows[0]["type"] == "invoice"
    assert Decimal(rows[0]["balance"]) == Decimal("800.00")
    # For supplier (credit-normal AP), invoice is shown in CREDIT column
    assert Decimal(rows[0]["credit"]) == Decimal("800.00")
    assert Decimal(rows[0]["debit"]) == Decimal("0")

    # Disbursement on 3/15 → balance 500; shown in DEBIT column
    assert rows[1]["type"] == "payment"
    assert Decimal(rows[1]["debit"]) == Decimal("300.00")
    assert Decimal(rows[1]["balance"]) == Decimal("500.00")

    # Invoice on 3/20 → balance 900
    assert rows[2]["type"] == "invoice"
    assert Decimal(rows[2]["credit"]) == Decimal("400.00")
    assert Decimal(rows[2]["balance"]) == Decimal("900.00")

    assert Decimal(body["closing_balance"]) == Decimal("900.00")

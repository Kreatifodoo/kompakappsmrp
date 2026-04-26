"""Payments module: receipts, disbursements, journal posting,
invoice settlement, cash-basis P&L recognition for credit sales."""

from decimal import Decimal

from httpx import AsyncClient


async def _create_customer(client: AsyncClient, headers: dict, code: str) -> str:
    r = await client.post("/api/v1/customers", headers=headers, json={"code": code, "name": f"Cust {code}"})
    assert r.status_code == 201
    return r.json()["id"]


async def _post_sales_invoice(
    client: AsyncClient, headers: dict, customer_id: str, amount: str, date_: str
) -> dict:
    r = await client.post(
        "/api/v1/sales-invoices?post_now=true",
        headers=headers,
        json={
            "invoice_date": date_,
            "customer_id": customer_id,
            "lines": [{"description": "x", "qty": "1", "unit_price": amount}],
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _kas_account_id(client: AsyncClient, headers: dict) -> str:
    r = await client.get("/api/v1/accounts?include_zero=true", headers=headers)
    return next(a["id"] for a in r.json() if a["code"] == "1110")


async def test_receipt_payment_creates_journal_and_settles_invoice(client: AsyncClient, seeded_tenant: dict):
    headers = seeded_tenant["headers"]
    cust = await _create_customer(client, headers, "C001")
    invoice = await _post_sales_invoice(client, headers, cust, "1000", "2026-04-01")
    cash_id = await _kas_account_id(client, headers)

    r = await client.post(
        "/api/v1/payments",
        headers=headers,
        json={
            "payment_date": "2026-04-15",
            "direction": "receipt",
            "customer_id": cust,
            "amount": "1000.00",
            "cash_account_id": cash_id,
            "applications": [{"sales_invoice_id": invoice["id"], "amount": "1000.00"}],
        },
    )
    assert r.status_code == 201, r.text
    payment = r.json()
    assert payment["status"] == "posted"
    assert payment["payment_no"].startswith("RCV-2026-")
    assert payment["journal_entry_id"] is not None

    # Verify journal: Dr Cash 1000 / Cr AR 1000
    rj = await client.get(f"/api/v1/journals/{payment['journal_entry_id']}", headers=headers)
    journal = rj.json()
    debits = sum(Decimal(ln["debit"]) for ln in journal["lines"])
    credits = sum(Decimal(ln["credit"]) for ln in journal["lines"])
    assert debits == credits == Decimal("1000.00")

    # Invoice should be marked paid
    ri = await client.get(f"/api/v1/sales-invoices/{invoice['id']}", headers=headers)
    inv_now = ri.json()
    assert inv_now["status"] == "paid"
    assert Decimal(inv_now["paid_amount"]) == Decimal("1000.00")


async def test_partial_payment_keeps_invoice_posted(client: AsyncClient, seeded_tenant: dict):
    headers = seeded_tenant["headers"]
    cust = await _create_customer(client, headers, "C002")
    invoice = await _post_sales_invoice(client, headers, cust, "1000", "2026-04-01")
    cash_id = await _kas_account_id(client, headers)

    r = await client.post(
        "/api/v1/payments",
        headers=headers,
        json={
            "payment_date": "2026-04-10",
            "direction": "receipt",
            "customer_id": cust,
            "amount": "400.00",
            "cash_account_id": cash_id,
            "applications": [{"sales_invoice_id": invoice["id"], "amount": "400.00"}],
        },
    )
    assert r.status_code == 201

    ri = await client.get(f"/api/v1/sales-invoices/{invoice['id']}", headers=headers)
    inv_now = ri.json()
    assert inv_now["status"] == "posted"  # not paid yet
    assert Decimal(inv_now["paid_amount"]) == Decimal("400.00")


async def test_overpayment_is_rejected(client: AsyncClient, seeded_tenant: dict):
    headers = seeded_tenant["headers"]
    cust = await _create_customer(client, headers, "C003")
    invoice = await _post_sales_invoice(client, headers, cust, "500", "2026-04-01")
    cash_id = await _kas_account_id(client, headers)

    r = await client.post(
        "/api/v1/payments",
        headers=headers,
        json={
            "payment_date": "2026-04-10",
            "direction": "receipt",
            "customer_id": cust,
            "amount": "999.00",  # exceeds invoice total of 500
            "cash_account_id": cash_id,
            "applications": [{"sales_invoice_id": invoice["id"], "amount": "999.00"}],
        },
    )
    assert r.status_code == 422
    assert "outstanding" in r.json()["error"]["message"].lower()


async def test_void_payment_reverses_settlement(client: AsyncClient, seeded_tenant: dict):
    headers = seeded_tenant["headers"]
    cust = await _create_customer(client, headers, "C004")
    invoice = await _post_sales_invoice(client, headers, cust, "1000", "2026-04-01")
    cash_id = await _kas_account_id(client, headers)

    rp = await client.post(
        "/api/v1/payments",
        headers=headers,
        json={
            "payment_date": "2026-04-15",
            "direction": "receipt",
            "customer_id": cust,
            "amount": "1000",
            "cash_account_id": cash_id,
            "applications": [{"sales_invoice_id": invoice["id"], "amount": "1000"}],
        },
    )
    assert rp.status_code == 201
    payment_id = rp.json()["id"]
    journal_id = rp.json()["journal_entry_id"]

    # Void the payment
    rv = await client.post(
        f"/api/v1/payments/{payment_id}/void",
        headers=headers,
        json={"reason": "wrong customer"},
    )
    assert rv.status_code == 200
    assert rv.json()["status"] == "void"

    # Invoice should be back to posted, paid_amount=0
    ri = await client.get(f"/api/v1/sales-invoices/{invoice['id']}", headers=headers)
    inv_now = ri.json()
    assert inv_now["status"] == "posted"
    assert Decimal(inv_now["paid_amount"]) == Decimal("0")

    # Linked journal voided
    rj = await client.get(f"/api/v1/journals/{journal_id}", headers=headers)
    assert rj.json()["status"] == "void"


async def test_cash_basis_pl_recognizes_credit_sale_at_payment(client: AsyncClient, seeded_tenant: dict):
    """The original sale invoice journal is Dr AR / Cr Sales (no cash).
    The receipt payment journal is Dr Cash / Cr AR (no income).
    Cash-basis P&L must walk the payment application back to the
    original invoice and proportionally recognize income at payment time."""
    headers = seeded_tenant["headers"]
    cust = await _create_customer(client, headers, "C100")
    invoice = await _post_sales_invoice(client, headers, cust, "1000", "2026-03-01")

    # Before any payment: cash-basis income = 0
    r1 = await client.get(
        "/api/v1/reports/profit-loss?cash_basis=true&date_from=2026-01-01&date_to=2026-12-31",
        headers=headers,
    )
    assert Decimal(r1.json()["total_income"]) == Decimal("0")

    # Record full payment in April
    cash_id = await _kas_account_id(client, headers)
    rp = await client.post(
        "/api/v1/payments",
        headers=headers,
        json={
            "payment_date": "2026-04-10",
            "direction": "receipt",
            "customer_id": cust,
            "amount": "1000",
            "cash_account_id": cash_id,
            "applications": [{"sales_invoice_id": invoice["id"], "amount": "1000"}],
        },
    )
    assert rp.status_code == 201

    # Cash-basis P&L now recognizes the 1000 income at payment time
    r2 = await client.get(
        "/api/v1/reports/profit-loss?cash_basis=true&date_from=2026-01-01&date_to=2026-12-31",
        headers=headers,
    )
    assert Decimal(r2.json()["total_income"]) == Decimal("1000.00")

    # Restricted to only April → still 1000 (payment is in April)
    r3 = await client.get(
        "/api/v1/reports/profit-loss?cash_basis=true&date_from=2026-04-01&date_to=2026-04-30",
        headers=headers,
    )
    assert Decimal(r3.json()["total_income"]) == Decimal("1000.00")

    # Restricted to only March → 0 (no payment in March)
    r4 = await client.get(
        "/api/v1/reports/profit-loss?cash_basis=true&date_from=2026-03-01&date_to=2026-03-31",
        headers=headers,
    )
    assert Decimal(r4.json()["total_income"]) == Decimal("0")


async def test_cash_basis_partial_payment_proportional(client: AsyncClient, seeded_tenant: dict):
    """A 400-of-1000 partial payment recognizes 40% of the income."""
    headers = seeded_tenant["headers"]
    cust = await _create_customer(client, headers, "C200")
    invoice = await _post_sales_invoice(client, headers, cust, "1000", "2026-03-01")
    cash_id = await _kas_account_id(client, headers)

    rp = await client.post(
        "/api/v1/payments",
        headers=headers,
        json={
            "payment_date": "2026-04-10",
            "direction": "receipt",
            "customer_id": cust,
            "amount": "400",
            "cash_account_id": cash_id,
            "applications": [{"sales_invoice_id": invoice["id"], "amount": "400"}],
        },
    )
    assert rp.status_code == 201

    r = await client.get(
        "/api/v1/reports/profit-loss?cash_basis=true&date_from=2026-01-01&date_to=2026-12-31",
        headers=headers,
    )
    # 400/1000 of 1000 income = 400
    assert Decimal(r.json()["total_income"]) == Decimal("400.00")

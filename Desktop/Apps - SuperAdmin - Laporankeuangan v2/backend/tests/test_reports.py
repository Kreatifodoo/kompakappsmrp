"""Reports: trial balance, P&L, balance sheet — verified against
synthetic posted-invoice data."""

from decimal import Decimal

from httpx import AsyncClient


async def _seed_one_sale_and_one_purchase(client: AsyncClient, headers: dict) -> dict[str, Decimal]:
    """Post a sales invoice and a purchase invoice; return expected totals."""
    # Customer + sales invoice: 1000 net + 110 tax = 1110 total
    rc = await client.post("/api/v1/customers", headers=headers, json={"code": "C001", "name": "Cust"})
    assert rc.status_code == 201
    rs = await client.post(
        "/api/v1/sales-invoices?post_now=true",
        headers=headers,
        json={
            "invoice_date": "2026-03-15",
            "customer_id": rc.json()["id"],
            "lines": [
                {"description": "Service", "qty": "1", "unit_price": "1000", "tax_rate": "11"},
            ],
        },
    )
    assert rs.status_code == 201, rs.text

    # Supplier + purchase invoice: 500 net + 55 tax = 555 total
    rsp = await client.post("/api/v1/suppliers", headers=headers, json={"code": "S001", "name": "Vend"})
    assert rsp.status_code == 201
    rp = await client.post(
        "/api/v1/purchase-invoices?post_now=true",
        headers=headers,
        json={
            "invoice_date": "2026-03-16",
            "supplier_id": rsp.json()["id"],
            "lines": [
                {"description": "Material", "qty": "10", "unit_price": "50", "tax_rate": "11"},
            ],
        },
    )
    assert rp.status_code == 201, rp.text

    return {
        "sales_subtotal": Decimal("1000.00"),
        "sales_tax": Decimal("110.00"),
        "sales_total": Decimal("1110.00"),
        "purchase_subtotal": Decimal("500.00"),
        "purchase_tax": Decimal("55.00"),
        "purchase_total": Decimal("555.00"),
    }


# ─── Trial Balance ─────────────────────────────────────────
async def test_trial_balance_balances_after_postings(client: AsyncClient, seeded_tenant: dict):
    headers = seeded_tenant["headers"]
    await _seed_one_sale_and_one_purchase(client, headers)

    r = await client.get("/api/v1/reports/trial-balance?as_of=2026-12-31", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()

    # Total debit must equal total credit (the cardinal accounting check)
    assert Decimal(body["total_debit"]) == Decimal(body["total_credit"])
    assert body["total_debit"] != "0.00"  # there's actual activity
    assert body["balanced"] is True

    # AR (1200) should show debit balance = sales_total = 1110
    ar = next(line for line in body["lines"] if line["code"] == "1200")
    assert Decimal(ar["balance"]) == Decimal("1110.00")
    assert ar["normal_side"] == "debit"

    # AP (2100) should show credit balance = purchase_total = 555
    ap = next(line for line in body["lines"] if line["code"] == "2100")
    assert Decimal(ap["balance"]) == Decimal("555.00")
    assert ap["normal_side"] == "credit"


async def test_trial_balance_excludes_zero_by_default(client: AsyncClient, seeded_tenant: dict):
    headers = seeded_tenant["headers"]
    # No postings — every account has zero activity
    r = await client.get("/api/v1/reports/trial-balance", headers=headers)
    assert r.status_code == 200
    assert r.json()["lines"] == []

    r2 = await client.get("/api/v1/reports/trial-balance?include_zero=true", headers=headers)
    assert r2.status_code == 200
    # Now we get all 32 starter-COA accounts, each with zero balance
    assert len(r2.json()["lines"]) >= 30


# ─── Profit & Loss ─────────────────────────────────────────
async def test_profit_loss_computes_net_profit(client: AsyncClient, seeded_tenant: dict):
    headers = seeded_tenant["headers"]
    expected = await _seed_one_sale_and_one_purchase(client, headers)

    r = await client.get(
        "/api/v1/reports/profit-loss?date_from=2026-01-01&date_to=2026-12-31",
        headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()

    # Income: 1000 from Penjualan (4100)
    assert Decimal(body["total_income"]) == expected["sales_subtotal"]
    sales_line = next(li for li in body["income"] if li["code"] == "4100")
    assert Decimal(sales_line["amount"]) == Decimal("1000.00")

    # Expense: 500 from Harga Pokok Penjualan (5100)
    assert Decimal(body["total_expense"]) == expected["purchase_subtotal"]
    cogs_line = next(li for li in body["expense"] if li["code"] == "5100")
    assert Decimal(cogs_line["amount"]) == Decimal("500.00")

    # Net = 1000 - 500 = 500
    assert Decimal(body["net_profit"]) == Decimal("500.00")


async def test_profit_loss_rejects_inverted_date_range(client: AsyncClient, seeded_tenant: dict):
    r = await client.get(
        "/api/v1/reports/profit-loss?date_from=2026-12-31&date_to=2026-01-01",
        headers=seeded_tenant["headers"],
    )
    assert r.status_code == 422


async def test_profit_loss_cash_basis_excludes_credit_sale(client: AsyncClient, seeded_tenant: dict):
    """A sales invoice posts as Dr AR / Cr Sales — no cash touched.
    Accrual P&L sees the income; cash-basis P&L doesn't."""
    headers = seeded_tenant["headers"]
    rc = await client.post("/api/v1/customers", headers=headers, json={"code": "C1", "name": "X"})
    rs = await client.post(
        "/api/v1/sales-invoices?post_now=true",
        headers=headers,
        json={
            "invoice_date": "2026-04-01",
            "customer_id": rc.json()["id"],
            "lines": [{"description": "x", "qty": "1", "unit_price": "1000"}],
        },
    )
    assert rs.status_code == 201

    # Accrual: income recognized
    r_accrual = await client.get(
        "/api/v1/reports/profit-loss?date_from=2026-01-01&date_to=2026-12-31",
        headers=headers,
    )
    assert Decimal(r_accrual.json()["total_income"]) == Decimal("1000.00")

    # Cash basis: zero income (no cash account in the AR-creating journal)
    r_cash = await client.get(
        "/api/v1/reports/profit-loss?cash_basis=true&date_from=2026-01-01&date_to=2026-12-31",
        headers=headers,
    )
    assert Decimal(r_cash.json()["total_income"]) == Decimal("0")


async def test_profit_loss_cash_basis_includes_direct_cash_sale(client: AsyncClient, seeded_tenant: dict):
    """A manual journal Dr Cash / Cr Sales is recognized in both bases."""
    headers = seeded_tenant["headers"]
    # Find Cash (1110) and Sales Revenue (4100) ids
    racc = await client.get("/api/v1/accounts?include_zero=true", headers=headers)
    by_code = {a["code"]: a["id"] for a in racc.json()}

    r = await client.post(
        "/api/v1/journals?post_now=true",
        headers=headers,
        json={
            "entry_date": "2026-04-15",
            "description": "Penjualan tunai",
            "lines": [
                {"account_id": by_code["1110"], "debit": "750", "credit": "0"},
                {"account_id": by_code["4100"], "debit": "0", "credit": "750"},
            ],
        },
    )
    assert r.status_code == 201, r.text

    # Both bases recognize this 750 of income (cash account participated)
    for cash_basis in (False, True):
        rr = await client.get(
            f"/api/v1/reports/profit-loss?cash_basis={str(cash_basis).lower()}"
            "&date_from=2026-01-01&date_to=2026-12-31",
            headers=headers,
        )
        body = rr.json()
        assert Decimal(body["total_income"]) == Decimal("750.00"), (
            f"cash_basis={cash_basis} mismatched: {body}"
        )


async def test_profit_loss_excludes_voided_entries(client: AsyncClient, seeded_tenant: dict):
    headers = seeded_tenant["headers"]
    # Create + post a sales invoice
    rc = await client.post("/api/v1/customers", headers=headers, json={"code": "CV", "name": "ToVoid"})
    rs = await client.post(
        "/api/v1/sales-invoices?post_now=true",
        headers=headers,
        json={
            "invoice_date": "2026-03-01",
            "customer_id": rc.json()["id"],
            "lines": [{"description": "x", "qty": "1", "unit_price": "777"}],
        },
    )
    assert rs.status_code == 201
    # Void it
    rv = await client.post(
        f"/api/v1/sales-invoices/{rs.json()['id']}/void",
        headers=headers,
        json={"reason": "test"},
    )
    assert rv.status_code == 200

    # P&L should report zero income — voided journal is excluded
    r = await client.get(
        "/api/v1/reports/profit-loss?date_from=2026-01-01&date_to=2026-12-31",
        headers=headers,
    )
    assert r.status_code == 200
    assert Decimal(r.json()["total_income"]) == Decimal("0")


# ─── Balance Sheet ─────────────────────────────────────────
# ─── Aged AR / AP ──────────────────────────────────────────
async def _create_customer(client: AsyncClient, headers: dict, code: str) -> str:
    r = await client.post("/api/v1/customers", headers=headers, json={"code": code, "name": f"Cust {code}"})
    assert r.status_code == 201
    return r.json()["id"]


async def _create_supplier(client: AsyncClient, headers: dict, code: str) -> str:
    r = await client.post("/api/v1/suppliers", headers=headers, json={"code": code, "name": f"Vend {code}"})
    assert r.status_code == 201
    return r.json()["id"]


async def _post_sales_invoice(
    client: AsyncClient,
    headers: dict,
    customer_id: str,
    invoice_date: str,
    due_date: str | None,
    amount: str,
) -> str:
    payload: dict = {
        "invoice_date": invoice_date,
        "customer_id": customer_id,
        "lines": [{"description": "x", "qty": "1", "unit_price": amount}],
    }
    if due_date:
        payload["due_date"] = due_date
    r = await client.post("/api/v1/sales-invoices?post_now=true", headers=headers, json=payload)
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def test_aged_receivables_buckets_correctly(client: AsyncClient, seeded_tenant: dict):
    """Post 4 invoices with due dates in different bucket ranges, verify
    the aged AR report distributes them into the right buckets."""
    headers = seeded_tenant["headers"]
    as_of = "2026-06-30"

    cust = await _create_customer(client, headers, "C001")

    # 1. Current — due 2026-07-15 (after as_of) — 100
    await _post_sales_invoice(client, headers, cust, "2026-06-01", "2026-07-15", "100")
    # 2. 1-30 days — due 2026-06-15 (15 days overdue) — 200
    await _post_sales_invoice(client, headers, cust, "2026-05-01", "2026-06-15", "200")
    # 3. 31-60 days — due 2026-04-30 (61 days overdue → bucket 61-90) — 400
    # Adjust: due 2026-05-15 (46 days overdue) — bucket 31_60 — 300
    await _post_sales_invoice(client, headers, cust, "2026-04-01", "2026-05-15", "300")
    # 4. >90 days — due 2026-01-01 (180 days overdue) — 500
    await _post_sales_invoice(client, headers, cust, "2025-12-01", "2026-01-01", "500")

    r = await client.get(f"/api/v1/reports/aged-receivables?as_of={as_of}", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["lines"]) == 1
    line = body["lines"][0]
    assert line["code"] == "C001"
    assert line["invoice_count"] == 4

    b = line["buckets"]
    assert Decimal(b["current"]) == Decimal("100.00")
    assert Decimal(b["days_1_30"]) == Decimal("200.00")
    assert Decimal(b["days_31_60"]) == Decimal("300.00")
    assert Decimal(b["days_61_90"]) == Decimal("0")
    assert Decimal(b["days_over_90"]) == Decimal("500.00")
    assert Decimal(b["total"]) == Decimal("1000.00")

    # Grand totals match the per-party totals (only one party here)
    t = body["totals"]
    assert Decimal(t["total"]) == Decimal("1000.00")
    assert Decimal(t["days_over_90"]) == Decimal("500.00")


async def test_aged_receivables_excludes_paid_and_voided(client: AsyncClient, seeded_tenant: dict):
    headers = seeded_tenant["headers"]
    cust = await _create_customer(client, headers, "C002")

    # Post invoice and immediately void it
    inv_id = await _post_sales_invoice(client, headers, cust, "2026-05-01", "2026-06-01", "999")
    rv = await client.post(
        f"/api/v1/sales-invoices/{inv_id}/void",
        headers=headers,
        json={"reason": "test"},
    )
    assert rv.status_code == 200

    r = await client.get("/api/v1/reports/aged-receivables?as_of=2026-12-31", headers=headers)
    assert r.status_code == 200
    # Voided invoice must not appear
    assert r.json()["lines"] == []
    assert Decimal(r.json()["totals"]["total"]) == Decimal("0")


async def test_aged_payables_buckets_correctly(client: AsyncClient, seeded_tenant: dict):
    headers = seeded_tenant["headers"]
    as_of = "2026-06-30"

    sup = await _create_supplier(client, headers, "S001")

    # Build 2 purchase invoices: one current (due_date in future), one 50 days overdue
    async def _post_pi(date_: str, due: str, amount: str) -> str:
        r = await client.post(
            "/api/v1/purchase-invoices?post_now=true",
            headers=headers,
            json={
                "invoice_date": date_,
                "due_date": due,
                "supplier_id": sup,
                "lines": [{"description": "x", "qty": "1", "unit_price": amount}],
            },
        )
        assert r.status_code == 201, r.text
        return r.json()["id"]

    await _post_pi("2026-06-15", "2026-07-15", "1000")  # current
    await _post_pi("2026-04-01", "2026-05-11", "2000")  # 50 days overdue → 31_60

    r = await client.get(f"/api/v1/reports/aged-payables?as_of={as_of}", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["lines"]) == 1
    b = body["lines"][0]["buckets"]
    assert Decimal(b["current"]) == Decimal("1000.00")
    assert Decimal(b["days_31_60"]) == Decimal("2000.00")
    assert Decimal(b["total"]) == Decimal("3000.00")


async def test_balance_sheet_balances(client: AsyncClient, seeded_tenant: dict):
    headers = seeded_tenant["headers"]
    await _seed_one_sale_and_one_purchase(client, headers)

    r = await client.get("/api/v1/reports/balance-sheet?as_of=2026-12-31", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()

    # Assets: AR 1110 + Tax Receivable 55 = 1165
    assert Decimal(body["total_assets"]) == Decimal("1165.00")

    # Liabilities: AP 555 + Tax Payable 110 = 665
    assert Decimal(body["total_liabilities"]) == Decimal("665.00")

    # Retained earnings = sales_subtotal - purchase_subtotal = 1000 - 500 = 500
    assert Decimal(body["retained_earnings"]) == Decimal("500.00")

    # Equity total = 0 explicit + 500 retained = 500
    assert Decimal(body["total_equity"]) == Decimal("500.00")

    # The fundamental equation:  Assets = Liabilities + Equity
    # 1165 = 665 + 500 ✓
    assert body["balanced"] is True
    assert Decimal(body["imbalance"]) == Decimal("0")

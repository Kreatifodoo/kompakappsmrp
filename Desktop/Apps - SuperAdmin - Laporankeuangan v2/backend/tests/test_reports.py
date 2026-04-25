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

"""Inventory ↔ invoicing integration:
- Purchase of stock items: Dr Inventory + stock-in movement
- Sale of stock items: Dr COGS / Cr Inventory + stock-out at avg_cost
- Void on either side reverses both sides cleanly
"""

from decimal import Decimal

from httpx import AsyncClient


async def _wh(client: AsyncClient, headers: dict) -> str:
    r = await client.post(
        "/api/v1/warehouses",
        headers=headers,
        json={"code": "MAIN", "name": "Main", "is_default": True},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _item(client: AsyncClient, headers: dict, sku: str) -> str:
    r = await client.post(
        "/api/v1/items",
        headers=headers,
        json={"sku": sku, "name": f"Item {sku}", "type": "stock"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _customer(client: AsyncClient, headers: dict, code: str) -> str:
    r = await client.post("/api/v1/customers", headers=headers, json={"code": code, "name": code})
    return r.json()["id"]


async def _supplier(client: AsyncClient, headers: dict, code: str) -> str:
    r = await client.post("/api/v1/suppliers", headers=headers, json={"code": code, "name": code})
    return r.json()["id"]


async def _account_id(client: AsyncClient, headers: dict, code: str) -> str:
    r = await client.get("/api/v1/accounts?include_zero=true", headers=headers)
    return next(a["id"] for a in r.json() if a["code"] == code)


# ─── Purchase: stock-in + Dr Inventory ────────────────────
async def test_purchase_stock_item_routes_to_inventory(client: AsyncClient, seeded_tenant: dict):
    """Buying 10 units @ 100 should:
    - Hit Inventory (1300) for 1000 instead of HPP (5100)
    - Increase on-hand qty by 10 with avg_cost 100
    - Create a stock-in movement linked to the invoice
    """
    headers = seeded_tenant["headers"]
    wh = await _wh(client, headers)
    item = await _item(client, headers, "WIDGET")
    sup = await _supplier(client, headers, "S1")

    r = await client.post(
        "/api/v1/purchase-invoices?post_now=true",
        headers=headers,
        json={
            "invoice_date": "2026-04-01",
            "supplier_id": sup,
            "lines": [
                {
                    "description": "Widget",
                    "qty": "10",
                    "unit_price": "100",
                    "item_id": item,
                    "warehouse_id": wh,
                }
            ],
        },
    )
    assert r.status_code == 201, r.text
    invoice = r.json()
    assert Decimal(invoice["total"]) == Decimal("1000.00")

    # Journal: Dr Inventory 1000 / Cr AP 1000 (no tax this time)
    rj = await client.get(f"/api/v1/journals/{invoice['journal_entry_id']}", headers=headers)
    journal = rj.json()
    inv_acct_id = await _account_id(client, headers, "1300")
    hpp_acct_id = await _account_id(client, headers, "5100")
    debit_accounts = {ln["account_id"] for ln in journal["lines"] if Decimal(ln["debit"]) > 0}
    assert inv_acct_id in debit_accounts
    assert hpp_acct_id not in debit_accounts  # NOT routed to HPP

    # Stock balance updated
    rb = await client.get(f"/api/v1/stock-balances?item_id={item}&warehouse_id={wh}", headers=headers)
    bals = rb.json()
    assert len(bals) == 1
    assert Decimal(bals[0]["on_hand_qty"]) == Decimal("10.0000")
    assert Decimal(bals[0]["avg_cost"]) == Decimal("100.0000")

    # Stock movement linked to the invoice
    rm = await client.get(f"/api/v1/stock-movements?item_id={item}", headers=headers)
    moves = rm.json()
    assert len(moves) == 1
    assert moves[0]["direction"] == "in"
    assert moves[0]["source"] == "purchase_invoice"
    assert moves[0]["source_id"] == invoice["id"]


# ─── Sale: stock-out + Dr COGS / Cr Inventory ─────────────
async def test_sale_of_stock_item_creates_cogs_and_movement(client: AsyncClient, seeded_tenant: dict):
    """After buying 10 @ 100 and selling 3 @ 250:
    - Sale journal has Dr AR + Dr COGS / Cr Sales + Cr Inventory
    - On-hand drops from 10 to 7; avg_cost stays 100
    - Stock-out movement valued at 100 (avg_cost), total_cost 300
    """
    headers = seeded_tenant["headers"]
    wh = await _wh(client, headers)
    item = await _item(client, headers, "WIDGET")
    sup = await _supplier(client, headers, "S1")
    cust = await _customer(client, headers, "C1")

    # Buy 10 @ 100
    rp = await client.post(
        "/api/v1/purchase-invoices?post_now=true",
        headers=headers,
        json={
            "invoice_date": "2026-04-01",
            "supplier_id": sup,
            "lines": [
                {
                    "description": "Widget",
                    "qty": "10",
                    "unit_price": "100",
                    "item_id": item,
                    "warehouse_id": wh,
                }
            ],
        },
    )
    assert rp.status_code == 201

    # Sell 3 @ 250
    rs = await client.post(
        "/api/v1/sales-invoices?post_now=true",
        headers=headers,
        json={
            "invoice_date": "2026-04-15",
            "customer_id": cust,
            "lines": [
                {
                    "description": "Widget",
                    "qty": "3",
                    "unit_price": "250",
                    "item_id": item,
                    "warehouse_id": wh,
                }
            ],
        },
    )
    assert rs.status_code == 201, rs.text
    sale = rs.json()
    assert Decimal(sale["total"]) == Decimal("750.00")

    # Verify journal: Dr AR 750 / Cr Sales 750 / Dr COGS 300 / Cr Inv 300
    rj = await client.get(f"/api/v1/journals/{sale['journal_entry_id']}", headers=headers)
    journal = rj.json()
    debits = sum(Decimal(ln["debit"]) for ln in journal["lines"])
    credits = sum(Decimal(ln["credit"]) for ln in journal["lines"])
    assert debits == credits == Decimal("1050.00")  # 750 + 300

    cogs_acct = await _account_id(client, headers, "5100")  # cogs maps to 5100
    inv_acct = await _account_id(client, headers, "1300")
    cogs_lines = [ln for ln in journal["lines"] if ln["account_id"] == cogs_acct]
    inv_lines = [ln for ln in journal["lines"] if ln["account_id"] == inv_acct]
    assert len(cogs_lines) == 1
    assert Decimal(cogs_lines[0]["debit"]) == Decimal("300.00")
    assert len(inv_lines) == 1
    assert Decimal(inv_lines[0]["credit"]) == Decimal("300.00")

    # Stock balance updated
    rb = await client.get(f"/api/v1/stock-balances?item_id={item}&warehouse_id={wh}", headers=headers)
    bal = rb.json()[0]
    assert Decimal(bal["on_hand_qty"]) == Decimal("7.0000")
    assert Decimal(bal["avg_cost"]) == Decimal("100.0000")  # unchanged on outflow


# ─── Void of sale restores stock ──────────────────────────
async def test_void_sale_restores_stock(client: AsyncClient, seeded_tenant: dict):
    headers = seeded_tenant["headers"]
    wh = await _wh(client, headers)
    item = await _item(client, headers, "W2")
    sup = await _supplier(client, headers, "S2")
    cust = await _customer(client, headers, "C2")

    # Buy 10 @ 100, sell 4 @ 200
    await client.post(
        "/api/v1/purchase-invoices?post_now=true",
        headers=headers,
        json={
            "invoice_date": "2026-04-01",
            "supplier_id": sup,
            "lines": [
                {"description": "x", "qty": "10", "unit_price": "100", "item_id": item, "warehouse_id": wh}
            ],
        },
    )
    rs = await client.post(
        "/api/v1/sales-invoices?post_now=true",
        headers=headers,
        json={
            "invoice_date": "2026-04-15",
            "customer_id": cust,
            "lines": [
                {"description": "x", "qty": "4", "unit_price": "200", "item_id": item, "warehouse_id": wh}
            ],
        },
    )
    sale = rs.json()
    # Pre-void: 6 on hand
    rb = await client.get(f"/api/v1/stock-balances?item_id={item}&warehouse_id={wh}", headers=headers)
    assert Decimal(rb.json()[0]["on_hand_qty"]) == Decimal("6.0000")

    # Void the sale
    rv = await client.post(
        f"/api/v1/sales-invoices/{sale['id']}/void",
        headers=headers,
        json={"reason": "test"},
    )
    assert rv.status_code == 200

    # Post-void: 10 on hand again
    rb2 = await client.get(f"/api/v1/stock-balances?item_id={item}&warehouse_id={wh}", headers=headers)
    assert Decimal(rb2.json()[0]["on_hand_qty"]) == Decimal("10.0000")

    # Movement ledger now has out + compensating in
    rm = await client.get(f"/api/v1/stock-movements?item_id={item}", headers=headers)
    moves = rm.json()
    sources = sorted(m["source"] for m in moves)
    assert sources == ["purchase_invoice", "sales_invoice", "void_sales_invoice"]


async def test_void_purchase_reverses_stock_in(client: AsyncClient, seeded_tenant: dict):
    headers = seeded_tenant["headers"]
    wh = await _wh(client, headers)
    item = await _item(client, headers, "W3")
    sup = await _supplier(client, headers, "S3")

    rp = await client.post(
        "/api/v1/purchase-invoices?post_now=true",
        headers=headers,
        json={
            "invoice_date": "2026-04-01",
            "supplier_id": sup,
            "lines": [
                {"description": "x", "qty": "5", "unit_price": "200", "item_id": item, "warehouse_id": wh}
            ],
        },
    )
    inv = rp.json()
    rb = await client.get(f"/api/v1/stock-balances?item_id={item}&warehouse_id={wh}", headers=headers)
    assert Decimal(rb.json()[0]["on_hand_qty"]) == Decimal("5.0000")

    rv = await client.post(
        f"/api/v1/purchase-invoices/{inv['id']}/void",
        headers=headers,
        json={"reason": "received in error"},
    )
    assert rv.status_code == 200

    rb2 = await client.get(f"/api/v1/stock-balances?item_id={item}&warehouse_id={wh}", headers=headers)
    assert Decimal(rb2.json()[0]["on_hand_qty"]) == Decimal("0")


# ─── Mixed lines: services + stock in same invoice ────────
async def test_mixed_invoice_with_service_and_stock_lines(client: AsyncClient, seeded_tenant: dict):
    """A single sales invoice with one stock line and one service line.
    Only the stock line drives a stock-out + COGS."""
    headers = seeded_tenant["headers"]
    wh = await _wh(client, headers)
    item = await _item(client, headers, "MIX-1")
    sup = await _supplier(client, headers, "MIX-S")
    cust = await _customer(client, headers, "MIX-C")

    await client.post(
        "/api/v1/purchase-invoices?post_now=true",
        headers=headers,
        json={
            "invoice_date": "2026-04-01",
            "supplier_id": sup,
            "lines": [
                {"description": "x", "qty": "5", "unit_price": "100", "item_id": item, "warehouse_id": wh}
            ],
        },
    )

    rs = await client.post(
        "/api/v1/sales-invoices?post_now=true",
        headers=headers,
        json={
            "invoice_date": "2026-04-20",
            "customer_id": cust,
            "lines": [
                {
                    "description": "Widget",
                    "qty": "2",
                    "unit_price": "150",
                    "item_id": item,
                    "warehouse_id": wh,
                },  # stock line, COGS=200
                {"description": "Setup fee", "qty": "1", "unit_price": "50"},  # service
            ],
        },
    )
    assert rs.status_code == 201
    sale = rs.json()
    assert Decimal(sale["subtotal"]) == Decimal("350.00")  # 300 + 50

    # Journal: AR 350 dr; Sales 350 cr; COGS 200 dr; Inventory 200 cr
    rj = await client.get(f"/api/v1/journals/{sale['journal_entry_id']}", headers=headers)
    journal = rj.json()
    cogs_acct = await _account_id(client, headers, "5100")
    inv_acct = await _account_id(client, headers, "1300")
    cogs_dr = sum(Decimal(ln["debit"]) for ln in journal["lines"] if ln["account_id"] == cogs_acct)
    inv_cr = sum(Decimal(ln["credit"]) for ln in journal["lines"] if ln["account_id"] == inv_acct)
    assert cogs_dr == Decimal("200.00")  # only the 2 stock units × 100 avg
    assert inv_cr == Decimal("200.00")

    # Only one stock-out movement (for the stock line)
    rm = await client.get(f"/api/v1/stock-movements?item_id={item}", headers=headers)
    out_moves = [m for m in rm.json() if m["source"] == "sales_invoice"]
    assert len(out_moves) == 1
    assert Decimal(out_moves[0]["qty"]) == Decimal("2.0000")


# ─── Validation: stock item without warehouse_id ──────────
async def test_stock_item_without_warehouse_rejected(client: AsyncClient, seeded_tenant: dict):
    headers = seeded_tenant["headers"]
    item = await _item(client, headers, "NW")
    sup = await _supplier(client, headers, "NW-S")

    r = await client.post(
        "/api/v1/purchase-invoices",
        headers=headers,
        json={
            "invoice_date": "2026-04-01",
            "supplier_id": sup,
            "lines": [
                {"description": "x", "qty": "1", "unit_price": "100", "item_id": item}  # no warehouse_id
            ],
        },
    )
    assert r.status_code == 422
    assert "warehouse_id" in r.json()["error"]["message"]

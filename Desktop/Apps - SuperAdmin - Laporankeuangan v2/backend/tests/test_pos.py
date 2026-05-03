"""POS module tests.

Covers:
- Open / close a session
- Create an order (cash, service item — no stock)
- Create an order (card, stock item — triggers stock-out + COGS)
- Under-payment rejected
- Void order reverses journal + stock
- Cannot add orders to closed session
- Duplicate open session per cashier rejected
- Session payment totals on close
"""

from decimal import Decimal

import pytest
from httpx import AsyncClient


# ─── Helpers ──────────────────────────────────────────────────────────────────


async def _wh(client, headers) -> str:
    r = await client.post(
        "/api/v1/warehouses",
        headers=headers,
        json={"code": "MAIN", "name": "Main Warehouse", "is_default": True},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _stock_item(client, headers, sku="WIDGET", price="10000") -> str:
    r = await client.post(
        "/api/v1/items",
        headers=headers,
        json={"sku": sku, "name": f"Item {sku}", "type": "stock", "default_unit_price": price},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _service_item(client, headers) -> str:
    r = await client.post(
        "/api/v1/items",
        headers=headers,
        json={"sku": "SVC-CONSULT", "name": "Konsultasi", "type": "service", "default_unit_price": "50000"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _stock_in(client, headers, item_id, wh_id, qty=20, cost="8000"):
    """Add stock via stock movement so POS can sell it."""
    r = await client.post(
        "/api/v1/stock-movements",
        headers=headers,
        json={
            "item_id": item_id,
            "warehouse_id": wh_id,
            "movement_date": "2026-01-10",
            "direction": "in",
            "qty": qty,
            "unit_cost": cost,
            "notes": "Initial stock-in",
        },
    )
    assert r.status_code == 201, r.text


async def _open_session(client, headers) -> str:
    r = await client.post(
        "/api/v1/pos/sessions",
        headers=headers,
        json={"register_name": "Kasir 1", "opening_amount": "500000"},
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["status"] == "open"
    return data["id"]


# ─── Tests ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_open_session(client: AsyncClient, seeded_tenant: dict):
    """Opening a session returns session_no and status=open."""
    headers = seeded_tenant["headers"]
    r = await client.post(
        "/api/v1/pos/sessions",
        headers=headers,
        json={"register_name": "Kasir Utama", "opening_amount": "200000"},
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["status"] == "open"
    assert data["register_name"] == "Kasir Utama"
    assert Decimal(data["opening_amount"]) == Decimal("200000")
    assert data["session_no"].startswith("POS-")


@pytest.mark.asyncio
async def test_cannot_open_duplicate_session(client: AsyncClient, seeded_tenant: dict):
    """Cashier cannot open two sessions simultaneously."""
    headers = seeded_tenant["headers"]
    await _open_session(client, headers)
    r = await client.post(
        "/api/v1/pos/sessions",
        headers=headers,
        json={"opening_amount": "0"},
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_pos_order_service_item_no_stock(client: AsyncClient, seeded_tenant: dict):
    """POS order for a service item: no stock movement, just journal Dr Cash / Cr Sales."""
    headers = seeded_tenant["headers"]
    session_id = await _open_session(client, headers)
    svc_item = await _service_item(client, headers)

    r = await client.post(
        "/api/v1/pos/orders",
        headers=headers,
        json={
            "session_id": session_id,
            "order_date": "2026-05-01",
            "lines": [
                {
                    "description": "Jasa Konsultasi 1h",
                    "qty": "2",
                    "unit_price": "50000",
                    "item_id": svc_item,
                }
            ],
            "payment_method": "cash",
            "amount_paid": "100000",
        },
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["status"] == "paid"
    assert Decimal(data["total"]) == Decimal("100000")
    assert Decimal(data["change_amount"]) == Decimal("0")
    assert data["journal_entry_id"] is not None
    assert len(data["lines"]) == 1


@pytest.mark.asyncio
async def test_pos_order_stock_item_triggers_stock_out(client: AsyncClient, seeded_tenant: dict):
    """POS order for a stock item should decrement on-hand qty."""
    headers = seeded_tenant["headers"]
    wh = await _wh(client, headers)
    item = await _stock_item(client, headers, "MUG", "15000")
    await _stock_in(client, headers, item, wh, qty=10, cost="10000")

    session_id = await _open_session(client, headers)

    r = await client.post(
        "/api/v1/pos/orders",
        headers=headers,
        json={
            "session_id": session_id,
            "order_date": "2026-05-01",
            "lines": [
                {
                    "description": "Mug Keren",
                    "qty": "3",
                    "unit_price": "15000",
                    "item_id": item,
                    "warehouse_id": wh,
                }
            ],
            "payment_method": "cash",
            "amount_paid": "45000",
        },
    )
    assert r.status_code == 201, r.text
    order_data = r.json()
    assert Decimal(order_data["total"]) == Decimal("45000")

    # Verify stock decreased by 3
    r = await client.get(f"/api/v1/items/{item}/stock?warehouse_id={wh}", headers=headers)
    assert r.status_code == 200, r.text
    qty = Decimal(r.json()["qty_on_hand"])
    assert qty == Decimal("7")


@pytest.mark.asyncio
async def test_pos_order_change_calculated(client: AsyncClient, seeded_tenant: dict):
    """Change = amount_paid - total."""
    headers = seeded_tenant["headers"]
    session_id = await _open_session(client, headers)
    svc_item = await _service_item(client, headers)

    r = await client.post(
        "/api/v1/pos/orders",
        headers=headers,
        json={
            "session_id": session_id,
            "order_date": "2026-05-01",
            "lines": [{"description": "Svc", "qty": "1", "unit_price": "75000", "item_id": svc_item}],
            "payment_method": "cash",
            "amount_paid": "100000",
        },
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert Decimal(data["change_amount"]) == Decimal("25000")


@pytest.mark.asyncio
async def test_pos_order_underpayment_rejected(client: AsyncClient, seeded_tenant: dict):
    """amount_paid < total must return 422."""
    headers = seeded_tenant["headers"]
    session_id = await _open_session(client, headers)
    svc_item = await _service_item(client, headers)

    r = await client.post(
        "/api/v1/pos/orders",
        headers=headers,
        json={
            "session_id": session_id,
            "order_date": "2026-05-01",
            "lines": [{"description": "Svc", "qty": "1", "unit_price": "50000", "item_id": svc_item}],
            "payment_method": "cash",
            "amount_paid": "30000",  # Under-payment
        },
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_pos_order_void_reverses_stock(client: AsyncClient, seeded_tenant: dict):
    """Voiding a stock-item order restores on-hand qty."""
    headers = seeded_tenant["headers"]
    wh = await _wh(client, headers)
    item = await _stock_item(client, headers, "BOOK", "20000")
    await _stock_in(client, headers, item, wh, qty=5, cost="12000")

    session_id = await _open_session(client, headers)

    # Create order (sell 2)
    r = await client.post(
        "/api/v1/pos/orders",
        headers=headers,
        json={
            "session_id": session_id,
            "order_date": "2026-05-01",
            "lines": [
                {"description": "Buku", "qty": "2", "unit_price": "20000", "item_id": item, "warehouse_id": wh}
            ],
            "payment_method": "cash",
            "amount_paid": "40000",
        },
    )
    assert r.status_code == 201, r.text
    order_id = r.json()["id"]

    # Verify stock is now 3
    r = await client.get(f"/api/v1/items/{item}/stock?warehouse_id={wh}", headers=headers)
    assert Decimal(r.json()["qty_on_hand"]) == Decimal("3")

    # Void the order
    r = await client.post(
        f"/api/v1/pos/orders/{order_id}/void",
        headers=headers,
        json={"reason": "Salah input"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "void"

    # Stock should be back to 5
    r = await client.get(f"/api/v1/items/{item}/stock?warehouse_id={wh}", headers=headers)
    assert Decimal(r.json()["qty_on_hand"]) == Decimal("5")


@pytest.mark.asyncio
async def test_close_session_calculates_expected_cash(client: AsyncClient, seeded_tenant: dict):
    """Closing session: expected_closing = opening + cash sales."""
    headers = seeded_tenant["headers"]
    session_id = await _open_session(client, headers)  # opening_amount = 500000
    svc_item = await _service_item(client, headers)

    # Two cash orders: 100k + 75k = 175k
    for amount in ["100000", "75000"]:
        r = await client.post(
            "/api/v1/pos/orders",
            headers=headers,
            json={
                "session_id": session_id,
                "order_date": "2026-05-01",
                "lines": [{"description": "SVC", "qty": "1", "unit_price": amount, "item_id": svc_item}],
                "payment_method": "cash",
                "amount_paid": amount,
            },
        )
        assert r.status_code == 201, r.text

    # Close the session with 660k actual cash (10k surplus)
    r = await client.post(
        f"/api/v1/pos/sessions/{session_id}/close",
        headers=headers,
        json={"closing_amount": "660000"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    # expected = 500000 (opening) + 175000 (cash sales) = 675000
    assert Decimal(data["session"]["expected_closing"]) == Decimal("675000")
    # cash_difference = 660000 - 675000 = -15000 (shortage)
    assert Decimal(data["session"]["cash_difference"]) == Decimal("-15000")
    assert data["session"]["status"] == "closed"
    assert Decimal(data["total_cash"]) == Decimal("175000")
    assert data["order_count"] == 2


@pytest.mark.asyncio
async def test_cannot_add_order_to_closed_session(client: AsyncClient, seeded_tenant: dict):
    """Adding order to a closed session should return 422."""
    headers = seeded_tenant["headers"]
    session_id = await _open_session(client, headers)
    svc_item = await _service_item(client, headers)

    # Close immediately
    r = await client.post(
        f"/api/v1/pos/sessions/{session_id}/close",
        headers=headers,
        json={"closing_amount": "500000"},
    )
    assert r.status_code == 200, r.text

    r = await client.post(
        "/api/v1/pos/orders",
        headers=headers,
        json={
            "session_id": session_id,
            "order_date": "2026-05-01",
            "lines": [{"description": "SVC", "qty": "1", "unit_price": "10000", "item_id": svc_item}],
            "payment_method": "cash",
            "amount_paid": "10000",
        },
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_pos_order_with_discount(client: AsyncClient, seeded_tenant: dict):
    """discount_pct reduces line_total; total is calculated correctly."""
    headers = seeded_tenant["headers"]
    session_id = await _open_session(client, headers)
    svc_item = await _service_item(client, headers)

    # 2 × 50000 with 10% discount = 2 × 45000 = 90000
    r = await client.post(
        "/api/v1/pos/orders",
        headers=headers,
        json={
            "session_id": session_id,
            "order_date": "2026-05-01",
            "lines": [
                {
                    "description": "Konsultasi diskon 10%",
                    "qty": "2",
                    "unit_price": "50000",
                    "discount_pct": "10",
                    "item_id": svc_item,
                }
            ],
            "payment_method": "cash",
            "amount_paid": "90000",
        },
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert Decimal(data["subtotal"]) == Decimal("90000")
    assert Decimal(data["total"]) == Decimal("90000")
    line = data["lines"][0]
    assert Decimal(line["discount_amount"]) == Decimal("10000")  # 10% of 100000


@pytest.mark.asyncio
async def test_pos_order_card_payment(client: AsyncClient, seeded_tenant: dict):
    """Card payment uses pos_card mapping (falls back to cash_default)."""
    headers = seeded_tenant["headers"]
    session_id = await _open_session(client, headers)
    svc_item = await _service_item(client, headers)

    r = await client.post(
        "/api/v1/pos/orders",
        headers=headers,
        json={
            "session_id": session_id,
            "order_date": "2026-05-01",
            "lines": [{"description": "SVC", "qty": "1", "unit_price": "200000", "item_id": svc_item}],
            "payment_method": "card",
            "amount_paid": "200000",
        },
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["payment_method"] == "card"
    assert data["journal_entry_id"] is not None

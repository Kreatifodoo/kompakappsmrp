"""Stock card report — per-(item, warehouse) chronological ledger."""

from decimal import Decimal

from httpx import AsyncClient


# ── helpers ──────────────────────────────────────────────────────────────────

async def _wh(client: AsyncClient, headers: dict, code: str = "MAIN") -> str:
    r = await client.post(
        "/api/v1/warehouses",
        headers=headers,
        json={"code": code, "name": code},
    )
    assert r.status_code == 201
    return r.json()["id"]


async def _item(client: AsyncClient, headers: dict, sku: str) -> str:
    r = await client.post(
        "/api/v1/items",
        headers=headers,
        json={"sku": sku, "name": sku, "type": "stock"},
    )
    assert r.status_code == 201
    return r.json()["id"]


async def _move(
    client: AsyncClient,
    headers: dict,
    *,
    item_id: str,
    warehouse_id: str,
    direction: str,
    qty: str,
    unit_cost: str = "0",
    date_: str,
) -> dict:
    r = await client.post(
        "/api/v1/stock-movements",
        headers=headers,
        json={
            "item_id": item_id,
            "warehouse_id": warehouse_id,
            "movement_date": date_,
            "direction": direction,
            "qty": qty,
            "unit_cost": unit_cost,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


# ── tests ─────────────────────────────────────────────────────────────────────

async def test_stock_card_no_movements_returns_zero_balances(
    client: AsyncClient, seeded_tenant: dict
):
    """Empty stock card — no movements at all → all zeros, empty lines."""
    headers = seeded_tenant["headers"]
    wh = await _wh(client, headers)
    item = await _item(client, headers, "SC-EMPTY")

    r = await client.get(
        f"/api/v1/items/{item}/stock-card",
        params={"warehouse_id": wh},
        headers=headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["lines"] == []
    assert Decimal(body["opening_qty"]) == Decimal("0")
    assert Decimal(body["closing_qty"]) == Decimal("0")
    assert Decimal(body["period_in_qty"]) == Decimal("0")
    assert Decimal(body["period_out_qty"]) == Decimal("0")


async def test_stock_card_full_history_in_out(client: AsyncClient, seeded_tenant: dict):
    """Full history (no date filter): 2 ins + 1 out.
    Verifies running qty_after, avg_cost_after, value_after per row."""
    headers = seeded_tenant["headers"]
    wh = await _wh(client, headers, "WH-SC1")
    item = await _item(client, headers, "SC-1")

    # Day 1: buy 10 @ 100
    await _move(client, headers, item_id=item, warehouse_id=wh,
                direction="in", qty="10", unit_cost="100", date_="2026-01-10")
    # Day 5: buy 5 @ 200  → avg = (1000+1000)/15 = 133.3333...
    await _move(client, headers, item_id=item, warehouse_id=wh,
                direction="in", qty="5", unit_cost="200", date_="2026-01-15")
    # Day 10: sell 6 at current avg
    await _move(client, headers, item_id=item, warehouse_id=wh,
                direction="out", qty="6", date_="2026-01-20")

    r = await client.get(
        f"/api/v1/items/{item}/stock-card",
        params={"warehouse_id": wh},
        headers=headers,
    )
    assert r.status_code == 200
    body = r.json()

    assert Decimal(body["opening_qty"]) == Decimal("0")
    assert Decimal(body["opening_value"]) == Decimal("0.00")

    lines = body["lines"]
    assert len(lines) == 3

    # Row 1: in 10 @ 100 → qty_after=10, avg=100
    assert lines[0]["direction"] == "in"
    assert Decimal(lines[0]["qty_after"]) == Decimal("10.0000")
    assert Decimal(lines[0]["avg_cost_after"]) == Decimal("100.0000")
    assert Decimal(lines[0]["value_after"]) == Decimal("1000.00")

    # Row 2: in 5 @ 200 → qty_after=15
    assert lines[1]["direction"] == "in"
    assert Decimal(lines[1]["qty_after"]) == Decimal("15.0000")

    # Row 3: out 6 → qty_after=9
    assert lines[2]["direction"] == "out"
    assert Decimal(lines[2]["qty_after"]) == Decimal("9.0000")

    # Closing = last row's snapshot
    assert Decimal(body["closing_qty"]) == Decimal("9.0000")
    assert Decimal(body["closing_avg_cost"]) == Decimal(lines[2]["avg_cost_after"])

    # Period summary
    assert Decimal(body["period_in_qty"]) == Decimal("15.0000")
    assert Decimal(body["period_out_qty"]) == Decimal("6.0000")
    assert Decimal(body["period_in_value"]) == Decimal("2000.00")  # 10×100 + 5×200


async def test_stock_card_date_filter_opening_seeded_from_prior_movement(
    client: AsyncClient, seeded_tenant: dict
):
    """With date_from set, the opening balance is taken from the last
    movement *before* that date (not from zero)."""
    headers = seeded_tenant["headers"]
    wh = await _wh(client, headers, "WH-SC2")
    item = await _item(client, headers, "SC-2")

    # Pre-period: buy 20 @ 50  (before date_from)
    await _move(client, headers, item_id=item, warehouse_id=wh,
                direction="in", qty="20", unit_cost="50", date_="2026-02-01")
    # In-period: sell 5
    await _move(client, headers, item_id=item, warehouse_id=wh,
                direction="out", qty="5", date_="2026-03-10")
    # In-period: buy 10 @ 80
    await _move(client, headers, item_id=item, warehouse_id=wh,
                direction="in", qty="10", unit_cost="80", date_="2026-03-15")

    r = await client.get(
        f"/api/v1/items/{item}/stock-card",
        params={"warehouse_id": wh, "date_from": "2026-03-01"},
        headers=headers,
    )
    assert r.status_code == 200
    body = r.json()

    # Opening = snapshot after the Feb-01 movement: qty=20, avg=50
    assert Decimal(body["opening_qty"]) == Decimal("20.0000")
    assert Decimal(body["opening_avg_cost"]) == Decimal("50.0000")
    assert Decimal(body["opening_value"]) == Decimal("1000.00")

    # Only the two March movements should appear
    assert len(body["lines"]) == 2
    assert body["lines"][0]["direction"] == "out"
    assert body["lines"][1]["direction"] == "in"

    # Closing matches last line
    assert Decimal(body["closing_qty"]) == Decimal(body["lines"][-1]["qty_after"])


async def test_stock_card_date_to_filter(client: AsyncClient, seeded_tenant: dict):
    """date_to cuts off movements after the given date."""
    headers = seeded_tenant["headers"]
    wh = await _wh(client, headers, "WH-SC3")
    item = await _item(client, headers, "SC-3")

    await _move(client, headers, item_id=item, warehouse_id=wh,
                direction="in", qty="10", unit_cost="100", date_="2026-04-01")
    await _move(client, headers, item_id=item, warehouse_id=wh,
                direction="in", qty="5", unit_cost="200", date_="2026-04-10")
    await _move(client, headers, item_id=item, warehouse_id=wh,
                direction="out", qty="3", date_="2026-04-20")

    # Ask for up to Apr-10 only → 2 rows, no outflow
    r = await client.get(
        f"/api/v1/items/{item}/stock-card",
        params={"warehouse_id": wh, "date_to": "2026-04-10"},
        headers=headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["lines"]) == 2
    assert all(ln["direction"] == "in" for ln in body["lines"])
    assert Decimal(body["closing_qty"]) == Decimal("15.0000")


async def test_stock_card_date_range_no_movements_in_range(
    client: AsyncClient, seeded_tenant: dict
):
    """If movements exist outside the range the card has no lines but
    opening balance is correctly seeded from the last prior movement."""
    headers = seeded_tenant["headers"]
    wh = await _wh(client, headers, "WH-SC4")
    item = await _item(client, headers, "SC-4")

    await _move(client, headers, item_id=item, warehouse_id=wh,
                direction="in", qty="8", unit_cost="100", date_="2026-01-05")

    # Ask for a future window — nothing there
    r = await client.get(
        f"/api/v1/items/{item}/stock-card",
        params={"warehouse_id": wh, "date_from": "2026-06-01", "date_to": "2026-06-30"},
        headers=headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["lines"] == []
    # Opening = closing = state after Jan-05 movement
    assert Decimal(body["opening_qty"]) == Decimal("8.0000")
    assert Decimal(body["closing_qty"]) == Decimal("8.0000")


async def test_stock_card_unknown_item_returns_404(
    client: AsyncClient, seeded_tenant: dict
):
    from uuid import uuid4

    headers = seeded_tenant["headers"]
    wh = await _wh(client, headers, "WH-SC5")
    r = await client.get(
        f"/api/v1/items/{uuid4()}/stock-card",
        params={"warehouse_id": wh},
        headers=headers,
    )
    assert r.status_code == 404


async def test_stock_card_unknown_warehouse_returns_404(
    client: AsyncClient, seeded_tenant: dict
):
    from uuid import uuid4

    headers = seeded_tenant["headers"]
    item = await _item(client, headers, "SC-5")
    r = await client.get(
        f"/api/v1/items/{item}/stock-card",
        params={"warehouse_id": str(uuid4())},
        headers=headers,
    )
    assert r.status_code == 404


async def test_stock_card_metadata_fields(client: AsyncClient, seeded_tenant: dict):
    """Verify item/warehouse metadata is echoed correctly."""
    headers = seeded_tenant["headers"]
    wh = await _wh(client, headers, "META-WH")
    item_id = await _item(client, headers, "META-SKU")

    await _move(client, headers, item_id=item_id, warehouse_id=wh,
                direction="in", qty="1", unit_cost="10", date_="2026-05-01")

    r = await client.get(
        f"/api/v1/items/{item_id}/stock-card",
        params={"warehouse_id": wh},
        headers=headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["item_id"] == item_id
    assert body["sku"] == "META-SKU"
    assert body["warehouse_id"] == wh
    assert body["warehouse_code"] == "META-WH"

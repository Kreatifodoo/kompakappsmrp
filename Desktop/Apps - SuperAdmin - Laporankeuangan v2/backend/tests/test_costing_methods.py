"""FIFO / LIFO costing — verifies layer consumption and method switching."""

from decimal import Decimal

from httpx import AsyncClient


async def _wh(client: AsyncClient, headers: dict) -> str:
    r = await client.post(
        "/api/v1/warehouses",
        headers=headers,
        json={"code": "MAIN", "name": "Main", "is_default": True},
    )
    return r.json()["id"]


async def _item(client: AsyncClient, headers: dict, sku: str) -> str:
    r = await client.post(
        "/api/v1/items",
        headers=headers,
        json={"sku": sku, "name": sku, "type": "stock"},
    )
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
    date_: str = "2026-04-15",
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
    return r


async def _set_method(client: AsyncClient, headers: dict, method: str) -> dict:
    r = await client.put(
        "/api/v1/costing-method",
        headers=headers,
        json={"method": method, "seed_opening_layers": True},
    )
    assert r.status_code == 200, r.text
    return r.json()


# ─── Method get/set ───────────────────────────────────────
async def test_default_method_is_avg(client: AsyncClient, seeded_tenant: dict):
    r = await client.get("/api/v1/costing-method", headers=seeded_tenant["headers"])
    assert r.status_code == 200
    assert r.json()["method"] == "avg"


async def test_switch_to_fifo_seeds_opening_layers(client: AsyncClient, seeded_tenant: dict):
    """Switching avg → fifo while stock exists should create one opening
    layer per (item, warehouse), so the next outflow has something to
    consume."""
    headers = seeded_tenant["headers"]
    wh = await _wh(client, headers)
    item = await _item(client, headers, "OPEN")
    # Receive 10 @ 100 under avg
    await _move(client, headers, item_id=item, warehouse_id=wh, direction="in", qty="10", unit_cost="100")

    await _set_method(client, headers, "fifo")

    # Now an outflow should succeed (consuming the seeded opening layer)
    r = await _move(client, headers, item_id=item, warehouse_id=wh, direction="out", qty="3")
    assert r.status_code == 201, r.text
    body = r.json()
    assert Decimal(body["unit_cost"]) == Decimal("100.0000")
    assert Decimal(body["total_cost"]) == Decimal("300.00")
    assert Decimal(body["qty_after"]) == Decimal("7.0000")


# ─── FIFO consumption ─────────────────────────────────────
async def test_fifo_consumes_oldest_layer_first(client: AsyncClient, seeded_tenant: dict):
    """Layer A (10@100) + Layer B (5@120). FIFO out 12:
    all 10 from A (1000) + 2 from B (240) = 1240; blended = 103.3333"""
    headers = seeded_tenant["headers"]
    await _set_method(client, headers, "fifo")
    wh = await _wh(client, headers)
    item = await _item(client, headers, "FIFO-1")

    await _move(
        client,
        headers,
        item_id=item,
        warehouse_id=wh,
        direction="in",
        qty="10",
        unit_cost="100",
        date_="2026-04-01",
    )
    await _move(
        client,
        headers,
        item_id=item,
        warehouse_id=wh,
        direction="in",
        qty="5",
        unit_cost="120",
        date_="2026-04-05",
    )

    r = await _move(
        client, headers, item_id=item, warehouse_id=wh, direction="out", qty="12", date_="2026-04-10"
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert Decimal(body["qty_after"]) == Decimal("3.0000")
    assert Decimal(body["total_cost"]) == Decimal("1240.00")
    # Blended unit_cost ≈ 103.3333 (1240/12)
    assert abs(Decimal(body["unit_cost"]) - Decimal("103.3333")) < Decimal("0.001")
    # Remaining stock is 3 units @ 120 → avg_cost should reflect that
    assert Decimal(body["avg_cost_after"]) == Decimal("120.0000")


# ─── LIFO consumption ─────────────────────────────────────
async def test_lifo_consumes_newest_layer_first(client: AsyncClient, seeded_tenant: dict):
    """Same layers as FIFO test but LIFO out 12:
    all 5 from B (600) + 7 from A (700) = 1300; blended = 108.3333.
    Remaining: 3 of A @ 100."""
    headers = seeded_tenant["headers"]
    await _set_method(client, headers, "lifo")
    wh = await _wh(client, headers)
    item = await _item(client, headers, "LIFO-1")

    await _move(
        client,
        headers,
        item_id=item,
        warehouse_id=wh,
        direction="in",
        qty="10",
        unit_cost="100",
        date_="2026-04-01",
    )
    await _move(
        client,
        headers,
        item_id=item,
        warehouse_id=wh,
        direction="in",
        qty="5",
        unit_cost="120",
        date_="2026-04-05",
    )

    r = await _move(
        client, headers, item_id=item, warehouse_id=wh, direction="out", qty="12", date_="2026-04-10"
    )
    body = r.json()
    assert Decimal(body["qty_after"]) == Decimal("3.0000")
    assert Decimal(body["total_cost"]) == Decimal("1300.00")
    assert Decimal(body["avg_cost_after"]) == Decimal("100.0000")  # only A remaining


# ─── FIFO: full layer exhaustion + valuation ─────────────
async def test_fifo_layer_exhaustion(client: AsyncClient, seeded_tenant: dict):
    """After consuming Layer A entirely, valuation report uses Layer B's cost."""
    headers = seeded_tenant["headers"]
    await _set_method(client, headers, "fifo")
    wh = await _wh(client, headers)
    item = await _item(client, headers, "EXH-1")

    await _move(
        client,
        headers,
        item_id=item,
        warehouse_id=wh,
        direction="in",
        qty="10",
        unit_cost="100",
        date_="2026-04-01",
    )
    await _move(
        client,
        headers,
        item_id=item,
        warehouse_id=wh,
        direction="in",
        qty="5",
        unit_cost="200",
        date_="2026-04-05",
    )
    # Take exactly Layer A
    await _move(client, headers, item_id=item, warehouse_id=wh, direction="out", qty="10", date_="2026-04-08")

    rv = await client.get("/api/v1/reports/stock-valuation", headers=headers)
    line = next(li for li in rv.json()["lines"] if li["sku"] == "EXH-1")
    assert Decimal(line["on_hand_qty"]) == Decimal("5.0000")
    # Only Layer B remains, all at 200
    assert Decimal(line["weighted_avg_cost"]) == Decimal("200")
    assert Decimal(line["value"]) == Decimal("1000.00")

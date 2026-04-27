"""Inventory: items, warehouses, weighted-average stock movements,
and on-hand / valuation reports."""

from decimal import Decimal

from httpx import AsyncClient


async def _wh(client: AsyncClient, headers: dict, code: str, *, default: bool = False) -> str:
    r = await client.post(
        "/api/v1/warehouses",
        headers=headers,
        json={"code": code, "name": f"WH {code}", "is_default": default},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _item(client: AsyncClient, headers: dict, sku: str, *, type_: str = "stock") -> str:
    r = await client.post(
        "/api/v1/items",
        headers=headers,
        json={"sku": sku, "name": f"Item {sku}", "type": type_, "min_stock": "5"},
    )
    assert r.status_code == 201, r.text
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


# ─── Master data ───────────────────────────────────────────
async def test_create_warehouse_and_item(client: AsyncClient, seeded_tenant: dict):
    headers = seeded_tenant["headers"]
    wh_id = await _wh(client, headers, "MAIN", default=True)
    item_id = await _item(client, headers, "ITEM-1")

    r = await client.get("/api/v1/items", headers=headers)
    assert r.status_code == 200
    assert any(i["id"] == item_id and i["sku"] == "ITEM-1" for i in r.json())

    r = await client.get("/api/v1/warehouses", headers=headers)
    assert any(w["id"] == wh_id and w["is_default"] for w in r.json())


async def test_duplicate_sku_conflicts(client: AsyncClient, seeded_tenant: dict):
    headers = seeded_tenant["headers"]
    await _item(client, headers, "DUP-1")
    r = await client.post(
        "/api/v1/items",
        headers=headers,
        json={"sku": "DUP-1", "name": "Other"},
    )
    assert r.status_code == 409


async def test_promoting_default_warehouse_demotes_others(client: AsyncClient, seeded_tenant: dict):
    """Two warehouses; only the most-recently-promoted holds is_default=true."""
    headers = seeded_tenant["headers"]
    a = await _wh(client, headers, "A", default=True)
    b = await _wh(client, headers, "B", default=False)

    rb = await client.patch(f"/api/v1/warehouses/{b}", headers=headers, json={"is_default": True})
    assert rb.status_code == 200

    r = await client.get("/api/v1/warehouses", headers=headers)
    by_id = {w["id"]: w for w in r.json()}
    assert by_id[a]["is_default"] is False
    assert by_id[b]["is_default"] is True


# ─── Weighted-average math ─────────────────────────────────
async def test_weighted_average_flow(client: AsyncClient, seeded_tenant: dict):
    """Receive 10@100, receive 10@120 → avg 110.
    Issue 5 → avg unchanged at 110, qty 15.
    Receive 5@80 → avg = (15*110 + 5*80)/20 = 102.5
    Adjust_out 3 → qty 17, avg unchanged.
    """
    headers = seeded_tenant["headers"]
    wh = await _wh(client, headers, "M", default=True)
    item = await _item(client, headers, "AVG-1")

    # 1) IN 10 @ 100
    r1 = await _move(
        client,
        headers,
        item_id=item,
        warehouse_id=wh,
        direction="in",
        qty="10",
        unit_cost="100",
    )
    assert r1.status_code == 201
    assert Decimal(r1.json()["qty_after"]) == Decimal("10.0000")
    assert Decimal(r1.json()["avg_cost_after"]) == Decimal("100.0000")

    # 2) IN 10 @ 120
    r2 = await _move(
        client,
        headers,
        item_id=item,
        warehouse_id=wh,
        direction="in",
        qty="10",
        unit_cost="120",
    )
    assert Decimal(r2.json()["qty_after"]) == Decimal("20.0000")
    assert Decimal(r2.json()["avg_cost_after"]) == Decimal("110.0000")

    # 3) OUT 5 — avg unchanged
    r3 = await _move(
        client,
        headers,
        item_id=item,
        warehouse_id=wh,
        direction="out",
        qty="5",
    )
    body3 = r3.json()
    assert Decimal(body3["qty_after"]) == Decimal("15.0000")
    assert Decimal(body3["avg_cost_after"]) == Decimal("110.0000")
    # Outbound movement uses avg_cost as its own unit_cost
    assert Decimal(body3["unit_cost"]) == Decimal("110.0000")
    assert Decimal(body3["total_cost"]) == Decimal("550.00")  # 5 × 110

    # 4) IN 5 @ 80 → avg = (15*110 + 5*80) / 20 = 102.5
    r4 = await _move(
        client,
        headers,
        item_id=item,
        warehouse_id=wh,
        direction="in",
        qty="5",
        unit_cost="80",
    )
    assert Decimal(r4.json()["qty_after"]) == Decimal("20.0000")
    assert Decimal(r4.json()["avg_cost_after"]) == Decimal("102.5000")

    # 5) ADJUST_OUT 3 — qty 17, avg unchanged
    r5 = await _move(
        client,
        headers,
        item_id=item,
        warehouse_id=wh,
        direction="adjust_out",
        qty="3",
    )
    assert Decimal(r5.json()["qty_after"]) == Decimal("17.0000")
    assert Decimal(r5.json()["avg_cost_after"]) == Decimal("102.5000")


async def test_insufficient_stock_rejected(client: AsyncClient, seeded_tenant: dict):
    headers = seeded_tenant["headers"]
    wh = await _wh(client, headers, "M2")
    item = await _item(client, headers, "INS-1")
    # No inflows — try to issue
    r = await _move(
        client,
        headers,
        item_id=item,
        warehouse_id=wh,
        direction="out",
        qty="1",
    )
    assert r.status_code == 422
    assert "insufficient" in r.json()["error"]["message"].lower()


async def test_cannot_move_service_item(client: AsyncClient, seeded_tenant: dict):
    headers = seeded_tenant["headers"]
    wh = await _wh(client, headers, "WS")
    svc = await _item(client, headers, "SVC-1", type_="service")
    r = await _move(
        client,
        headers,
        item_id=svc,
        warehouse_id=wh,
        direction="in",
        qty="1",
        unit_cost="100",
    )
    assert r.status_code == 422
    assert "non-stock" in r.json()["error"]["message"].lower()


# ─── Reports ──────────────────────────────────────────────
async def test_stock_on_hand_includes_value_and_below_min_flag(client: AsyncClient, seeded_tenant: dict):
    headers = seeded_tenant["headers"]
    wh = await _wh(client, headers, "OH", default=True)
    item = await _item(client, headers, "OH-1")  # min_stock = 5
    # Receive 3 @ 50 → below min_stock
    await _move(
        client,
        headers,
        item_id=item,
        warehouse_id=wh,
        direction="in",
        qty="3",
        unit_cost="50",
    )

    r = await client.get("/api/v1/reports/stock-on-hand", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert len(body["lines"]) == 1
    line = body["lines"][0]
    assert Decimal(line["on_hand_qty"]) == Decimal("3.0000")
    assert Decimal(line["avg_cost"]) == Decimal("50.0000")
    assert Decimal(line["value"]) == Decimal("150.00")
    assert line["below_min_stock"] is True
    assert Decimal(body["total_value"]) == Decimal("150.00")


async def test_stock_valuation_aggregates_across_warehouses(client: AsyncClient, seeded_tenant: dict):
    """Same item in two warehouses with different costs aggregates with
    a weighted average across both."""
    headers = seeded_tenant["headers"]
    wh_a = await _wh(client, headers, "VA")
    wh_b = await _wh(client, headers, "VB")
    item = await _item(client, headers, "VAL-1")

    # WH-A: 10 @ 100 → value 1000
    await _move(
        client,
        headers,
        item_id=item,
        warehouse_id=wh_a,
        direction="in",
        qty="10",
        unit_cost="100",
    )
    # WH-B: 10 @ 200 → value 2000
    await _move(
        client,
        headers,
        item_id=item,
        warehouse_id=wh_b,
        direction="in",
        qty="10",
        unit_cost="200",
    )

    r = await client.get("/api/v1/reports/stock-valuation", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert len(body["lines"]) == 1
    line = body["lines"][0]
    assert Decimal(line["on_hand_qty"]) == Decimal("20.0000")
    # Weighted avg = 3000 / 20 = 150
    assert Decimal(line["weighted_avg_cost"]) == Decimal("150")
    assert Decimal(line["value"]) == Decimal("3000.00")
    assert Decimal(body["total_value"]) == Decimal("3000.00")


async def test_movement_in_closed_period_blocked(client: AsyncClient, seeded_tenant: dict):
    headers = seeded_tenant["headers"]
    wh = await _wh(client, headers, "CL")
    item = await _item(client, headers, "CL-1")

    # Close Jan
    r = await client.post(
        "/api/v1/periods/close",
        headers=headers,
        json={"through_date": "2026-01-31"},
    )
    assert r.status_code == 200

    rmv = await _move(
        client,
        headers,
        item_id=item,
        warehouse_id=wh,
        direction="in",
        qty="5",
        unit_cost="100",
        date_="2026-01-15",
    )
    assert rmv.status_code == 422
    assert rmv.json()["error"]["code"] == "period_closed"

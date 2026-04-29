"""Cost layers ledger endpoint — drill-down per item showing remaining
FIFO/LIFO layers."""

from decimal import Decimal

from httpx import AsyncClient


async def _wh(client: AsyncClient, headers: dict, code: str = "MAIN") -> str:
    r = await client.post(
        "/api/v1/warehouses",
        headers=headers,
        json={"code": code, "name": code},
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
    return r.json()


async def _set_fifo(client: AsyncClient, headers: dict) -> None:
    r = await client.put(
        "/api/v1/costing-method",
        headers=headers,
        json={"method": "fifo", "seed_opening_layers": True},
    )
    assert r.status_code == 200


async def test_cost_layers_empty_for_avg_method(client: AsyncClient, seeded_tenant: dict):
    """Default tenant is on `avg` — no layers are written, so the
    drill-down returns an empty list with zero totals."""
    headers = seeded_tenant["headers"]
    wh = await _wh(client, headers)
    item = await _item(client, headers, "AVG-1")
    await _move(
        client,
        headers,
        item_id=item,
        warehouse_id=wh,
        direction="in",
        qty="10",
        unit_cost="100",
    )

    r = await client.get(f"/api/v1/items/{item}/cost-layers", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["layers"] == []
    assert Decimal(body["total_remaining_qty"]) == Decimal("0")
    assert Decimal(body["total_remaining_value"]) == Decimal("0")


async def test_cost_layers_show_two_open_layers_under_fifo(client: AsyncClient, seeded_tenant: dict):
    headers = seeded_tenant["headers"]
    await _set_fifo(client, headers)
    wh = await _wh(client, headers)
    item = await _item(client, headers, "F-1")

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

    r = await client.get(f"/api/v1/items/{item}/cost-layers", headers=headers)
    body = r.json()
    layers = body["layers"]
    assert len(layers) == 2
    # Ordered by received_at ASC
    assert Decimal(layers[0]["original_qty"]) == Decimal("10.0000")
    assert Decimal(layers[0]["unit_cost"]) == Decimal("100.0000")
    assert Decimal(layers[0]["remaining_qty"]) == Decimal("10.0000")
    assert Decimal(layers[0]["remaining_value"]) == Decimal("1000.00")
    assert layers[0]["is_exhausted"] is False

    assert Decimal(layers[1]["original_qty"]) == Decimal("5.0000")
    assert Decimal(layers[1]["unit_cost"]) == Decimal("200.0000")

    assert Decimal(body["total_remaining_qty"]) == Decimal("15.0000")
    assert Decimal(body["total_remaining_value"]) == Decimal("2000.00")


async def test_partial_consumption_reflects_remaining_qty(client: AsyncClient, seeded_tenant: dict):
    """After consuming 7 from a 10-unit FIFO layer, the layer is still
    open with remaining_qty=3 and remaining_value updated accordingly."""
    headers = seeded_tenant["headers"]
    await _set_fifo(client, headers)
    wh = await _wh(client, headers)
    item = await _item(client, headers, "F-2")

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
        direction="out",
        qty="7",
        date_="2026-04-10",
    )

    r = await client.get(f"/api/v1/items/{item}/cost-layers", headers=headers)
    body = r.json()
    assert len(body["layers"]) == 1
    la = body["layers"][0]
    assert Decimal(la["original_qty"]) == Decimal("10.0000")
    assert Decimal(la["remaining_qty"]) == Decimal("3.0000")
    assert Decimal(la["remaining_value"]) == Decimal("300.00")
    assert la["is_exhausted"] is False
    assert Decimal(body["total_remaining_value"]) == Decimal("300.00")


async def test_exhausted_layers_hidden_by_default_visible_with_flag(client: AsyncClient, seeded_tenant: dict):
    """After consuming a whole layer, it's marked is_exhausted and
    omitted from the default response. include_exhausted=true brings
    it back for forensic review."""
    headers = seeded_tenant["headers"]
    await _set_fifo(client, headers)
    wh = await _wh(client, headers)
    item = await _item(client, headers, "F-3")

    await _move(
        client,
        headers,
        item_id=item,
        warehouse_id=wh,
        direction="in",
        qty="5",
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
    # Consume the entire first layer
    await _move(
        client,
        headers,
        item_id=item,
        warehouse_id=wh,
        direction="out",
        qty="5",
        date_="2026-04-10",
    )

    r1 = await client.get(f"/api/v1/items/{item}/cost-layers", headers=headers)
    body1 = r1.json()
    # Only the second layer remains
    assert len(body1["layers"]) == 1
    assert Decimal(body1["layers"][0]["unit_cost"]) == Decimal("200.0000")

    r2 = await client.get(
        f"/api/v1/items/{item}/cost-layers?include_exhausted=true",
        headers=headers,
    )
    body2 = r2.json()
    # Both layers, exhausted one flagged
    assert len(body2["layers"]) == 2
    exhausted = [la for la in body2["layers"] if la["is_exhausted"]]
    assert len(exhausted) == 1
    assert Decimal(exhausted[0]["unit_cost"]) == Decimal("100.0000")
    assert Decimal(exhausted[0]["remaining_qty"]) == Decimal("0")


async def test_warehouse_filter(client: AsyncClient, seeded_tenant: dict):
    """Two layers in different warehouses; warehouse_id filter narrows."""
    headers = seeded_tenant["headers"]
    await _set_fifo(client, headers)
    a = await _wh(client, headers, "A")
    b = await _wh(client, headers, "B")
    item = await _item(client, headers, "F-4")

    await _move(
        client,
        headers,
        item_id=item,
        warehouse_id=a,
        direction="in",
        qty="5",
        unit_cost="100",
    )
    await _move(
        client,
        headers,
        item_id=item,
        warehouse_id=b,
        direction="in",
        qty="3",
        unit_cost="200",
    )

    r = await client.get(f"/api/v1/items/{item}/cost-layers?warehouse_id={a}", headers=headers)
    body = r.json()
    assert len(body["layers"]) == 1
    assert body["layers"][0]["warehouse_id"] == a


async def test_unknown_item_returns_404(client: AsyncClient, seeded_tenant: dict):
    from uuid import uuid4

    r = await client.get(f"/api/v1/items/{uuid4()}/cost-layers", headers=seeded_tenant["headers"])
    assert r.status_code == 404

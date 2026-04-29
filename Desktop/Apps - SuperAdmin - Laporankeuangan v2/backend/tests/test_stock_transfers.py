"""Stock transfers — atomic out+in across two warehouses preserving cost basis."""

from decimal import Decimal

from httpx import AsyncClient


async def _wh(client: AsyncClient, headers: dict, code: str) -> str:
    r = await client.post(
        "/api/v1/warehouses",
        headers=headers,
        json={"code": code, "name": f"WH {code}"},
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


async def _transfer(
    client: AsyncClient,
    headers: dict,
    *,
    src: str,
    dst: str,
    item_id: str,
    qty: str,
    date_: str = "2026-04-20",
) -> dict:
    r = await client.post(
        "/api/v1/stock-transfers",
        headers=headers,
        json={
            "transfer_date": date_,
            "source_warehouse_id": src,
            "destination_warehouse_id": dst,
            "lines": [{"item_id": item_id, "qty": qty}],
        },
    )
    return r


async def _balance(client: AsyncClient, headers: dict, item_id: str, warehouse_id: str) -> dict | None:
    r = await client.get(
        f"/api/v1/stock-balances?item_id={item_id}&warehouse_id={warehouse_id}",
        headers=headers,
    )
    bals = r.json()
    return bals[0] if bals else None


async def test_transfer_moves_stock_and_preserves_cost(client: AsyncClient, seeded_tenant: dict):
    """Receive 10 @ 100 at A, transfer 4 to B → A has 6, B has 4 both at cost 100."""
    headers = seeded_tenant["headers"]
    a = await _wh(client, headers, "A")
    b = await _wh(client, headers, "B")
    item = await _item(client, headers, "T-1")

    await _move(client, headers, item_id=item, warehouse_id=a, direction="in", qty="10", unit_cost="100")

    r = await _transfer(client, headers, src=a, dst=b, item_id=item, qty="4")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "posted"
    assert body["transfer_no"].startswith("TR-2026-")
    assert len(body["lines"]) == 1
    assert Decimal(body["lines"][0]["unit_cost"]) == Decimal("100.0000")

    bal_a = await _balance(client, headers, item, a)
    assert Decimal(bal_a["on_hand_qty"]) == Decimal("6.0000")
    assert Decimal(bal_a["avg_cost"]) == Decimal("100.0000")

    bal_b = await _balance(client, headers, item, b)
    assert Decimal(bal_b["on_hand_qty"]) == Decimal("4.0000")
    assert Decimal(bal_b["avg_cost"]) == Decimal("100.0000")


async def test_transfer_blends_cost_into_existing_destination(client: AsyncClient, seeded_tenant: dict):
    """B already has 5 @ 200. Transfer 5 from A (cost 100) → B becomes
    10 units at weighted avg (5*200 + 5*100)/10 = 150."""
    headers = seeded_tenant["headers"]
    a = await _wh(client, headers, "A")
    b = await _wh(client, headers, "B")
    item = await _item(client, headers, "T-2")

    await _move(client, headers, item_id=item, warehouse_id=a, direction="in", qty="5", unit_cost="100")
    await _move(client, headers, item_id=item, warehouse_id=b, direction="in", qty="5", unit_cost="200")

    r = await _transfer(client, headers, src=a, dst=b, item_id=item, qty="5")
    assert r.status_code == 201

    bal_a = await _balance(client, headers, item, a)
    assert Decimal(bal_a["on_hand_qty"]) == Decimal("0")
    bal_b = await _balance(client, headers, item, b)
    assert Decimal(bal_b["on_hand_qty"]) == Decimal("10.0000")
    assert Decimal(bal_b["avg_cost"]) == Decimal("150.0000")


async def test_transfer_insufficient_stock_rejected(client: AsyncClient, seeded_tenant: dict):
    headers = seeded_tenant["headers"]
    a = await _wh(client, headers, "A")
    b = await _wh(client, headers, "B")
    item = await _item(client, headers, "T-3")
    # A has only 2; try to transfer 5
    await _move(client, headers, item_id=item, warehouse_id=a, direction="in", qty="2", unit_cost="50")

    r = await _transfer(client, headers, src=a, dst=b, item_id=item, qty="5")
    assert r.status_code == 422
    assert "insufficient" in r.json()["error"]["message"].lower()


async def test_transfer_same_warehouse_rejected(client: AsyncClient, seeded_tenant: dict):
    headers = seeded_tenant["headers"]
    a = await _wh(client, headers, "A")
    item = await _item(client, headers, "T-4")
    await _move(client, headers, item_id=item, warehouse_id=a, direction="in", qty="5", unit_cost="50")

    r = await _transfer(client, headers, src=a, dst=a, item_id=item, qty="2")
    assert r.status_code == 422
    assert "different" in r.json()["error"]["message"].lower()


async def test_void_transfer_reverses_both_legs(client: AsyncClient, seeded_tenant: dict):
    headers = seeded_tenant["headers"]
    a = await _wh(client, headers, "A")
    b = await _wh(client, headers, "B")
    item = await _item(client, headers, "T-5")

    await _move(client, headers, item_id=item, warehouse_id=a, direction="in", qty="10", unit_cost="100")

    rt = await _transfer(client, headers, src=a, dst=b, item_id=item, qty="6")
    assert rt.status_code == 201
    transfer_id = rt.json()["id"]

    rv = await client.post(
        f"/api/v1/stock-transfers/{transfer_id}/void",
        headers=headers,
        json={"reason": "test"},
    )
    assert rv.status_code == 200
    assert rv.json()["status"] == "void"

    # A is back to 10, B is back to 0
    bal_a = await _balance(client, headers, item, a)
    assert Decimal(bal_a["on_hand_qty"]) == Decimal("10.0000")
    bal_b = await _balance(client, headers, item, b)
    assert bal_b is None or Decimal(bal_b["on_hand_qty"]) == Decimal("0")


async def test_transfer_with_fifo_uses_blended_cost(client: AsyncClient, seeded_tenant: dict):
    """Under FIFO with two layers (5@100, 5@200), transferring 7 sends
    5+2 (blended cost = (500+400)/7 ≈ 128.5714) into a single layer at
    the destination."""
    headers = seeded_tenant["headers"]
    # Switch to FIFO first
    rsm = await client.put(
        "/api/v1/costing-method",
        headers=headers,
        json={"method": "fifo", "seed_opening_layers": True},
    )
    assert rsm.status_code == 200

    a = await _wh(client, headers, "A")
    b = await _wh(client, headers, "B")
    item = await _item(client, headers, "FIFO-T")

    await _move(
        client,
        headers,
        item_id=item,
        warehouse_id=a,
        direction="in",
        qty="5",
        unit_cost="100",
        date_="2026-04-01",
    )
    await _move(
        client,
        headers,
        item_id=item,
        warehouse_id=a,
        direction="in",
        qty="5",
        unit_cost="200",
        date_="2026-04-05",
    )

    r = await _transfer(client, headers, src=a, dst=b, item_id=item, qty="7", date_="2026-04-10")
    body = r.json()
    line_cost = Decimal(body["lines"][0]["unit_cost"])
    # 5 from L1 (500) + 2 from L2 (400) = 900; blended = 128.5714
    assert abs(line_cost - Decimal("128.5714")) < Decimal("0.001")

    bal_b = await _balance(client, headers, item, b)
    assert Decimal(bal_b["on_hand_qty"]) == Decimal("7.0000")
    # Single blended layer at destination
    assert abs(Decimal(bal_b["avg_cost"]) - Decimal("128.5714")) < Decimal("0.001")

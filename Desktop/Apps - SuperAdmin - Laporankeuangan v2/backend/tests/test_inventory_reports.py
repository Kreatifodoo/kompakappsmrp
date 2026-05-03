"""Reorder report + Slow-moving items report."""

from decimal import Decimal

from httpx import AsyncClient


# ── shared helpers ─────────────────────────────────────────────────────────

async def _wh(client: AsyncClient, headers: dict, code: str) -> str:
    r = await client.post(
        "/api/v1/warehouses", headers=headers, json={"code": code, "name": code}
    )
    assert r.status_code == 201
    return r.json()["id"]


async def _item(
    client: AsyncClient,
    headers: dict,
    sku: str,
    *,
    min_stock: str = "0",
) -> str:
    r = await client.post(
        "/api/v1/items",
        headers=headers,
        json={"sku": sku, "name": sku, "type": "stock", "min_stock": min_stock},
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
    unit_cost: str = "100",
    date_: str,
) -> None:
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


# ═══════════════════════════════════════════════════════════════════════════
# REORDER REPORT
# ═══════════════════════════════════════════════════════════════════════════

async def test_reorder_empty_when_all_items_above_min(
    client: AsyncClient, seeded_tenant: dict
):
    """Item on hand >= min_stock → not in reorder report."""
    headers = seeded_tenant["headers"]
    wh = await _wh(client, headers, "RO-WH1")
    item = await _item(client, headers, "RO-ABOVE", min_stock="5")
    await _move(client, headers, item_id=item, warehouse_id=wh,
                direction="in", qty="10", date_="2026-01-10")

    r = await client.get("/api/v1/reports/reorder", headers=headers)
    assert r.status_code == 200
    skus = [ln["sku"] for ln in r.json()["lines"]]
    assert "RO-ABOVE" not in skus


async def test_reorder_item_with_zero_stock_appears(
    client: AsyncClient, seeded_tenant: dict
):
    """Item with min_stock=5 and no stock at all → shortfall = 5."""
    headers = seeded_tenant["headers"]
    item = await _item(client, headers, "RO-ZERO", min_stock="5")

    r = await client.get("/api/v1/reports/reorder", headers=headers)
    assert r.status_code == 200
    body = r.json()
    line = next((ln for ln in body["lines"] if ln["sku"] == "RO-ZERO"), None)
    assert line is not None
    assert Decimal(line["on_hand_qty"]) == Decimal("0")
    assert Decimal(line["min_stock"]) == Decimal("5.0000")
    assert Decimal(line["shortage"]) == Decimal("5.0000")


async def test_reorder_partial_shortage(client: AsyncClient, seeded_tenant: dict):
    """3 on hand, min_stock=10 → shortage=7, shortage_value=7×avg_cost."""
    headers = seeded_tenant["headers"]
    wh = await _wh(client, headers, "RO-WH2")
    item = await _item(client, headers, "RO-PARTIAL", min_stock="10")
    await _move(client, headers, item_id=item, warehouse_id=wh,
                direction="in", qty="3", unit_cost="200", date_="2026-01-15")

    r = await client.get("/api/v1/reports/reorder", headers=headers)
    body = r.json()
    line = next(ln for ln in body["lines"] if ln["sku"] == "RO-PARTIAL")
    assert Decimal(line["on_hand_qty"]) == Decimal("3.0000")
    assert Decimal(line["shortage"]) == Decimal("7.0000")
    assert Decimal(line["avg_cost"]) == Decimal("200.0000")
    assert Decimal(line["shortage_value"]) == Decimal("1400.00")  # 7 × 200


async def test_reorder_aggregates_across_warehouses(
    client: AsyncClient, seeded_tenant: dict
):
    """Two warehouses: wh-a has 3, wh-b has 4. Total = 7, min = 10.
    Without warehouse filter → shortage = 3.
    With wh-a filter → shortage = 7 (only 3 in that wh)."""
    headers = seeded_tenant["headers"]
    wha = await _wh(client, headers, "RO-A")
    whb = await _wh(client, headers, "RO-B")
    item = await _item(client, headers, "RO-MULTI", min_stock="10")

    await _move(client, headers, item_id=item, warehouse_id=wha,
                direction="in", qty="3", unit_cost="100", date_="2026-02-01")
    await _move(client, headers, item_id=item, warehouse_id=whb,
                direction="in", qty="4", unit_cost="100", date_="2026-02-01")

    # All warehouses: 7 on hand, shortage=3
    r_all = await client.get("/api/v1/reports/reorder", headers=headers)
    line_all = next(ln for ln in r_all.json()["lines"] if ln["sku"] == "RO-MULTI")
    assert Decimal(line_all["on_hand_qty"]) == Decimal("7.0000")
    assert Decimal(line_all["shortage"]) == Decimal("3.0000")

    # Filter wh-a only: 3 on hand, shortage=7
    r_wh = await client.get(
        "/api/v1/reports/reorder",
        params={"warehouse_id": wha},
        headers=headers,
    )
    line_wh = next(ln for ln in r_wh.json()["lines"] if ln["sku"] == "RO-MULTI")
    assert Decimal(line_wh["on_hand_qty"]) == Decimal("3.0000")
    assert Decimal(line_wh["shortage"]) == Decimal("7.0000")


async def test_reorder_item_with_zero_min_stock_excluded(
    client: AsyncClient, seeded_tenant: dict
):
    """Items with min_stock=0 are never in the reorder report regardless
    of current stock."""
    headers = seeded_tenant["headers"]
    item = await _item(client, headers, "RO-NOMIN", min_stock="0")

    r = await client.get("/api/v1/reports/reorder", headers=headers)
    skus = [ln["sku"] for ln in r.json()["lines"]]
    assert "RO-NOMIN" not in skus


async def test_reorder_total_shortage_value_summed(
    client: AsyncClient, seeded_tenant: dict
):
    """total_shortage_value is the sum of all line shortage_values."""
    headers = seeded_tenant["headers"]
    wh = await _wh(client, headers, "RO-WH3")
    item_a = await _item(client, headers, "RO-SUM-A", min_stock="10")
    item_b = await _item(client, headers, "RO-SUM-B", min_stock="5")

    await _move(client, headers, item_id=item_a, warehouse_id=wh,
                direction="in", qty="2", unit_cost="50", date_="2026-03-01")
    # item_b: zero stock, min_stock=5, avg_cost=0 → shortage_value=0

    r = await client.get("/api/v1/reports/reorder", headers=headers)
    body = r.json()
    lines = {ln["sku"]: ln for ln in body["lines"]}

    expected = sum(
        Decimal(ln["shortage_value"]) for ln in body["lines"]
    )
    assert Decimal(body["total_shortage_value"]) == expected
    # item_a: shortage=8, avg=50 → shortage_value=400
    assert Decimal(lines["RO-SUM-A"]["shortage_value"]) == Decimal("400.00")


# ═══════════════════════════════════════════════════════════════════════════
# SLOW-MOVING ITEMS REPORT
# ═══════════════════════════════════════════════════════════════════════════

async def test_slow_moving_empty_when_no_stock(
    client: AsyncClient, seeded_tenant: dict
):
    """No stock on hand → empty slow-moving report."""
    headers = seeded_tenant["headers"]
    r = await client.get(
        "/api/v1/reports/slow-moving", params={"days": 90}, headers=headers
    )
    assert r.status_code == 200
    assert r.json()["lines"] == []


async def test_slow_moving_never_sold_item_appears(
    client: AsyncClient, seeded_tenant: dict
):
    """Item received but never sold → last_outflow_date is None,
    days_since_last_outflow is None, period_out_qty=0."""
    headers = seeded_tenant["headers"]
    wh = await _wh(client, headers, "SM-WH1")
    item = await _item(client, headers, "SM-NEVER")
    await _move(client, headers, item_id=item, warehouse_id=wh,
                direction="in", qty="10", unit_cost="100", date_="2026-01-01")

    r = await client.get(
        "/api/v1/reports/slow-moving", params={"days": 90}, headers=headers
    )
    body = r.json()
    line = next((ln for ln in body["lines"] if ln["sku"] == "SM-NEVER"), None)
    assert line is not None
    assert line["last_outflow_date"] is None
    assert line["days_since_last_outflow"] is None
    assert Decimal(line["period_out_qty"]) == Decimal("0")
    assert Decimal(line["on_hand_qty"]) == Decimal("10.0000")


async def test_slow_moving_recent_sale_not_flagged(
    client: AsyncClient, seeded_tenant: dict
):
    """Item sold 5 days ago with 90-day window → NOT slow-moving."""
    import datetime

    headers = seeded_tenant["headers"]
    wh = await _wh(client, headers, "SM-WH2")
    item = await _item(client, headers, "SM-RECENT")
    today = datetime.date.today()

    await _move(client, headers, item_id=item, warehouse_id=wh,
                direction="in", qty="20", unit_cost="50",
                date_=str(today - datetime.timedelta(days=30)))
    await _move(client, headers, item_id=item, warehouse_id=wh,
                direction="out", qty="5",
                date_=str(today - datetime.timedelta(days=5)))

    r = await client.get(
        "/api/v1/reports/slow-moving", params={"days": 90}, headers=headers
    )
    skus = [ln["sku"] for ln in r.json()["lines"]]
    assert "SM-RECENT" not in skus


async def test_slow_moving_old_sale_is_flagged(
    client: AsyncClient, seeded_tenant: dict
):
    """Item last sold 120 days ago with 90-day window → IS slow-moving."""
    import datetime

    headers = seeded_tenant["headers"]
    wh = await _wh(client, headers, "SM-WH3")
    item = await _item(client, headers, "SM-OLD")
    today = datetime.date.today()
    old_date = today - datetime.timedelta(days=120)

    await _move(client, headers, item_id=item, warehouse_id=wh,
                direction="in", qty="15", unit_cost="80", date_=str(old_date))
    await _move(client, headers, item_id=item, warehouse_id=wh,
                direction="out", qty="3", date_=str(old_date))

    r = await client.get(
        "/api/v1/reports/slow-moving", params={"days": 90}, headers=headers
    )
    body = r.json()
    line = next((ln for ln in body["lines"] if ln["sku"] == "SM-OLD"), None)
    assert line is not None
    assert line["days_since_last_outflow"] >= 120
    assert Decimal(line["period_out_qty"]) == Decimal("0")  # nothing in last 90d
    assert Decimal(line["on_hand_qty"]) == Decimal("12.0000")  # 15-3


async def test_slow_moving_warehouse_filter(
    client: AsyncClient, seeded_tenant: dict
):
    """Filtering by warehouse_id excludes items in other warehouses."""
    import datetime

    headers = seeded_tenant["headers"]
    wha = await _wh(client, headers, "SM-A")
    whb = await _wh(client, headers, "SM-B")
    item = await _item(client, headers, "SM-WF")
    today = datetime.date.today()
    old = str(today - datetime.timedelta(days=200))

    # Stock in both warehouses, never sold
    await _move(client, headers, item_id=item, warehouse_id=wha,
                direction="in", qty="5", unit_cost="10", date_=old)
    await _move(client, headers, item_id=item, warehouse_id=whb,
                direction="in", qty="5", unit_cost="10", date_=old)

    r_all = await client.get(
        "/api/v1/reports/slow-moving", params={"days": 90}, headers=headers
    )
    wh_ids_all = [ln["warehouse_id"] for ln in r_all.json()["lines"]
                  if ln["sku"] == "SM-WF"]
    assert wha in wh_ids_all
    assert whb in wh_ids_all

    r_a = await client.get(
        "/api/v1/reports/slow-moving",
        params={"days": 90, "warehouse_id": wha},
        headers=headers,
    )
    wh_ids_a = [ln["warehouse_id"] for ln in r_a.json()["lines"]
                if ln["sku"] == "SM-WF"]
    assert wh_ids_a == [wha]


async def test_slow_moving_sorted_never_moved_first(
    client: AsyncClient, seeded_tenant: dict
):
    """Never-sold items appear before old-but-ever-sold items."""
    import datetime

    headers = seeded_tenant["headers"]
    wh = await _wh(client, headers, "SM-SORT")
    today = datetime.date.today()
    old = str(today - datetime.timedelta(days=150))

    item_never = await _item(client, headers, "SM-SORT-NEVER")
    item_old   = await _item(client, headers, "SM-SORT-OLD")

    await _move(client, headers, item_id=item_never, warehouse_id=wh,
                direction="in", qty="5", unit_cost="10", date_=old)
    await _move(client, headers, item_id=item_old, warehouse_id=wh,
                direction="in", qty="5", unit_cost="10", date_=old)
    await _move(client, headers, item_id=item_old, warehouse_id=wh,
                direction="out", qty="1", date_=old)

    r = await client.get(
        "/api/v1/reports/slow-moving", params={"days": 90}, headers=headers
    )
    skus = [ln["sku"] for ln in r.json()["lines"]
            if ln["sku"] in ("SM-SORT-NEVER", "SM-SORT-OLD")]
    assert skus.index("SM-SORT-NEVER") < skus.index("SM-SORT-OLD")


async def test_slow_moving_total_value_summed(
    client: AsyncClient, seeded_tenant: dict
):
    """total_on_hand_value equals sum of individual line on_hand_values."""
    import datetime

    headers = seeded_tenant["headers"]
    wh = await _wh(client, headers, "SM-VAL")
    item = await _item(client, headers, "SM-TOTVAL")
    old = str(datetime.date.today() - datetime.timedelta(days=200))

    await _move(client, headers, item_id=item, warehouse_id=wh,
                direction="in", qty="7", unit_cost="150", date_=old)

    r = await client.get(
        "/api/v1/reports/slow-moving", params={"days": 90}, headers=headers
    )
    body = r.json()
    expected = sum(Decimal(ln["on_hand_value"]) for ln in body["lines"])
    assert Decimal(body["total_on_hand_value"]) == expected


async def test_slow_moving_custom_days_threshold(
    client: AsyncClient, seeded_tenant: dict
):
    """days=30: item last sold 45 days ago IS slow; days=60: it is NOT."""
    import datetime

    headers = seeded_tenant["headers"]
    wh = await _wh(client, headers, "SM-THRESH")
    item = await _item(client, headers, "SM-THRESHOLD")
    today = datetime.date.today()

    await _move(client, headers, item_id=item, warehouse_id=wh,
                direction="in", qty="10", unit_cost="100",
                date_=str(today - datetime.timedelta(days=90)))
    await _move(client, headers, item_id=item, warehouse_id=wh,
                direction="out", qty="2",
                date_=str(today - datetime.timedelta(days=45)))

    # 30-day window → last outflow 45 days ago > 30 → slow
    r30 = await client.get(
        "/api/v1/reports/slow-moving", params={"days": 30}, headers=headers
    )
    assert any(ln["sku"] == "SM-THRESHOLD" for ln in r30.json()["lines"])

    # 60-day window → last outflow 45 days ago ≤ 60 → NOT slow
    r60 = await client.get(
        "/api/v1/reports/slow-moving", params={"days": 60}, headers=headers
    )
    assert not any(ln["sku"] == "SM-THRESHOLD" for ln in r60.json()["lines"])

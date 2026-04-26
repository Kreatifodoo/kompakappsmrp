"""PPN (Indonesian VAT) report — monthly output vs input VAT."""

from decimal import Decimal

from httpx import AsyncClient


async def _customer(client: AsyncClient, headers: dict, code: str, tax_id: str | None = None) -> str:
    body = {"code": code, "name": f"Cust {code}"}
    if tax_id is not None:
        body["tax_id"] = tax_id
    r = await client.post("/api/v1/customers", headers=headers, json=body)
    assert r.status_code == 201
    return r.json()["id"]


async def _supplier(client: AsyncClient, headers: dict, code: str, tax_id: str | None = None) -> str:
    body = {"code": code, "name": f"Vend {code}"}
    if tax_id is not None:
        body["tax_id"] = tax_id
    r = await client.post("/api/v1/suppliers", headers=headers, json=body)
    assert r.status_code == 201
    return r.json()["id"]


async def _post_si(
    client: AsyncClient, headers: dict, customer_id: str, amount: str, tax_rate: str, d: str
) -> str:
    r = await client.post(
        "/api/v1/sales-invoices?post_now=true",
        headers=headers,
        json={
            "invoice_date": d,
            "customer_id": customer_id,
            "lines": [{"description": "x", "qty": "1", "unit_price": amount, "tax_rate": tax_rate}],
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _post_pi(
    client: AsyncClient,
    headers: dict,
    supplier_id: str,
    amount: str,
    tax_rate: str,
    d: str,
    supplier_invoice_no: str | None = None,
) -> str:
    body = {
        "invoice_date": d,
        "supplier_id": supplier_id,
        "lines": [{"description": "x", "qty": "1", "unit_price": amount, "tax_rate": tax_rate}],
    }
    if supplier_invoice_no:
        body["supplier_invoice_no"] = supplier_invoice_no
    r = await client.post("/api/v1/purchase-invoices?post_now=true", headers=headers, json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def test_ppn_aggregates_month_correctly(client: AsyncClient, seeded_tenant: dict):
    """One taxed sale (1000 + 110), one taxed purchase (500 + 55).
    Output VAT 110 - Input VAT 55 = 55 net payable."""
    headers = seeded_tenant["headers"]
    cust = await _customer(client, headers, "C-PPN", tax_id="01.234.567.8-901.000")
    sup = await _supplier(client, headers, "S-PPN", tax_id="02.345.678.9-012.000")
    await _post_si(client, headers, cust, "1000", "11", "2026-04-15")
    await _post_pi(client, headers, sup, "500", "11", "2026-04-20", "VND-A-1")

    r = await client.get("/api/v1/reports/ppn?year=2026&month=4", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["period"] == "2026-04"

    # One sales row with tax_id propagated
    assert len(body["sales"]) == 1
    s = body["sales"][0]
    assert s["customer_code"] == "C-PPN"
    assert s["customer_tax_id"] == "01.234.567.8-901.000"
    assert Decimal(s["base"]) == Decimal("1000.00")
    assert Decimal(s["tax"]) == Decimal("110.00")

    # One purchase row with supplier_invoice_no
    assert len(body["purchases"]) == 1
    p = body["purchases"][0]
    assert p["supplier_invoice_no"] == "VND-A-1"
    assert p["supplier_tax_id"] == "02.345.678.9-012.000"
    assert Decimal(p["base"]) == Decimal("500.00")
    assert Decimal(p["tax"]) == Decimal("55.00")

    # Totals
    t = body["totals"]
    assert Decimal(t["sales_base_total"]) == Decimal("1000.00")
    assert Decimal(t["output_vat_total"]) == Decimal("110.00")
    assert Decimal(t["purchase_base_total"]) == Decimal("500.00")
    assert Decimal(t["input_vat_total"]) == Decimal("55.00")
    assert Decimal(t["net_vat_payable"]) == Decimal("55.00")


async def test_ppn_excludes_other_months_and_voided(client: AsyncClient, seeded_tenant: dict):
    headers = seeded_tenant["headers"]
    cust = await _customer(client, headers, "C-X")

    # One in March, one in April; void the April one
    await _post_si(client, headers, cust, "300", "11", "2026-03-10")
    apr_id = await _post_si(client, headers, cust, "999", "11", "2026-04-05")
    rv = await client.post(f"/api/v1/sales-invoices/{apr_id}/void", headers=headers, json={"reason": "x"})
    assert rv.status_code == 200

    # April: voided invoice excluded → 0 rows
    r_apr = await client.get("/api/v1/reports/ppn?year=2026&month=4", headers=headers)
    assert Decimal(r_apr.json()["totals"]["output_vat_total"]) == Decimal("0")

    # March: only the 300 invoice
    r_mar = await client.get("/api/v1/reports/ppn?year=2026&month=3", headers=headers)
    body = r_mar.json()
    assert len(body["sales"]) == 1
    assert Decimal(body["totals"]["sales_base_total"]) == Decimal("300.00")
    assert Decimal(body["totals"]["output_vat_total"]) == Decimal("33.00")


async def test_ppn_net_refund_when_input_exceeds_output(client: AsyncClient, seeded_tenant: dict):
    """Bigger purchases than sales → net_vat_payable is negative
    (refundable / lebih bayar)."""
    headers = seeded_tenant["headers"]
    cust = await _customer(client, headers, "C-LB")
    sup = await _supplier(client, headers, "S-LB")
    await _post_si(client, headers, cust, "100", "11", "2026-05-10")
    await _post_pi(client, headers, sup, "1000", "11", "2026-05-15")

    r = await client.get("/api/v1/reports/ppn?year=2026&month=5", headers=headers)
    body = r.json()
    # Output 11 - Input 110 = -99
    assert Decimal(body["totals"]["net_vat_payable"]) == Decimal("-99.00")


async def test_ppn_invalid_month_rejected(client: AsyncClient, seeded_tenant: dict):
    r = await client.get("/api/v1/reports/ppn?year=2026&month=13", headers=seeded_tenant["headers"])
    assert r.status_code == 422  # FastAPI Query validation

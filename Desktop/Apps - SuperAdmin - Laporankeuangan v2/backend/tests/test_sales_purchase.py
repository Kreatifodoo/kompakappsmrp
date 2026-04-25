"""End-to-end: posting a sales/purchase invoice creates a balanced journal
in the same DB transaction; voiding the invoice voids the journal."""
from decimal import Decimal

from httpx import AsyncClient


# ─── Sales ─────────────────────────────────────────────────
async def test_sales_invoice_post_creates_balanced_journal(
    client: AsyncClient, seeded_tenant: dict
):
    headers = seeded_tenant["headers"]

    # Create a customer
    r = await client.post(
        "/api/v1/customers",
        headers=headers,
        json={"code": "C001", "name": "Test Customer"},
    )
    assert r.status_code == 201
    customer_id = r.json()["id"]

    # Create + post a sales invoice in one shot
    r = await client.post(
        "/api/v1/sales-invoices?post_now=true",
        headers=headers,
        json={
            "invoice_date": "2026-02-01",
            "customer_id": customer_id,
            "lines": [
                {
                    "description": "Consulting fee",
                    "qty": "1",
                    "unit_price": "1000.00",
                    "tax_rate": "11",
                },
            ],
        },
    )
    assert r.status_code == 201, r.text
    invoice = r.json()
    assert invoice["status"] == "posted"
    assert Decimal(invoice["subtotal"]) == Decimal("1000.00")
    assert Decimal(invoice["tax_amount"]) == Decimal("110.00")
    assert Decimal(invoice["total"]) == Decimal("1110.00")
    assert invoice["journal_entry_id"] is not None

    # Fetch the linked journal
    rj = await client.get(
        f"/api/v1/journals/{invoice['journal_entry_id']}", headers=headers
    )
    assert rj.status_code == 200
    journal = rj.json()
    assert journal["status"] == "posted"
    assert journal["source"] == "sales_invoice"

    # Verify Dr/Cr distribution: AR 1110, Sales 1000, Tax 110
    debits = sum(Decimal(l["debit"]) for l in journal["lines"])
    credits = sum(Decimal(l["credit"]) for l in journal["lines"])
    assert debits == credits == Decimal("1110.00")
    assert any(Decimal(l["debit"]) == Decimal("1110.00") for l in journal["lines"])
    assert any(Decimal(l["credit"]) == Decimal("1000.00") for l in journal["lines"])
    assert any(Decimal(l["credit"]) == Decimal("110.00") for l in journal["lines"])


async def test_void_sales_invoice_voids_journal(
    client: AsyncClient, seeded_tenant: dict
):
    headers = seeded_tenant["headers"]
    rc = await client.post(
        "/api/v1/customers", headers=headers,
        json={"code": "C002", "name": "ToVoid"},
    )
    customer_id = rc.json()["id"]

    ri = await client.post(
        "/api/v1/sales-invoices?post_now=true",
        headers=headers,
        json={
            "invoice_date": "2026-02-02",
            "customer_id": customer_id,
            "lines": [{"description": "x", "qty": "1", "unit_price": "500"}],
        },
    )
    invoice = ri.json()

    rv = await client.post(
        f"/api/v1/sales-invoices/{invoice['id']}/void",
        headers=headers,
        json={"reason": "test"},
    )
    assert rv.status_code == 200
    assert rv.json()["status"] == "void"

    # Linked journal should also be void
    rj = await client.get(
        f"/api/v1/journals/{invoice['journal_entry_id']}", headers=headers
    )
    assert rj.json()["status"] == "void"


# ─── Purchase ──────────────────────────────────────────────
async def test_purchase_invoice_post_creates_balanced_journal(
    client: AsyncClient, seeded_tenant: dict
):
    headers = seeded_tenant["headers"]

    rs = await client.post(
        "/api/v1/suppliers", headers=headers,
        json={"code": "S001", "name": "Vendor A"},
    )
    assert rs.status_code == 201
    supplier_id = rs.json()["id"]

    r = await client.post(
        "/api/v1/purchase-invoices?post_now=true",
        headers=headers,
        json={
            "invoice_date": "2026-02-03",
            "supplier_id": supplier_id,
            "supplier_invoice_no": "VEN-A-0042",
            "lines": [
                {"description": "Raw material", "qty": "10",
                 "unit_price": "50.00", "tax_rate": "11"},
            ],
        },
    )
    assert r.status_code == 201, r.text
    invoice = r.json()
    assert invoice["status"] == "posted"
    assert Decimal(invoice["subtotal"]) == Decimal("500.00")
    assert Decimal(invoice["tax_amount"]) == Decimal("55.00")
    assert Decimal(invoice["total"]) == Decimal("555.00")

    # Verify journal: Dr Expense 500, Dr Tax Receivable 55, Cr AP 555
    rj = await client.get(
        f"/api/v1/journals/{invoice['journal_entry_id']}", headers=headers
    )
    journal = rj.json()
    assert journal["source"] == "purchase_invoice"
    debits = sum(Decimal(l["debit"]) for l in journal["lines"])
    credits = sum(Decimal(l["credit"]) for l in journal["lines"])
    assert debits == credits == Decimal("555.00")
    # AP credit = gross
    assert any(Decimal(l["credit"]) == Decimal("555.00") for l in journal["lines"])


async def test_post_invoice_without_mappings_fails(
    client: AsyncClient, tenant_token: dict
):
    """Without seeded COA / mappings, posting must error cleanly."""
    headers = tenant_token["headers"]

    # Create a customer (sales.write only — no posting yet)
    rc = await client.post(
        "/api/v1/customers", headers=headers,
        json={"code": "C100", "name": "Early Bird"},
    )
    assert rc.status_code == 201

    # Attempt to post — should fail with validation error about missing mappings
    r = await client.post(
        "/api/v1/sales-invoices?post_now=true",
        headers=headers,
        json={
            "invoice_date": "2026-02-04",
            "customer_id": rc.json()["id"],
            "lines": [{"description": "x", "qty": "1", "unit_price": "100"}],
        },
    )
    assert r.status_code == 422
    assert "mapping" in r.json()["error"]["message"].lower()

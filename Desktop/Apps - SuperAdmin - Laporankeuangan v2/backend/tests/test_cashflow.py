"""Cash Flow Statement — indirect method.

The seeded tenant gets the full starter COA with cf_section pre-tagged:
  operating  → 1200 Piutang, 1300 Persediaan, 1400 PPN Masukan,
                2100 Hutang, 2200 PPN Keluaran
  investing  → 1510 Peralatan, 1520 Akumulasi Penyusutan
  financing  → 2300 Hutang Jangka Panjang, 3100 Modal Pemilik, 3300 Prive

Tests post manual journal entries and verify the cash flow report maths.
"""

from decimal import Decimal

from httpx import AsyncClient


# ── helpers ────────────────────────────────────────────────────────────────

async def _accounts(client: AsyncClient, headers: dict) -> dict[str, dict]:
    """Return {code: account_dict} for the tenant's COA."""
    r = await client.get("/api/v1/accounts", headers=headers)
    assert r.status_code == 200
    return {a["code"]: a for a in r.json()}


async def _journal(
    client: AsyncClient,
    headers: dict,
    *,
    date_: str,
    memo: str,
    lines: list[dict],
) -> dict:
    r = await client.post(
        "/api/v1/journal-entries",
        headers=headers,
        json={"entry_date": date_, "memo": memo, "lines": lines},
    )
    assert r.status_code == 201, r.text
    entry = r.json()
    # Post immediately
    r2 = await client.post(
        f"/api/v1/journal-entries/{entry['id']}/post", headers=headers
    )
    assert r2.status_code == 200, r2.text
    return r2.json()


async def _cashflow(
    client: AsyncClient,
    headers: dict,
    date_from: str,
    date_to: str,
) -> dict:
    r = await client.get(
        "/api/v1/reports/cash-flow",
        params={"date_from": date_from, "date_to": date_to},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    return r.json()


# ── tests ──────────────────────────────────────────────────────────────────

async def test_empty_period_returns_zero_cashflow(
    client: AsyncClient, seeded_tenant: dict
):
    """No journals → everything zero, reconciled=True."""
    headers = seeded_tenant["headers"]
    body = await _cashflow(client, headers, "2026-01-01", "2026-01-31")

    assert Decimal(body["net_income"]) == Decimal("0")
    assert Decimal(body["net_change"]) == Decimal("0")
    assert Decimal(body["opening_cash"]) == Decimal("0")
    assert Decimal(body["closing_cash"]) == Decimal("0")
    assert Decimal(body["book_closing_cash"]) == Decimal("0")
    assert body["reconciled"] is True


async def test_cash_sale_reconciles(client: AsyncClient, seeded_tenant: dict):
    """
    Post a cash sale: Dr Kas 1000 / Cr Penjualan 1000.
    Net income = 1000. No working-capital changes (AR not touched).
    Net operating = 1000. Opening cash = 0, closing cash = 1000.
    book_closing_cash = 1000 → reconciled.
    """
    headers = seeded_tenant["headers"]
    coa = await _accounts(client, headers)
    kas = coa["1110"]["id"]      # Kas (is_cash=True)
    penjualan = coa["4100"]["id"]  # Penjualan (income)

    await _journal(
        client, headers,
        date_="2026-02-10",
        memo="Cash sale",
        lines=[
            {"account_id": kas, "debit": "1000", "credit": "0"},
            {"account_id": penjualan, "debit": "0", "credit": "1000"},
        ],
    )

    body = await _cashflow(client, headers, "2026-02-01", "2026-02-28")

    assert Decimal(body["net_income"]) == Decimal("1000.00")
    # No cf_section lines contributed; operating section adjustments = 0
    assert Decimal(body["operating"]["subtotal"]) == Decimal("0.00")
    assert Decimal(body["net_operating"]) == Decimal("1000.00")
    assert Decimal(body["net_change"]) == Decimal("1000.00")
    assert Decimal(body["closing_cash"]) == Decimal("1000.00")
    assert Decimal(body["book_closing_cash"]) == Decimal("1000.00")
    assert body["reconciled"] is True


async def test_credit_sale_increases_ar_reduces_operating_cash(
    client: AsyncClient, seeded_tenant: dict
):
    """
    Post a credit sale: Dr Piutang 500 / Cr Penjualan 500.
    Net income = 500.
    AR (cf_section=operating, asset/debit-normal) increases by 500
      → cash effect = -500 (uses cash because we haven't collected yet).
    Net operating = 500 + (-500) = 0.
    Cash doesn't actually move → book_closing_cash = 0 → reconciled.
    """
    headers = seeded_tenant["headers"]
    coa = await _accounts(client, headers)
    piutang = coa["1200"]["id"]    # Piutang Usaha (operating)
    penjualan = coa["4100"]["id"]

    await _journal(
        client, headers,
        date_="2026-03-05",
        memo="Credit sale",
        lines=[
            {"account_id": piutang, "debit": "500", "credit": "0"},
            {"account_id": penjualan, "debit": "0", "credit": "500"},
        ],
    )

    body = await _cashflow(client, headers, "2026-03-01", "2026-03-31")

    assert Decimal(body["net_income"]) == Decimal("500.00")

    # Find the AR line
    ar_lines = [
        ln for ln in body["operating"]["lines"]
        if ln["code"] == "1200"
    ]
    assert len(ar_lines) == 1
    assert Decimal(ar_lines[0]["amount"]) == Decimal("-500.00")

    assert Decimal(body["operating"]["subtotal"]) == Decimal("-500.00")
    assert Decimal(body["net_operating"]) == Decimal("0.00")
    assert Decimal(body["net_change"]) == Decimal("0.00")
    assert Decimal(body["book_closing_cash"]) == Decimal("0.00")
    assert body["reconciled"] is True


async def test_collect_ar_no_income_effect(client: AsyncClient, seeded_tenant: dict):
    """
    First credit sale (period A), then collection in period B.
    In period B: Dr Kas / Cr Piutang.
    Net income B = 0, AR decreases → operating adjustment = +500.
    Net operating = +500. Cash increases by 500 → reconciled.
    """
    headers = seeded_tenant["headers"]
    coa = await _accounts(client, headers)
    kas = coa["1110"]["id"]
    piutang = coa["1200"]["id"]
    penjualan = coa["4100"]["id"]

    # Period A: credit sale
    await _journal(
        client, headers,
        date_="2026-04-05",
        memo="Credit sale Apr",
        lines=[
            {"account_id": piutang, "debit": "500", "credit": "0"},
            {"account_id": penjualan, "debit": "0", "credit": "500"},
        ],
    )
    # Period B: collect cash
    await _journal(
        client, headers,
        date_="2026-05-10",
        memo="Collection May",
        lines=[
            {"account_id": kas, "debit": "500", "credit": "0"},
            {"account_id": piutang, "debit": "0", "credit": "500"},
        ],
    )

    body = await _cashflow(client, headers, "2026-05-01", "2026-05-31")

    assert Decimal(body["net_income"]) == Decimal("0.00")

    ar_line = next(ln for ln in body["operating"]["lines"] if ln["code"] == "1200")
    # Opening AR = 500 (from April), closing AR = 0 → delta = -500
    # asset debit-normal → amount = -(-500) = +500
    assert Decimal(ar_line["opening_balance"]) == Decimal("500.00")
    assert Decimal(ar_line["closing_balance"]) == Decimal("0.00")
    assert Decimal(ar_line["amount"]) == Decimal("500.00")

    assert Decimal(body["net_operating"]) == Decimal("500.00")
    assert Decimal(body["net_change"]) == Decimal("500.00")
    assert Decimal(body["book_closing_cash"]) == Decimal("500.00")
    assert body["reconciled"] is True


async def test_investing_fixed_asset_purchase(client: AsyncClient, seeded_tenant: dict):
    """
    Buy equipment for cash: Dr Peralatan 2000 / Cr Kas 2000.
    Net income = 0. No operating changes.
    Peralatan (investing, debit-normal) increases by 2000 → cash = -2000.
    Net change = -2000. Cash drops by 2000 → reconciled.
    """
    headers = seeded_tenant["headers"]
    coa = await _accounts(client, headers)
    kas = coa["1110"]["id"]
    peralatan = coa["1510"]["id"]   # investing

    await _journal(
        client, headers,
        date_="2026-06-01",
        memo="Buy equipment",
        lines=[
            {"account_id": peralatan, "debit": "2000", "credit": "0"},
            {"account_id": kas, "debit": "0", "credit": "2000"},
        ],
    )

    body = await _cashflow(client, headers, "2026-06-01", "2026-06-30")

    assert Decimal(body["net_income"]) == Decimal("0.00")
    assert Decimal(body["operating"]["subtotal"]) == Decimal("0.00")

    inv_lines = body["investing"]["lines"]
    equip = next(ln for ln in inv_lines if ln["code"] == "1510")
    assert Decimal(equip["amount"]) == Decimal("-2000.00")

    assert Decimal(body["investing"]["subtotal"]) == Decimal("-2000.00")
    assert Decimal(body["net_change"]) == Decimal("-2000.00")
    assert Decimal(body["book_closing_cash"]) == Decimal("-2000.00")
    assert body["reconciled"] is True


async def test_financing_equity_injection(client: AsyncClient, seeded_tenant: dict):
    """
    Owner invests cash: Dr Kas 5000 / Cr Modal 5000.
    Net income = 0. No operating or investing.
    Modal (financing, credit-normal) increases 5000 → cash = +5000.
    Net change = +5000. Reconciled.
    """
    headers = seeded_tenant["headers"]
    coa = await _accounts(client, headers)
    kas = coa["1110"]["id"]
    modal = coa["3100"]["id"]   # financing

    await _journal(
        client, headers,
        date_="2026-07-01",
        memo="Capital injection",
        lines=[
            {"account_id": kas, "debit": "5000", "credit": "0"},
            {"account_id": modal, "debit": "0", "credit": "5000"},
        ],
    )

    body = await _cashflow(client, headers, "2026-07-01", "2026-07-31")

    fin_lines = body["financing"]["lines"]
    modal_line = next(ln for ln in fin_lines if ln["code"] == "3100")
    assert Decimal(modal_line["amount"]) == Decimal("5000.00")

    assert Decimal(body["financing"]["subtotal"]) == Decimal("5000.00")
    assert Decimal(body["net_change"]) == Decimal("5000.00")
    assert Decimal(body["book_closing_cash"]) == Decimal("5000.00")
    assert body["reconciled"] is True


async def test_date_from_after_date_to_returns_422(
    client: AsyncClient, seeded_tenant: dict
):
    headers = seeded_tenant["headers"]
    r = await client.get(
        "/api/v1/reports/cash-flow",
        params={"date_from": "2026-12-31", "date_to": "2026-01-01"},
        headers=headers,
    )
    assert r.status_code == 422


async def test_opening_cash_seeded_from_prior_period(
    client: AsyncClient, seeded_tenant: dict
):
    """Cash earned in period A appears as opening_cash in period B."""
    headers = seeded_tenant["headers"]
    coa = await _accounts(client, headers)
    kas = coa["1110"]["id"]
    penjualan = coa["4100"]["id"]

    await _journal(
        client, headers,
        date_="2026-08-15",
        memo="Aug sale",
        lines=[
            {"account_id": kas, "debit": "300", "credit": "0"},
            {"account_id": penjualan, "debit": "0", "credit": "300"},
        ],
    )

    body = await _cashflow(client, headers, "2026-09-01", "2026-09-30")

    assert Decimal(body["opening_cash"]) == Decimal("300.00")
    assert Decimal(body["net_income"]) == Decimal("0.00")
    assert Decimal(body["net_change"]) == Decimal("0.00")
    assert Decimal(body["closing_cash"]) == Decimal("300.00")
    assert body["reconciled"] is True

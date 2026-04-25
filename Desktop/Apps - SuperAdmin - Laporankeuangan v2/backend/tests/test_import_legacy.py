"""Legacy JSON importer end-to-end test."""

import argparse
import json
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select

from app.modules.accounting.models import Account, JournalEntry
from app.modules.identity.models import Tenant
from app.modules.sales.models import Customer, SalesInvoice
from app.scripts.import_legacy import _run


def _make_args(data_dir: Path, **overrides) -> argparse.Namespace:
    base = dict(
        data_dir=str(data_dir),
        tenant_slug="legacy",
        tenant_name="Legacy Co",
        owner_email="legacy@test.com",
        owner_password="LegacyP@ss1",
        owner_full_name="Legacy Owner",
        seed_coa=False,
        overwrite_mappings=False,
        dry_run=False,
    )
    base.update(overrides)
    return argparse.Namespace(**base)


@pytest.fixture
def legacy_data_dir(tmp_path: Path) -> Path:
    """Synthesize a small legacy data folder."""
    (tmp_path / "accounts.json").write_text(
        json.dumps(
            [
                {"code": "1100", "name": "Kas", "type": "asset", "normal_side": "debit"},
                {"code": "3100", "name": "Modal", "type": "equity", "normal_side": "credit"},
                {"code": "4100", "name": "Penjualan", "type": "income"},
                {"code": "5100", "name": "HPP", "type": "expense"},
            ]
        )
    )
    (tmp_path / "customers.json").write_text(json.dumps([{"code": "C001", "name": "Toko A"}]))
    (tmp_path / "suppliers.json").write_text(json.dumps([{"code": "S001", "name": "Vendor B"}]))
    (tmp_path / "journals.json").write_text(
        json.dumps(
            [
                {
                    "no": "JV-2026-00001",
                    "date": "2026-02-01",
                    "description": "Setoran modal",
                    "lines": [
                        {"account_code": "1100", "debit": 5000000},
                        {"account_code": "3100", "credit": 5000000},
                    ],
                }
            ]
        )
    )
    (tmp_path / "sales_invoices.json").write_text(
        json.dumps(
            [
                {
                    "no": "INV-2026-00001",
                    "date": "2026-02-10",
                    "customer_code": "C001",
                    "lines": [{"description": "Jasa", "qty": 1, "unit_price": 1000, "tax_rate": 11}],
                }
            ]
        )
    )
    return tmp_path


async def test_importer_creates_tenant_and_data(legacy_data_dir: Path, session_factory):
    rc = await _run(_make_args(legacy_data_dir))
    assert rc == 0

    async with session_factory() as s:
        # Tenant created
        tenant = (await s.execute(select(Tenant).where(Tenant.slug == "legacy"))).scalar_one()
        assert tenant.name == "Legacy Co"

        # 4 accounts imported
        accts = (await s.execute(select(Account).where(Account.tenant_id == tenant.id))).scalars().all()
        assert {a.code for a in accts} == {"1100", "3100", "4100", "5100"}
        # default normal_side derivation worked: 4100 income → credit, 5100 expense → debit
        by_code = {a.code: a for a in accts}
        assert by_code["4100"].normal_side == "credit"
        assert by_code["5100"].normal_side == "debit"

        # Customer + journal + sales invoice present
        cust = (await s.execute(select(Customer).where(Customer.tenant_id == tenant.id))).scalar_one()
        assert cust.code == "C001"

        je = (await s.execute(select(JournalEntry).where(JournalEntry.tenant_id == tenant.id))).scalar_one()
        assert je.entry_no == "JV-2026-00001"
        assert je.source == "legacy_import"

        sinv = (await s.execute(select(SalesInvoice).where(SalesInvoice.tenant_id == tenant.id))).scalar_one()
        assert sinv.invoice_no == "INV-2026-00001"
        assert sinv.subtotal == Decimal("1000.00")
        assert sinv.tax_amount == Decimal("110.00")
        assert sinv.total == Decimal("1110.00")


async def test_importer_is_idempotent(legacy_data_dir: Path, session_factory):
    """Running twice must not duplicate any data."""
    assert await _run(_make_args(legacy_data_dir)) == 0
    assert await _run(_make_args(legacy_data_dir)) == 0  # second run, all skips

    async with session_factory() as s:
        tenants = (await s.execute(select(Tenant).where(Tenant.slug == "legacy"))).scalars().all()
        assert len(tenants) == 1
        accts = (await s.execute(select(Account))).scalars().all()
        assert len(accts) == 4  # not duplicated
        je_count = len((await s.execute(select(JournalEntry))).scalars().all())
        assert je_count == 1


async def test_importer_dry_run_rolls_back(legacy_data_dir: Path, session_factory):
    rc = await _run(_make_args(legacy_data_dir, dry_run=True))
    assert rc == 0
    async with session_factory() as s:
        # No data committed
        assert (await s.execute(select(Tenant).where(Tenant.slug == "legacy"))).scalar_one_or_none() is None


async def test_importer_rejects_unbalanced_journal(tmp_path: Path, session_factory):
    (tmp_path / "accounts.json").write_text(
        json.dumps(
            [
                {"code": "1100", "name": "Kas", "type": "asset"},
                {"code": "3100", "name": "Modal", "type": "equity"},
            ]
        )
    )
    (tmp_path / "journals.json").write_text(
        json.dumps(
            [
                {
                    "no": "JV-BAD",
                    "date": "2026-02-01",
                    "lines": [
                        {"account_code": "1100", "debit": 1000},
                        {"account_code": "3100", "credit": 999},  # unbalanced
                    ],
                }
            ]
        )
    )
    rc = await _run(_make_args(tmp_path, tenant_slug="bal-test"))
    # Returns 1 because there were import errors, but other imports still committed
    assert rc == 1
    async with session_factory() as s:
        # Accounts imported, but bad journal rejected
        je_count = len((await s.execute(select(JournalEntry))).scalars().all())
        assert je_count == 0

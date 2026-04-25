"""Starter Chart of Accounts (Indonesian SAK-style, generic SME).

Each entry: (code, name, type, normal_side, parent_code, mapping_key)
- parent_code: code of parent account (None for top-level)
- mapping_key: well-known AccountMapping key to bind this account to,
  or None if no mapping. See app.modules.accounting.schemas
  WELL_KNOWN_MAPPING_KEYS.

Codes follow a 4-digit numbering convention with sub-account suffixes:
  1xxx Assets, 2xxx Liabilities, 3xxx Equity, 4xxx Income, 5xxx Expenses
"""

from typing import NamedTuple


class StarterAccount(NamedTuple):
    code: str
    name: str
    type: str  # asset / liability / equity / income / expense
    normal_side: str  # debit / credit
    parent_code: str | None
    mapping_key: str | None  # binds AccountMapping on creation
    is_cash: bool = False  # flagged for cash-basis P&L


STARTER_COA: list[StarterAccount] = [
    # ── 1xxx Assets ─────────────────────────────────────────
    StarterAccount("1000", "Aset", "asset", "debit", None, None),
    StarterAccount("1100", "Kas & Bank", "asset", "debit", "1000", None),
    StarterAccount("1110", "Kas", "asset", "debit", "1100", "cash_default", is_cash=True),
    StarterAccount("1120", "Bank", "asset", "debit", "1100", None, is_cash=True),
    StarterAccount("1200", "Piutang Usaha", "asset", "debit", "1000", "ar"),
    StarterAccount("1300", "Persediaan", "asset", "debit", "1000", None),
    StarterAccount("1400", "PPN Masukan (Tax Receivable)", "asset", "debit", "1000", "tax_receivable"),
    StarterAccount("1500", "Aset Tetap", "asset", "debit", "1000", None),
    StarterAccount("1510", "Peralatan", "asset", "debit", "1500", None),
    StarterAccount("1520", "Akumulasi Penyusutan", "asset", "credit", "1500", None),
    # ── 2xxx Liabilities ────────────────────────────────────
    StarterAccount("2000", "Kewajiban", "liability", "credit", None, None),
    StarterAccount("2100", "Hutang Usaha", "liability", "credit", "2000", "ap"),
    StarterAccount("2200", "PPN Keluaran (Tax Payable)", "liability", "credit", "2000", "tax_payable"),
    StarterAccount("2300", "Hutang Jangka Panjang", "liability", "credit", "2000", None),
    # ── 3xxx Equity ─────────────────────────────────────────
    StarterAccount("3000", "Ekuitas", "equity", "credit", None, None),
    StarterAccount("3100", "Modal Pemilik", "equity", "credit", "3000", None),
    StarterAccount("3200", "Laba Ditahan", "equity", "credit", "3000", None),
    StarterAccount("3300", "Prive", "equity", "debit", "3000", None),
    # ── 4xxx Income ─────────────────────────────────────────
    StarterAccount("4000", "Pendapatan", "income", "credit", None, None),
    StarterAccount("4100", "Penjualan", "income", "credit", "4000", "sales_revenue"),
    StarterAccount("4200", "Pendapatan Lain-lain", "income", "credit", "4000", None),
    StarterAccount("4300", "Diskon Penjualan", "income", "debit", "4000", None),
    # ── 5xxx Expenses ───────────────────────────────────────
    StarterAccount("5000", "Beban", "expense", "debit", None, None),
    StarterAccount("5100", "Harga Pokok Penjualan", "expense", "debit", "5000", "purchase_expense"),
    StarterAccount("5200", "Beban Operasional", "expense", "debit", "5000", None),
    StarterAccount("5210", "Beban Gaji", "expense", "debit", "5200", None),
    StarterAccount("5220", "Beban Sewa", "expense", "debit", "5200", None),
    StarterAccount("5230", "Beban Listrik & Air", "expense", "debit", "5200", None),
    StarterAccount("5240", "Beban Telekomunikasi", "expense", "debit", "5200", None),
    StarterAccount("5250", "Beban ATK", "expense", "debit", "5200", None),
    StarterAccount("5260", "Beban Penyusutan", "expense", "debit", "5200", None),
    StarterAccount("5300", "Beban Bunga & Bank", "expense", "debit", "5000", None),
    StarterAccount("5900", "Beban Lain-lain", "expense", "debit", "5000", None),
]

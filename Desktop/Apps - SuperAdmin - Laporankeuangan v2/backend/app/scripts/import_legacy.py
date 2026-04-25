"""Legacy JSON → PostgreSQL importer.

Reads a directory of legacy JSON files (one per "table") and imports them
into a new or existing tenant. Designed for the file-based backend that
preceded this FastAPI service.

Usage:
    python -m app.scripts.import_legacy \\
        --data-dir /path/to/legacy/data \\
        --tenant-slug acme \\
        --tenant-name "Acme Corp" \\
        --owner-email owner@acme.com \\
        --owner-password 'StrongP@ss1' \\
        --owner-full-name "Owner Name" \\
        [--dry-run] [--seed-coa]

Idempotency:
- Tenant: created if slug doesn't exist; reused otherwise
- Owner user: created if email doesn't exist; reused otherwise
  (membership added if missing)
- Accounts / Customers / Suppliers: skipped if `code` already exists
- Journals / Sales invoices / Purchase invoices: skipped if their
  `entry_no` / `invoice_no` already exists
- Account mappings: only set when missing (use `--seed-coa
  --overwrite-mappings` to force)

Expected JSON file names (each is optional — missing files are skipped):
  accounts.json, customers.json, suppliers.json, journals.json,
  sales_invoices.json, purchase_invoices.json

See backend/README.md for the schema each file expects.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import transaction
from app.core.security import hash_password
from app.modules.accounting.models import Account, JournalEntry, JournalLine
from app.modules.accounting.repository import AccountingRepository
from app.modules.identity.models import Tenant, TenantUser, User
from app.modules.identity.repository import IdentityRepository
from app.modules.purchase.models import PurchaseInvoice, PurchaseInvoiceLine, Supplier
from app.modules.sales.models import Customer, SalesInvoice, SalesInvoiceLine


# ─── Result tracking ──────────────────────────────────────
@dataclass
class ImportStats:
    section: str
    created: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)

    def line(self) -> str:
        err = f"  ERRORS: {len(self.errors)}" if self.errors else ""
        return f"  {self.section:<22}  created={self.created:<5}  skipped={self.skipped:<5}{err}"


# ─── JSON helpers ─────────────────────────────────────────
def _read_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def _unwrap(data: Any, key: str) -> list[dict]:
    """Accept either a top-level list or a dict with a single list field."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if key in data and isinstance(data[key], list):
            return data[key]
        # Try plural/singular variants
        for k in (f"{key}s", "items", "data"):
            if k in data and isinstance(data[k], list):
                return data[k]
    return []


def _money(v: Any) -> Decimal:
    if v is None or v == "":
        return Decimal("0")
    return Decimal(str(v)).quantize(Decimal("0.01"))


def _qty(v: Any) -> Decimal:
    if v is None or v == "":
        return Decimal("0")
    return Decimal(str(v))


def _parse_date(v: Any) -> date:
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, str):
        # Accept "YYYY-MM-DD" or ISO-with-time
        return datetime.fromisoformat(v.split("T")[0]).date()
    raise ValueError(f"Unparseable date: {v!r}")


def _norm_side(account_type: str, declared: str | None) -> str:
    if declared in ("debit", "credit"):
        return declared
    # Default by type
    return "debit" if account_type in ("asset", "expense") else "credit"


# ─── Tenant + user setup ──────────────────────────────────
async def _ensure_tenant_and_owner(
    session: AsyncSession,
    *,
    slug: str,
    name: str,
    owner_email: str,
    owner_password: str,
    owner_full_name: str,
) -> tuple[Tenant, User]:
    repo = IdentityRepository(session)
    tenant = await repo.get_tenant_by_slug(slug)
    if tenant is None:
        tenant = Tenant(name=name, slug=slug)
        await repo.add_tenant(tenant)
        print(f"  ✓ Created tenant '{slug}'")
    else:
        print(f"  ✓ Reusing existing tenant '{slug}'")

    user = await repo.get_user_by_email(owner_email)
    if user is None:
        user = User(
            email=owner_email,
            password_hash=hash_password(owner_password),
            full_name=owner_full_name,
        )
        await repo.add_user(user)
        print(f"  ✓ Created owner user '{owner_email}'")
    else:
        print(f"  ✓ Reusing existing user '{owner_email}'")

    # Ensure membership with admin role
    membership = await repo.get_membership(user.id, tenant.id)
    if membership is None:
        admin_role = await repo.get_role_by_name("admin", tenant_id=None)
        if admin_role is None:
            raise RuntimeError("System role 'admin' not seeded. Run `python -m app.scripts.seed` first.")
        await repo.add_membership(
            TenantUser(
                tenant_id=tenant.id,
                user_id=user.id,
                role_id=admin_role.id,
                is_owner=True,
                accepted_at=datetime.utcnow(),
            )
        )
        print("  ✓ Added owner membership (admin role)")

    return tenant, user


# ─── Importers ────────────────────────────────────────────
async def _import_accounts(session: AsyncSession, tenant_id: UUID, items: list[dict]) -> ImportStats:
    stats = ImportStats("accounts")
    repo = AccountingRepository(session, tenant_id)

    # Pass 1: insert flat (no parent linkage)
    code_to_id: dict[str, UUID] = {}
    for a in await repo.list_accounts(active_only=False):
        code_to_id[a.code] = a.id

    for entry in items:
        try:
            code = str(entry["code"]).strip()
            if code in code_to_id:
                stats.skipped += 1
                continue
            atype = str(entry["type"]).strip().lower()
            if atype not in {"asset", "liability", "equity", "income", "expense"}:
                stats.errors.append(f"account {code}: unknown type {atype!r}")
                continue
            account = Account(
                tenant_id=tenant_id,
                code=code,
                name=str(entry["name"]).strip(),
                type=atype,
                normal_side=_norm_side(atype, entry.get("normal_side")),
                description=entry.get("description"),
            )
            session.add(account)
            await session.flush()
            code_to_id[code] = account.id
            stats.created += 1
        except KeyError as e:
            stats.errors.append(f"account missing field {e}")
        except Exception as e:  # noqa: BLE001
            stats.errors.append(f"account {entry.get('code')}: {e}")

    # Pass 2: parent linkage
    for entry in items:
        parent_code = entry.get("parent_code") or entry.get("parent")
        if not parent_code:
            continue
        code = str(entry.get("code", "")).strip()
        if code not in code_to_id or parent_code not in code_to_id:
            continue
        result = await session.execute(select(Account).where(Account.id == code_to_id[code]))
        account = result.scalar_one()
        if account.parent_id is None:
            account.parent_id = code_to_id[parent_code]
    await session.flush()
    return stats


async def _import_customers(session: AsyncSession, tenant_id: UUID, items: list[dict]) -> ImportStats:
    stats = ImportStats("customers")
    existing = {
        c.code
        for c in (await session.execute(select(Customer.code).where(Customer.tenant_id == tenant_id)))
        .scalars()
        .all()
    }
    for c in items:
        try:
            code = str(c["code"]).strip()
            if code in existing:
                stats.skipped += 1
                continue
            session.add(
                Customer(
                    tenant_id=tenant_id,
                    code=code,
                    name=str(c["name"]).strip(),
                    email=c.get("email") or None,
                    phone=c.get("phone") or None,
                    address=c.get("address") or None,
                    tax_id=c.get("tax_id") or c.get("npwp") or None,
                    notes=c.get("notes"),
                )
            )
            existing.add(code)
            stats.created += 1
        except KeyError as e:
            stats.errors.append(f"customer missing field {e}")
        except Exception as e:  # noqa: BLE001
            stats.errors.append(f"customer {c.get('code')}: {e}")
    await session.flush()
    return stats


async def _import_suppliers(session: AsyncSession, tenant_id: UUID, items: list[dict]) -> ImportStats:
    stats = ImportStats("suppliers")
    existing = {
        s.code
        for s in (await session.execute(select(Supplier.code).where(Supplier.tenant_id == tenant_id)))
        .scalars()
        .all()
    }
    for s in items:
        try:
            code = str(s["code"]).strip()
            if code in existing:
                stats.skipped += 1
                continue
            session.add(
                Supplier(
                    tenant_id=tenant_id,
                    code=code,
                    name=str(s["name"]).strip(),
                    email=s.get("email") or None,
                    phone=s.get("phone") or None,
                    address=s.get("address") or None,
                    tax_id=s.get("tax_id") or s.get("npwp") or None,
                    notes=s.get("notes"),
                )
            )
            existing.add(code)
            stats.created += 1
        except KeyError as e:
            stats.errors.append(f"supplier missing field {e}")
        except Exception as e:  # noqa: BLE001
            stats.errors.append(f"supplier {s.get('code')}: {e}")
    await session.flush()
    return stats


async def _import_journals(
    session: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    items: list[dict],
) -> ImportStats:
    stats = ImportStats("journals")

    # Build account_code → id map
    accounts = (await session.execute(select(Account).where(Account.tenant_id == tenant_id))).scalars().all()
    code_to_id = {a.code: a.id for a in accounts}

    existing_nos = set(
        (await session.execute(select(JournalEntry.entry_no).where(JournalEntry.tenant_id == tenant_id)))
        .scalars()
        .all()
    )

    for j in items:
        try:
            entry_no = str(j.get("no") or j.get("entry_no") or "").strip()
            if entry_no and entry_no in existing_nos:
                stats.skipped += 1
                continue

            entry_date = _parse_date(j.get("date") or j["entry_date"])
            lines_in = j.get("lines") or []
            if len(lines_in) < 2:
                stats.errors.append(f"journal {entry_no}: needs at least 2 lines")
                continue

            # Validate balance + accounts
            total_debit = sum((_money(ln.get("debit", 0)) for ln in lines_in), Decimal("0"))
            total_credit = sum((_money(ln.get("credit", 0)) for ln in lines_in), Decimal("0"))
            if total_debit != total_credit:
                stats.errors.append(
                    f"journal {entry_no}: unbalanced debit={total_debit} credit={total_credit}"
                )
                continue

            unknown = [
                ln.get("account_code") or ln.get("account")
                for ln in lines_in
                if (ln.get("account_code") or ln.get("account")) not in code_to_id
            ]
            if unknown:
                stats.errors.append(f"journal {entry_no}: unknown accounts {unknown}")
                continue

            # Allocate entry_no if blank
            if not entry_no:
                # Derive sequential JV-YYYY-#####
                year = entry_date.year
                count = sum(1 for n in existing_nos if n.startswith(f"JV-{year}-"))
                entry_no = f"JV-{year}-{count + 1:05d}"

            posted = bool(j.get("posted", True))
            entry = JournalEntry(
                tenant_id=tenant_id,
                entry_no=entry_no,
                entry_date=entry_date,
                description=j.get("description"),
                reference=j.get("reference"),
                status="posted" if posted else "draft",
                source="legacy_import",
                created_by=user_id,
                posted_by=user_id if posted else None,
                posted_at=datetime.utcnow() if posted else None,
            )
            for idx, ln in enumerate(lines_in, start=1):
                acct_code = ln.get("account_code") or ln.get("account")
                entry.lines.append(
                    JournalLine(
                        tenant_id=tenant_id,
                        line_no=idx,
                        account_id=code_to_id[acct_code],
                        description=ln.get("description"),
                        debit=_money(ln.get("debit", 0)),
                        credit=_money(ln.get("credit", 0)),
                    )
                )
            session.add(entry)
            await session.flush()
            existing_nos.add(entry_no)
            stats.created += 1
        except Exception as e:  # noqa: BLE001
            stats.errors.append(f"journal {j.get('no')}: {e}")
    return stats


async def _import_sales_invoices(
    session: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    items: list[dict],
) -> ImportStats:
    stats = ImportStats("sales_invoices")
    customers = {
        c.code: c.id
        for c in (await session.execute(select(Customer).where(Customer.tenant_id == tenant_id)))
        .scalars()
        .all()
    }
    existing = set(
        (await session.execute(select(SalesInvoice.invoice_no).where(SalesInvoice.tenant_id == tenant_id)))
        .scalars()
        .all()
    )

    for inv in items:
        try:
            no = str(inv.get("no") or inv.get("invoice_no") or "").strip()
            if no and no in existing:
                stats.skipped += 1
                continue

            cust_code = inv.get("customer_code") or inv.get("customer")
            customer_id = customers.get(cust_code)
            if customer_id is None:
                stats.errors.append(f"sales {no}: unknown customer {cust_code!r}")
                continue

            inv_date = _parse_date(inv.get("date") or inv["invoice_date"])
            lines_in = inv.get("lines") or []
            if not lines_in:
                stats.errors.append(f"sales {no}: no lines")
                continue

            if not no:
                year = inv_date.year
                count = sum(1 for n in existing if n.startswith(f"INV-{year}-"))
                no = f"INV-{year}-{count + 1:05d}"

            subtotal = Decimal("0")
            tax_total = Decimal("0")
            sales = SalesInvoice(
                tenant_id=tenant_id,
                invoice_no=no,
                invoice_date=inv_date,
                due_date=_parse_date(inv["due_date"]) if inv.get("due_date") else None,
                customer_id=customer_id,
                notes=inv.get("notes"),
                status=inv.get("status", "draft"),
                created_by=user_id,
            )
            for idx, ln in enumerate(lines_in, start=1):
                qty = _qty(ln.get("qty", 1))
                price = _money(ln.get("unit_price") or ln.get("price") or 0)
                line_total = (qty * price).quantize(Decimal("0.01"))
                rate = Decimal(str(ln.get("tax_rate", 0)))
                line_tax = (line_total * rate / Decimal("100")).quantize(Decimal("0.01"))
                subtotal += line_total
                tax_total += line_tax
                sales.lines.append(
                    SalesInvoiceLine(
                        tenant_id=tenant_id,
                        line_no=idx,
                        description=str(ln.get("description") or ln.get("name") or ""),
                        qty=qty,
                        unit_price=price,
                        line_total=line_total,
                        tax_rate=rate,
                        tax_amount=line_tax,
                    )
                )

            sales.subtotal = subtotal
            sales.tax_amount = tax_total
            sales.total = subtotal + tax_total
            sales.paid_amount = _money(inv.get("paid_amount", 0))
            session.add(sales)
            await session.flush()
            existing.add(no)
            stats.created += 1
        except Exception as e:  # noqa: BLE001
            stats.errors.append(f"sales {inv.get('no')}: {e}")
    return stats


async def _import_purchase_invoices(
    session: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    items: list[dict],
) -> ImportStats:
    stats = ImportStats("purchase_invoices")
    suppliers = {
        s.code: s.id
        for s in (await session.execute(select(Supplier).where(Supplier.tenant_id == tenant_id)))
        .scalars()
        .all()
    }
    existing = set(
        (
            await session.execute(
                select(PurchaseInvoice.invoice_no).where(PurchaseInvoice.tenant_id == tenant_id)
            )
        )
        .scalars()
        .all()
    )

    for inv in items:
        try:
            no = str(inv.get("no") or inv.get("invoice_no") or "").strip()
            if no and no in existing:
                stats.skipped += 1
                continue
            sup_code = inv.get("supplier_code") or inv.get("supplier")
            supplier_id = suppliers.get(sup_code)
            if supplier_id is None:
                stats.errors.append(f"purchase {no}: unknown supplier {sup_code!r}")
                continue

            inv_date = _parse_date(inv.get("date") or inv["invoice_date"])
            lines_in = inv.get("lines") or []
            if not lines_in:
                stats.errors.append(f"purchase {no}: no lines")
                continue
            if not no:
                year = inv_date.year
                count = sum(1 for n in existing if n.startswith(f"BILL-{year}-"))
                no = f"BILL-{year}-{count + 1:05d}"

            subtotal = Decimal("0")
            tax_total = Decimal("0")
            pi = PurchaseInvoice(
                tenant_id=tenant_id,
                invoice_no=no,
                supplier_invoice_no=inv.get("supplier_invoice_no"),
                invoice_date=inv_date,
                due_date=_parse_date(inv["due_date"]) if inv.get("due_date") else None,
                supplier_id=supplier_id,
                notes=inv.get("notes"),
                status=inv.get("status", "draft"),
                created_by=user_id,
            )
            for idx, ln in enumerate(lines_in, start=1):
                qty = _qty(ln.get("qty", 1))
                price = _money(ln.get("unit_price") or ln.get("price") or 0)
                line_total = (qty * price).quantize(Decimal("0.01"))
                rate = Decimal(str(ln.get("tax_rate", 0)))
                line_tax = (line_total * rate / Decimal("100")).quantize(Decimal("0.01"))
                subtotal += line_total
                tax_total += line_tax
                pi.lines.append(
                    PurchaseInvoiceLine(
                        tenant_id=tenant_id,
                        line_no=idx,
                        description=str(ln.get("description") or ln.get("name") or ""),
                        qty=qty,
                        unit_price=price,
                        line_total=line_total,
                        tax_rate=rate,
                        tax_amount=line_tax,
                    )
                )

            pi.subtotal = subtotal
            pi.tax_amount = tax_total
            pi.total = subtotal + tax_total
            pi.paid_amount = _money(inv.get("paid_amount", 0))
            session.add(pi)
            await session.flush()
            existing.add(no)
            stats.created += 1
        except Exception as e:  # noqa: BLE001
            stats.errors.append(f"purchase {inv.get('no')}: {e}")
    return stats


# ─── Orchestration ────────────────────────────────────────
async def _run(args: argparse.Namespace) -> int:
    data_dir = Path(args.data_dir)
    if not data_dir.is_dir():  # noqa: ASYNC240 — CLI entrypoint, blocking I/O acceptable
        print(f"ERROR: data dir {data_dir} not found", file=sys.stderr)
        return 2

    print(f"\n=== Importing legacy data from {data_dir} ===")
    print(f"  tenant: '{args.tenant_slug}'  owner: '{args.owner_email}'")
    if args.dry_run:
        print("  *** DRY RUN — no commit ***")

    async with transaction() as session:
        tenant, user = await _ensure_tenant_and_owner(
            session,
            slug=args.tenant_slug,
            name=args.tenant_name,
            owner_email=args.owner_email,
            owner_password=args.owner_password,
            owner_full_name=args.owner_full_name,
        )

        all_stats: list[ImportStats] = []

        if args.seed_coa:
            from app.modules.accounting.service import AccountingService

            svc = AccountingService(session, tenant.id, user.id)
            result = await svc.seed_starter_coa(overwrite_mappings=args.overwrite_mappings)
            print(
                f"  ✓ Starter COA: created={result['accounts_created']} "
                f"skipped={result['accounts_skipped']} "
                f"mappings={result['mappings_set']}"
            )

        # ── accounts.json ──
        data = _read_json(data_dir / "accounts.json")
        if data is not None:
            all_stats.append(await _import_accounts(session, tenant.id, _unwrap(data, "account")))

        # ── customers.json ──
        data = _read_json(data_dir / "customers.json")
        if data is not None:
            all_stats.append(await _import_customers(session, tenant.id, _unwrap(data, "customer")))

        # ── suppliers.json ──
        data = _read_json(data_dir / "suppliers.json")
        if data is not None:
            all_stats.append(await _import_suppliers(session, tenant.id, _unwrap(data, "supplier")))

        # ── journals.json ──
        data = _read_json(data_dir / "journals.json")
        if data is not None:
            all_stats.append(await _import_journals(session, tenant.id, user.id, _unwrap(data, "journal")))

        # ── sales_invoices.json ──
        data = _read_json(data_dir / "sales_invoices.json")
        if data is not None:
            all_stats.append(
                await _import_sales_invoices(session, tenant.id, user.id, _unwrap(data, "sales_invoice"))
            )

        # ── purchase_invoices.json ──
        data = _read_json(data_dir / "purchase_invoices.json")
        if data is not None:
            all_stats.append(
                await _import_purchase_invoices(
                    session, tenant.id, user.id, _unwrap(data, "purchase_invoice")
                )
            )

        # Summary
        print("\n=== Import summary ===")
        for s in all_stats:
            print(s.line())

        total_errors = sum(len(s.errors) for s in all_stats)
        if total_errors:
            print(f"\n  *** {total_errors} errors:")
            for s in all_stats:
                for e in s.errors[:20]:
                    print(f"    [{s.section}] {e}")
                if len(s.errors) > 20:
                    print(f"    [{s.section}] ... +{len(s.errors) - 20} more")

        if args.dry_run:
            await session.rollback()
            print("\n*** DRY RUN — rolled back ***")
        # else: outer `transaction()` commits on exit

    print("\n✓ Done")
    return 0 if not all_stats or all(not s.errors for s in all_stats) else 1


def main() -> None:
    p = argparse.ArgumentParser(
        description="Import legacy JSON data into a Postgres tenant.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--data-dir", required=True, help="Directory containing legacy *.json files")
    p.add_argument("--tenant-slug", required=True)
    p.add_argument("--tenant-name", required=True)
    p.add_argument("--owner-email", required=True)
    p.add_argument(
        "--owner-password",
        required=True,
        help="Owner login password (only used if creating a new user)",
    )
    p.add_argument("--owner-full-name", required=True)
    p.add_argument(
        "--seed-coa",
        action="store_true",
        help="Run starter-COA provisioner before importing accounts/journals",
    )
    p.add_argument(
        "--overwrite-mappings",
        action="store_true",
        help="With --seed-coa, force re-bind of account mappings",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse + validate everything, then ROLLBACK at the end",
    )
    args = p.parse_args()
    rc = asyncio.run(_run(args))
    sys.exit(rc)


if __name__ == "__main__":
    main()

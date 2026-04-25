# Kompak Accounting — Backend

[![Backend CI](https://github.com/Kreatifodoo/kompakappsmrp/actions/workflows/backend-ci.yml/badge.svg)](https://github.com/Kreatifodoo/kompakappsmrp/actions/workflows/backend-ci.yml)

FastAPI + SQLAlchemy 2.0 (async) + PostgreSQL 16 + Redis + Celery.
Multi-tenant SaaS backend for the Kompak Accounting platform.

## Architecture

Modular monolith. Each business capability lives under `app/modules/<name>/`
with the same structure:

```
app/
├── api_v1/routes.py        # mounts module routers under /api/v1
├── config.py               # Pydantic Settings (env-driven)
├── core/                   # database, security, cache, ratelimit, events, logging
├── deps.py                 # CurrentUser, get_current_user, require_permission
├── main.py                 # FastAPI app factory
├── modules/
│   ├── identity/           # Tenants, Users, Roles, Permissions, JWT auth
│   │   ├── models.py
│   │   ├── schemas.py
│   │   ├── repository.py
│   │   ├── service.py
│   │   └── api.py
│   └── accounting/         # COA, Journal Entries, Journal Lines
│       └── ...
├── scripts/seed.py         # Seed system roles + permissions
└── worker/celery_app.py    # Celery instance (autodiscover module tasks)
migrations/                 # Alembic (async)
```

Tenant isolation is enforced two ways:
1. **Application layer** — every accounting query is scoped via
   `AccountingRepository(session, tenant_id)`.
2. **Database layer** — Postgres RLS using `SET LOCAL app.current_tenant`
   (set via `core.database.set_tenant_context`) — to be enabled per-table
   in a follow-up migration.

## Local development (Docker)

```bash
cd backend
cp .env.example .env
# generate a 32+ char secret
python -c "import secrets; print(secrets.token_urlsafe(48))" \
    | xargs -I {} sed -i '' 's|JWT_SECRET=.*|JWT_SECRET={}|' .env

docker compose up -d postgres redis
docker compose build api worker
docker compose run --rm api alembic upgrade head
docker compose run --rm api python -m app.scripts.seed
docker compose up api worker
```

API: http://localhost:8000 — interactive docs at `/docs`.

## Local development (without Docker)

Requires Python 3.12+, Postgres 16 (with `citext` extension), Redis 7.

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e .

cp .env.example .env  # then edit DB_PRIMARY_URL, JWT_SECRET, etc.

alembic upgrade head
python -m app.scripts.seed

uvicorn app.main:app --reload
```

## Endpoints (current)

### Identity — `/api/v1/auth`
| Method | Path                  | Auth | Description                          |
|--------|-----------------------|------|--------------------------------------|
| POST   | `/auth/register-tenant` | —    | Bootstrap a tenant + owner user      |
| POST   | `/auth/login`         | —    | Email + password → access + refresh  |
| POST   | `/auth/refresh`       | —    | Rotate refresh token                 |
| GET    | `/auth/me`            | JWT  | Current user, tenant, role, perms    |

### Accounting — `/api/v1`
| Method | Path                          | Permission     |
|--------|-------------------------------|----------------|
| GET    | `/accounts`                   | `coa.read`     |
| POST   | `/accounts`                   | `coa.write`    |
| POST   | `/accounts/seed-starter-coa`  | `coa.write`    |
| PATCH  | `/accounts/{id}`              | `coa.write`    |
| GET    | `/account-mappings`           | `coa.read`     |
| PUT    | `/account-mappings`           | `coa.write`    |
| GET    | `/journals`                   | `journal.read` |
| GET    | `/journals/{id}`              | `journal.read` |
| POST   | `/journals` (`?post_now=...`) | `journal.write` (+ `journal.post` if posting) |
| POST   | `/journals/{id}/post`         | `journal.post` |
| POST   | `/journals/{id}/void`         | `journal.post` |

### Reports — `/api/v1/reports`
| Method | Path                                              | Permission    |
|--------|---------------------------------------------------|---------------|
| GET    | `/reports/trial-balance?as_of=YYYY-MM-DD`         | `report.read` |
| GET    | `/reports/profit-loss?date_from=&date_to=`        | `report.read` |
| GET    | `/reports/balance-sheet?as_of=YYYY-MM-DD`         | `report.read` |
| GET    | `/reports/aged-receivables?as_of=YYYY-MM-DD`      | `report.read` |
| GET    | `/reports/aged-payables?as_of=YYYY-MM-DD`         | `report.read` |

All reports:
- Run against the **read replica** via `get_read_session()` so they
  don't compete with OLTP writes
- Aggregate over `journal_lines` joined to posted `journal_entries`
  only — drafts and voided entries are excluded
- Are tenant-scoped at every join

**Trial balance** — list of every account with cumulative `total_debit`
/ `total_credit` and a signed `balance` (positive = on the account's
natural side). Includes a `balanced` flag (always true for valid books).

**Profit & Loss** — income & expense lines for a date range, plus
`total_income`, `total_expense`, `net_profit`.

**Balance sheet** — snapshot at `as_of` with assets / liabilities /
explicit equity broken out, **plus a computed `retained_earnings`**
(cumulative net P/L through `as_of`). The `balanced` flag verifies the
fundamental equation `Assets = Liabilities + Equity` (within 0.01 IDR
rounding tolerance).

**Aged AR / AP** — outstanding posted invoices grouped per customer
(or supplier), with each invoice's outstanding amount bucketed by
days overdue:

| Bucket          | Range                              |
|-----------------|------------------------------------|
| `current`       | not yet due (`due_date >= as_of`)  |
| `days_1_30`     | 1–30 days overdue                  |
| `days_31_60`    | 31–60 days overdue                 |
| `days_61_90`    | 61–90 days overdue                 |
| `days_over_90`  | 91+ days overdue                   |

Days overdue is computed against `due_date` if set, otherwise against
`invoice_date`. Voided and fully-paid invoices are excluded. Each
party row includes its individual invoice list for drill-down.

### Sales — `/api/v1`
| Method | Path                                  | Permission       |
|--------|---------------------------------------|------------------|
| GET    | `/customers`                          | `sales.read`     |
| POST   | `/customers`                          | `sales.write`    |
| PATCH  | `/customers/{id}`                     | `sales.write`    |
| GET    | `/sales-invoices`                     | `sales.read`     |
| GET    | `/sales-invoices/{id}`                | `sales.read`     |
| POST   | `/sales-invoices` (`?post_now=...`)   | `sales.write` (+ `sales.post` if posting) |
| POST   | `/sales-invoices/{id}/post`           | `sales.post`     |
| POST   | `/sales-invoices/{id}/void`           | `sales.post`     |

### Purchase — `/api/v1`
| Method | Path                                     | Permission         |
|--------|------------------------------------------|--------------------|
| GET    | `/suppliers`                             | `purchase.read`    |
| POST   | `/suppliers`                             | `purchase.write`   |
| PATCH  | `/suppliers/{id}`                        | `purchase.write`   |
| GET    | `/purchase-invoices`                     | `purchase.read`    |
| GET    | `/purchase-invoices/{id}`                | `purchase.read`    |
| POST   | `/purchase-invoices` (`?post_now=...`)   | `purchase.write` (+ `purchase.post` if posting) |
| POST   | `/purchase-invoices/{id}/post`           | `purchase.post`    |
| POST   | `/purchase-invoices/{id}/void`           | `purchase.post`    |

### Auto-journal posting

Posting a sales/purchase invoice creates a balanced journal entry **in the
same DB transaction** (atomicity guaranteed by shared `AsyncSession`):

**Sales invoice post:**
```
Dr  Accounts Receivable     (subtotal + tax)
    Cr  Sales Revenue       (subtotal)
    Cr  Tax Payable         (tax, if > 0)
```

**Purchase invoice post:**
```
Dr  Purchase Expense        (per-line, optionally per-line override)
Dr  Tax Receivable          (tax, if > 0)
    Cr  Accounts Payable    (gross total)
```

The `JournalEntry.source` / `source_id` fields link the journal back to its
source document. Voiding an invoice voids the linked journal automatically.

**Required setup before posting** — every tenant needs accounts assigned
to all 7 well-known mapping keys: `ar`, `ap`, `sales_revenue`,
`purchase_expense`, `tax_payable`, `tax_receivable`, `cash_default`.
Easiest way: call `POST /api/v1/accounts/seed-starter-coa` (see below).
Otherwise create accounts manually then call `PUT /api/v1/account-mappings`
for each key.

### Tenant onboarding flow

```bash
# 1. Bootstrap a new tenant + owner user
POST /api/v1/auth/register-tenant
  { "tenant_name": "Toko Maju", "tenant_slug": "toko-maju",
    "owner_email": "owner@toko.com", "owner_password": "••••••••",
    "owner_full_name": "Pak Budi" }

# 2. Login → obtain access + refresh tokens
POST /api/v1/auth/login

# 3. One-shot: provision ~32 standard SAK accounts AND auto-bind all
#    7 account mappings (idempotent; safe to re-run)
POST /api/v1/accounts/seed-starter-coa
  → { "accounts_created": 32, "accounts_skipped": 0, "mappings_set": 7 }

# 4. Customize: rename / hide accounts your business doesn't use
PATCH /api/v1/accounts/{id}

# 5. Done — invoices can now post and create journals atomically
POST /api/v1/sales-invoices?post_now=true
```

The seeder is idempotent — running it again on a tenant that already has
accounts skips existing codes (`accounts_skipped` count) and only sets
mappings that aren't yet bound. Pass `?overwrite_mappings=true` to force
re-binding.

## System roles seeded

| Role        | Permissions                                                |
|-------------|-------------------------------------------------------------|
| admin       | All 17                                                      |
| accountant  | COA read/write, journal read/write/post, sales/purchase read, reports |
| staff       | COA read, journal read/write, sales+purchase read/write, report read   |
| viewer      | All `*.read` only                                           |

## Importing legacy JSON data

A CLI importer migrates a tenant from the file-based predecessor service
into PostgreSQL. It's idempotent — safe to re-run.

```bash
python -m app.scripts.import_legacy \
    --data-dir /path/to/legacy/data \
    --tenant-slug acme \
    --tenant-name "Acme Corp" \
    --owner-email owner@acme.com \
    --owner-password 'StrongP@ss1' \
    --owner-full-name "Owner Name" \
    [--seed-coa] [--dry-run]
```

Flags:
- `--seed-coa` — provision the standard 32-account starter COA + auto-bind
  account mappings before importing (skip if your `accounts.json` already
  has everything)
- `--overwrite-mappings` — with `--seed-coa`, force re-bind of mappings
- `--dry-run` — parse + validate everything; rollback at the end

The importer scans the `--data-dir` for these files (each is optional —
missing files are silently skipped). All amounts accept int / float /
string; dates accept `YYYY-MM-DD` or ISO-with-time.

### `accounts.json`
```json
[
  {"code": "1100", "name": "Kas",       "type": "asset",     "normal_side": "debit",  "parent_code": null},
  {"code": "3100", "name": "Modal",     "type": "equity",    "normal_side": "credit"},
  {"code": "4100", "name": "Penjualan", "type": "income"},
  {"code": "5100", "name": "HPP",       "type": "expense",   "description": "Cost of goods"}
]
```
- `normal_side` is optional — defaults to `debit` for asset/expense, `credit` for the rest
- `parent_code` is optional — wired up in a second pass after all accounts are inserted

### `customers.json` / `suppliers.json`
```json
[{"code": "C001", "name": "Toko A", "email": "a@x.id", "phone": "0812", "address": "...", "tax_id": "..."}]
```

### `journals.json`
```json
[
  {
    "no": "JV-2026-00001",                    // optional; auto-generated if missing
    "date": "2026-02-01",
    "description": "Setoran modal",
    "reference": "BUKTI-001",
    "posted": true,                           // default true
    "lines": [
      {"account_code": "1100", "debit": 5000000, "description": "Kas masuk"},
      {"account_code": "3100", "credit": 5000000}
    ]
  }
]
```
- Each entry must be balanced (sum debits == sum credits) — unbalanced entries are rejected with errors logged but don't abort the rest
- Tagged `source = "legacy_import"` for forensics

### `sales_invoices.json` / `purchase_invoices.json`
```json
[
  {
    "no": "INV-2026-00001",
    "date": "2026-02-10",
    "due_date": "2026-03-10",
    "customer_code": "C001",                  // or supplier_code
    "status": "draft",                        // draft|posted|paid|void
    "paid_amount": 0,
    "lines": [
      {"description": "Jasa", "qty": 1, "unit_price": 1000, "tax_rate": 11}
    ]
  }
]
```
- Imported invoices are NOT auto-posted (no journal created). Invoices
  legitimately posted in the legacy system should also include matching
  entries in `journals.json` so the books reconcile

### Idempotency rules

| Section            | Skip condition                              |
|--------------------|---------------------------------------------|
| Tenant             | `slug` already exists                       |
| Owner user         | `email` already exists (membership added)   |
| Accounts           | `code` already exists in this tenant        |
| Customers          | `code` already exists                       |
| Suppliers          | `code` already exists                       |
| Journals           | `no` (entry_no) already exists              |
| Sales invoices     | `no` (invoice_no) already exists            |
| Purchase invoices  | `no` (invoice_no) already exists            |

So you can re-run with new data files added to the same directory and
only the new rows will be inserted. Errors per row are logged but don't
abort the rest of the import — exit code is 1 if any errors occurred,
0 otherwise.

### Bulk migration script for many tenants

```bash
for slug in $(ls /opt/legacy/tenants/); do
    python -m app.scripts.import_legacy \
        --data-dir /opt/legacy/tenants/$slug \
        --tenant-slug $slug \
        --tenant-name "$(cat /opt/legacy/tenants/$slug/name.txt)" \
        --owner-email "owner@$slug.kompakapps.com" \
        --owner-password "$(openssl rand -hex 16)" \
        --owner-full-name "Owner of $slug" \
        --seed-coa
done
```

## Tenant isolation: Postgres RLS

As of migration `0005`, every business-data table has **Row-Level
Security** enabled with `FORCE ROW LEVEL SECURITY` (so even the
table owner is subject to the policy). RLS is the safety net if the
application ever forgets a `WHERE tenant_id = …` clause.

### Tables protected

```
accounts, account_mappings,
journal_entries, journal_lines (incl. all monthly partitions),
customers, sales_invoices, sales_invoice_lines,
suppliers, purchase_invoices, purchase_invoice_lines
```

Identity tables (`tenants`, `users`, `roles`, `permissions`,
`role_permissions`, `tenant_users`, `refresh_tokens`) are NOT RLS-
protected — login, register-tenant, and refresh flows must be able to
read across tenants before any tenant context exists. Application-level
auth is authoritative for those tables.

### How the GUC is set

`get_write_session` and `get_read_session` decode the request's bearer
token inline and run, in the same transaction:

```sql
SELECT set_config('app.current_tenant', '<tenant-uuid>', true);  -- LOCAL
SELECT set_config('app.is_super_admin', 'true', true);           -- only if `sa` claim
```

The policy on each table is then:

```sql
USING (
    tenant_id::text = current_setting('app.current_tenant', true)
    OR current_setting('app.is_super_admin', true) = 'true'
)
WITH CHECK (...)  -- same condition for INSERT/UPDATE
```

### Bypassing RLS in admin scripts

CLI scripts that operate across tenants (e.g. `seed`, `import_legacy`,
`manage_partitions`) use the standalone `transaction()` context manager
in `app.core.database`, which sets `app.is_super_admin = 'true'` at
session start. **Never use `transaction()` from inside a request
handler** — always go through `get_write_session`.

### What this protects against

- Bug: a new query forgets `WHERE tenant_id = ?` → RLS returns 0 rows
  instead of leaking another tenant's data
- Bug: a service erroneously builds `Account(tenant_id=other_tenant_id)`
  and tries to commit → Postgres rejects the INSERT with
  `new row violates row-level security policy`
- Compromised JWT for tenant A can never read tenant B's data via
  the API regardless of any code path it traverses

## Journal table partitioning

`journal_entries` and `journal_lines` are **RANGE-partitioned by
`entry_date` (monthly)** as of migration `0004`. This is the highest-
churn data in the system — at scale, partitioning gives:
- Partition pruning on date-range reports (trial balance, P&L, balance
  sheet) — Postgres scans only the months in scope, not the whole table
- Cheap maintenance: vacuum, reindex, and (eventually) archival happen
  per-partition rather than over a multi-billion-row monolith
- Per-partition statistics that produce more accurate query plans

### Schema details

- Composite primary key `(id, entry_date)` (Postgres requires the
  partition column to be part of every unique constraint)
- `journal_lines.entry_date` is **denormalized** from
  `journal_entries.entry_date`, with composite FK
  `(entry_id, entry_date) → journal_entries(id, entry_date)`. This lets
  partition pruning work on `journal_lines` too when reports filter
  by date — without it, every line query would scan all partitions.
- `sales_invoices.journal_entry_id` and
  `purchase_invoices.journal_entry_id` no longer have FK constraints
  (a single-column FK can't reference a composite PK). Application-
  level integrity (Sales/PurchaseService) is the source of truth.

### Keeping partitions ahead of real time

Migration `0004` creates partitions covering
`[min_year - 1, max_year + 1]` from the data at upgrade time (or
`[2024, 2027]` if no data). As real time advances, top up the future
window:

```bash
python -m app.scripts.manage_partitions --months-ahead 12
```

Idempotent — existing partitions are skipped. Run on a cron / Celery
beat schedule (e.g. monthly, on the 1st):

```cron
# /etc/cron.d/kompak-partitions
0 2 1 * * kompak python -m app.scripts.manage_partitions --months-ahead 12
```

If you forget to run it and a tenant tries to post into an unpartitioned
month, Postgres raises:
```
ERROR: no partition of relation "journal_entries" found for row
DETAIL: Partition key of the failing row contains (entry_date) = (2030-05-15).
```

## Migrations

```bash
# Create a new revision after model changes
alembic revision --autogenerate -m "add x"

# Apply
alembic upgrade head

# Rollback one step
alembic downgrade -1
```

## Testing

Stack: **pytest + pytest-asyncio + httpx (ASGITransport)** against a
dedicated Postgres test database.

### Setup

```bash
# 1. Create the test database (one-time)
docker compose exec postgres createdb -U kompak kompak_test

# 2. Install dev deps
pip install -e ".[dev]"  # or:
pip install pytest pytest-asyncio pytest-cov httpx
```

### Run

```bash
# Default test DB:  postgresql+asyncpg://kompak:kompak_dev@localhost:5432/kompak_test
pytest                                    # run everything
pytest -v tests/test_sales_purchase.py    # one file
pytest -k "balanced"                      # by keyword
pytest --cov=app --cov-report=term-missing # with coverage

# Override the test DB
TEST_DB_URL=postgresql+asyncpg://user:pass@host:5432/mydb pytest
```

### How isolation works

- **Once per session**: drop+recreate full schema via `Base.metadata`,
  install `citext`.
- **Once per test (autouse)**: `TRUNCATE` every table, then re-seed
  the 19 system permissions and 4 system roles. No bcrypt happens
  during reset, so it's fast (~5 ms per test).
- **Per request**: a `dependency_overrides` swap routes
  `get_write_session` to the test session factory.
- **HTTP**: `AsyncClient` with `ASGITransport(app)` — no socket, no
  uvicorn — direct in-process calls.

### Lint & format

```bash
ruff check app tests          # static analysis (E/F/I/N/UP/B/SIM/ASYNC)
ruff check --fix app tests    # auto-fix what's safe
ruff format app tests         # apply formatter
ruff format --check app tests # CI mode (no writes)
```

### What's covered

- `tests/test_identity.py` — register tenant, login, `/me`, refresh
  token rotation + revocation
- `tests/test_accounting.py` — starter-COA seed (idempotency check),
  account creation, duplicate code conflict, balanced/unbalanced
  journal validation
- `tests/test_sales_purchase.py` — full E2E: posting a sales /
  purchase invoice creates a balanced journal in the same DB
  transaction; voiding the invoice voids the journal; posting
  without account mappings fails cleanly

## Roadmap (next milestones)

- [ ] Tests (pytest + transactional DB fixture)
- [ ] Convert `journal_entries` / `journal_lines` to monthly partitions
- [ ] Enable Postgres RLS per tenant on all tenant-scoped tables
- [ ] Sales + Purchase modules (with auto journal posting via event bus)
- [ ] Reports module (trial balance, P&L, balance sheet — materialized views)
- [ ] JSON → PostgreSQL importer for legacy tenant data
- [ ] CI: GitHub Actions running lint + tests + migration smoke check

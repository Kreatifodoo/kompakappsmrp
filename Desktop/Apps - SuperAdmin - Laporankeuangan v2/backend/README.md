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

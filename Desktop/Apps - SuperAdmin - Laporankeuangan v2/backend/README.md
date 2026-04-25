# Kompak Accounting — Backend

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

**Required setup before posting** — call `PUT /api/v1/account-mappings`
once per tenant for each well-known key:
`ar`, `ap`, `sales_revenue`, `purchase_expense`, `tax_payable`,
`tax_receivable`, `cash_default`.

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

## Testing (TBD)

`pytest` + `pytest-asyncio` + `httpx.AsyncClient` against a transactional
fixture. Coming next.

## Roadmap (next milestones)

- [ ] Tests (pytest + transactional DB fixture)
- [ ] Convert `journal_entries` / `journal_lines` to monthly partitions
- [ ] Enable Postgres RLS per tenant on all tenant-scoped tables
- [ ] Sales + Purchase modules (with auto journal posting via event bus)
- [ ] Reports module (trial balance, P&L, balance sheet — materialized views)
- [ ] JSON → PostgreSQL importer for legacy tenant data
- [ ] CI: GitHub Actions running lint + tests + migration smoke check

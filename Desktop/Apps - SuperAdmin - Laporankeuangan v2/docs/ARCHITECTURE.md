# Kompak Accounting — Enterprise SaaS Architecture

**Target Scale**: 10,000+ tenants, 100k+ transactions per tenant
**Strategy**: Modular Monolith → Selective Microservices (only when needed)
**Priority Modules**: Accounting Core, Purchase/Sales (AP/AR), Multi-tenant Auth & RBAC

---

## 1. CURRENT ARCHITECTURE — PROBLEMS FOUND

### 1.1 Backend (`app/serve.py`)

| # | Problem | Risk | Why It Fails at Scale |
|---|---------|------|----------------------|
| 1 | Python `http.server` (single-thread, blocking) | 🔴 HIGH | Crashes at >10 concurrent users. No async, no worker pool |
| 2 | File-based JSON storage (no DB) | 🔴 HIGH | No ACID, no concurrent writes, no indexing. 100k transactions = full file rewrite each save |
| 3 | No backend authentication | 🔴 HIGH | Frontend can be bypassed via direct API calls. `curl PUT /api/data/users` overwrites all users |
| 4 | CORS wildcard (`*`) | 🟡 MED | Any site can call API. CSRF exposure if cookies added |
| 5 | No tenant isolation | 🔴 HIGH | All data in single `data/` folder. Can't serve multiple companies |
| 6 | Path traversal sanitization weak | 🟡 MED | `re.sub(r'[^a-zA-Z0-9_\-]', '_', key)` may not catch edge cases |
| 7 | Restore deletes all data first (no atomic) | 🔴 HIGH | Crash mid-restore = data loss |
| 8 | No rate limiting | 🟡 MED | DDoS / brute-force vulnerable |
| 9 | No request logging / audit trail | 🟡 MED | Can't debug production issues, no compliance trail |
| 10 | No health check / monitoring | 🟡 MED | Can't auto-recover from crashes |

### 1.2 Frontend (`app/js/*.js`)

| # | Problem | Risk |
|---|---------|------|
| 1 | All data loaded into localStorage upfront (`_pullAll`) | 🔴 HIGH — 10k tenants × 100k transactions = browser OOM |
| 2 | Password hashing with weak salt (`'_finreport_gki_salt_2024'`) | 🔴 HIGH — Same salt for all users = rainbow table attack |
| 3 | Permissions checked client-side only | 🔴 HIGH — Easily bypassed |
| 4 | No data pagination | 🔴 HIGH — Loading 100k journal entries kills UI |
| 5 | Session in `sessionStorage` (cleared on tab close) | 🟢 OK |
| 6 | 13 separate JS modules, all loaded at once | 🟡 MED — No code-splitting, 11k LOC parsed every page load |

### 1.3 Infrastructure

| # | Problem | Risk |
|---|---------|------|
| 1 | Single VPS (no redundancy) | 🔴 HIGH — Single point of failure |
| 2 | Manual `nohup` process management | 🔴 HIGH — No auto-restart, no log rotation |
| 3 | No backup automation (manual ZIP only) | 🔴 HIGH — Data loss risk |
| 4 | CI/CD just `git pull` (no atomic deploy) | 🟡 MED — Mid-deploy = broken state |
| 5 | No staging environment | 🟡 MED — Bugs go straight to production |

**Verdict**: Current architecture suitable for **1 customer, single user**. For 10,000+ tenants this is a **complete rewrite** of backend + significant frontend refactor.

---

## 2. NEW ARCHITECTURE — MODULAR MONOLITH

```
┌──────────────────────────────────────────────────────────────┐
│                       CLIENT LAYER                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │
│  │  Web SPA     │  │ Mobile (PWA) │  │ Native App   │        │
│  │ (React/Vite) │  │  (React)     │  │  (Flutter)   │        │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘        │
└─────────┼─────────────────┼─────────────────┼────────────────┘
          │                 │                 │
          └─────────┬───────┴─────────────────┘
                    ▼
          ┌─────────────────────┐
          │   CDN (Cloudflare)  │ — Static assets, DDoS protection
          └─────────┬───────────┘
                    ▼
          ┌─────────────────────┐
          │  Load Balancer      │ — Linode NodeBalancer / HAProxy
          │  + WAF              │
          └─────────┬───────────┘
                    ▼
┌──────────────────────────────────────────────────────────────┐
│                    APPLICATION LAYER                         │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  FastAPI App (3-10 instances, auto-scaling)            │  │
│  │  ┌───────────┐  ┌───────────┐  ┌───────────┐           │  │
│  │  │ Auth      │  │ Accounting│  │ Purchase  │  ...      │  │
│  │  │ Module    │  │ Module    │  │ Module    │           │  │
│  │  └───────────┘  └───────────┘  └───────────┘           │  │
│  │       │              │              │                  │  │
│  │       └──────────────┴──────────────┘                  │  │
│  │                      │                                 │  │
│  │              [Domain/Service Layer]                    │  │
│  │                      │                                 │  │
│  │              [Repository Layer]                        │  │
│  └──────────────────────┬─────────────────────────────────┘  │
└─────────────────────────┼────────────────────────────────────┘
                          │
       ┌──────────────────┼──────────────────┐
       ▼                  ▼                  ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ PostgreSQL   │  │   Redis      │  │  Object      │
│ (Primary +   │  │ (Cache,      │  │  Storage     │
│  2 Replicas) │  │  Sessions,   │  │ (S3/Linode   │
│ Partitioned  │  │  Queue)      │  │  Object)     │
└──────────────┘  └──────────────┘  └──────────────┘
       │                  │
       ▼                  ▼
┌──────────────────────────────┐
│  Worker Processes (Celery)   │
│  - Report generation         │
│  - Email/Notification        │
│  - Data export/import        │
│  - Webhook delivery          │
└──────────────────────────────┘
```

**Key Decisions**:
- **Modular Monolith** (NOT microservices yet) — single deployable, but strict module boundaries via dependency injection
- **PostgreSQL primary + 2 read replicas** — read-heavy reports go to replicas
- **Table partitioning** by `(tenant_id, year)` for `journal_entries` (largest table)
- **Redis** for session, cache, rate limiting, Celery queue
- **Object storage** (S3-compatible) for files (PDFs, statements, attachments)
- **Celery workers** for async jobs (report generation, exports)

---

## 3. FOLDER STRUCTURE — CODE-READY

```
kompak-accounting-backend/
├── alembic/                      # DB migrations (versioned schema)
│   ├── versions/
│   └── env.py
│
├── app/
│   ├── main.py                   # FastAPI entry point
│   ├── config.py                 # Pydantic Settings (env vars)
│   ├── deps.py                   # Dependency injection (DB, current_user, tenant)
│   │
│   ├── core/                     # Cross-cutting concerns
│   │   ├── database.py           # Async SQLAlchemy engine + session
│   │   ├── security.py           # JWT, bcrypt, RBAC enforcement
│   │   ├── exceptions.py         # Custom exception classes
│   │   ├── middleware.py         # CORS, tenant resolver, request ID
│   │   ├── logging.py            # Structured logging (JSON)
│   │   ├── cache.py              # Redis client
│   │   ├── events.py             # Internal event bus (pub/sub)
│   │   └── ratelimit.py          # Rate limiting per tenant/user
│   │
│   ├── modules/                  # Bounded contexts (DDD)
│   │   ├── identity/             # Auth, Users, Tenants, RBAC
│   │   │   ├── api.py            # FastAPI routers (HTTP layer)
│   │   │   ├── schemas.py        # Pydantic request/response models
│   │   │   ├── models.py         # SQLAlchemy ORM
│   │   │   ├── service.py        # Business logic
│   │   │   ├── repository.py     # Data access
│   │   │   └── events.py         # Domain events (UserCreated, etc.)
│   │   │
│   │   ├── accounting/           # COA, Journal, Reports
│   │   │   ├── api.py
│   │   │   ├── schemas.py
│   │   │   ├── models.py         # COA, JournalEntry, JournalLine
│   │   │   ├── service.py        # Posting logic, balance calculation
│   │   │   ├── repository.py
│   │   │   ├── reports/
│   │   │   │   ├── balance_sheet.py
│   │   │   │   ├── income_statement.py
│   │   │   │   ├── cash_flow.py
│   │   │   │   └── trial_balance.py
│   │   │   └── events.py
│   │   │
│   │   ├── sales/                # AR — Customers, Invoices, Payments
│   │   │   ├── api.py
│   │   │   ├── schemas.py
│   │   │   ├── models.py         # Customer, Invoice, Payment
│   │   │   ├── service.py        # Invoice → Journal entry posting
│   │   │   ├── repository.py
│   │   │   └── events.py
│   │   │
│   │   ├── purchase/             # AP — Vendors, Bills, Payments
│   │   │   ├── ... (same structure)
│   │   │
│   │   ├── pos/                  # Point of Sale
│   │   │   ├── ... (same structure)
│   │   │
│   │   ├── files/                # File upload/download (S3)
│   │   │   ├── api.py
│   │   │   ├── service.py        # Presigned URLs
│   │   │   └── ...
│   │   │
│   │   └── audit/                # Audit log (cross-module)
│   │       ├── models.py         # AuditLog table
│   │       └── service.py
│   │
│   ├── workers/                  # Celery tasks
│   │   ├── celery_app.py
│   │   ├── reports.py            # Async report generation
│   │   ├── exports.py            # Excel/PDF export
│   │   ├── notifications.py      # Email/Webhook
│   │   └── sync.py               # Mobile sync background work
│   │
│   └── api_v1/                   # API versioning router
│       └── routes.py             # Mounts all module routers under /api/v1/
│
├── tests/
│   ├── unit/                     # Per-module isolated tests
│   ├── integration/              # DB + service tests
│   └── e2e/                      # Full HTTP API tests
│
├── scripts/
│   ├── seed_dev.py               # Dev data seeding
│   ├── migrate_legacy.py         # Import old JSON data
│   └── partition_create.py       # Create new partitions monthly
│
├── docker/
│   ├── Dockerfile.api            # API container
│   ├── Dockerfile.worker         # Celery worker container
│   └── docker-compose.yml
│
├── deploy/
│   ├── nginx.conf
│   ├── systemd/
│   └── terraform/                # IaC for Linode infrastructure
│
├── pyproject.toml                # Poetry / uv dependencies
├── alembic.ini
└── .env.example
```

### Module Dependency Rules (STRICT)

```
modules/identity        ← no internal deps (foundation)
modules/accounting      ← depends on identity (current_user, tenant)
modules/sales           ← depends on identity, accounting (post journals)
modules/purchase        ← depends on identity, accounting
modules/pos             ← depends on identity, sales (creates invoices)
modules/files           ← depends on identity
modules/audit           ← listens to events from ALL modules
```

**Anti-pattern to avoid**: `accounting/service.py` directly importing `sales/models.py`. Use **events** instead.

---

## 4. DATABASE DESIGN — POSTGRESQL FOR 10K+ TENANTS

### 4.1 Multi-tenancy Strategy

**Choice**: **Row-level tenancy** with `tenant_id` column (NOT schema-per-tenant).

| Strategy | Pros | Cons | Verdict at 10k tenants |
|----------|------|------|------------------------|
| Schema-per-tenant | Strong isolation, easy backup per tenant | 10k schemas = catalog bloat, migration nightmare, connection pool issues | ❌ Bad |
| Database-per-tenant | Strongest isolation, GDPR-friendly | 10k DBs = ops nightmare, cost prohibitive | ❌ Bad |
| **Row-level (`tenant_id` col)** | Single schema, easy migrations, scales horizontally via partitioning | Bug = data leak (mitigated by RLS + ORM filters) | ✅ **Best for SaaS** |

**Enforcement**:
1. Every multi-tenant table has `tenant_id UUID NOT NULL`
2. Composite index `(tenant_id, ...)` on every query path
3. **Postgres Row-Level Security (RLS)** enabled — defense in depth
4. ORM session middleware sets `SET app.current_tenant = ?` per request

### 4.2 Schema (Core Tables)

```sql
-- ============================================================
-- IDENTITY MODULE
-- ============================================================

CREATE TABLE tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,           -- URL: tenant-slug.kompakapps.com
    plan TEXT NOT NULL,                   -- 'free', 'pro', 'enterprise'
    status TEXT NOT NULL DEFAULT 'active',-- active, suspended, deleted
    settings JSONB NOT NULL DEFAULT '{}', -- per-tenant config
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ
);
CREATE INDEX idx_tenants_slug ON tenants(slug) WHERE deleted_at IS NULL;

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email CITEXT UNIQUE NOT NULL,         -- case-insensitive
    password_hash TEXT NOT NULL,           -- bcrypt cost=12
    full_name TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT true,
    is_super_admin BOOLEAN NOT NULL DEFAULT false,
    last_login_at TIMESTAMPTZ,
    failed_login_count INT NOT NULL DEFAULT 0,
    locked_until TIMESTAMPTZ,
    mfa_secret TEXT,                       -- TOTP secret (encrypted)
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_users_email ON users(email);

-- A user can belong to multiple tenants (e.g., accountant serving 5 companies)
CREATE TABLE tenant_users (
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id UUID NOT NULL REFERENCES roles(id),
    is_owner BOOLEAN NOT NULL DEFAULT false,
    invited_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    accepted_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, user_id)
);
CREATE INDEX idx_tenant_users_user ON tenant_users(user_id);

CREATE TABLE roles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE, -- NULL = system role
    name TEXT NOT NULL,
    description TEXT,
    is_system BOOLEAN NOT NULL DEFAULT false, -- 'admin', 'accountant', 'viewer'
    UNIQUE (tenant_id, name)
);

CREATE TABLE permissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code TEXT UNIQUE NOT NULL,            -- 'journal.create', 'invoice.approve'
    description TEXT
);

CREATE TABLE role_permissions (
    role_id UUID REFERENCES roles(id) ON DELETE CASCADE,
    permission_id UUID REFERENCES permissions(id) ON DELETE CASCADE,
    PRIMARY KEY (role_id, permission_id)
);

CREATE TABLE refresh_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL,             -- SHA-256 of token
    device_info JSONB,                     -- browser, OS, IP
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_refresh_tokens_user ON refresh_tokens(user_id) WHERE revoked_at IS NULL;
CREATE INDEX idx_refresh_tokens_hash ON refresh_tokens(token_hash);

-- ============================================================
-- ACCOUNTING MODULE
-- ============================================================

CREATE TABLE chart_of_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    code TEXT NOT NULL,                    -- '1-1110'
    name TEXT NOT NULL,                    -- 'Bank BCA'
    type TEXT NOT NULL,                    -- 'asset','liability','equity','income','expense'
    parent_id UUID REFERENCES chart_of_accounts(id),
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, code)
);
CREATE INDEX idx_coa_tenant ON chart_of_accounts(tenant_id, code);

-- ⚡ PARTITIONED TABLE: 100k transactions × 10k tenants = 1B rows
CREATE TABLE journal_entries (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    entry_number TEXT NOT NULL,            -- 'JE-2026-04-0001'
    date DATE NOT NULL,
    description TEXT,
    source_type TEXT,                       -- 'manual','invoice','bill','payment'
    source_id UUID,                         -- ID of originating doc
    posted_at TIMESTAMPTZ,
    posted_by UUID REFERENCES users(id),
    is_reversed BOOLEAN NOT NULL DEFAULT false,
    reversed_by UUID REFERENCES journal_entries(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (id, date)                  -- partition key must be in PK
) PARTITION BY RANGE (date);

-- Create yearly partitions (auto-create monthly via cron)
CREATE TABLE journal_entries_2026 PARTITION OF journal_entries
    FOR VALUES FROM ('2026-01-01') TO ('2027-01-01');
CREATE TABLE journal_entries_2027 PARTITION OF journal_entries
    FOR VALUES FROM ('2027-01-01') TO ('2028-01-01');

CREATE INDEX idx_je_tenant_date ON journal_entries(tenant_id, date DESC);
CREATE INDEX idx_je_source ON journal_entries(tenant_id, source_type, source_id);
CREATE UNIQUE INDEX idx_je_entry_number ON journal_entries(tenant_id, entry_number);

CREATE TABLE journal_lines (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    journal_entry_id UUID NOT NULL,
    journal_entry_date DATE NOT NULL,        -- denormalized for partition pruning
    account_id UUID NOT NULL REFERENCES chart_of_accounts(id),
    debit NUMERIC(18, 2) NOT NULL DEFAULT 0,
    credit NUMERIC(18, 2) NOT NULL DEFAULT 0,
    description TEXT,
    line_number INT NOT NULL,
    PRIMARY KEY (id, journal_entry_date)
) PARTITION BY RANGE (journal_entry_date);

CREATE TABLE journal_lines_2026 PARTITION OF journal_lines
    FOR VALUES FROM ('2026-01-01') TO ('2027-01-01');

CREATE INDEX idx_jl_entry ON journal_lines(tenant_id, journal_entry_id);
CREATE INDEX idx_jl_account ON journal_lines(tenant_id, account_id, journal_entry_date DESC);

-- ============================================================
-- AGGREGATION TABLES (for fast reports)
-- ============================================================

CREATE TABLE account_balances_monthly (
    tenant_id UUID NOT NULL,
    account_id UUID NOT NULL,
    period DATE NOT NULL,                   -- first day of month
    debit_total NUMERIC(18, 2) NOT NULL DEFAULT 0,
    credit_total NUMERIC(18, 2) NOT NULL DEFAULT 0,
    closing_balance NUMERIC(18, 2) NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, account_id, period)
);
-- Refreshed by Celery worker after journal posts (debounced)

-- ============================================================
-- AUDIT LOG (high-volume, partitioned)
-- ============================================================

CREATE TABLE audit_log (
    id BIGSERIAL,
    tenant_id UUID,
    user_id UUID,
    action TEXT NOT NULL,                   -- 'journal.created'
    resource_type TEXT NOT NULL,            -- 'journal_entry'
    resource_id UUID,
    old_values JSONB,
    new_values JSONB,
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);
-- Monthly partitions, retain 12 months hot, archive older
```

### 4.3 Indexing Strategy (CRITICAL)

```sql
-- Rule 1: Every multi-tenant query starts with tenant_id
-- Bad:  WHERE date > '2026-01-01'           (scans all tenants)
-- Good: WHERE tenant_id = ? AND date > '2026-01-01'

-- Rule 2: Composite indexes match query patterns
-- For "list invoices by status, ordered by date":
CREATE INDEX idx_invoices_list ON invoices(tenant_id, status, date DESC);

-- Rule 3: Partial indexes for hot queries
CREATE INDEX idx_invoices_unpaid ON invoices(tenant_id, due_date)
    WHERE status IN ('sent', 'overdue');

-- Rule 4: BRIN for huge time-series tables (cheaper than B-tree)
CREATE INDEX idx_audit_created_brin ON audit_log USING BRIN (created_at);

-- Rule 5: GIN for JSONB search
CREATE INDEX idx_tenants_settings ON tenants USING GIN (settings);
```

### 4.4 Row-Level Security (RLS) — Defense in Depth

```sql
ALTER TABLE journal_entries ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON journal_entries
    USING (tenant_id::text = current_setting('app.current_tenant', true));

-- In FastAPI middleware, before each query:
-- SET LOCAL app.current_tenant = '<uuid>';
```

If an ORM bug forgets `WHERE tenant_id = ?`, RLS blocks the query at DB level.

---

## 5. SECURITY UPGRADE — JWT + RBAC + TENANT ISOLATION

### 5.1 JWT + Refresh Token Flow

```
┌─────────┐                    ┌──────────┐                ┌─────────┐
│ Client  │                    │ FastAPI  │                │   DB    │
└────┬────┘                    └────┬─────┘                └────┬────┘
     │                              │                           │
     │ POST /auth/login             │                           │
     │ {email, password}            │                           │
     ├──────────────────────────────►                           │
     │                              │ verify bcrypt             │
     │                              ├──────────────────────────►│
     │                              │                           │
     │                              │ store refresh_token_hash  │
     │                              ├──────────────────────────►│
     │                              │                           │
     │  {access (15min), refresh}   │                           │
     │◄──────────────────────────────                           │
     │                              │                           │
     │ GET /api/v1/journals         │                           │
     │ Authorization: Bearer <jwt>  │                           │
     ├──────────────────────────────►                           │
     │                              │ verify JWT signature      │
     │                              │ extract user_id, tenant_id│
     │                              │ check permission          │
     │                              ├──────────────────────────►│
     │  {data}                      │                           │
     │◄──────────────────────────────                           │
     │                              │                           │
     │ (after 15 min, access expires)                           │
     │                              │                           │
     │ POST /auth/refresh           │                           │
     │ {refresh_token}              │                           │
     ├──────────────────────────────►                           │
     │                              │ verify hash, check revoked│
     │                              │ rotate refresh_token      │
     │  {access, new_refresh}       │                           │
     │◄──────────────────────────────                           │
```

### 5.2 Sample Code — Auth Module

```python
# app/core/security.py
from datetime import datetime, timedelta, timezone
from passlib.context import CryptContext
from jose import jwt, JWTError
from app.config import settings

pwd_ctx = CryptContext(schemes=["bcrypt"], bcrypt__rounds=12)

def hash_password(plain: str) -> str:
    return pwd_ctx.hash(plain)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_ctx.verify(plain, hashed)

def create_access_token(user_id: str, tenant_id: str, role: str, perms: list[str]) -> str:
    payload = {
        "sub": str(user_id),
        "tid": str(tenant_id),
        "role": role,
        "perms": perms,
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "exp": int((datetime.now(timezone.utc) + timedelta(minutes=15)).timestamp()),
        "type": "access",
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")

def create_refresh_token(user_id: str) -> tuple[str, str]:
    """Returns (raw_token, sha256_hash). Store hash in DB."""
    import secrets, hashlib
    raw = secrets.token_urlsafe(48)
    hashed = hashlib.sha256(raw.encode()).hexdigest()
    return raw, hashed

def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
```

```python
# app/deps.py
from fastapi import Depends, HTTPException, status, Request
from app.core.security import decode_token

async def get_current_user(request: Request) -> dict:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    try:
        payload = decode_token(auth[7:])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Wrong token type")
        return payload
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

async def get_tenant_id(user: dict = Depends(get_current_user)) -> str:
    return user["tid"]

def require_permission(perm: str):
    async def checker(user: dict = Depends(get_current_user)):
        if perm not in user.get("perms", []) and not user.get("is_super_admin"):
            raise HTTPException(status_code=403, detail=f"Missing permission: {perm}")
        return user
    return checker
```

```python
# app/modules/accounting/api.py
from fastapi import APIRouter, Depends
from app.deps import get_tenant_id, require_permission
from app.modules.accounting.service import JournalService

router = APIRouter(prefix="/journals", tags=["accounting"])

@router.post("", dependencies=[Depends(require_permission("journal.create"))])
async def create_journal(
    payload: JournalCreate,
    tenant_id: str = Depends(get_tenant_id),
    svc: JournalService = Depends(),
):
    return await svc.create(tenant_id, payload)

@router.get("")
async def list_journals(
    page: int = 1,
    size: int = 50,
    tenant_id: str = Depends(get_tenant_id),
    svc: JournalService = Depends(),
):
    return await svc.list(tenant_id, page, size)
```

### 5.3 Rate Limiting (per tenant + per user)

```python
# app/core/ratelimit.py
from app.core.cache import redis
from fastapi import HTTPException

async def check_rate_limit(key: str, limit: int, window_sec: int):
    """Sliding window via Redis."""
    bucket = f"rl:{key}:{int(time.time() // window_sec)}"
    count = await redis.incr(bucket)
    if count == 1:
        await redis.expire(bucket, window_sec)
    if count > limit:
        raise HTTPException(status_code=429, detail="Too many requests")

# Tiers per plan:
# - free:       60 req/min per user
# - pro:        600 req/min per user
# - enterprise: 6000 req/min per user
```

---

## 6. PERFORMANCE & SCALING

### 6.1 Caching Strategy

| Data Type | Where | TTL | Invalidation |
|-----------|-------|-----|--------------|
| User permissions | Redis | 5 min | On role change event |
| Tenant config | Redis | 15 min | On settings update |
| COA list | Redis (per tenant) | 1 hour | On COA mutation |
| Reports (Balance Sheet) | Redis | 5 min | On journal post |
| Static lookups (currencies) | App memory | App lifetime | Restart |
| User session | Redis | 30 min sliding | Logout |

### 6.2 Background Jobs (Celery)

```python
# app/workers/reports.py
from app.workers.celery_app import celery

@celery.task(bind=True, max_retries=3)
def generate_balance_sheet_pdf(self, tenant_id: str, period: str, user_id: str):
    """Generates PDF, uploads to S3, sends notification."""
    try:
        # 1. Query DB (heavy)
        # 2. Render PDF
        # 3. Upload to S3
        # 4. Insert notification row
        # 5. Send WebSocket event to user
        pass
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)
```

**Tasks moved to async**:
- Report generation (PDF/Excel >5s queries)
- Bulk imports (CSV upload)
- Email/notification sending
- Audit log writes (fire-and-forget)
- Webhook delivery
- Bank statement parsing (already 5+ sec)

### 6.3 Read Replicas

```python
# app/core/database.py
from sqlalchemy.ext.asyncio import create_async_engine

write_engine = create_async_engine(settings.DB_PRIMARY_URL, pool_size=20)
read_engine = create_async_engine(settings.DB_REPLICA_URL, pool_size=40)

async def get_read_session():
    async with AsyncSession(read_engine) as s:
        yield s

async def get_write_session():
    async with AsyncSession(write_engine) as s:
        yield s
```

**Routing rules**:
- Reports / List queries → read replica
- Write operations → primary
- After write, force read from primary for 5 sec (read-your-writes)

### 6.4 Event-Driven (Lightweight)

```python
# app/core/events.py — internal pub/sub for cross-module communication
from typing import Callable
import asyncio

_subscribers: dict[str, list[Callable]] = {}

def subscribe(event_type: str):
    def decorator(fn: Callable):
        _subscribers.setdefault(event_type, []).append(fn)
        return fn
    return decorator

async def publish(event_type: str, payload: dict):
    handlers = _subscribers.get(event_type, [])
    # Run async handlers concurrently, don't block caller
    asyncio.create_task(_run_handlers(handlers, payload))

async def _run_handlers(handlers, payload):
    await asyncio.gather(*[h(payload) for h in handlers], return_exceptions=True)
```

```python
# app/modules/sales/service.py — when invoice posted, publish event
from app.core.events import publish

async def post_invoice(self, invoice_id):
    invoice = await self.repo.get(invoice_id)
    invoice.status = "posted"
    await self.repo.save(invoice)
    await publish("invoice.posted", {
        "tenant_id": invoice.tenant_id,
        "invoice_id": invoice.id,
        "amount": invoice.total,
    })

# app/modules/accounting/handlers.py — listens to invoice events
from app.core.events import subscribe

@subscribe("invoice.posted")
async def create_journal_for_invoice(payload):
    # Auto-create journal entry: Dr A/R, Cr Revenue
    ...

@subscribe("invoice.posted")
async def update_audit_log(payload):
    ...
```

For **inter-process** events (between API and workers), use Redis Pub/Sub or Postgres LISTEN/NOTIFY.

---

## 7. OFFLINE SYNC DESIGN (for future mobile app)

### 7.1 Sync Strategy: **Operation-Based Sync** (vs State-Based)

State-based (full table sync) doesn't scale. Use **change feeds**.

### 7.2 Schema Additions

```sql
-- Every syncable table gets:
ALTER TABLE journal_entries ADD COLUMN updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
ALTER TABLE journal_entries ADD COLUMN deleted_at TIMESTAMPTZ;
ALTER TABLE journal_entries ADD COLUMN client_id TEXT;          -- mobile-generated UUID for idempotency
ALTER TABLE journal_entries ADD COLUMN version INT NOT NULL DEFAULT 1;

CREATE INDEX idx_je_sync ON journal_entries(tenant_id, updated_at DESC);

-- Sync cursors per device
CREATE TABLE sync_cursors (
    user_id UUID NOT NULL,
    device_id TEXT NOT NULL,
    table_name TEXT NOT NULL,
    last_synced_at TIMESTAMPTZ NOT NULL DEFAULT '1970-01-01',
    PRIMARY KEY (user_id, device_id, table_name)
);
```

### 7.3 Sync API

```
POST /api/v1/sync/pull
Body: { since: "2026-04-25T10:00:00Z", tables: ["journals","coa"] }
Response: {
  changes: { journals: [...], coa: [...] },
  cursor: "2026-04-25T11:30:42Z"
}

POST /api/v1/sync/push
Body: {
  operations: [
    { client_id, op: "create"|"update"|"delete", table, data, base_version }
  ]
}
Response: {
  results: [{ client_id, status: "ok"|"conflict", server_id, server_version }]
}
```

### 7.4 Conflict Resolution

| Conflict Type | Strategy |
|---------------|----------|
| Concurrent updates same row | **Last-write-wins** (default) OR field-level merge for non-overlapping fields |
| Client deletes, server modifies | **Server wins** (resurrect with conflict flag for user review) |
| Client creates duplicate (network retry) | **Idempotency via `client_id`** — if exists, return existing |
| Schema changed after offline | **Soft fail** — mark as needs-review, surface to user |

For accounting: **NEVER allow offline posting of journals**. Mobile can draft, but `posted_at` only set when online + server validates.

---

## 8. REPORTING SYSTEM

### 8.1 Three-Tier Strategy

```
┌────────────────────────────────────────────────────────┐
│  Tier 1: Live OLTP queries (small data, <1k rows)      │
│  - Use case: COA list, recent journals                 │
│  - Source: Primary DB                                  │
│  - Latency: <100ms                                     │
└────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────┐
│  Tier 2: Aggregation tables (medium reports)           │
│  - Use case: Balance Sheet, Income Statement           │
│  - Source: account_balances_monthly (pre-aggregated)   │
│  - Refresh: Celery task on journal post (debounced 30s)│
│  - Latency: <500ms                                     │
└────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────┐
│  Tier 3: Async report generation (heavy reports)       │
│  - Use case: Year-end report, custom date range, PDF   │
│  - Flow: Queue → Worker → S3 → Notify user             │
│  - Latency: 5-60s, user gets email/push when ready     │
└────────────────────────────────────────────────────────┘
```

### 8.2 Materialized Views for Common Reports

```sql
CREATE MATERIALIZED VIEW mv_trial_balance AS
SELECT
    jl.tenant_id,
    coa.id AS account_id,
    coa.code,
    coa.name,
    coa.type,
    SUM(jl.debit) AS total_debit,
    SUM(jl.credit) AS total_credit,
    SUM(jl.debit - jl.credit) AS balance,
    DATE_TRUNC('month', je.date) AS period
FROM journal_lines jl
JOIN journal_entries je ON je.id = jl.journal_entry_id
JOIN chart_of_accounts coa ON coa.id = jl.account_id
WHERE je.posted_at IS NOT NULL
GROUP BY jl.tenant_id, coa.id, coa.code, coa.name, coa.type, DATE_TRUNC('month', je.date);

CREATE UNIQUE INDEX idx_mv_tb ON mv_trial_balance(tenant_id, account_id, period);

-- Refresh on schedule (every 5 min) or on-demand
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_trial_balance;
```

### 8.3 Report Generation Flow (Async)

```python
@router.post("/reports/balance-sheet")
async def request_report(
    period: str,
    tenant_id: str = Depends(get_tenant_id),
    user_id: str = Depends(get_user_id),
):
    job_id = str(uuid4())
    generate_balance_sheet_pdf.delay(tenant_id, period, user_id, job_id)
    return {"job_id": job_id, "status": "queued"}

@router.get("/reports/{job_id}")
async def get_report_status(job_id: str):
    result = AsyncResult(job_id)
    return {
        "status": result.status,
        "download_url": result.result if result.successful() else None,
    }
```

---

## 9. SCALING ROADMAP — WHEN TO SPLIT

### Phase 1 (0–500 tenants): Modular Monolith
- Single FastAPI app, 2-3 instances behind LB
- Single PostgreSQL primary + 1 replica
- Single Redis instance
- 1 Celery worker pool

### Phase 2 (500–2,000 tenants): Optimize Monolith
- 5-10 FastAPI instances (horizontal scale)
- 2 read replicas
- Celery: separate queues (reports, sync, notifications)
- Add CDN for static assets
- **Time to address**: Month 6-9 of production

### Phase 3 (2,000–10,000 tenants): Selective Splitting
**Split this module first** based on traffic pattern:

| Module | Why split | When |
|--------|-----------|------|
| **Reports / Analytics** | CPU-heavy, slow queries impact OLTP | First — ~3,000 tenants |
| **POS** | Real-time, high TPS, different SLA | Second — ~5,000 tenants |
| **File/Document service** | I/O bound, scales differently | Third — ~7,000 tenants |
| **Notifications** | Event-driven, different deploy cadence | Fourth — ~7,000 tenants |
| **Accounting Core** | Keep monolithic — too coupled | Last resort, only if needed |

Each split = standalone FastAPI service + shared DB initially → eventually own DB.

### Phase 4 (10,000+ tenants): Full Distribution
- Database sharding by `tenant_id` (use Citus or app-level sharding)
- Per-region deployments (EU, US, APAC)
- Event bus = Kafka / Redpanda (instead of internal pub/sub)
- Service mesh (Linkerd / Istio)

---

## 10. PRIORITY ROADMAP — IMPLEMENTATION ORDER

### 🔴 P0 — MUST FIX FIRST (Weeks 1-3)
1. **Set up FastAPI backend** with PostgreSQL + Redis (Week 1)
2. **Build Identity module** — Tenants, Users, JWT, RBAC (Week 1-2)
3. **Migrate existing data** to PostgreSQL with `tenant_id` (Week 2)
4. **Server-side enforce all permissions** (Week 2)
5. **Frontend**: switch DataStore.js to FastAPI endpoints with JWT (Week 3)
6. **Pagination on all list endpoints** (Week 3)
7. **Deploy to staging** with managed PostgreSQL (Week 3)

### 🟡 P1 — STABILIZE (Weeks 4-6)
8. **Accounting module** with proper journal entry validation (debit=credit)
9. **Audit log** (every mutation logged)
10. **Rate limiting** + brute-force lockout
11. **Aggregation tables** + Celery worker for refresh
12. **Backup automation** (pg_dump → S3 daily, hourly WAL archiving)
13. **Sentry** error tracking + structured logging

### 🟢 P2 — SCALE (Weeks 7-12)
14. **Sales/Purchase modules** with auto journal posting via events
15. **Read replicas** for reports
16. **Materialized views** for trial balance, balance sheet
17. **Async report generation** (Celery + S3)
18. **Multi-region object storage** for files
19. **Mobile sync API** design + implementation
20. **Penetration testing** + security audit

### 🔵 P3 — OPTIMIZE (Months 4-6)
21. **Database partitioning** for journal_entries / journal_lines
22. **Postgres RLS** enforcement
23. **API documentation** (OpenAPI + Stoplight/Scalar)
24. **Webhook delivery** system
25. **Admin dashboard** for super-admin tenant management
26. **Tenant data export** (GDPR right-to-portability)

### 🟣 P4 — ENTERPRISE FEATURES (Months 6-12)
27. **SSO / SAML** integration
28. **Advanced RBAC** — custom roles per tenant, field-level permissions
29. **API rate limit tiers** by plan
30. **SLA monitoring** + status page (statuspage.io)
31. **SOC 2 Type II** prep (controls, audit trail, access reviews)
32. **Multi-currency** + per-tenant locale

---

## 11. INFRASTRUCTURE — LINODE-BASED (Phase 1-2)

```
Domain: kompakapps.com

  ┌─────────────────────────────┐
  │  Cloudflare (WAF + CDN)     │
  └──────────────┬──────────────┘
                 ▼
  ┌─────────────────────────────┐
  │  Linode NodeBalancer ($10)  │
  └──────────────┬──────────────┘
                 ▼
       ┌─────────┴─────────┐
       ▼                   ▼
  ┌─────────┐         ┌─────────┐
  │ App #1  │         │ App #2  │   Linode 4GB Shared ($24 each)
  │ FastAPI │         │ FastAPI │
  └────┬────┘         └────┬────┘
       │                   │
       └─────────┬─────────┘
                 │
       ┌─────────┴─────────┐
       ▼                   ▼
  ┌─────────────┐     ┌─────────────┐
  │ PostgreSQL  │     │ Redis       │   Linode Managed DB ($60/mo)
  │ Managed     │     │ Managed     │
  │ 8GB / 2vCPU │     │ 1GB         │
  └─────────────┘     └─────────────┘
       │
       ▼
  ┌─────────────────────┐
  │ Linode Object Store │   $5/mo + bandwidth
  │ (S3-compatible)     │
  └─────────────────────┘

  ┌─────────────┐
  │ Worker      │   Linode 2GB ($12)
  │ Celery x2   │
  └─────────────┘

Estimated monthly cost (Phase 1):
  - 2 app servers:     $48
  - Worker:            $12
  - Managed PG (HA):   $60
  - Managed Redis:     $24
  - NodeBalancer:      $10
  - Object Storage:    $10
  - Backup storage:    $10
  --------------------------
  TOTAL:               ~$174/month
```

Phase 2 (1k+ tenants): scale to ~$500-800/month.
Phase 3 (5k+ tenants): ~$2,000-3,500/month.

---

## 12. NEXT STEPS

**Immediate**:
1. Decide: FastAPI vs Django (recommend FastAPI for performance + async)
2. Set up Linode Managed PostgreSQL + Redis
3. Bootstrap project skeleton (folder structure above)
4. Build Identity module first (Week 1 deliverable: working `POST /auth/login`)

**This Week**:
- I can scaffold the entire backend structure
- Migrate existing JSON data to PostgreSQL schema
- Build Identity + Auth module end-to-end
- Set up staging environment on Linode

**Decision Points Needed**:
- ORM: SQLAlchemy 2.0 (async) vs Tortoise ORM vs SQLModel?
- API style: REST only or REST + GraphQL?
- Frontend rewrite later? (Current vanilla JS will hit limits at scale)
- Tenant onboarding flow: self-service signup or sales-led?

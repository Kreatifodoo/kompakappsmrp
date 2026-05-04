/**
 * API.JS — Kompak Backend API Client
 * Wrapper fetch ke FastAPI backend (/api/v1) dengan JWT auto-refresh.
 */

const API_BASE = '/api/v1';
const TOKEN_KEY = 'kompak_access_token';
const REFRESH_KEY = 'kompak_refresh_token';
const TOKEN_EXPIRY_KEY = 'kompak_token_expiry';

// ─── Token storage ────────────────────────────────────────────
const ApiTokens = {
  get access() { return sessionStorage.getItem(TOKEN_KEY); },
  get refresh() { return localStorage.getItem(REFRESH_KEY); },
  get expiry()  { return parseInt(sessionStorage.getItem(TOKEN_EXPIRY_KEY) || '0', 10); },

  save(tokenPair) {
    sessionStorage.setItem(TOKEN_KEY, tokenPair.access_token);
    localStorage.setItem(REFRESH_KEY, tokenPair.refresh_token);
    // expires_in is in seconds; store absolute epoch ms
    sessionStorage.setItem(TOKEN_EXPIRY_KEY, String(Date.now() + tokenPair.expires_in * 1000));
  },

  clear() {
    sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(TOKEN_EXPIRY_KEY);
    localStorage.removeItem(REFRESH_KEY);
  },

  isExpired() {
    if (!this.access) return true;
    return Date.now() >= this.expiry - 30_000; // 30s buffer
  }
};

// ─── Refresh lock (prevent concurrent refresh calls) ──────────
let _refreshPromise = null;

async function _refreshTokens() {
  if (_refreshPromise) return _refreshPromise;
  _refreshPromise = (async () => {
    const rt = ApiTokens.refresh;
    if (!rt) throw new Error('No refresh token');
    const res = await fetch(`${API_BASE}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: rt }),
    });
    if (!res.ok) {
      ApiTokens.clear();
      throw new Error('Refresh failed');
    }
    ApiTokens.save(await res.json());
  })();
  try {
    await _refreshPromise;
  } finally {
    _refreshPromise = null;
  }
}

// ─── Core request ─────────────────────────────────────────────
async function apiRequest(method, path, body, opts = {}) {
  if (ApiTokens.access && ApiTokens.isExpired()) {
    try { await _refreshTokens(); } catch { /* will get 401 below */ }
  }

  const headers = { 'Content-Type': 'application/json', ...opts.headers };
  if (ApiTokens.access) headers['Authorization'] = `Bearer ${ApiTokens.access}`;

  const fetchOpts = { method, headers };
  if (body !== undefined) fetchOpts.body = JSON.stringify(body);

  let res = await fetch(`${API_BASE}${path}`, fetchOpts);

  // One auto-retry after token refresh on 401
  if (res.status === 401 && ApiTokens.refresh) {
    try {
      await _refreshTokens();
      headers['Authorization'] = `Bearer ${ApiTokens.access}`;
      res = await fetch(`${API_BASE}${path}`, { ...fetchOpts, headers });
    } catch {
      ApiTokens.clear();
      if (typeof showLoginScreen === 'function') showLoginScreen();
      throw new Error('Session expired. Please login again.');
    }
  }

  if (!res.ok) {
    let msg = `${method} ${path} → ${res.status}`;
    try {
      const err = await res.json();
      msg = err.detail || err.message || msg;
    } catch { /* ignore */ }
    throw new Error(msg);
  }

  // 204 No Content
  if (res.status === 204) return null;
  return res.json();
}

// ─── Convenience helpers ──────────────────────────────────────
const Api = {
  get:    (path, opts)       => apiRequest('GET',    path, undefined, opts),
  post:   (path, body, opts) => apiRequest('POST',   path, body, opts),
  put:    (path, body, opts) => apiRequest('PUT',    path, body, opts),
  patch:  (path, body, opts) => apiRequest('PATCH',  path, body, opts),
  delete: (path, opts)       => apiRequest('DELETE', path, undefined, opts),

  // ── Auth ──────────────────────────────────────────────────
  async login(email, password, tenantSlug) {
    const data = await apiRequest('POST', '/auth/login', {
      email, password, ...(tenantSlug ? { tenant_slug: tenantSlug } : {})
    });
    ApiTokens.save(data);
    return data;
  },

  async me() {
    return Api.get('/auth/me');
  },

  logout() {
    ApiTokens.clear();
  },

  isLoggedIn() {
    return !!ApiTokens.access && !ApiTokens.isExpired();
  },

  // ── Chart of Accounts ─────────────────────────────────────
  accounts: {
    list:   ()       => Api.get('/accounts'),
    get:    (id)     => Api.get(`/accounts/${id}`),
    create: (body)   => Api.post('/accounts', body),
    update: (id, b)  => Api.put(`/accounts/${id}`, b),
    delete: (id)     => Api.delete(`/accounts/${id}`),
  },

  // ── Journal Entries ───────────────────────────────────────
  journals: {
    list:   (params) => Api.get('/journals' + _qs(params)),
    get:    (id)     => Api.get(`/journals/${id}`),
    create: (body)   => Api.post('/journals', body),
    post:   (id)     => Api.post(`/journals/${id}/post`),
    void:   (id)     => Api.post(`/journals/${id}/void`),
  },

  // ── Customers ─────────────────────────────────────────────
  customers: {
    list:   (params) => Api.get('/customers' + _qs(params)),
    get:    (id)     => Api.get(`/customers/${id}`),
    create: (body)   => Api.post('/customers', body),
    update: (id, b)  => Api.put(`/customers/${id}`, b),
  },

  // ── Sales Invoices ────────────────────────────────────────
  salesInvoices: {
    list:   (params) => Api.get('/sales-invoices' + _qs(params)),
    get:    (id)     => Api.get(`/sales-invoices/${id}`),
    create: (body)   => Api.post('/sales-invoices', body),
    update: (id, b)  => Api.put(`/sales-invoices/${id}`, b),
    post:   (id)     => Api.post(`/sales-invoices/${id}/post`),
    void:   (id)     => Api.post(`/sales-invoices/${id}/void`),
  },

  // ── Suppliers ─────────────────────────────────────────────
  suppliers: {
    list:   (params) => Api.get('/suppliers' + _qs(params)),
    get:    (id)     => Api.get(`/suppliers/${id}`),
    create: (body)   => Api.post('/suppliers', body),
    update: (id, b)  => Api.put(`/suppliers/${id}`, b),
  },

  // ── Purchase Invoices ─────────────────────────────────────
  purchaseInvoices: {
    list:   (params) => Api.get('/purchase-invoices' + _qs(params)),
    get:    (id)     => Api.get(`/purchase-invoices/${id}`),
    create: (body)   => Api.post('/purchase-invoices', body),
    update: (id, b)  => Api.put(`/purchase-invoices/${id}`, b),
    post:   (id)     => Api.post(`/purchase-invoices/${id}/post`),
    void:   (id)     => Api.post(`/purchase-invoices/${id}/void`),
  },

  // ── Payments ──────────────────────────────────────────────
  payments: {
    list:   (params) => Api.get('/payments' + _qs(params)),
    get:    (id)     => Api.get(`/payments/${id}`),
    create: (body)   => Api.post('/payments', body),
    void:   (id)     => Api.post(`/payments/${id}/void`),
  },

  // ── Inventory ─────────────────────────────────────────────
  items: {
    list:        (params) => Api.get('/items' + _qs(params)),
    get:         (id)     => Api.get(`/items/${id}`),
    create:      (body)   => Api.post('/items', body),
    update:      (id, b)  => Api.patch(`/items/${id}`, b),
    stockCard:   (id, p)  => Api.get(`/items/${id}/stock-card` + _qs(p)),
    costLayers:  (id, p)  => Api.get(`/items/${id}/cost-layers` + _qs(p)),
  },
  warehouses: {
    list:   ()       => Api.get('/warehouses'),
    get:    (id)     => Api.get(`/warehouses/${id}`),
    create: (body)   => Api.post('/warehouses', body),
    update: (id, b)  => Api.patch(`/warehouses/${id}`, b),
  },
  stockMovements: {
    list:   (params) => Api.get('/stock-movements' + _qs(params)),
    create: (body)   => Api.post('/stock-movements', body),
  },
  stockBalances: {
    list:   (params) => Api.get('/stock-balances' + _qs(params)),
  },
  stockTransfers: {
    list:   (params) => Api.get('/stock-transfers' + _qs(params)),
    get:    (id)     => Api.get(`/stock-transfers/${id}`),
    create: (body)   => Api.post('/stock-transfers', body),
    void:   (id, b)  => Api.post(`/stock-transfers/${id}/void`, b),
  },
  costingMethod: {
    get:    ()       => Api.get('/costing-method'),
    set:    (body)   => Api.put('/costing-method', body),
  },
  inventoryReports: {
    stockOnHand:   (params) => Api.get('/reports/stock-on-hand' + _qs(params)),
    stockValuation:(params) => Api.get('/reports/stock-valuation' + _qs(params)),
    reorder:       (params) => Api.get('/reports/reorder' + _qs(params)),
    slowMoving:    (params) => Api.get('/reports/slow-moving' + _qs(params)),
  },

  // ── POS ───────────────────────────────────────────────────
  posSessions: {
    list:   (params) => Api.get('/pos/sessions' + _qs(params)),
    get:    (id)     => Api.get(`/pos/sessions/${id}`),
    open:   (body)   => Api.post('/pos/sessions', body),
    close:  (id, b)  => Api.post(`/pos/sessions/${id}/close`, b),
  },
  posOrders: {
    list:   (params) => Api.get('/pos/orders' + _qs(params)),
    get:    (id)     => Api.get(`/pos/orders/${id}`),
    create: (body)   => Api.post('/pos/orders', body),
    void:   (id)     => Api.post(`/pos/orders/${id}/void`),
  },

  // ── Reports ───────────────────────────────────────────────
  reports: {
    trialBalance:    (p) => Api.get('/reports/trial-balance' + _qs(p)),
    profitLoss:      (p) => Api.get('/reports/profit-loss' + _qs(p)),
    balanceSheet:    (p) => Api.get('/reports/balance-sheet' + _qs(p)),
    agedReceivables: (p) => Api.get('/reports/aged-receivables' + _qs(p)),
    agedPayables:    (p) => Api.get('/reports/aged-payables' + _qs(p)),
    cashFlow:        (p) => Api.get('/reports/cash-flow' + _qs(p)),
    ppn:             (p) => Api.get('/reports/ppn' + _qs(p)),
    // Async job endpoints
    submitAsync:     (type, p) => Api.post(`/reports/${type}/async`, p),
    jobStatus:       (id) => Api.get(`/reports/jobs/${id}/status`),
    jobResult:       (id) => Api.get(`/reports/jobs/${id}/result`),
    downloadUrl:     (id, fmt) => `${API_BASE}/reports/jobs/${id}/download?format=${fmt}&token=${ApiTokens.access}`,
  },

  // ── Periods ───────────────────────────────────────────────
  periods: {
    status: () => Api.get('/periods/status'),
    close:  (b) => Api.post('/periods/close', b),
    reopen: (b) => Api.post('/periods/reopen', b),
  },

  // ── Audit ─────────────────────────────────────────────────
  audit: {
    list: (params) => Api.get('/audit/logs' + _qs(params)),
    get:  (id)     => Api.get(`/audit/logs/${id}/history`),
  },
};

// ─── Query string helper ──────────────────────────────────────
function _qs(params) {
  if (!params) return '';
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') q.set(k, v);
  }
  const s = q.toString();
  return s ? `?${s}` : '';
}

// ─── Backend availability check ───────────────────────────────
let _backendAvailable = null;

async function checkBackendAvailable() {
  if (_backendAvailable !== null) return _backendAvailable;
  try {
    const res = await fetch('/health', { signal: AbortSignal.timeout(3000) });
    _backendAvailable = res.ok;
  } catch {
    _backendAvailable = false;
  }
  return _backendAvailable;
}

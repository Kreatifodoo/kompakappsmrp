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
    update: (id, b)  => Api.patch(`/accounts/${id}`, b),
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
    update: (id, b)  => Api.patch(`/customers/${id}`, b),
  },

  // ── Sales Invoices ────────────────────────────────────────
  salesInvoices: {
    list:   (params) => Api.get('/sales-invoices' + _qs(params)),
    get:    (id)     => Api.get(`/sales-invoices/${id}`),
    create: (body)   => Api.post('/sales-invoices', body),
    update: (id, b)  => Api.patch(`/sales-invoices/${id}`, b),
    post:   (id)     => Api.post(`/sales-invoices/${id}/post`),
    void:   (id, b)  => Api.post(`/sales-invoices/${id}/void`, b || {reason: 'Voided from UI'}),
  },

  // ── Suppliers ─────────────────────────────────────────────
  suppliers: {
    list:   (params) => Api.get('/suppliers' + _qs(params)),
    get:    (id)     => Api.get(`/suppliers/${id}`),
    create: (body)   => Api.post('/suppliers', body),
    update: (id, b)  => Api.patch(`/suppliers/${id}`, b),
  },

  // ── Purchase Invoices ─────────────────────────────────────
  purchaseInvoices: {
    list:   (params) => Api.get('/purchase-invoices' + _qs(params)),
    get:    (id)     => Api.get(`/purchase-invoices/${id}`),
    create: (body)   => Api.post('/purchase-invoices', body),
    update: (id, b)  => Api.patch(`/purchase-invoices/${id}`, b),
    post:   (id)     => Api.post(`/purchase-invoices/${id}/post`),
    void:   (id, b)  => Api.post(`/purchase-invoices/${id}/void`, b || {reason: 'Voided from UI'}),
  },

  // ── Payments ──────────────────────────────────────────────
  payments: {
    list:   (params) => Api.get('/payments' + _qs(params)),
    get:    (id)     => Api.get(`/payments/${id}`),
    create: (body, opts) => Api.post('/payments' + _qs(opts), body),  // opts.post_now=true|false
    void:   (id, b)  => Api.post(`/payments/${id}/void`, b || {reason: 'Voided from UI'}),
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
  // Lot / Batch
  stockLots: {
    list:         (params) => Api.get('/stock-lots' + _qs(params)),
    get:          (id)     => Api.get(`/stock-lots/${id}`),
    traceability: (id)     => Api.get(`/stock-lots/${id}/traceability`),
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
  customInvOps: {
    list:   (params) => Api.get('/custom-inventory-operations' + _qs(params)),
    create: (body)   => Api.post('/custom-inventory-operations', body),
    update: (id, b)  => Api.patch(`/custom-inventory-operations/${id}`, b),
    delete: (id)     => Api.delete(`/custom-inventory-operations/${id}`),
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
    customerStatement: (id, p) => Api.get(`/reports/customer-statement/${id}` + _qs(p)),
    supplierStatement: (id, p) => Api.get(`/reports/supplier-statement/${id}` + _qs(p)),
    bankReconciliation: (body) => Api.post('/reports/bank-reconciliation', body),
    // Async job endpoints
    submitAsync:     (type, p) => Api.post(`/reports/${type}/async`, p),
    jobStatus:       (id) => Api.get(`/reports/jobs/${id}/status`),
    jobResult:       (id) => Api.get(`/reports/jobs/${id}/result`),
    downloadUrl:     (id, fmt) => `${API_BASE}/reports/jobs/${id}/download?format=${fmt}&token=${ApiTokens.access}`,
  },

  // ── Account Mappings (well-known keys: ar, ap, sales_revenue, …) ─
  accountMappings: {
    list:   () => Api.get('/account-mappings'),
    set:    (body) => Api.put('/account-mappings', body),  // {key, account_id}
    delete: (key) => Api.delete(`/account-mappings/${encodeURIComponent(key)}`),
  },
  seedStarterCOA: (overwrite) => Api.post(`/accounts/seed-starter-coa${overwrite?'?overwrite_mappings=true':''}`),

  // ── Periods ───────────────────────────────────────────────
  periods: {
    status: () => Api.get('/periods/status'),
    close:  (b) => Api.post('/periods/close', b),
    reopen: (b) => Api.post('/periods/reopen', b),
    events: (params) => Api.get('/periods/events' + _qs(params)),
  },

  // ── Audit ─────────────────────────────────────────────────
  audit: {
    list: (params) => Api.get('/audit/logs' + _qs(params)),
    history: (rowId) => Api.get(`/audit/logs/${rowId}/history`),
  },

  // ── Users (tenant-scoped) ─────────────────────────────────
  users: {
    list:      () => Api.get('/users'),
    invite:    (body) => Api.post('/users', body),
    update:    (id, body) => Api.patch(`/users/${id}`, body),
    deactivate:(id) => Api.delete(`/users/${id}`),
  },

  // ── Roles & Permissions ───────────────────────────────────
  roles: {
    list:   () => Api.get('/roles'),
    get:    (id) => Api.get(`/roles/${id}`),
    create: (body) => Api.post('/roles', body),
    update: (id, body) => Api.patch(`/roles/${id}`, body),
    delete: (id) => Api.delete(`/roles/${id}`),
  },
  permissions: {
    list: () => Api.get('/permissions'),
  },

  // ── Sales Orders ──────────────────────────────────────────
  salesOrders: {
    list:    (params) => Api.get('/sales-orders' + _qs(params)),
    get:     (id)     => Api.get(`/sales-orders/${id}`),
    create:  (body, opts) => Api.post('/sales-orders' + _qs(opts), body),
    confirm: (id)     => Api.post(`/sales-orders/${id}/confirm`),
    cancel:  (id, b)  => Api.post(`/sales-orders/${id}/cancel`, b || {reason:'Cancelled from UI'}),
  },

  // ── Purchase Orders ───────────────────────────────────────
  purchaseOrders: {
    list:    (params) => Api.get('/purchase-orders' + _qs(params)),
    get:     (id)     => Api.get(`/purchase-orders/${id}`),
    create:  (body, opts) => Api.post('/purchase-orders' + _qs(opts), body),
    confirm: (id)     => Api.post(`/purchase-orders/${id}/confirm`),
    cancel:  (id, b)  => Api.post(`/purchase-orders/${id}/cancel`, b || {reason:'Cancelled from UI'}),
  },

  // ── Delivery Orders ───────────────────────────────────────
  deliveryOrders: {
    list:   (params) => Api.get('/delivery-orders' + _qs(params)),
    get:    (id)     => Api.get(`/delivery-orders/${id}`),
    create: (body, opts) => Api.post('/delivery-orders' + _qs(opts), body),
    post:   (id)     => Api.post(`/delivery-orders/${id}/post`),
    void:   (id, b)  => Api.post(`/delivery-orders/${id}/void`, b || {reason:'Voided from UI'}),
  },

  // ── Goods Receipts ────────────────────────────────────────
  goodsReceipts: {
    list:   (params) => Api.get('/goods-receipts' + _qs(params)),
    get:    (id)     => Api.get(`/goods-receipts/${id}`),
    create: (body, opts) => Api.post('/goods-receipts' + _qs(opts), body),
    post:   (id)     => Api.post(`/goods-receipts/${id}/post`),
    void:   (id, b)  => Api.post(`/goods-receipts/${id}/void`, b || {reason:'Voided from UI'}),
  },

  // ── RMAs (Return Merchandise Authorization) ───────────────
  rmas: {
    list:   (params) => Api.get('/rmas' + _qs(params)),
    get:    (id)     => Api.get(`/rmas/${id}`),
    create: (body, opts) => Api.post('/rmas' + _qs(opts), body),
    post:   (id)     => Api.post(`/rmas/${id}/post`),
    void:   (id, b)  => Api.post(`/rmas/${id}/void`, b || {reason:'Voided from UI'}),
  },

  // ── Manufacturing: BOM ────────────────────────────────────
  boms: {
    list:     (params) => Api.get('/boms' + _qs(params)),
    get:      (id)     => Api.get(`/boms/${id}`),
    create:   (body, opts) => Api.post('/boms' + _qs(opts), body),   // opts.activate=true
    update:   (id, body) => Api.patch(`/boms/${id}`, body),
    activate: (id)     => Api.post(`/boms/${id}/activate`),
    obsolete: (id)     => Api.post(`/boms/${id}/obsolete`),
    delete:   (id)     => Api.delete(`/boms/${id}`),
  },

  // ── Manufacturing: Manufacturing Orders ───────────────────
  manufacturingOrders: {
    list:     (params) => Api.get('/manufacturing-orders' + _qs(params)),
    get:      (id)     => Api.get(`/manufacturing-orders/${id}`),
    create:   (body, opts) => Api.post('/manufacturing-orders' + _qs(opts), body),
    confirm:  (id)     => Api.post(`/manufacturing-orders/${id}/confirm`),
    start:    (id)     => Api.post(`/manufacturing-orders/${id}/start`),
    issue:    (id, body) => Api.post(`/manufacturing-orders/${id}/issue`, body),
    complete: (id, body) => Api.post(`/manufacturing-orders/${id}/complete`, body),
    cancel:   (id, body) => Api.post(`/manufacturing-orders/${id}/cancel`, body || {reason:'Cancelled from UI'}),
    updateOperations: (id, body) => Api.post(`/manufacturing-orders/${id}/operations/update`, body),
  },

  // ── Manufacturing: Subcontracting / Maklon ────────────────
  subcontracts: {
    list:    (params) => Api.get('/subcontracts' + _qs(params)),
    get:     (id)     => Api.get(`/subcontracts/${id}`),
    create:  (body, opts) => Api.post('/subcontracts' + _qs(opts), body),
    issue:   (id)     => Api.post(`/subcontracts/${id}/issue`),
    receive: (id, b)  => Api.post(`/subcontracts/${id}/receive`, b),
    cancel:  (id, b)  => Api.post(`/subcontracts/${id}/cancel`, b || {reason:'Cancelled from UI'}),
  },

  // ── Manufacturing: MO Cost Analysis Report ────────────────
  mfgReports: {
    moCostAnalysis: (p) => Api.get('/reports/mfg-mo-cost-analysis' + _qs(p)),
  },

  // ── Manufacturing: Scrap (Sprint M6) ──────────────────────
  mfgScraps: {
    list:   (params) => Api.get('/mfg-scraps' + _qs(params)),
    get:    (id)     => Api.get(`/mfg-scraps/${id}`),
    create: (body, opts) => Api.post('/mfg-scraps' + _qs(opts), body),
    post:   (id)     => Api.post(`/mfg-scraps/${id}/post`),
    void:   (id, b)  => Api.post(`/mfg-scraps/${id}/void`, b || {reason:'Voided from UI'}),
  },

  // ── Manufacturing: Work Centers ───────────────────────────
  workCenters: {
    list:   (params) => Api.get('/work-centers' + _qs(params)),
    get:    (id)     => Api.get(`/work-centers/${id}`),
    create: (body)   => Api.post('/work-centers', body),
    update: (id, b)  => Api.patch(`/work-centers/${id}`, b),
  },

  // ── Password reset (forgot/reset flow) ────────────────────
  authPassword: {
    forgot: (email) => Api.post('/auth/forgot-password', {email}),
    reset:  (token, new_password) => Api.post('/auth/reset-password', {token, new_password}),
    change: (old_password, new_password) => Api.post('/auth/change-password', {old_password, new_password}),
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

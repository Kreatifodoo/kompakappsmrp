/**
 * BACKEND-SYNC.JS — Push local data to backend FastAPI as a parallel sync.
 *
 * Design rationale:
 *   The legacy modules (sales/purchase/journal/coa/pos) deeply depend on the
 *   localStorage object shapes. A full UI rewrite to use the backend directly
 *   would require touching ~5000 lines across 7 files. Instead we add a thin
 *   sync layer that mirrors local data to the backend on save events. The UI
 *   keeps reading from localStorage; the backend gets a faithful copy used
 *   for reports, multi-device sync, and the new modules (inventory, payments,
 *   notifications).
 *
 * Trigger points (call these from the relevant save handlers):
 *   - BackendSync.syncCOA()                       after coa.js saves COA
 *   - BackendSync.syncJournal(entry)              after journal.js posts an entry
 *   - BackendSync.syncCustomer(customer)          after sales.js saves a customer
 *   - BackendSync.syncSalesInvoice(invoice)       after sales.js posts an invoice
 *   - BackendSync.syncSupplier(supplier)          after purchase.js saves a vendor
 *   - BackendSync.syncPurchaseInvoice(invoice)    after purchase.js posts a bill
 *   - BackendSync.syncAll()                       full bootstrap on login
 *
 * Each function is idempotent — calling it twice with the same data is safe
 * (backend returns 409 / "already exists" which we silently swallow).
 */

const BackendSync = (() => {
  // ─── Type mapping: legacy Indonesian → backend English ─────
  const TYPE_MAP = {
    'Aset':       'asset',
    'Liabilitas': 'liability',
    'Ekuitas':    'equity',
    'Pendapatan': 'income',
    'Beban':      'expense',
  };

  const NORMAL_MAP = { 'Debit': 'debit', 'Kredit': 'credit' };

  // ─── Helpers ────────────────────────────────────────────────
  function _isLoggedIn() {
    return typeof Api !== 'undefined' && Api.isLoggedIn();
  }

  function _silent(promise, label) {
    return promise.catch(e => {
      // Conflicts (already exists) and 422 (validation) are non-fatal
      const msg = (e?.message || String(e)).toLowerCase();
      if (msg.includes('already') || msg.includes('exists') || msg.includes('duplicate') || msg.includes('conflict')) {
        return null;
      }
      console.warn(`[BackendSync] ${label} failed:`, e?.message || e);
      return null;
    });
  }

  // Sleep helper for throttling — backend has 60 req/min rate limit on free plan
  const _sleep = (ms) => new Promise(r => setTimeout(r, ms));

  // Adaptive backoff: on 429, wait the suggested time then retry once
  async function _withBackoff(fn, label) {
    try { return await fn(); }
    catch (e) {
      const msg = (e?.message || '').toLowerCase();
      if (msg.includes('429') || msg.includes('rate limit')) {
        console.warn(`[BackendSync] rate-limited on ${label}, sleeping 65s`);
        await _sleep(65000);
        return _silent(fn(), label);
      }
      throw e;
    }
  }

  // Cache backend account IDs by legacy code (e.g. '1-1100' → uuid)
  const _accountIdByCode = new Map();

  async function _refreshAccountCache() {
    if (!_isLoggedIn()) return;
    try {
      const accounts = await Api.accounts.list();
      _accountIdByCode.clear();
      for (const a of accounts) _accountIdByCode.set(a.code, a.id);
    } catch (e) {
      console.warn('[BackendSync] refreshAccountCache failed', e?.message);
    }
  }

  // ─── COA sync ───────────────────────────────────────────────
  async function syncCOA() {
    if (!_isLoggedIn()) return { skipped: true };
    if (typeof COA === 'undefined') return { skipped: true };

    const accounts = await Api.accounts.list().catch(() => []);
    const existing = new Set(accounts.map(a => a.code));

    // Filter pending creates first so we know the workload
    const todo = Object.values(COA).filter(a => a.category !== 'Header' && !existing.has(a.code));
    if (todo.length === 0) {
      await _refreshAccountCache();
      return { created: 0, total: Object.keys(COA).length, alreadySynced: true };
    }

    // Throttle to ~50 req/min to stay under 60 req/min rate limit (1100ms gap)
    let created = 0;
    for (const acct of todo) {
      const body = {
        code: acct.code,
        name: acct.name,
        type: TYPE_MAP[acct.type] || 'asset',
        normal_side: NORMAL_MAP[acct.normal] || 'debit',
      };
      const r = await _withBackoff(
        () => _silent(Api.accounts.create(body), `COA ${acct.code}`),
        `COA ${acct.code}`
      );
      if (r) created++;
      await _sleep(1200);
    }

    await _refreshAccountCache();
    return { created, total: Object.keys(COA).length };
  }

  // ─── Customer sync ──────────────────────────────────────────
  async function syncCustomer(localCust) {
    if (!_isLoggedIn() || !localCust) return null;
    const body = {
      code:    localCust.code || `CUST-${localCust.id}`.slice(0, 30),
      name:    localCust.name || 'Unnamed Customer',
      email:   localCust.email || null,
      phone:   localCust.phone || null,
      address: localCust.address || null,
      tax_id:  localCust.taxId || localCust.npwp || null,
    };
    return _silent(Api.customers.create(body), `Customer ${body.code}`);
  }

  async function syncAllCustomers() {
    if (typeof CustomerState === 'undefined') return { skipped: true };
    if (!_isLoggedIn()) return { skipped: true };
    // Check existing first to avoid 409 noise
    const existing = await Api.customers.list().catch(() => []);
    const codes = new Set(existing.map(c => c.code));
    let synced = 0;
    for (const c of CustomerState.customers) {
      const code = c.code || `CUST-${c.id}`.slice(0, 30);
      if (codes.has(code)) continue;
      if (await syncCustomer(c)) synced++;
      await _sleep(1200); // throttle
    }
    return { synced, alreadySynced: existing.length };
  }

  // ─── Supplier sync ──────────────────────────────────────────
  async function syncSupplier(localSupp) {
    if (!_isLoggedIn() || !localSupp) return null;
    const body = {
      code:    localSupp.code || `SUP-${localSupp.id}`.slice(0, 30),
      name:    localSupp.name || 'Unnamed Supplier',
      email:   localSupp.email || null,
      phone:   localSupp.phone || null,
      address: localSupp.address || null,
      tax_id:  localSupp.taxId || localSupp.npwp || null,
    };
    return _silent(Api.suppliers.create(body), `Supplier ${body.code}`);
  }

  async function syncAllSuppliers() {
    if (typeof PurchaseState === 'undefined') return { skipped: true };
    if (!_isLoggedIn()) return { skipped: true };
    const existing = await Api.suppliers.list().catch(() => []);
    const codes = new Set(existing.map(s => s.code));
    let synced = 0;
    for (const v of PurchaseState.vendors) {
      const code = v.code || `SUP-${v.id}`.slice(0, 30);
      if (codes.has(code)) continue;
      if (await syncSupplier(v)) synced++;
      await _sleep(1200);
    }
    return { synced, alreadySynced: existing.length };
  }

  // ─── Journal entry sync ─────────────────────────────────────
  // Local entry shape: { id, date, description, entries: [{accountCode, debit, credit, description}] }
  async function syncJournal(localEntry) {
    if (!_isLoggedIn() || !localEntry) return null;
    if (!localEntry.entries?.length) return null;

    if (_accountIdByCode.size === 0) await _refreshAccountCache();

    // Build journal lines, skip if any account_id can't be resolved
    const lines = [];
    for (const e of localEntry.entries) {
      const acctId = _accountIdByCode.get(e.accountCode);
      if (!acctId) {
        console.warn(`[BackendSync] Journal skipped — account ${e.accountCode} not in backend`);
        return null;
      }
      lines.push({
        account_id: acctId,
        debit:  Number(e.debit  || 0),
        credit: Number(e.credit || 0),
        description: e.description || null,
      });
    }

    const body = {
      entry_date:  localEntry.date || new Date().toISOString().slice(0, 10),
      description: localEntry.description || 'Journal entry',
      reference:   localEntry.reference || localEntry.id || null,
      lines,
    };
    return _silent(Api.journals.create(body), `Journal ${body.reference}`);
  }

  // ─── Sales invoice sync ─────────────────────────────────────
  // We only sync the header; lines need item_id mapping which the legacy
  // schema doesn't have. Backend will compute totals from lines.
  async function syncSalesInvoice(localInv, localCustomer) {
    if (!_isLoggedIn() || !localInv) return null;
    // Need a backend customer first
    let custBackend = null;
    if (localCustomer) {
      custBackend = await syncCustomer(localCustomer);
      // If create returned null (already exists), fetch from list
      if (!custBackend) {
        const list = await Api.customers.list().catch(() => []);
        custBackend = list.find(c => c.code === localCustomer.code);
      }
    }
    if (!custBackend) return null;

    const lines = (localInv.lines || []).map(l => ({
      description: l.description || 'Item',
      qty:         Number(l.qty || 1),
      unit_price:  Number(l.unitPrice || 0),
      tax_rate:    Number(l.taxRate || 0),
    }));
    if (!lines.length) return null;

    const body = {
      invoice_no:   localInv.invoiceNo || localInv.no || null,
      invoice_date: localInv.date || new Date().toISOString().slice(0, 10),
      due_date:     localInv.dueDate || null,
      customer_id:  custBackend.id,
      notes:        localInv.notes || null,
      lines,
    };
    return _silent(Api.salesInvoices.create(body), `SalesInv ${body.invoice_no}`);
  }

  // ─── Purchase invoice sync ──────────────────────────────────
  async function syncPurchaseInvoice(localBill, localVendor) {
    if (!_isLoggedIn() || !localBill) return null;
    let suppBackend = null;
    if (localVendor) {
      suppBackend = await syncSupplier(localVendor);
      if (!suppBackend) {
        const list = await Api.suppliers.list().catch(() => []);
        suppBackend = list.find(s => s.code === localVendor.code);
      }
    }
    if (!suppBackend) return null;

    const lines = (localBill.lines || []).map(l => ({
      description: l.description || 'Item',
      qty:         Number(l.qty || 1),
      unit_price:  Number(l.unitPrice || 0),
      tax_rate:    Number(l.taxRate || 0),
    }));
    if (!lines.length) return null;

    const body = {
      invoice_no:    localBill.billNo || localBill.no || null,
      invoice_date:  localBill.date || new Date().toISOString().slice(0, 10),
      due_date:      localBill.dueDate || null,
      supplier_id:   suppBackend.id,
      supplier_invoice_no: localBill.vendorInvoiceNo || null,
      notes:         localBill.notes || null,
      lines,
    };
    return _silent(Api.purchaseInvoices.create(body), `PurchInv ${body.invoice_no}`);
  }

  // ─── Bootstrap: full sync on login ─────────────────────────
  async function syncAll() {
    if (!_isLoggedIn()) return { skipped: 'not-logged-in' };
    const t0 = Date.now();
    const result = {
      coa:       await syncCOA().catch(e => ({error: e.message})),
      customers: await syncAllCustomers().catch(e => ({error: e.message})),
      suppliers: await syncAllSuppliers().catch(e => ({error: e.message})),
      ms: 0,
    };
    result.ms = Date.now() - t0;
    console.log('[BackendSync] syncAll done', result);
    return result;
  }

  return {
    syncCOA,
    syncCustomer,
    syncAllCustomers,
    syncSupplier,
    syncAllSuppliers,
    syncJournal,
    syncSalesInvoice,
    syncPurchaseInvoice,
    syncAll,
    refreshAccountCache: _refreshAccountCache,
  };
})();

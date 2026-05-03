/**
 * BACKEND-LOADER.JS — Hydrate in-memory state from backend FastAPI on login.
 *
 * In full-online mode the backend is the source of truth. localStorage is
 * disabled (saveXxxData() functions become no-ops), and on every login we
 * pull fresh data from the backend and populate CustomerState, PurchaseState,
 * PosState, AppState.manualJournals, etc.
 *
 * Backend → legacy field name mapping:
 *   Customer:  {id, code, name, email, phone, address, tax_id} → {id, code, name, contactPerson, phone, email, address, taxId}
 *   Supplier:  {id, code, name, ...}                           → {id, code, name, ...}
 *   Account:   {id, code, name, type:'asset'|...}              → COA[code] = {code, name, type:'Aset'|...}
 *   Journal:   {id, entry_no, entry_date, lines:[{account_id, debit, credit, description}]}
 *              → {id, no, date, description, entries:[{accountCode, debit, kredit, note}]}
 */

const BackendLoader = (() => {
  // English → Indonesian type mapping (reverse of BackendSync)
  const TYPE_BACK = {
    'asset':     'Aset',
    'liability': 'Liabilitas',
    'equity':    'Ekuitas',
    'income':    'Pendapatan',
    'expense':   'Beban',
  };
  const NORMAL_BACK = { 'debit': 'Debit', 'credit': 'Kredit' };

  // Cache backend account_id → legacy code (and code → uuid) for journal load/save
  const _idToCode = new Map();
  const _codeToId = new Map();

  function _isLoggedIn() {
    return typeof Api !== 'undefined' && Api.isLoggedIn();
  }

  // ─── COA: replace hardcoded entries with backend data ─────────
  async function loadCOA() {
    if (!_isLoggedIn() || typeof COA === 'undefined') return { skipped: true };
    let accounts;
    try {
      accounts = await Api.accounts.list();
    } catch (e) {
      console.warn('[BackendLoader] loadCOA failed:', e?.message);
      return { error: e?.message };
    }

    _idToCode.clear();
    _codeToId.clear();
    for (const a of accounts) {
      _idToCode.set(a.id, a.code);
      _codeToId.set(a.code, a.id);
      // Update or add COA[code]
      COA[a.code] = {
        code: a.code,
        name: a.name,
        type: TYPE_BACK[a.type] || a.type,
        category: COA[a.code]?.category || _categorize(a),
        normal: NORMAL_BACK[a.normal_side] || 'Debit',
        desc: '',
        _backendId: a.id,
      };
    }
    return { loaded: accounts.length };
  }

  function _categorize(a) {
    // Best-effort category inference for new backend-only accounts
    if (a.type === 'asset' && a.is_cash) return 'Kas & Bank';
    if (a.type === 'asset')              return 'Aset Lancar';
    if (a.type === 'liability')          return 'Utang';
    if (a.type === 'equity')             return 'Modal';
    if (a.type === 'income')             return 'Pendapatan';
    if (a.type === 'expense')            return 'Beban';
    return 'Lain-lain';
  }

  function getCodeFromId(uuid)  { return _idToCode.get(uuid); }
  function getIdFromCode(code)  { return _codeToId.get(code); }

  // ─── Customer ─────────────────────────────────────────────────
  async function loadCustomers() {
    if (!_isLoggedIn() || typeof CustomerState === 'undefined') return { skipped: true };
    try {
      const list = await Api.customers.list();
      CustomerState.customers = list.map(c => ({
        id:            c.id,
        code:          c.code,
        name:          c.name,
        contactPerson: '',
        phone:         c.phone || '',
        email:         c.email || '',
        address:       c.address || '',
        taxId:         c.tax_id || '',
        receivableCoa: '1-1200',  // legacy default; user can override
        isActive:      c.is_active,
      }));
      return { loaded: list.length };
    } catch (e) {
      console.warn('[BackendLoader] loadCustomers failed:', e?.message);
      return { error: e?.message };
    }
  }

  // ─── Supplier ─────────────────────────────────────────────────
  async function loadSuppliers() {
    if (!_isLoggedIn() || typeof PurchaseState === 'undefined') return { skipped: true };
    try {
      const list = await Api.suppliers.list();
      PurchaseState.vendors = list.map(s => ({
        id:            s.id,
        code:          s.code,
        name:          s.name,
        contactPerson: '',
        phone:         s.phone || '',
        email:         s.email || '',
        address:       s.address || '',
        taxId:         s.tax_id || '',
        payableCoa:    '2-1100',
        isActive:      s.is_active,
      }));
      return { loaded: list.length };
    } catch (e) {
      console.warn('[BackendLoader] loadSuppliers failed:', e?.message);
      return { error: e?.message };
    }
  }

  // ─── Journals (manual + posted) ───────────────────────────────
  async function loadJournals() {
    if (!_isLoggedIn() || typeof AppState === 'undefined') return { skipped: true };
    try {
      const list = await Api.journals.list();
      // Map backend journals → legacy shape
      AppState.manualJournals = list.map(j => ({
        id:          j.entry_no || j.id,
        no:          j.entry_no || j.id,
        date:        j.entry_date,
        description: j.description,
        isManual:    true,
        entries: (j.lines || []).map(l => ({
          accountCode: getCodeFromId(l.account_id) || '',
          accountName: '',
          debit:  Number(l.debit  || 0),
          kredit: Number(l.credit || 0),
          note:   l.description || '',
        })),
      }));
      // Rebuild derived state if helpers exist
      if (typeof _mergeManualJournalsInto === 'function' && typeof flattenJournalForTable === 'function' && typeof buildLedger === 'function') {
        AppState.journals = (AppState.journals || []).filter(j => !j.id?.startsWith?.('JE-MAN'));
        _mergeManualJournalsInto(AppState.journals);
        AppState.journalRows = flattenJournalForTable(AppState.journals);
        AppState.ledger      = buildLedger(AppState.journals);
      }
      return { loaded: list.length };
    } catch (e) {
      console.warn('[BackendLoader] loadJournals failed:', e?.message);
      return { error: e?.message };
    }
  }

  // ─── Sales invoices ───────────────────────────────────────────
  async function loadSalesInvoices() {
    if (!_isLoggedIn() || typeof CustomerState === 'undefined') return { skipped: true };
    try {
      const list = await Api.salesInvoices.list();
      CustomerState.invoices = list.map(inv => ({
        id:           inv.invoice_no || inv.id,
        customerId:   inv.customer_id,
        customerName: inv.customer_name || '',
        date:         inv.invoice_date,
        dueDate:      inv.due_date || '',
        ref:          inv.reference || '',
        total:        Number(inv.total || 0),
        paidAmount:   Number(inv.paid_amount || 0),
        status:       _mapInvStatus(inv.status, Number(inv.paid_amount), Number(inv.total)),
        items: (inv.lines || []).map(l => ({
          lineId:      l.id,
          productId:   '',
          productName: '',
          description: l.description,
          incomeAccount: '',
          qty:         Number(l.qty),
          unitPrice:   Number(l.unit_price),
          lineTotal:   Number(l.line_total || 0),
        })),
        confirmedAt: inv.posted_at || null,
        journalId:   inv.journal_entry_id || null,
        payments:    [],
      }));
      return { loaded: list.length };
    } catch (e) {
      console.warn('[BackendLoader] loadSalesInvoices failed:', e?.message);
      return { error: e?.message };
    }
  }

  function _mapInvStatus(backendStatus, paid, total) {
    if (backendStatus === 'void') return 'cancelled';
    if (backendStatus === 'draft') return 'draft';
    if (paid >= total) return 'paid';
    if (paid > 0) return 'partial';
    return 'outstanding';
  }

  // ─── Purchase bills ───────────────────────────────────────────
  async function loadPurchaseBills() {
    if (!_isLoggedIn() || typeof PurchaseState === 'undefined') return { skipped: true };
    try {
      const list = await Api.purchaseInvoices.list();
      PurchaseState.bills = list.map(b => ({
        id:         b.invoice_no || b.id,
        vendorId:   b.supplier_id,
        vendorName: b.supplier_name || '',
        date:       b.invoice_date,
        dueDate:    b.due_date || '',
        vendorRef:  b.supplier_invoice_no || '',
        total:      Number(b.total || 0),
        paidAmount: Number(b.paid_amount || 0),
        status:     _mapInvStatus(b.status, Number(b.paid_amount), Number(b.total)),
        items: (b.lines || []).map(l => ({
          lineId:      l.id,
          productId:   '',
          description: l.description,
          inventoryAccount: '',
          qty:         Number(l.qty),
          unitPrice:   Number(l.unit_price),
          lineTotal:   Number(l.line_total || 0),
        })),
        confirmedAt: b.posted_at || null,
      }));
      return { loaded: list.length };
    } catch (e) {
      console.warn('[BackendLoader] loadPurchaseBills failed:', e?.message);
      return { error: e?.message };
    }
  }

  // ─── Payments (sales receipts + purchase disbursements) ───────
  async function loadPayments() {
    if (!_isLoggedIn()) return { skipped: true };
    try {
      const list = await Api.payments.list();
      const receipts      = list.filter(p => p.payment_type === 'receipt');
      const disbursements = list.filter(p => p.payment_type === 'disbursement');

      if (typeof CustomerState !== 'undefined') {
        CustomerState.payments = receipts.map(p => ({
          id:        p.payment_no || p.id,
          date:      p.payment_date,
          customerId: p.party_id,
          amount:    Number(p.amount),
          paymentCoa: '',
          allocations: (p.applications || []).map(a => ({
            invoiceId: a.sales_invoice_id || '',
            amount:    Number(a.amount),
          })),
        }));
      }
      if (typeof PurchaseState !== 'undefined') {
        PurchaseState.payments = disbursements.map(p => ({
          id:        p.payment_no || p.id,
          date:      p.payment_date,
          vendorId:  p.party_id,
          amount:    Number(p.amount),
          paymentCoa: '',
          allocations: (p.applications || []).map(a => ({
            billId:   a.purchase_invoice_id || '',
            amount:   Number(a.amount),
          })),
        }));
      }
      return { receipts: receipts.length, disbursements: disbursements.length };
    } catch (e) {
      console.warn('[BackendLoader] loadPayments failed:', e?.message);
      return { error: e?.message };
    }
  }

  // ─── Bootstrap: fetch everything on login ─────────────────────
  async function loadAll() {
    if (!_isLoggedIn()) return { skipped: 'not-logged-in' };
    const t0 = Date.now();
    // Load COA first (needed to map journal lines back to legacy codes)
    const coa = await loadCOA();
    // Then load entities in parallel
    const [customers, suppliers, sales, purchases, payments, journals] = await Promise.all([
      loadCustomers(),
      loadSuppliers(),
      loadSalesInvoices(),
      loadPurchaseBills(),
      loadPayments(),
      loadJournals(),
    ]);
    const result = { coa, customers, suppliers, sales, purchases, payments, journals, ms: Date.now() - t0 };
    console.log('[BackendLoader] loadAll done', result);
    return result;
  }

  return {
    loadCOA,
    loadCustomers,
    loadSuppliers,
    loadJournals,
    loadSalesInvoices,
    loadPurchaseBills,
    loadPayments,
    loadAll,
    getCodeFromId,
    getIdFromCode,
  };
})();

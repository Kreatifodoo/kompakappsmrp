/**
 * SALES.JS — Customer Module v2
 * Master Customer, Customer Invoice, Penerimaan, Laporan Customer Invoice
 * v2: COGS journal (Dr HPP / Cr Persediaan) + onhandQty reduction on confirm/cancel
 */

// ===== STATE =====
const CustomerState = {
  customers: [],
  invoices:  [],
  payments:  []
};
const CUSTOMER_STORAGE_KEY = 'customer_data_v1';

// ===== COUNTERS =====
let _invJeCounter = 0;
let _recJeCounter = 0;

// ===== UTILS =====
function _fmtRpSales(n) {
  return 'Rp\u00a0' + Math.round(n || 0).toLocaleString('id-ID');
}
function _todayStrSales() {
  return new Date().toISOString().slice(0, 10);
}
function _genSalesId(prefix) {
  return prefix + '_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 6);
}
function _nextInvNumber() {
  const now = new Date();
  const y   = now.getFullYear();
  const m   = String(now.getMonth() + 1).padStart(2, '0');
  const seq = String(CustomerState.invoices.length + 1).padStart(4, '0');
  return `INV-${y}${m}-${seq}`;
}
function _nextRecNumber() {
  const now = new Date();
  const y   = now.getFullYear();
  const m   = String(now.getMonth() + 1).padStart(2, '0');
  const seq = String(CustomerState.payments.length + 1).padStart(4, '0');
  return `REC-${y}${m}-${seq}`;
}
function _nextInvJeId() { return 'JE-INV-' + String(++_invJeCounter).padStart(4, '0'); }
function _nextRecJeId() { return 'JE-REC-' + String(++_recJeCounter).padStart(4, '0'); }

function _escSales(s) {
  return String(s || '')
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

// COA dropdown helpers
function _coaOptsSales(selectedCode, filter) {
  const entries = Object.values(COA).filter(a => {
    if (a.category === 'Header') return false;
    if (filter === 'piutang')  return a.type === 'Aset' && a.category === 'Piutang';
    if (filter === 'kas-bank') return a.type === 'Aset' && a.category === 'Kas & Bank';
    if (filter === 'pendapatan') return a.type === 'Pendapatan';
    return true;
  }).sort((a, b) => a.code.localeCompare(b.code));
  return '<option value="">-- Pilih Akun --</option>' +
    entries.map(a =>
      `<option value="${a.code}" ${a.code === selectedCode ? 'selected' : ''}>${a.code} — ${_escSales(a.name)}</option>`
    ).join('');
}

function _coaOptsIncomeAll(selected) {
  const entries = Object.values(COA)
    .filter(a => a.category !== 'Header')
    .sort((a, b) => a.code.localeCompare(b.code));
  return '<option value="">-- Pilih Akun --</option>' +
    entries.map(a =>
      `<option value="${a.code}" ${a.code === selected ? 'selected' : ''}>${a.code} — ${_escSales(a.name)}</option>`
    ).join('');
}

// Customer dropdown options
function _customerOptions(selectedId) {
  if (!CustomerState.customers.length)
    return '<option value="">-- Belum ada customer --</option>';
  return '<option value="">-- Pilih Customer --</option>' +
    CustomerState.customers
      .filter(c => c.isActive)
      .map(c => `<option value="${c.id}" ${c.id === selectedId ? 'selected' : ''}>${_escSales(c.name)}</option>`)
      .join('');
}

// Status badge
function _invStatusBadge(status) {
  const map = {
    draft:       '<span class="badge badge-neutral">Draft</span>',
    outstanding: '<span class="badge badge-red">Outstanding</span>',
    partial:     '<span class="badge badge-blue">Partial</span>',
    paid:        '<span class="badge badge-green">Paid</span>',
  };
  return map[status] || `<span class="badge badge-neutral">${_escSales(status)}</span>`;
}

// ===== STORAGE =====
function saveCustomerData() {
  try {
    localStorage.setItem(CUSTOMER_STORAGE_KEY, JSON.stringify({
      customers: CustomerState.customers,
      invoices:  CustomerState.invoices,
      payments:  CustomerState.payments
    }));
    if (typeof DataStore !== 'undefined') DataStore.push(CUSTOMER_STORAGE_KEY);
  } catch(e) { console.warn('[Sales] Save failed:', e); }
}

function loadCustomerData() {
  try {
    const raw = localStorage.getItem(CUSTOMER_STORAGE_KEY);
    if (raw) {
      const d = JSON.parse(raw);
      if (Array.isArray(d.customers)) CustomerState.customers = d.customers;
      if (Array.isArray(d.invoices))  CustomerState.invoices  = d.invoices;
      if (Array.isArray(d.payments))  CustomerState.payments  = d.payments;
      // Restore JE counters
      CustomerState.invoices.forEach(inv => {
        const n = parseInt((inv.journalId || '').replace('JE-INV-', '')) || 0;
        if (n > _invJeCounter) _invJeCounter = n;
      });
      CustomerState.payments.forEach(p => {
        const n = parseInt((p.journalId || '').replace('JE-REC-', '')) || 0;
        if (n > _recJeCounter) _recJeCounter = n;
      });
    }
  } catch(e) { console.warn('[Sales] Load failed:', e); }
  _restoreCustomerJournalsToState();
}

// ===== JOURNAL INTEGRATION =====
function _restoreCustomerJournalsToState() {
  if (typeof AppState === 'undefined' || !Array.isArray(AppState.journals)) return;
  AppState.journals = AppState.journals.filter(j =>
    !String(j.id || '').startsWith('JE-INV-') && !String(j.id || '').startsWith('JE-REC-')
  );
  CustomerState.invoices.forEach(inv => { if (inv.journalEntry) AppState.journals.push(inv.journalEntry); });
  CustomerState.payments.forEach(p   => { if (p.journalEntry)   AppState.journals.push(p.journalEntry); });
  _rebuildAfterCustomer();
}

function _rebuildAfterCustomer() {
  if (typeof AppState === 'undefined') return;
  if (typeof buildLedger           === 'function') AppState.ledger     = buildLedger(AppState.journals);
  if (typeof flattenJournalForTable === 'function') AppState.journalRows = flattenJournalForTable(AppState.journals);
  if (AppState.currentPage === 'journal' && typeof renderJournalTable === 'function') renderJournalTable();
}

// ===== INVOICE STATUS HELPER =====
function _updateInvoiceStatus(inv) {
  if (!inv.confirmedAt) { inv.status = 'draft'; return; }
  const paid  = inv.paidAmount || 0;
  const total = inv.total || 0;
  if (paid <= 0)          inv.status = 'outstanding';
  else if (paid >= total) inv.status = 'paid';
  else                    inv.status = 'partial';
}

// ===== JOURNAL GENERATORS =====
function generateInvoiceJournal(inv) {
  // Cr side: income per line
  const incMap = {};
  inv.items.forEach(item => {
    const ac = item.incomeAccount || '4-1100';
    incMap[ac] = (incMap[ac] || 0) + item.lineTotal;
  });
  const entries = [];

  // Dr side: Piutang Usaha (customer receivable COA) = total
  const customer = CustomerState.customers.find(c => c.id === inv.customerId);
  const arCode   = customer?.receivableCoa || '1-1200';
  const arName   = (typeof COA !== 'undefined' && COA[arCode]) ? COA[arCode].name : 'Piutang Usaha';
  entries.push({
    accountCode: arCode, accountName: arName,
    debit: inv.total, kredit: 0,
    note: `Invoice ${inv.ref || inv.id}`
  });

  // Cr side: income per account
  Object.entries(incMap).forEach(([code, amt]) => {
    entries.push({
      accountCode: code,
      accountName: (typeof COA !== 'undefined' && COA[code]) ? COA[code].name : 'Pendapatan',
      debit: 0, kredit: amt,
      note: `Penjualan ke ${inv.customerName}`
    });
  });

  // COGS: Dr HPP / Cr Persediaan (only for lines linked to products with cost accounts)
  const cogsMap   = {};
  const invAccMap = {};
  inv.items.forEach(item => {
    if (!item.productId || !item.cogsAccount || !item.inventoryAccount) return;
    const cogsAmt = Math.round((item.costPrice || 0) * (item.qty || 0));
    if (cogsAmt <= 0) return;
    cogsMap[item.cogsAccount]       = (cogsMap[item.cogsAccount]       || 0) + cogsAmt;
    invAccMap[item.inventoryAccount] = (invAccMap[item.inventoryAccount] || 0) + cogsAmt;
  });
  Object.entries(cogsMap).forEach(([code, amt]) => {
    entries.push({
      accountCode: code,
      accountName: (typeof COA !== 'undefined' && COA[code]) ? COA[code].name : 'HPP',
      debit: amt, kredit: 0,
      note: `HPP penjualan ke ${inv.customerName}`
    });
  });
  Object.entries(invAccMap).forEach(([code, amt]) => {
    entries.push({
      accountCode: code,
      accountName: (typeof COA !== 'undefined' && COA[code]) ? COA[code].name : 'Persediaan',
      debit: 0, kredit: amt,
      note: `Keluar persediaan — Invoice ${inv.id}`
    });
  });

  const jeId = _nextInvJeId();
  const je   = {
    id: jeId, txId: inv.id, date: inv.date, no: jeId,
    description: `Customer Invoice ${inv.id} — ${inv.customerName}`,
    entries
  };
  inv.journalId    = jeId;
  inv.journalEntry = je;
  if (typeof AppState !== 'undefined') AppState.journals.push(je);
  return jeId;
}

function generateReceiptJournal(payment) {
  const arName   = (typeof COA !== 'undefined' && COA[payment.receivableCoa]) ? COA[payment.receivableCoa].name : 'Piutang Usaha';
  const bankName = (typeof COA !== 'undefined' && COA[payment.paymentCoa])    ? COA[payment.paymentCoa].name    : 'Kas/Bank';
  const entries = [
    { accountCode: payment.paymentCoa,    accountName: bankName, debit: payment.amount, kredit: 0,               note: `Penerimaan dari ${payment.customerName}` },
    { accountCode: payment.receivableCoa, accountName: arName,   debit: 0,              kredit: payment.amount,  note: `Ref: ${payment.ref || payment.id}` }
  ];
  const jeId = _nextRecJeId();
  const je   = {
    id: jeId, txId: payment.id, date: payment.date, no: jeId,
    description: `Penerimaan ${payment.id} — ${payment.customerName}`,
    entries
  };
  payment.journalId    = jeId;
  payment.journalEntry = je;
  if (typeof AppState !== 'undefined') AppState.journals.push(je);
  return jeId;
}

// ============================================================
// ===== MASTER CUSTOMER =====
// ============================================================
function renderMasterCustomerPage() {
  const wrap = document.getElementById('customerTableWrap');
  if (!wrap) return;
  if (!CustomerState.customers.length) {
    wrap.innerHTML = `<div style="padding:48px;text-align:center;color:#6b7280">
      Belum ada customer. Klik <strong>"Tambah Customer"</strong> untuk mulai.</div>`;
    return;
  }
  wrap.innerHTML = `
    <table class="data-table">
      <thead><tr>
        <th>Nama Customer</th><th>Kontak Person</th><th>Telepon</th><th>Akun Piutang (Receivable)</th><th>Status</th><th style="text-align:center">Aksi</th>
      </tr></thead>
      <tbody>
      ${CustomerState.customers.map(c => {
        const coaLabel = (typeof COA !== 'undefined' && COA[c.receivableCoa])
          ? `${c.receivableCoa} — ${COA[c.receivableCoa].name}` : (c.receivableCoa || '-');
        return `<tr>
          <td><strong>${_escSales(c.name)}</strong></td>
          <td>${_escSales(c.contactPerson || '-')}</td>
          <td>${_escSales(c.phone || '-')}</td>
          <td><code style="font-size:11px">${_escSales(coaLabel)}</code></td>
          <td>${c.isActive ? '<span class="badge badge-green">Aktif</span>' : '<span class="badge badge-neutral">Nonaktif</span>'}</td>
          <td style="text-align:center">
            <button class="btn btn-sm btn-outline" onclick="showCustomerModal('${c.id}')">Edit</button>
          </td>
        </tr>`;
      }).join('')}
      </tbody>
    </table>`;
}

let _editingCustomerId = null;

function showCustomerModal(id) {
  _editingCustomerId = id || null;
  const c = id ? CustomerState.customers.find(x => x.id === id) : null;
  document.getElementById('customerModalTitle').textContent = c ? 'Edit Customer' : 'Tambah Customer';
  document.getElementById('custName').value        = c?.name          || '';
  document.getElementById('custContact').value     = c?.contactPerson || '';
  document.getElementById('custPhone').value       = c?.phone         || '';
  document.getElementById('custEmail').value       = c?.email         || '';
  document.getElementById('custAddress').value     = c?.address       || '';
  document.getElementById('custIsActive').value    = String(c?.isActive !== false);
  document.getElementById('custReceivableCoa').innerHTML = _coaOptsSales(c?.receivableCoa || '1-1200', 'piutang');
  const btnDel = document.getElementById('btnDeleteCustomer');
  if (btnDel) btnDel.style.display = c ? 'inline-flex' : 'none';
  document.getElementById('salesCustomerModal').style.display = 'flex';
  if (typeof feather !== 'undefined') feather.replace();
}

function closeCustomerModal() {
  document.getElementById('salesCustomerModal').style.display = 'none';
  _editingCustomerId = null;
}

function saveCustomerFromModal() {
  const name         = document.getElementById('custName').value.trim();
  const receivableCoa = document.getElementById('custReceivableCoa').value;
  if (!name)         { showToast('Nama customer wajib diisi', 'error'); return; }
  if (!receivableCoa){ showToast('Akun piutang wajib dipilih', 'error'); return; }
  const data = {
    name,
    contactPerson: document.getElementById('custContact').value.trim(),
    phone:         document.getElementById('custPhone').value.trim(),
    email:         document.getElementById('custEmail').value.trim(),
    address:       document.getElementById('custAddress').value.trim(),
    receivableCoa,
    isActive: document.getElementById('custIsActive').value === 'true'
  };
  if (_editingCustomerId) {
    const idx = CustomerState.customers.findIndex(c => c.id === _editingCustomerId);
    if (idx >= 0) CustomerState.customers[idx] = { ...CustomerState.customers[idx], ...data };
  } else {
    CustomerState.customers.push({ id: _genSalesId('cust'), ...data });
  }
  saveCustomerData();
  closeCustomerModal();
  renderMasterCustomerPage();
  showToast('Customer disimpan', 'success');
}

function deleteCustomerItem(id) {
  if (!id) return;
  if (CustomerState.invoices.some(inv => inv.customerId === id)) {
    showToast('Customer tidak bisa dihapus — masih ada invoice terkait', 'error');
    return;
  }
  if (!confirm('Hapus customer ini?')) return;
  CustomerState.customers = CustomerState.customers.filter(c => c.id !== id);
  saveCustomerData();
  closeCustomerModal();
  renderMasterCustomerPage();
  showToast('Customer dihapus', 'success');
}

// ============================================================
// ===== CUSTOMER INVOICE =====
// ============================================================
function renderCustomerInvoicePage() {
  const filterCustomer = document.getElementById('invFilterCustomer')?.value || '';
  const filterStatus   = document.getElementById('invFilterStatus')?.value   || '';
  const filterFrom     = document.getElementById('invFilterFrom')?.value     || '';
  const filterTo       = document.getElementById('invFilterTo')?.value       || '';

  // Populate customer filter
  const custSel = document.getElementById('invFilterCustomer');
  if (custSel) {
    const cur = custSel.value;
    custSel.innerHTML = '<option value="">Semua Customer</option>' +
      CustomerState.customers.map(c => `<option value="${c.id}" ${c.id===cur?'selected':''}>${_escSales(c.name)}</option>`).join('');
  }

  let invoices = [...CustomerState.invoices];
  if (filterCustomer) invoices = invoices.filter(i => i.customerId === filterCustomer);
  if (filterStatus)   invoices = invoices.filter(i => i.status     === filterStatus);
  if (filterFrom)     invoices = invoices.filter(i => i.date       >= filterFrom);
  if (filterTo)       invoices = invoices.filter(i => i.date       <= filterTo);
  invoices.sort((a, b) => (b.date || '').localeCompare(a.date || ''));

  // KPI cards
  const confirmed     = CustomerState.invoices.filter(i => i.status !== 'draft');
  const totOutstanding = confirmed.filter(i => i.status !== 'paid')
    .reduce((s, i) => s + ((i.total || 0) - (i.paidAmount || 0)), 0);
  const totPaid  = confirmed.filter(i => i.status === 'paid').reduce((s, i) => s + (i.total || 0), 0);
  const totDraft = CustomerState.invoices.filter(i => i.status === 'draft').length;
  const kpiEl = document.getElementById('invKpiCards');
  if (kpiEl) {
    kpiEl.innerHTML = `
      <div class="kpi-card"><div class="kpi-label">Total Piutang</div><div class="kpi-value" style="color:#f59e0b">${_fmtRpSales(totOutstanding)}</div></div>
      <div class="kpi-card"><div class="kpi-label">Total Lunas</div><div class="kpi-value" style="color:#10b981">${_fmtRpSales(totPaid)}</div></div>
      <div class="kpi-card"><div class="kpi-label">Draft</div><div class="kpi-value" style="color:#6b7280">${totDraft}</div></div>`;
  }

  const wrap = document.getElementById('invTableWrap');
  if (!wrap) return;
  if (!invoices.length) {
    wrap.innerHTML = `<div style="padding:48px;text-align:center;color:#6b7280">
      Tidak ada invoice${filterStatus||filterCustomer ? ' untuk filter ini' : '. Klik <strong>"Buat Invoice"</strong> untuk mulai'}.</div>`;
    return;
  }
  wrap.innerHTML = `
    <table class="data-table">
      <thead><tr>
        <th>Nomor</th><th>Tanggal</th><th>Customer</th><th>Ref</th>
        <th style="text-align:right">Total</th>
        <th style="text-align:right">Dibayar</th>
        <th style="text-align:right">Sisa</th>
        <th>Status</th><th style="text-align:center">Aksi</th>
      </tr></thead>
      <tbody>
      ${invoices.map(inv => {
        const sisa = (inv.total || 0) - (inv.paidAmount || 0);
        return `<tr>
          <td><code>${_escSales(inv.id)}</code></td>
          <td>${inv.date || '-'}</td>
          <td>${_escSales(inv.customerName)}</td>
          <td>${_escSales(inv.ref || '-')}</td>
          <td style="text-align:right"><strong>${_fmtRpSales(inv.total)}</strong></td>
          <td style="text-align:right">${_fmtRpSales(inv.paidAmount)}</td>
          <td style="text-align:right${sisa > 0 ? ';color:#f59e0b;font-weight:600' : ''}">${_fmtRpSales(sisa)}</td>
          <td>${_invStatusBadge(inv.status)}</td>
          <td style="text-align:center;white-space:nowrap">
            <button class="btn btn-sm btn-outline" onclick="showInvoiceModal('${inv.id}')">
              ${inv.status === 'draft' ? 'Edit' : 'Lihat'}
            </button>
            ${inv.status === 'draft' ? `<button class="btn btn-sm btn-danger" style="margin-left:4px" onclick="deleteInvoiceItem('${inv.id}')">Hapus</button>` : ''}
          </td>
        </tr>`;
      }).join('')}
      </tbody>
    </table>`;
}

// ===== INVOICE MODAL =====
let _editingInvId  = null;
let _invLines      = [];
let _invLineCtr    = 0;

function showInvoiceModal(id) {
  _editingInvId = id || null;
  const inv        = id ? CustomerState.invoices.find(i => i.id === id) : null;
  const isConfirmed = inv && inv.status !== 'draft';

  document.getElementById('salesInvoiceModalTitle').textContent =
    inv ? `Customer Invoice — ${inv.id}` : 'Buat Customer Invoice';

  document.getElementById('invCustomerSelect').innerHTML = _customerOptions(inv?.customerId || '');
  document.getElementById('invDate').value    = inv?.date    || _todayStrSales();
  document.getElementById('invDueDate').value = inv?.dueDate || '';
  document.getElementById('invRef').value     = inv?.ref     || '';

  _invLineCtr = 0;
  if (inv?.items?.length) {
    _invLines = inv.items.map(item => ({ ...item, _tmpId: ++_invLineCtr }));
  } else {
    _invLines = [];
    _addEmptyInvLine();
  }

  ['invCustomerSelect','invDate','invDueDate','invRef'].forEach(elId => {
    const el = document.getElementById(elId);
    if (el) el.disabled = isConfirmed;
  });
  document.getElementById('btnSaveInvDraft').style.display    = isConfirmed ? 'none' : 'inline-flex';
  document.getElementById('btnConfirmInv').style.display      = isConfirmed ? 'none' : 'inline-flex';
  const btnCancel = document.getElementById('btnCancelInvoice');
  if (btnCancel) btnCancel.style.display = isConfirmed ? 'inline-flex' : 'none';
  const btnAddLine = document.getElementById('btnAddInvLine');
  if (btnAddLine) btnAddLine.style.display = isConfirmed ? 'none' : 'inline-flex';

  _renderInvLinesTable(isConfirmed);
  _recomputeInvSummary();

  document.getElementById('salesInvoiceModal').style.display = 'flex';
  if (typeof feather !== 'undefined') feather.replace();
}

function closeInvoiceModal() {
  document.getElementById('salesInvoiceModal').style.display = 'none';
  _editingInvId = null;
  _invLines = [];
}

function _addEmptyInvLine() {
  _invLines.push({
    _tmpId:           ++_invLineCtr,
    lineId:           _genSalesId('invl'),
    productId:        '',
    productName:      '',
    description:      '',
    incomeAccount:    '4-1100',
    cogsAccount:      '',
    inventoryAccount: '',
    costPrice:        0,
    qty: 1, unitPrice: 0, lineTotal: 0
  });
}

function addInvoiceLineItem() {
  _addEmptyInvLine();
  _renderInvLinesTable(false);
  _recomputeInvSummary();
  if (typeof feather !== 'undefined') feather.replace();
}

function _renderInvLinesTable(readonly) {
  const tbody = document.getElementById('invLinesBody');
  if (!tbody) return;

  // Build product options from PosState
  const productOptions = (typeof PosState !== 'undefined' && Array.isArray(PosState.products))
    ? PosState.products.filter(p => p.available !== false)
        .map(p => `<option value="${p.id}">${_escSales(p.name)}</option>`).join('')
    : '';

  tbody.innerHTML = _invLines.map(line => {
    const coaLabel = line.incomeAccount
      ? `${line.incomeAccount}${(typeof COA !== 'undefined' && COA[line.incomeAccount]) ? ' — ' + COA[line.incomeAccount].name : ''}`
      : '—';
    if (readonly) {
      return `<tr>
        <td>${_escSales(line.productName || line.description || '-')}</td>
        <td>${_escSales(line.description || '-')}</td>
        <td><code style="font-size:11px">${_escSales(coaLabel)}</code></td>
        <td style="text-align:right">${line.qty}</td>
        <td style="text-align:right">${_fmtRpSales(line.unitPrice)}</td>
        <td style="text-align:right"><strong>${_fmtRpSales(line.lineTotal)}</strong></td>
        <td></td>
      </tr>`;
    }
    const prodOpts = `<option value="">-- Pilih Produk --</option>` +
      productOptions.replace(`value="${line.productId}"`, `value="${line.productId}" selected`);
    return `<tr data-invline="${line._tmpId}">
      <td>
        <select class="j-select" style="min-width:160px" onchange="onInvProductChange(${line._tmpId})">
          ${prodOpts}
        </select>
      </td>
      <td>
        <input type="text" placeholder="Keterangan..."
          style="min-width:140px;padding:4px 6px;border:1px solid #e2e8f0;border-radius:4px;width:100%"
          value="${_escSales(line.description || '')}"
          oninput="onInvLineDescChange(${line._tmpId}, this.value)" />
      </td>
      <td>
        <select class="j-select" style="min-width:160px" onchange="onInvLineAccountChange(${line._tmpId}, this.value)">
          ${_coaOptsIncomeAll(line.incomeAccount)}
        </select>
      </td>
      <td>
        <input type="number" style="width:70px;text-align:right;padding:4px 6px;border:1px solid #e2e8f0;border-radius:4px"
          value="${line.qty}" min="0.001" step="1"
          oninput="onInvQtyPriceChange(${line._tmpId},'qty',this.value)" />
      </td>
      <td>
        <input type="number" style="width:110px;text-align:right;padding:4px 6px;border:1px solid #e2e8f0;border-radius:4px"
          value="${line.unitPrice}" min="0" step="1"
          oninput="onInvQtyPriceChange(${line._tmpId},'unitPrice',this.value)" />
      </td>
      <td style="text-align:right">
        <strong id="invLineTotal_${line._tmpId}">${_fmtRpSales(line.lineTotal)}</strong>
      </td>
      <td>
        <button onclick="removeInvLine(${line._tmpId})" style="border:none;background:none;cursor:pointer;color:#ef4444;font-size:18px;padding:2px 4px" title="Hapus baris">×</button>
      </td>
    </tr>`;
  }).join('');
}

function onInvProductChange(tmpId) {
  const line = _invLines.find(l => l._tmpId === tmpId);
  if (!line) return;
  const row = document.querySelector(`[data-invline="${tmpId}"]`);
  if (!row) return;
  const productId = row.querySelector('select').value;
  if (!productId) {
    line.productId = ''; line.productName = '';
    line.incomeAccount = '4-1100';
    line.cogsAccount = ''; line.inventoryAccount = ''; line.costPrice = 0;
    line.unitPrice = 0; line.lineTotal = 0;
  } else {
    const prod = (typeof PosState !== 'undefined') ? PosState.products.find(p => p.id === productId) : null;
    line.productId    = productId;
    line.productName  = prod?.name || productId;
    line.unitPrice    = prod?.price || 0;
    line.costPrice    = prod?.costPrice || 0;
    line.lineTotal    = Math.round(line.qty * line.unitPrice);
    // Pull COGS/inventory accounts from the product's category
    const cat = (typeof getCategoryById === 'function') ? getCategoryById(prod?.categoryId) : null;
    if (cat) {
      line.incomeAccount    = cat.incomeAccount    || '4-1100';
      line.cogsAccount      = cat.cogsAccount      || '';
      line.inventoryAccount = cat.inventoryAccount || '';
    }
  }
  const acctSel = row.querySelectorAll('select')[1];
  if (acctSel) acctSel.innerHTML = _coaOptsIncomeAll(line.incomeAccount);
  const numInputs = row.querySelectorAll('input[type="number"]');
  if (numInputs[1]) numInputs[1].value = line.unitPrice;
  const totalEl = document.getElementById(`invLineTotal_${tmpId}`);
  if (totalEl) totalEl.textContent = _fmtRpSales(line.lineTotal);
  _recomputeInvSummary();
}

function onInvLineDescChange(tmpId, value) {
  const line = _invLines.find(l => l._tmpId === tmpId);
  if (line) line.description = value;
}

function onInvLineAccountChange(tmpId, value) {
  const line = _invLines.find(l => l._tmpId === tmpId);
  if (line) line.incomeAccount = value;
}

function onInvQtyPriceChange(tmpId, field, value) {
  const line = _invLines.find(l => l._tmpId === tmpId);
  if (!line) return;
  line[field]    = parseFloat(value) || 0;
  line.lineTotal = Math.round(line.qty * line.unitPrice);
  const totalEl = document.getElementById(`invLineTotal_${tmpId}`);
  if (totalEl) totalEl.textContent = _fmtRpSales(line.lineTotal);
  _recomputeInvSummary();
}

function removeInvLine(tmpId) {
  _invLines = _invLines.filter(l => l._tmpId !== tmpId);
  _renderInvLinesTable(false);
  _recomputeInvSummary();
}

function _getInvSubtotal() {
  return _invLines.reduce((s, l) => s + (l.lineTotal || 0), 0);
}

function _recomputeInvSummary() {
  const el = document.getElementById('invFeeSummary');
  if (!el) return;
  const subtotal = _getInvSubtotal();
  el.innerHTML = `<div class="bill-fee-summary-box">
    <div class="bill-fee-row bill-fee-total-row">
      <span>TOTAL</span><span>${_fmtRpSales(subtotal)}</span>
    </div>
  </div>`;
}

function _collectInvData() {
  const customerId = document.getElementById('invCustomerSelect').value;
  const date       = document.getElementById('invDate').value;
  const dueDate    = document.getElementById('invDueDate').value;
  const ref        = document.getElementById('invRef').value.trim();
  const customer   = CustomerState.customers.find(c => c.id === customerId);

  if (!customerId)       { showToast('Pilih customer terlebih dahulu', 'error'); return null; }
  if (!date)             { showToast('Tanggal wajib diisi', 'error'); return null; }
  if (!_invLines.length) { showToast('Tambahkan minimal 1 baris item', 'error'); return null; }

  const total = _getInvSubtotal();
  return { customerId, customerName: customer.name, date, dueDate, ref, total };
}

function saveInvoiceAsDraft() {
  const hdr = _collectInvData();
  if (!hdr) return;
  const items = _invLines.map(l => ({
    lineId: l.lineId || _genSalesId('invl'),
    productId: l.productId, productName: l.productName,
    description: l.description || '',
    incomeAccount: l.incomeAccount,
    cogsAccount: l.cogsAccount || '',
    inventoryAccount: l.inventoryAccount || '',
    costPrice: l.costPrice || 0,
    qty: l.qty, unitPrice: l.unitPrice, lineTotal: l.lineTotal
  }));
  if (_editingInvId) {
    const idx = CustomerState.invoices.findIndex(i => i.id === _editingInvId);
    if (idx >= 0) CustomerState.invoices[idx] = { ...CustomerState.invoices[idx], ...hdr, items };
  } else {
    const inv = {
      id: _nextInvNumber(), ...hdr, items,
      paidAmount: 0, status: 'draft', journalId: null, journalEntry: null,
      payments: [], confirmedAt: null
    };
    CustomerState.invoices.push(inv);
    _editingInvId = inv.id;
  }
  saveCustomerData();
  closeInvoiceModal();
  renderCustomerInvoicePage();
  showToast('Invoice disimpan sebagai draft', 'success');
}

function confirmInvoiceFromModal() {
  const hdr = _collectInvData();
  if (!hdr) return;
  const items = _invLines.map(l => ({
    lineId: l.lineId || _genSalesId('invl'),
    productId: l.productId, productName: l.productName,
    description: l.description || '',
    incomeAccount: l.incomeAccount,
    cogsAccount: l.cogsAccount || '',
    inventoryAccount: l.inventoryAccount || '',
    costPrice: l.costPrice || 0,
    qty: l.qty, unitPrice: l.unitPrice, lineTotal: l.lineTotal
  }));
  let inv;
  if (_editingInvId) {
    const idx = CustomerState.invoices.findIndex(i => i.id === _editingInvId);
    if (idx >= 0) { CustomerState.invoices[idx] = { ...CustomerState.invoices[idx], ...hdr, items }; inv = CustomerState.invoices[idx]; }
  } else {
    inv = {
      id: _nextInvNumber(), ...hdr, items,
      paidAmount: 0, status: 'draft', journalId: null, journalEntry: null,
      payments: [], confirmedAt: null
    };
    CustomerState.invoices.push(inv);
  }
  if (!inv) return;
  confirmInvoice(inv.id);
}

function confirmInvoice(invoiceId) {
  const inv = CustomerState.invoices.find(i => i.id === invoiceId);
  if (!inv) return;
  if (inv.status !== 'draft') { showToast('Hanya invoice berstatus Draft yang bisa dikonfirmasi', 'error'); return; }

  inv.confirmedAt = new Date().toISOString();
  inv.status      = 'outstanding';

  generateInvoiceJournal(inv);

  // Reduce product onhand qty
  if (typeof PosState !== 'undefined' && Array.isArray(PosState.products)) {
    let stockChanged = false;
    inv.items.forEach(item => {
      if (!item.productId) return;
      const prod = PosState.products.find(p => p.id === item.productId);
      if (!prod) return;
      prod.onhandQty = Math.max(0, (prod.onhandQty || 0) - (item.qty || 0));
      stockChanged = true;
    });
    if (stockChanged && typeof savePosData === 'function') savePosData();
  }

  saveCustomerData();
  _rebuildAfterCustomer();
  closeInvoiceModal();
  renderCustomerInvoicePage();
  showToast(`Invoice ${invoiceId} dikonfirmasi ✓`, 'success');
}

function cancelInvoice(invoiceId) {
  const inv = CustomerState.invoices.find(i => i.id === invoiceId);
  if (!inv || inv.status === 'draft') return;

  const relatedPayments = CustomerState.payments.filter(p =>
    p.allocations.some(a => a.invoiceId === invoiceId)
  );

  let msg = `Batalkan Invoice ${invoiceId} dan kembalikan ke Draft?`;
  if (relatedPayments.length) {
    msg += `\n\n⚠️ ${relatedPayments.length} penerimaan terkait juga akan DIHAPUS:\n` +
      relatedPayments.map(p => `• ${p.id} — ${_fmtRpSales(p.amount)}`).join('\n');
  }
  if (!confirm(msg)) return;

  if (relatedPayments.length) {
    const payIds = new Set(relatedPayments.map(p => p.id));
    CustomerState.payments = CustomerState.payments.filter(p => !payIds.has(p.id));
  }

  inv.status       = 'draft';
  inv.confirmedAt  = null;
  inv.journalId    = null;
  inv.journalEntry = null;
  inv.paidAmount   = 0;
  inv.payments     = [];

  // Restore product onhand qty
  if (typeof PosState !== 'undefined' && Array.isArray(PosState.products)) {
    let stockChanged = false;
    inv.items.forEach(item => {
      if (!item.productId) return;
      const prod = PosState.products.find(p => p.id === item.productId);
      if (!prod) return;
      prod.onhandQty = (prod.onhandQty || 0) + (item.qty || 0);
      stockChanged = true;
    });
    if (stockChanged && typeof savePosData === 'function') savePosData();
  }

  saveCustomerData();
  _restoreCustomerJournalsToState();
  closeInvoiceModal();
  renderCustomerInvoicePage();
  showToast(`Invoice ${invoiceId} dibatalkan → Draft`, 'success');
}

function deleteInvoiceItem(id) {
  const inv = CustomerState.invoices.find(i => i.id === id);
  if (!inv) return;
  if (inv.status !== 'draft') { showToast('Hanya draft yang bisa dihapus', 'error'); return; }
  if (!confirm(`Hapus Invoice ${id}?`)) return;
  CustomerState.invoices = CustomerState.invoices.filter(i => i.id !== id);
  saveCustomerData();
  renderCustomerInvoicePage();
  showToast('Invoice dihapus', 'success');
}

// ============================================================
// ===== CUSTOMER PAYMENT (PENERIMAAN) =====
// ============================================================
function renderCustomerPaymentPage() {
  const filterCustomer = document.getElementById('recFilterCustomer')?.value || '';
  const filterFrom     = document.getElementById('recFilterFrom')?.value     || '';
  const filterTo       = document.getElementById('recFilterTo')?.value       || '';

  const custSel = document.getElementById('recFilterCustomer');
  if (custSel) {
    const cur = custSel.value;
    custSel.innerHTML = '<option value="">Semua Customer</option>' +
      CustomerState.customers.map(c => `<option value="${c.id}" ${c.id===cur?'selected':''}>${_escSales(c.name)}</option>`).join('');
  }

  let payments = [...CustomerState.payments];
  if (filterCustomer) payments = payments.filter(p => p.customerId === filterCustomer);
  if (filterFrom)     payments = payments.filter(p => p.date >= filterFrom);
  if (filterTo)       payments = payments.filter(p => p.date <= filterTo);
  payments.sort((a, b) => (b.date || '').localeCompare(a.date || ''));

  const wrap = document.getElementById('recTableWrap');
  if (!wrap) return;
  if (!payments.length) {
    wrap.innerHTML = `<div style="padding:48px;text-align:center;color:#6b7280">
      Belum ada penerimaan${filterCustomer ? ' untuk customer ini' : '. Klik <strong>"Buat Penerimaan"</strong> untuk mulai'}.</div>`;
    return;
  }
  wrap.innerHTML = `
    <table class="data-table">
      <thead><tr>
        <th>Nomor</th><th>Tanggal</th><th>Customer</th>
        <th style="text-align:right">Jumlah</th>
        <th>Akun Terima</th><th>Ref</th><th>Alokasi Invoice</th>
      </tr></thead>
      <tbody>
      ${payments.map(p => {
        const bankLabel = (typeof COA !== 'undefined' && COA[p.paymentCoa])
          ? `${p.paymentCoa} — ${COA[p.paymentCoa].name}` : (p.paymentCoa || '-');
        const allocList = (p.allocations || [])
          .map(a => `<code style="font-size:10px">${_escSales(a.invoiceId)}</code> ${_fmtRpSales(a.allocated)}`).join('<br>');
        return `<tr>
          <td><code>${_escSales(p.id)}</code></td>
          <td>${p.date || '-'}</td>
          <td>${_escSales(p.customerName)}</td>
          <td style="text-align:right"><strong>${_fmtRpSales(p.amount)}</strong></td>
          <td><code style="font-size:11px">${_escSales(bankLabel)}</code></td>
          <td>${_escSales(p.ref || '-')}</td>
          <td style="font-size:12px">${allocList || '-'}</td>
        </tr>`;
      }).join('')}
      </tbody>
    </table>`;
}

let _editingRecId = null;

function showCustomerPaymentModal(id) {
  _editingRecId = id || null;
  document.getElementById('recCustomerSelect').innerHTML = _customerOptions('');
  document.getElementById('recPaymentCoa').innerHTML     = _coaOptsSales('1-1110', 'kas-bank');
  document.getElementById('recDate').value   = _todayStrSales();
  document.getElementById('recAmount').value = '';
  document.getElementById('recRef').value    = '';
  document.getElementById('recNotes').value  = '';
  document.getElementById('recInvList').innerHTML =
    '<p style="color:#6b7280;font-size:13px">Pilih customer untuk melihat invoice outstanding.</p>';
  document.getElementById('salesPaymentModal').style.display = 'flex';
  if (typeof feather !== 'undefined') feather.replace();
}

function closeCustomerPaymentModal() {
  document.getElementById('salesPaymentModal').style.display = 'none';
  _editingRecId = null;
}

function onCustomerPaymentChange() {
  const customerId = document.getElementById('recCustomerSelect')?.value || '';
  const listEl     = document.getElementById('recInvList');
  if (!listEl) return;
  if (!customerId) {
    listEl.innerHTML = '<p style="color:#6b7280;font-size:13px">Pilih customer untuk melihat invoice outstanding.</p>';
    return;
  }
  const outInvs = CustomerState.invoices
    .filter(i => i.customerId === customerId && (i.status === 'outstanding' || i.status === 'partial'))
    .sort((a, b) => (a.date || '').localeCompare(b.date || ''));

  if (!outInvs.length) {
    listEl.innerHTML = '<p style="color:#10b981;font-size:13px">✓ Tidak ada invoice outstanding untuk customer ini.</p>';
    return;
  }
  const totalSisa = outInvs.reduce((s, i) => s + ((i.total || 0) - (i.paidAmount || 0)), 0);
  listEl.innerHTML = `
    <p style="font-size:13px;font-weight:600;margin-bottom:8px">
      Invoice Outstanding — sisa: <strong>${_fmtRpSales(totalSisa)}</strong>
    </p>
    <div class="table-card" style="max-height:220px;overflow-y:auto">
      <table style="width:100%;font-size:13px">
        <thead><tr>
          <th style="width:32px">
            <input type="checkbox" id="checkAllInvs" checked onchange="toggleAllInvChecks(this.checked)" />
          </th>
          <th>Nomor Invoice</th><th>Tanggal</th>
          <th style="text-align:right">Total</th>
          <th style="text-align:right">Dibayar</th>
          <th style="text-align:right">Sisa</th>
        </tr></thead>
        <tbody>
        ${outInvs.map(i => {
          const sisa = (i.total || 0) - (i.paidAmount || 0);
          return `<tr>
            <td><input type="checkbox" class="inv-pay-check" data-inv="${i.id}" data-sisa="${sisa}" checked /></td>
            <td><code>${_escSales(i.id)}</code></td>
            <td>${i.date || '-'}</td>
            <td style="text-align:right">${_fmtRpSales(i.total)}</td>
            <td style="text-align:right">${_fmtRpSales(i.paidAmount)}</td>
            <td style="text-align:right;font-weight:600;color:#f59e0b">${_fmtRpSales(sisa)}</td>
          </tr>`;
        }).join('')}
        </tbody>
      </table>
    </div>`;
}

function toggleAllInvChecks(checked) {
  document.querySelectorAll('.inv-pay-check').forEach(cb => { cb.checked = checked; });
}

function saveCustomerPaymentFromModal() {
  const customerId  = document.getElementById('recCustomerSelect').value;
  const date        = document.getElementById('recDate').value;
  const paymentCoa  = document.getElementById('recPaymentCoa').value;
  const amount      = parseFloat(document.getElementById('recAmount').value) || 0;
  const ref         = document.getElementById('recRef').value.trim();
  const notes       = document.getElementById('recNotes').value.trim();

  if (!customerId)  { showToast('Pilih customer', 'error'); return; }
  if (!date)        { showToast('Tanggal wajib diisi', 'error'); return; }
  if (!paymentCoa)  { showToast('Pilih akun penerimaan', 'error'); return; }
  if (amount <= 0)  { showToast('Jumlah harus lebih dari 0', 'error'); return; }

  const customer = CustomerState.customers.find(c => c.id === customerId);
  if (!customer)  { showToast('Customer tidak ditemukan', 'error'); return; }

  const checked = Array.from(document.querySelectorAll('.inv-pay-check:checked'))
    .map(cb => ({ invoiceId: cb.dataset.inv, sisa: parseFloat(cb.dataset.sisa) || 0 }));
  if (!checked.length) { showToast('Pilih minimal 1 invoice', 'error'); return; }

  const totalSisa = checked.reduce((s, c) => s + c.sisa, 0);
  if (amount > totalSisa + 0.01) {
    showToast(`Jumlah penerimaan ${_fmtRpSales(amount)} melebihi sisa piutang ${_fmtRpSales(totalSisa)}`, 'error');
    return;
  }

  // FIFO allocation
  const allocations = [];
  let remaining = amount;
  for (const c of checked) {
    if (remaining <= 0) break;
    const alloc = Math.min(remaining, c.sisa);
    allocations.push({ invoiceId: c.invoiceId, allocated: Math.round(alloc) });
    remaining -= alloc;
  }

  // Update invoices
  const recId = _nextRecNumber();
  allocations.forEach(a => {
    const inv = CustomerState.invoices.find(i => i.id === a.invoiceId);
    if (!inv) return;
    inv.paidAmount = (inv.paidAmount || 0) + a.allocated;
    inv.payments   = inv.payments || [];
    inv.payments.push({ paymentId: recId, amount: a.allocated, date });
    _updateInvoiceStatus(inv);
  });

  const payment = {
    id: recId, date, customerId, customerName: customer.name,
    receivableCoa: customer.receivableCoa || '1-1200',
    paymentCoa, amount, ref, notes,
    allocations, journalId: null, journalEntry: null
  };
  CustomerState.payments.push(payment);

  generateReceiptJournal(payment);
  saveCustomerData();
  _rebuildAfterCustomer();
  closeCustomerPaymentModal();
  renderCustomerPaymentPage();
  showToast(`Penerimaan ${recId} disimpan ✓`, 'success');
}

// ============================================================
// ===== LAPORAN CUSTOMER INVOICE =====
// ============================================================
function renderCustomerReportPage() {
  const filterCustomer = document.getElementById('custRptFilterCustomer')?.value || '';
  const filterStatus   = document.getElementById('custRptFilterStatus')?.value   || '';
  const filterFrom     = document.getElementById('custRptFilterFrom')?.value     || '';
  const filterTo       = document.getElementById('custRptFilterTo')?.value       || '';

  const custSel = document.getElementById('custRptFilterCustomer');
  if (custSel) {
    const cur = custSel.value;
    custSel.innerHTML = '<option value="">Semua Customer</option>' +
      CustomerState.customers.map(c => `<option value="${c.id}" ${c.id===cur?'selected':''}>${_escSales(c.name)}</option>`).join('');
  }

  let invoices = CustomerState.invoices.filter(i => i.status !== 'draft');
  if (filterCustomer) invoices = invoices.filter(i => i.customerId === filterCustomer);
  if (filterStatus)   invoices = invoices.filter(i => i.status     === filterStatus);
  if (filterFrom)     invoices = invoices.filter(i => i.date       >= filterFrom);
  if (filterTo)       invoices = invoices.filter(i => i.date       <= filterTo);
  invoices.sort((a, b) => (b.date || '').localeCompare(a.date || ''));

  const totalTagihan     = invoices.reduce((s, i) => s + (i.total || 0), 0);
  const totalLunas       = invoices.filter(i => i.status === 'paid').reduce((s, i) => s + (i.total || 0), 0);
  const totalOutstanding = invoices.filter(i => i.status !== 'paid').reduce((s, i) => s + ((i.total||0) - (i.paidAmount||0)), 0);

  const kpiEl = document.getElementById('custRptKpi');
  if (kpiEl) {
    kpiEl.innerHTML = `
      <div class="kpi-card"><div class="kpi-label">Total Tagihan</div><div class="kpi-value">${_fmtRpSales(totalTagihan)}</div></div>
      <div class="kpi-card"><div class="kpi-label">Sudah Lunas</div><div class="kpi-value" style="color:#10b981">${_fmtRpSales(totalLunas)}</div></div>
      <div class="kpi-card"><div class="kpi-label">Belum Lunas</div><div class="kpi-value" style="color:#f59e0b">${_fmtRpSales(totalOutstanding)}</div></div>`;
  }

  const wrap = document.getElementById('custRptTableWrap');
  if (!wrap) return;
  if (!invoices.length) {
    wrap.innerHTML = `<div style="padding:48px;text-align:center;color:#6b7280">Tidak ada data untuk filter ini.</div>`;
    return;
  }
  const today = _todayStrSales();
  wrap.innerHTML = `
    <table class="data-table">
      <thead><tr>
        <th>Nomor Invoice</th><th>Tanggal</th><th>Customer</th><th>Jatuh Tempo</th>
        <th style="text-align:right">Total</th>
        <th style="text-align:right">Dibayar</th>
        <th style="text-align:right">Sisa</th>
        <th>Status</th>
      </tr></thead>
      <tbody>
      ${invoices.map(inv => {
        const sisa    = (inv.total || 0) - (inv.paidAmount || 0);
        const overdue = inv.dueDate && inv.dueDate < today && inv.status !== 'paid';
        return `<tr>
          <td><code>${_escSales(inv.id)}</code></td>
          <td>${inv.date || '-'}</td>
          <td>${_escSales(inv.customerName)}</td>
          <td style="${overdue ? 'color:#ef4444;font-weight:600' : ''}">${inv.dueDate || '-'}${overdue ? ' ⚠' : ''}</td>
          <td style="text-align:right"><strong>${_fmtRpSales(inv.total)}</strong></td>
          <td style="text-align:right">${_fmtRpSales(inv.paidAmount)}</td>
          <td style="text-align:right${sisa > 0 ? ';color:#f59e0b;font-weight:600' : ''}">${_fmtRpSales(sisa)}</td>
          <td>${_invStatusBadge(inv.status)}</td>
        </tr>`;
      }).join('')}
      </tbody>
    </table>`;
}

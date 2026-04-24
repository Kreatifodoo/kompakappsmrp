/**
 * PURCHASE.JS — Purchase Module v8
 * Master Vendor, Vendor Bill, Payment, Laporan Pembelian
 */

// ===== STATE =====
const PurchaseState = {
  vendors:  [],
  bills:    [],
  payments: []
};
const PURCHASE_STORAGE_KEY = 'purchase_data_v1';

// ===== COUNTERS =====
let _billJeCounter = 0;
let _payJeCounter  = 0;

// ===== UTILS =====
function _fmtRp(n) {
  return 'Rp\u00a0' + Math.round(n || 0).toLocaleString('id-ID');
}
function _todayStr() {
  return new Date().toISOString().slice(0, 10);
}
function _genPurchaseId(prefix) {
  return prefix + '_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 6);
}
function _nextBillNumber() {
  const now = new Date();
  const y   = now.getFullYear();
  const m   = String(now.getMonth() + 1).padStart(2, '0');
  const seq = String(PurchaseState.bills.length + 1).padStart(4, '0');
  return `BILL-${y}${m}-${seq}`;
}
function _nextPayNumber() {
  const now = new Date();
  const y   = now.getFullYear();
  const m   = String(now.getMonth() + 1).padStart(2, '0');
  const seq = String(PurchaseState.payments.length + 1).padStart(4, '0');
  return `PAY-${y}${m}-${seq}`;
}
function _nextBillJeId() { return 'JE-BILL-' + String(++_billJeCounter).padStart(4, '0'); }
function _nextPayJeId()  { return 'JE-PAY-'  + String(++_payJeCounter).padStart(4, '0'); }

function _escPurchase(s) {
  return String(s || '')
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

// COA dropdown helper
function _coaOptsPurchase(selectedCode, filter) {
  const entries = Object.values(COA).filter(a => {
    if (a.category === 'Header') return false;
    if (filter === 'liabilitas') return a.type === 'Liabilitas';
    if (filter === 'kas-bank')   return a.type === 'Aset' && a.category === 'Kas & Bank';
    return true;
  }).sort((a, b) => a.code.localeCompare(b.code));
  return '<option value="">-- Pilih Akun --</option>' +
    entries.map(a =>
      `<option value="${a.code}" ${a.code === selectedCode ? 'selected' : ''}>${a.code} — ${_escPurchase(a.name)}</option>`
    ).join('');
}

// COA dropdown for inventory/expense account on bill line items (no POS dependency)
function _coaOptsInventory(selected) {
  const entries = Object.values(COA)
    .filter(a => a.category !== 'Header')
    .sort((a, b) => a.code.localeCompare(b.code));
  return '<option value="">-- Pilih Akun --</option>' +
    entries.map(a =>
      `<option value="${a.code}" ${a.code === selected ? 'selected' : ''}>${a.code} — ${_escPurchase(a.name)}</option>`
    ).join('');
}

// Vendor dropdown options
function _vendorOptions(selectedId) {
  if (!PurchaseState.vendors.length)
    return '<option value="">-- Belum ada vendor --</option>';
  return '<option value="">-- Pilih Vendor --</option>' +
    PurchaseState.vendors
      .filter(v => v.isActive)
      .map(v => `<option value="${v.id}" ${v.id === selectedId ? 'selected' : ''}>${_escPurchase(v.name)}</option>`)
      .join('');
}

// Status badge using existing badge classes
function _billStatusBadge(status) {
  const map = {
    draft:       '<span class="badge badge-neutral">Draft</span>',
    outstanding: '<span class="badge badge-red">Outstanding</span>',
    partial:     '<span class="badge badge-blue">Partial</span>',
    paid:        '<span class="badge badge-green">Paid</span>',
  };
  return map[status] || `<span class="badge badge-neutral">${_escPurchase(status)}</span>`;
}

// ===== STORAGE =====
function savePurchaseData() {
  try {
    localStorage.setItem(PURCHASE_STORAGE_KEY, JSON.stringify({
      vendors:  PurchaseState.vendors,
      bills:    PurchaseState.bills,
      payments: PurchaseState.payments
    }));
    if (typeof DataStore !== 'undefined') DataStore.push(PURCHASE_STORAGE_KEY);
  } catch(e) { console.warn('[Purchase] Save failed:', e); }
}

function loadPurchaseData() {
  try {
    const raw = localStorage.getItem(PURCHASE_STORAGE_KEY);
    if (raw) {
      const d = JSON.parse(raw);
      if (Array.isArray(d.vendors))  PurchaseState.vendors  = d.vendors;
      if (Array.isArray(d.bills))    PurchaseState.bills    = d.bills;
      if (Array.isArray(d.payments)) PurchaseState.payments = d.payments;
      // Restore JE counters from existing data
      PurchaseState.bills.forEach(b => {
        const n = parseInt((b.journalId || '').replace('JE-BILL-', '')) || 0;
        if (n > _billJeCounter) _billJeCounter = n;
      });
      PurchaseState.payments.forEach(p => {
        const n = parseInt((p.journalId || '').replace('JE-PAY-', '')) || 0;
        if (n > _payJeCounter) _payJeCounter = n;
      });
    }
  } catch(e) { console.warn('[Purchase] Load failed:', e); }
  _restorePurchaseJournalsToState();
}

// ===== JOURNAL INTEGRATION =====
function _restorePurchaseJournalsToState() {
  if (typeof AppState === 'undefined' || !Array.isArray(AppState.journals)) return;
  // Remove stale purchase journals to avoid duplicates
  AppState.journals = AppState.journals.filter(j =>
    !String(j.id || '').startsWith('JE-BILL-') && !String(j.id || '').startsWith('JE-PAY-')
  );
  PurchaseState.bills.forEach(b    => { if (b.journalEntry) AppState.journals.push(b.journalEntry); });
  PurchaseState.payments.forEach(p => { if (p.journalEntry) AppState.journals.push(p.journalEntry); });
  _rebuildAfterPurchase();
}

function _rebuildAfterPurchase() {
  if (typeof AppState === 'undefined') return;
  if (typeof buildLedger           === 'function') AppState.ledger     = buildLedger(AppState.journals);
  if (typeof flattenJournalForTable === 'function') AppState.journalRows = flattenJournalForTable(AppState.journals);
  // Re-render journal page if active
  if (AppState.currentPage === 'journal' && typeof renderJournalTable === 'function') renderJournalTable();
}

// ===== BILL STATUS HELPER =====
function _updateBillStatus(bill) {
  if (!bill.confirmedAt) { bill.status = 'draft'; return; }
  const paid = bill.paidAmount || 0;
  const total = bill.total || 0;
  if (paid <= 0)        bill.status = 'outstanding';
  else if (paid >= total) bill.status = 'paid';
  else                  bill.status = 'partial';
}

// ===== FEE COMPUTATION — no POS dependency, fees not used in Purchase module =====
function _computeBillFees(subtotal) {
  return []; // Purchase module is independent — no PosState.feeMasters reference
}

function _renderBillFeeSummary(subtotal) {
  const el = document.getElementById('billFeeSummary');
  if (!el) return;
  el.innerHTML = `<div class="bill-fee-summary-box">
    <div class="bill-fee-row bill-fee-total-row">
      <span>TOTAL</span><span>${_fmtRp(subtotal)}</span>
    </div>
  </div>`;
}

// ===== JOURNAL GENERATORS =====
function generateBillJournal(bill) {
  // Dr side 1: inventory per account
  const invMap = {};
  bill.items.forEach(item => {
    const ac = item.inventoryAccount || '1-1400';
    invMap[ac] = (invMap[ac] || 0) + item.lineTotal;
  });
  const entries = [];
  Object.entries(invMap).forEach(([code, amt]) => {
    entries.push({
      accountCode: code,
      accountName: (typeof COA !== 'undefined' && COA[code]) ? COA[code].name : 'Persediaan',
      debit: amt, kredit: 0,
      note: `Pembelian dari ${bill.vendorName}`
    });
  });
  // Dr side 2: fees
  (bill.appliedFees || []).forEach(f => {
    if ((f.computed || 0) > 0) {
      entries.push({
        accountCode: f.coaCode,
        accountName: (typeof COA !== 'undefined' && COA[f.coaCode]) ? COA[f.coaCode].name : f.name,
        debit: f.computed, kredit: 0,
        note: f.name
      });
    }
  });
  // Cr side: vendor payable = total incl. fees
  const vendor = PurchaseState.vendors.find(v => v.id === bill.vendorId);
  const apCode = vendor?.payableCoa || '2-1100';
  const apName = (typeof COA !== 'undefined' && COA[apCode]) ? COA[apCode].name : 'Utang Usaha';
  entries.push({
    accountCode: apCode, accountName: apName,
    debit: 0, kredit: bill.total,
    note: `Faktur ${bill.ref || bill.id}`
  });
  const jeId = _nextBillJeId();
  const je = {
    id: jeId, txId: bill.id, date: bill.date, no: jeId,
    description: `Vendor Bill ${bill.id} — ${bill.vendorName}`,
    entries
  };
  bill.journalId    = jeId;
  bill.journalEntry = je;
  if (typeof AppState !== 'undefined') AppState.journals.push(je);
  return jeId;
}

function generatePaymentJournal(payment) {
  const apName   = (typeof COA !== 'undefined' && COA[payment.payableCoa]) ? COA[payment.payableCoa].name : 'Utang Usaha';
  const bankName = (typeof COA !== 'undefined' && COA[payment.paymentCoa]) ? COA[payment.paymentCoa].name : 'Bank/Kas';
  const entries = [
    { accountCode: payment.payableCoa, accountName: apName,   debit: payment.amount, kredit: 0,               note: `Pembayaran ke ${payment.vendorName}` },
    { accountCode: payment.paymentCoa, accountName: bankName, debit: 0,              kredit: payment.amount,  note: `Ref: ${payment.ref || payment.id}` }
  ];
  const jeId = _nextPayJeId();
  const je   = {
    id: jeId, txId: payment.id, date: payment.date, no: jeId,
    description: `Payment ${payment.id} — ${payment.vendorName}`,
    entries
  };
  payment.journalId    = jeId;
  payment.journalEntry = je;
  if (typeof AppState !== 'undefined') AppState.journals.push(je);
  return jeId;
}

// ============================================================
// ===== MASTER VENDOR =====
// ============================================================
function renderMasterVendorPage() {
  const wrap = document.getElementById('vendorTableWrap');
  if (!wrap) return;
  if (!PurchaseState.vendors.length) {
    wrap.innerHTML = `<div style="padding:48px;text-align:center;color:#6b7280">
      Belum ada vendor. Klik <strong>"Tambah Vendor"</strong> untuk mulai.</div>`;
    return;
  }
  wrap.innerHTML = `
    <table class="data-table">
      <thead><tr>
        <th>Nama Vendor</th><th>Kontak Person</th><th>Telepon</th><th>Akun Hutang (Payable)</th><th>Status</th><th style="text-align:center">Aksi</th>
      </tr></thead>
      <tbody>
      ${PurchaseState.vendors.map(v => {
        const coaLabel = (typeof COA !== 'undefined' && COA[v.payableCoa])
          ? `${v.payableCoa} — ${COA[v.payableCoa].name}` : (v.payableCoa || '-');
        return `<tr>
          <td><strong>${_escPurchase(v.name)}</strong></td>
          <td>${_escPurchase(v.contactPerson || '-')}</td>
          <td>${_escPurchase(v.phone || '-')}</td>
          <td><code style="font-size:11px">${_escPurchase(coaLabel)}</code></td>
          <td>${v.isActive ? '<span class="badge badge-green">Aktif</span>' : '<span class="badge badge-neutral">Nonaktif</span>'}</td>
          <td style="text-align:center">
            <button class="btn btn-sm btn-outline" onclick="showVendorModal('${v.id}')">Edit</button>
          </td>
        </tr>`;
      }).join('')}
      </tbody>
    </table>`;
}

let _editingVendorId = null;

function showVendorModal(id) {
  try {
    _editingVendorId = id || null;
    const v = id ? PurchaseState.vendors.find(x => x.id === id) : null;
    document.getElementById('vendorModalTitle').textContent = v ? 'Edit Vendor' : 'Tambah Vendor';
    document.getElementById('vendorName').value      = v?.name          || '';
    document.getElementById('vendorContact').value   = v?.contactPerson || '';
    document.getElementById('vendorPhone').value     = v?.phone         || '';
    document.getElementById('vendorEmail').value     = v?.email         || '';
    document.getElementById('vendorAddress').value   = v?.address       || '';
    document.getElementById('vendorIsActive').value  = String(v?.isActive !== false);
    document.getElementById('vendorPayableCoa').innerHTML = _coaOptsPurchase(v?.payableCoa || '2-1100', 'liabilitas');
    const btnDel = document.getElementById('btnDeleteVendor');
    if (btnDel) btnDel.style.display = v ? 'inline-flex' : 'none';
    document.getElementById('purchaseVendorModal').style.display = 'flex';
    if (typeof feather !== 'undefined') feather.replace();
  } catch(e) {
    console.error('[Purchase] showVendorModal error:', e);
    showToast('Gagal membuka form vendor: ' + e.message, 'error');
  }
}

function closeVendorModal() {
  document.getElementById('purchaseVendorModal').style.display = 'none';
  _editingVendorId = null;
}

function saveVendorFromModal() {
  const name       = document.getElementById('vendorName').value.trim();
  const payableCoa = document.getElementById('vendorPayableCoa').value;
  if (!name)       { showToast('Nama vendor wajib diisi', 'error'); return; }
  if (!payableCoa) { showToast('Akun hutang wajib dipilih', 'error'); return; }
  const data = {
    name,
    contactPerson: document.getElementById('vendorContact').value.trim(),
    phone:         document.getElementById('vendorPhone').value.trim(),
    email:         document.getElementById('vendorEmail').value.trim(),
    address:       document.getElementById('vendorAddress').value.trim(),
    payableCoa,
    isActive:      document.getElementById('vendorIsActive').value === 'true'
  };
  if (_editingVendorId) {
    const idx = PurchaseState.vendors.findIndex(v => v.id === _editingVendorId);
    if (idx >= 0) PurchaseState.vendors[idx] = { ...PurchaseState.vendors[idx], ...data };
  } else {
    PurchaseState.vendors.push({ id: _genPurchaseId('vnd'), ...data });
  }
  savePurchaseData();
  closeVendorModal();
  renderMasterVendorPage();
  showToast('Vendor disimpan', 'success');
}

function deleteVendorItem(id) {
  if (!id) return;
  if (PurchaseState.bills.some(b => b.vendorId === id)) {
    showToast('Vendor tidak bisa dihapus — masih ada bill terkait', 'error');
    return;
  }
  if (!confirm('Hapus vendor ini?')) return;
  PurchaseState.vendors = PurchaseState.vendors.filter(v => v.id !== id);
  savePurchaseData();
  closeVendorModal();
  renderMasterVendorPage();
  showToast('Vendor dihapus', 'success');
}

// ============================================================
// ===== VENDOR BILL =====
// ============================================================
function renderVendorBillPage() {
  const filterVendor = document.getElementById('billFilterVendor')?.value || '';
  const filterStatus = document.getElementById('billFilterStatus')?.value || '';
  const filterFrom   = document.getElementById('billFilterFrom')?.value   || '';
  const filterTo     = document.getElementById('billFilterTo')?.value     || '';

  // Populate vendor filter dropdown
  const vendorSel = document.getElementById('billFilterVendor');
  if (vendorSel) {
    const cur = vendorSel.value;
    vendorSel.innerHTML = '<option value="">Semua Vendor</option>' +
      PurchaseState.vendors.map(v => `<option value="${v.id}" ${v.id===cur?'selected':''}>${_escPurchase(v.name)}</option>`).join('');
  }

  let bills = [...PurchaseState.bills];
  if (filterVendor) bills = bills.filter(b => b.vendorId === filterVendor);
  if (filterStatus) bills = bills.filter(b => b.status  === filterStatus);
  if (filterFrom)   bills = bills.filter(b => b.date    >= filterFrom);
  if (filterTo)     bills = bills.filter(b => b.date    <= filterTo);
  bills.sort((a, b) => (b.date || '').localeCompare(a.date || ''));

  // KPI cards
  const confirmed = PurchaseState.bills.filter(b => b.status !== 'draft');
  const totOutstanding = confirmed.filter(b => b.status !== 'paid')
    .reduce((s, b) => s + ((b.total || 0) - (b.paidAmount || 0)), 0);
  const totPaid = confirmed.filter(b => b.status === 'paid').reduce((s, b) => s + (b.total || 0), 0);
  const totDraft = PurchaseState.bills.filter(b => b.status === 'draft').length;
  const kpiEl = document.getElementById('billKpiCards');
  if (kpiEl) {
    kpiEl.innerHTML = `
      <div class="kpi-card"><div class="kpi-label">Total Belum Lunas</div><div class="kpi-value" style="color:#f59e0b">${_fmtRp(totOutstanding)}</div></div>
      <div class="kpi-card"><div class="kpi-label">Total Lunas</div><div class="kpi-value" style="color:#10b981">${_fmtRp(totPaid)}</div></div>
      <div class="kpi-card"><div class="kpi-label">Draft</div><div class="kpi-value" style="color:#6b7280">${totDraft}</div></div>`;
  }

  const wrap = document.getElementById('billTableWrap');
  if (!wrap) return;
  if (!bills.length) {
    wrap.innerHTML = `<div style="padding:48px;text-align:center;color:#6b7280">
      Tidak ada vendor bill${filterStatus||filterVendor ? ' untuk filter ini' : '. Klik <strong>"Buat Bill"</strong> untuk mulai'}.</div>`;
    return;
  }
  wrap.innerHTML = `
    <table class="data-table">
      <thead><tr>
        <th>Nomor</th><th>Tanggal</th><th>Vendor</th><th>Ref</th>
        <th style="text-align:right">Subtotal</th>
        <th style="text-align:right">Total (incl. pajak)</th>
        <th style="text-align:right">Dibayar</th>
        <th style="text-align:right">Sisa</th>
        <th>Status</th><th style="text-align:center">Aksi</th>
      </tr></thead>
      <tbody>
      ${bills.map(b => {
        const sisa = (b.total || 0) - (b.paidAmount || 0);
        return `<tr>
          <td><code>${_escPurchase(b.id)}</code></td>
          <td>${b.date || '-'}</td>
          <td>${_escPurchase(b.vendorName)}</td>
          <td>${_escPurchase(b.ref || '-')}</td>
          <td style="text-align:right">${_fmtRp(b.subtotal)}</td>
          <td style="text-align:right"><strong>${_fmtRp(b.total)}</strong></td>
          <td style="text-align:right">${_fmtRp(b.paidAmount)}</td>
          <td style="text-align:right${sisa > 0 ? ';color:#f59e0b;font-weight:600' : ''}">${_fmtRp(sisa)}</td>
          <td>${_billStatusBadge(b.status)}</td>
          <td style="text-align:center;white-space:nowrap">
            <button class="btn btn-sm btn-outline" onclick="showBillModal('${b.id}')">
              ${b.status === 'draft' ? 'Edit' : 'Lihat'}
            </button>
            ${b.status === 'draft' ? `<button class="btn btn-sm btn-danger" style="margin-left:4px" onclick="deleteBillItem('${b.id}')">Hapus</button>` : ''}
          </td>
        </tr>`;
      }).join('')}
      </tbody>
    </table>`;
}

// ===== BILL MODAL — editing state =====
let _editingBillId = null;
let _billLines     = [];
let _billLineCtr   = 0;

function showBillModal(id) {
  _editingBillId = id || null;
  const bill         = id ? PurchaseState.bills.find(b => b.id === id) : null;
  const isConfirmed  = bill && bill.status !== 'draft';

  document.getElementById('purchaseBillModalTitle').textContent =
    bill ? `Vendor Bill — ${bill.id}` : 'Buat Vendor Bill';

  // Populate dropdowns
  document.getElementById('billVendorSelect').innerHTML = _vendorOptions(bill?.vendorId || '');
  document.getElementById('billDate').value    = bill?.date    || _todayStr();
  document.getElementById('billDueDate').value = bill?.dueDate || '';
  document.getElementById('billRef').value     = bill?.ref     || '';

  // Build line items
  _billLineCtr = 0;
  if (bill?.items?.length) {
    _billLines = bill.items.map(item => ({ description: '', ...item, _tmpId: ++_billLineCtr }));
  } else {
    _billLines = [];
    _addEmptyBillLine();
  }

  // Readonly controls for confirmed bills
  ['billVendorSelect','billDate','billDueDate','billRef'].forEach(elId => {
    const el = document.getElementById(elId);
    if (el) el.disabled = isConfirmed;
  });
  document.getElementById('btnSaveBillDraft').style.display = isConfirmed ? 'none' : 'inline-flex';
  document.getElementById('btnConfirmBill').style.display   = isConfirmed ? 'none' : 'inline-flex';
  const btnCancel = document.getElementById('btnCancelBill');
  if (btnCancel) btnCancel.style.display = isConfirmed ? 'inline-flex' : 'none';
  const btnAddLine = document.getElementById('btnAddBillLine');
  if (btnAddLine) btnAddLine.style.display = isConfirmed ? 'none' : 'inline-flex';

  _renderBillLinesTable(isConfirmed);
  _recomputeAndRenderFeeSummary();

  document.getElementById('purchaseBillModal').style.display = 'flex';
  if (typeof feather !== 'undefined') feather.replace();
}

function closeBillModal() {
  document.getElementById('purchaseBillModal').style.display = 'none';
  _editingBillId = null;
  _billLines = [];
}

function _addEmptyBillLine() {
  _billLines.push({
    _tmpId: ++_billLineCtr,
    lineId: _genPurchaseId('li'),
    productId: '',
    productName: '',
    description: '',
    inventoryAccount: '1-1400',
    qty: 1, unitPrice: 0, lineTotal: 0
  });
}

function addBillLineItem() {
  _addEmptyBillLine();
  _renderBillLinesTable(false);
  _recomputeAndRenderFeeSummary();
  if (typeof feather !== 'undefined') feather.replace();
}

function _renderBillLinesTable(readonly) {
  const tbody = document.getElementById('billLinesBody');
  if (!tbody) return;

  // Build product options from PosState (if available)
  const productOptions = (typeof PosState !== 'undefined' && Array.isArray(PosState.products))
    ? PosState.products.filter(p => p.available !== false)
        .map(p => `<option value="${p.id}">${_escPurchase(p.name)}</option>`).join('')
    : '';

  tbody.innerHTML = _billLines.map(line => {
    const coaLabel = line.inventoryAccount
      ? `${line.inventoryAccount}${(typeof COA !== 'undefined' && COA[line.inventoryAccount]) ? ' — ' + COA[line.inventoryAccount].name : ''}`
      : '—';
    if (readonly) {
      return `<tr>
        <td>${_escPurchase(line.productName)}</td>
        <td>${_escPurchase(line.description || '-')}</td>
        <td><code style="font-size:11px">${_escPurchase(coaLabel)}</code></td>
        <td style="text-align:right">${line.qty}</td>
        <td style="text-align:right">${_fmtRp(line.unitPrice)}</td>
        <td style="text-align:right"><strong>${_fmtRp(line.lineTotal)}</strong></td>
        <td></td>
      </tr>`;
    }
    // Build product select with current selection
    const prodOpts = `<option value="">-- Pilih Produk --</option>` +
      productOptions.replace(`value="${line.productId}"`, `value="${line.productId}" selected`);
    return `<tr data-line="${line._tmpId}">
      <td>
        <select class="j-select" style="min-width:160px"
          onchange="onBillProductChange(${line._tmpId})">
          ${prodOpts}
        </select>
      </td>
      <td>
        <input type="text" placeholder="Keterangan..."
          style="min-width:140px;padding:4px 6px;border:1px solid #e2e8f0;border-radius:4px;width:100%"
          value="${_escPurchase(line.description || '')}"
          oninput="onBillLineDescChange(${line._tmpId}, this.value)" />
      </td>
      <td>
        <select class="j-select" style="min-width:160px"
          onchange="onBillLineAccountChange(${line._tmpId}, this.value)">
          ${_coaOptsInventory(line.inventoryAccount)}
        </select>
      </td>
      <td>
        <input type="number" style="width:70px;text-align:right;padding:4px 6px;border:1px solid #e2e8f0;border-radius:4px"
          value="${line.qty}" min="0.001" step="1"
          oninput="onBillQtyPriceChange(${line._tmpId},'qty',this.value)" />
      </td>
      <td>
        <input type="number" style="width:110px;text-align:right;padding:4px 6px;border:1px solid #e2e8f0;border-radius:4px"
          value="${line.unitPrice}" min="0" step="1"
          oninput="onBillQtyPriceChange(${line._tmpId},'unitPrice',this.value)" />
      </td>
      <td style="text-align:right">
        <strong id="billLineTotal_${line._tmpId}">${_fmtRp(line.lineTotal)}</strong>
      </td>
      <td>
        <button onclick="removeBillLine(${line._tmpId})" style="border:none;background:none;cursor:pointer;color:#ef4444;font-size:18px;padding:2px 4px" title="Hapus baris">×</button>
      </td>
    </tr>`;
  }).join('');
}

// Product change: auto-fill name, price, inventoryAccount from POS product master
function onBillProductChange(tmpId) {
  const line = _billLines.find(l => l._tmpId === tmpId);
  if (!line) return;
  const row = document.querySelector(`[data-line="${tmpId}"]`);
  if (!row) return;
  const productId = row.querySelector('select').value;
  if (!productId) {
    line.productId = ''; line.productName = '';
    line.inventoryAccount = '1-1400';
    line.unitPrice = 0; line.lineTotal = 0;
  } else {
    const prod = (typeof PosState !== 'undefined') ? PosState.products.find(p => p.id === productId) : null;
    const cat  = (prod && typeof getCategoryById === 'function') ? getCategoryById(prod.categoryId) : null;
    line.productId        = productId;
    line.productName      = prod?.name || productId;
    line.inventoryAccount = cat?.inventoryAccount || '1-1400';
    line.unitPrice        = prod?.costPrice || 0;
    line.lineTotal        = Math.round(line.qty * line.unitPrice);
  }
  // Update account COA select (2nd select in row)
  const acctSel = row.querySelectorAll('select')[1];
  if (acctSel) acctSel.innerHTML = _coaOptsInventory(line.inventoryAccount);
  // Update unit price input (2nd number input in row)
  const numInputs = row.querySelectorAll('input[type="number"]');
  if (numInputs[1]) numInputs[1].value = line.unitPrice;
  // Update total display
  const totalEl = document.getElementById(`billLineTotal_${tmpId}`);
  if (totalEl) totalEl.textContent = _fmtRp(line.lineTotal);
  _recomputeAndRenderFeeSummary();
}

// Description freetext per line
function onBillLineDescChange(tmpId, value) {
  const line = _billLines.find(l => l._tmpId === tmpId);
  if (line) line.description = value;
}

function onBillLineAccountChange(tmpId, value) {
  const line = _billLines.find(l => l._tmpId === tmpId);
  if (line) line.inventoryAccount = value;
}

function onBillQtyPriceChange(tmpId, field, value) {
  const line = _billLines.find(l => l._tmpId === tmpId);
  if (!line) return;
  line[field]   = parseFloat(value) || 0;
  line.lineTotal = Math.round(line.qty * line.unitPrice);
  const totalEl = document.getElementById(`billLineTotal_${tmpId}`);
  if (totalEl) totalEl.textContent = _fmtRp(line.lineTotal);
  _recomputeAndRenderFeeSummary();
}

function removeBillLine(tmpId) {
  _billLines = _billLines.filter(l => l._tmpId !== tmpId);
  _renderBillLinesTable(false);
  _recomputeAndRenderFeeSummary();
  if (typeof feather !== 'undefined') feather.replace();
}

function _getBillSubtotal() {
  return _billLines.reduce((s, l) => s + (l.lineTotal || 0), 0);
}

function _recomputeAndRenderFeeSummary() {
  _renderBillFeeSummary(_getBillSubtotal());
}

// Collect & validate bill header+lines, return data object or null
function _collectBillData() {
  const vendorId = document.getElementById('billVendorSelect').value;
  const date     = document.getElementById('billDate').value;
  const dueDate  = document.getElementById('billDueDate').value;
  const ref      = document.getElementById('billRef').value.trim();
  const vendor   = PurchaseState.vendors.find(v => v.id === vendorId);

  if (!vendorId) { showToast('Pilih vendor terlebih dahulu', 'error'); return null; }
  if (!date)     { showToast('Tanggal wajib diisi', 'error');         return null; }
  if (!_billLines.length) { showToast('Tambahkan minimal 1 baris item', 'error'); return null; }
  if (_billLines.some(l => !l.productId)) {
    showToast('Semua baris harus dipilih produknya', 'error'); return null;
  }

  const subtotal = _getBillSubtotal();
  const total    = subtotal; // no fees — Purchase module is POS-independent

  return { vendorId, vendorName: vendor.name, date, dueDate, ref, subtotal, appliedFees: [], total };
}

function saveBillAsDraft() {
  const hdr = _collectBillData();
  if (!hdr) return;
  const items = _billLines.map(l => ({
    lineId: l.lineId || _genPurchaseId('li'),
    productId: l.productId,
    productName: l.productName,
    description: l.description || '',
    inventoryAccount: l.inventoryAccount,
    qty: l.qty, unitPrice: l.unitPrice, lineTotal: l.lineTotal
  }));
  if (_editingBillId) {
    const idx = PurchaseState.bills.findIndex(b => b.id === _editingBillId);
    if (idx >= 0) PurchaseState.bills[idx] = { ...PurchaseState.bills[idx], ...hdr, items };
  } else {
    const newBill = {
      id: _nextBillNumber(), ...hdr, items,
      paidAmount: 0, status: 'draft', journalId: null, journalEntry: null,
      payments: [], confirmedAt: null
    };
    PurchaseState.bills.push(newBill);
    _editingBillId = newBill.id;
  }
  savePurchaseData();
  closeBillModal();
  renderVendorBillPage();
  showToast('Bill disimpan sebagai draft', 'success');
}

function confirmBillFromModal() {
  const hdr = _collectBillData();
  if (!hdr) return;
  const items = _billLines.map(l => ({
    lineId: l.lineId || _genPurchaseId('li'),
    productId: l.productId,
    productName: l.productName,
    description: l.description || '',
    inventoryAccount: l.inventoryAccount,
    qty: l.qty, unitPrice: l.unitPrice, lineTotal: l.lineTotal
  }));
  let bill;
  if (_editingBillId) {
    const idx = PurchaseState.bills.findIndex(b => b.id === _editingBillId);
    if (idx >= 0) { PurchaseState.bills[idx] = { ...PurchaseState.bills[idx], ...hdr, items }; bill = PurchaseState.bills[idx]; }
  } else {
    bill = {
      id: _nextBillNumber(), ...hdr, items,
      paidAmount: 0, status: 'draft', journalId: null, journalEntry: null,
      payments: [], confirmedAt: null
    };
    PurchaseState.bills.push(bill);
  }
  if (!bill) return;
  confirmBill(bill.id);
}

function confirmBill(billId) {
  const bill = PurchaseState.bills.find(b => b.id === billId);
  if (!bill) return;
  if (bill.status !== 'draft') { showToast('Hanya bill berstatus Draft yang bisa dikonfirmasi', 'error'); return; }

  bill.confirmedAt = new Date().toISOString();
  bill.status      = 'outstanding';

  // Generate journal — Dr inventoryAccount per line, Cr vendor.payableCoa
  generateBillJournal(bill);

  // Update POS product: stock on-hand + weighted average cost
  if (typeof PosState !== 'undefined' && Array.isArray(PosState.products)) {
    bill.items.forEach(item => {
      if (!item.productId) return;
      const prod = PosState.products.find(p => p.id === item.productId);
      if (!prod) return;

      const oldQty   = prod.onhandQty || 0;
      const oldCost  = prod.costPrice || 0;
      const newQty   = item.qty || 0;
      const newPrice = item.unitPrice || 0;

      // Snapshot sebelum update (untuk rollback saat cancel)
      item._prevOnhandQty = oldQty;
      item._prevCostPrice = oldCost;

      // Update stock (additive)
      prod.onhandQty = oldQty + newQty;

      // Weighted average cost (standard ERP formula)
      if (prod.onhandQty > 0) {
        prod.costPrice = Math.round((oldQty * oldCost + newQty * newPrice) / prod.onhandQty);
      } else {
        prod.costPrice = newPrice;
      }
    });
    if (typeof savePosData === 'function') savePosData();
  }

  savePurchaseData();
  _rebuildAfterPurchase();
  closeBillModal();
  renderVendorBillPage();
  showToast(`Bill ${billId} dikonfirmasi ✓`, 'success');
}

function cancelBill(billId) {
  const bill = PurchaseState.bills.find(b => b.id === billId);
  if (!bill || bill.status === 'draft') return;

  // Warn if bill has payments
  const relatedPayments = PurchaseState.payments.filter(p =>
    p.allocations.some(a => a.billId === billId)
  );

  let msg = `Batalkan Bill ${billId} dan kembalikan ke Draft?`;
  if (relatedPayments.length) {
    msg += `\n\n⚠️ ${relatedPayments.length} payment terkait juga akan DIHAPUS:\n` +
      relatedPayments.map(p => `• ${p.id} — ${_fmtRp(p.amount)}`).join('\n');
  }
  if (!confirm(msg)) return;

  // 1. Delete related payments
  if (relatedPayments.length) {
    const payIds = new Set(relatedPayments.map(p => p.id));
    PurchaseState.payments = PurchaseState.payments.filter(p => !payIds.has(p.id));
  }

  // 2. Reverse POS product: restore stock + cost from snapshot
  if (typeof PosState !== 'undefined' && Array.isArray(PosState.products)) {
    bill.items.forEach(item => {
      if (!item.productId) return;
      const prod = PosState.products.find(p => p.id === item.productId);
      if (!prod) return;

      // Restore from snapshot if available, fallback: subtract qty
      prod.onhandQty = (item._prevOnhandQty != null)
        ? item._prevOnhandQty
        : Math.max(0, (prod.onhandQty || 0) - (item.qty || 0));

      // Restore cost price from snapshot
      if (item._prevCostPrice != null) {
        prod.costPrice = item._prevCostPrice;
      }
    });
    if (typeof savePosData === 'function') savePosData();
  }

  // 3. Reset bill to draft
  bill.status       = 'draft';
  bill.confirmedAt  = null;
  bill.journalId    = null;
  bill.journalEntry = null;
  bill.paidAmount   = 0;
  bill.payments     = [];

  // 4. Save & rebuild (journals auto-cleaned by _restorePurchaseJournalsToState)
  savePurchaseData();
  _restorePurchaseJournalsToState();
  closeBillModal();
  renderVendorBillPage();
  showToast(`Bill ${billId} dibatalkan → Draft`, 'success');
}

function deleteBillItem(id) {
  const bill = PurchaseState.bills.find(b => b.id === id);
  if (!bill) return;
  if (bill.status !== 'draft') { showToast('Hanya draft yang bisa dihapus', 'error'); return; }
  if (!confirm(`Hapus Bill ${id}?`)) return;
  PurchaseState.bills = PurchaseState.bills.filter(b => b.id !== id);
  savePurchaseData();
  renderVendorBillPage();
  showToast('Bill dihapus', 'success');
}

// ============================================================
// ===== PAYMENT =====
// ============================================================
function renderPaymentPage() {
  const filterVendor = document.getElementById('payFilterVendor')?.value || '';
  const filterFrom   = document.getElementById('payFilterFrom')?.value   || '';
  const filterTo     = document.getElementById('payFilterTo')?.value     || '';

  // Populate vendor filter
  const vendorSel = document.getElementById('payFilterVendor');
  if (vendorSel) {
    const cur = vendorSel.value;
    vendorSel.innerHTML = '<option value="">Semua Vendor</option>' +
      PurchaseState.vendors.map(v => `<option value="${v.id}" ${v.id===cur?'selected':''}>${_escPurchase(v.name)}</option>`).join('');
  }

  let payments = [...PurchaseState.payments];
  if (filterVendor) payments = payments.filter(p => p.vendorId === filterVendor);
  if (filterFrom)   payments = payments.filter(p => p.date >= filterFrom);
  if (filterTo)     payments = payments.filter(p => p.date <= filterTo);
  payments.sort((a, b) => (b.date || '').localeCompare(a.date || ''));

  const wrap = document.getElementById('paymentTableWrap');
  if (!wrap) return;
  if (!payments.length) {
    wrap.innerHTML = `<div style="padding:48px;text-align:center;color:#6b7280">
      Belum ada payment${filterVendor ? ' untuk vendor ini' : '. Klik <strong>"Buat Payment"</strong> untuk mulai'}.</div>`;
    return;
  }
  wrap.innerHTML = `
    <table class="data-table">
      <thead><tr>
        <th>Nomor</th><th>Tanggal</th><th>Vendor</th>
        <th style="text-align:right">Jumlah</th>
        <th>Akun Pembayaran</th><th>Ref</th><th>Alokasi Bill</th>
      </tr></thead>
      <tbody>
      ${payments.map(p => {
        const bankLabel = (typeof COA !== 'undefined' && COA[p.paymentCoa])
          ? `${p.paymentCoa} — ${COA[p.paymentCoa].name}` : (p.paymentCoa || '-');
        const allocList = (p.allocations || [])
          .map(a => `<code style="font-size:10px">${_escPurchase(a.billId)}</code> ${_fmtRp(a.allocated)}`).join('<br>');
        return `<tr>
          <td><code>${_escPurchase(p.id)}</code></td>
          <td>${p.date || '-'}</td>
          <td>${_escPurchase(p.vendorName)}</td>
          <td style="text-align:right"><strong>${_fmtRp(p.amount)}</strong></td>
          <td><code style="font-size:11px">${_escPurchase(bankLabel)}</code></td>
          <td>${_escPurchase(p.ref || '-')}</td>
          <td style="font-size:12px">${allocList || '-'}</td>
        </tr>`;
      }).join('')}
      </tbody>
    </table>`;
}

let _editingPayId = null;

function showPurchasePaymentModal(id) {
  _editingPayId = id || null;
  // Reset vendor select and bills list
  document.getElementById('payVendorSelect').innerHTML = _vendorOptions('');
  document.getElementById('payPaymentCoa').innerHTML   = _coaOptsPurchase('1-1110', 'kas-bank');
  document.getElementById('payDate').value    = _todayStr();
  document.getElementById('payAmount').value  = '';
  document.getElementById('payRef').value     = '';
  document.getElementById('payNotes').value   = '';
  document.getElementById('payBillsList').innerHTML =
    '<p style="color:#6b7280;font-size:13px">Pilih vendor untuk melihat tagihan outstanding.</p>';
  document.getElementById('purchasePaymentModal').style.display = 'flex';
  if (typeof feather !== 'undefined') feather.replace();
}

function closePurchasePaymentModal() {
  document.getElementById('purchasePaymentModal').style.display = 'none';
  _editingPayId = null;
}

function onPaymentVendorChange() {
  const vendorId = document.getElementById('payVendorSelect')?.value || '';
  const listEl   = document.getElementById('payBillsList');
  if (!listEl) return;
  if (!vendorId) {
    listEl.innerHTML = '<p style="color:#6b7280;font-size:13px">Pilih vendor untuk melihat tagihan outstanding.</p>';
    return;
  }
  const outBills = PurchaseState.bills
    .filter(b => b.vendorId === vendorId && (b.status === 'outstanding' || b.status === 'partial'))
    .sort((a, b) => (a.date || '').localeCompare(b.date || ''));

  if (!outBills.length) {
    listEl.innerHTML = '<p style="color:#10b981;font-size:13px">✓ Tidak ada tagihan outstanding untuk vendor ini.</p>';
    return;
  }
  const totalSisa = outBills.reduce((s, b) => s + (b.total - (b.paidAmount || 0)), 0);
  listEl.innerHTML = `
    <p style="font-size:13px;font-weight:600;margin-bottom:8px">
      Tagihan Outstanding — sisa: <strong>${_fmtRp(totalSisa)}</strong>
    </p>
    <div class="table-card" style="max-height:220px;overflow-y:auto">
      <table style="width:100%;font-size:13px">
        <thead><tr>
          <th style="width:32px">
            <input type="checkbox" id="checkAllBills" checked onchange="toggleAllBillChecks(this.checked)" />
          </th>
          <th>Nomor Bill</th><th>Tanggal</th>
          <th style="text-align:right">Total</th>
          <th style="text-align:right">Dibayar</th>
          <th style="text-align:right">Sisa</th>
        </tr></thead>
        <tbody>
        ${outBills.map(b => {
          const sisa = (b.total || 0) - (b.paidAmount || 0);
          return `<tr>
            <td><input type="checkbox" class="bill-pay-check" data-bill="${b.id}" data-sisa="${sisa}" checked /></td>
            <td><code>${_escPurchase(b.id)}</code></td>
            <td>${b.date || '-'}</td>
            <td style="text-align:right">${_fmtRp(b.total)}</td>
            <td style="text-align:right">${_fmtRp(b.paidAmount)}</td>
            <td style="text-align:right;font-weight:600;color:#f59e0b">${_fmtRp(sisa)}</td>
          </tr>`;
        }).join('')}
        </tbody>
      </table>
    </div>`;
}

function toggleAllBillChecks(checked) {
  document.querySelectorAll('.bill-pay-check').forEach(cb => { cb.checked = checked; });
}

function savePaymentFromModal() {
  const vendorId   = document.getElementById('payVendorSelect').value;
  const date       = document.getElementById('payDate').value;
  const paymentCoa = document.getElementById('payPaymentCoa').value;
  const amount     = parseFloat(document.getElementById('payAmount').value) || 0;
  const ref        = document.getElementById('payRef').value.trim();
  const notes      = document.getElementById('payNotes').value.trim();

  if (!vendorId)   { showToast('Pilih vendor', 'error'); return; }
  if (!date)       { showToast('Tanggal wajib diisi', 'error'); return; }
  if (!paymentCoa) { showToast('Pilih akun pembayaran', 'error'); return; }
  if (amount <= 0) { showToast('Jumlah bayar harus lebih dari 0', 'error'); return; }

  const vendor = PurchaseState.vendors.find(v => v.id === vendorId);
  if (!vendor) { showToast('Vendor tidak ditemukan', 'error'); return; }

  // Collect checked bills
  const checked = Array.from(document.querySelectorAll('.bill-pay-check:checked'))
    .map(cb => ({ billId: cb.dataset.bill, sisa: parseFloat(cb.dataset.sisa) || 0 }));
  if (!checked.length) { showToast('Pilih minimal 1 tagihan', 'error'); return; }

  const totalSisa = checked.reduce((s, c) => s + c.sisa, 0);
  if (amount > totalSisa + 0.01) {
    showToast(`Jumlah bayar ${_fmtRp(amount)} melebihi sisa tagihan ${_fmtRp(totalSisa)}`, 'error');
    return;
  }

  // FIFO allocation
  const allocations = [];
  let remaining = amount;
  for (const c of checked) {
    if (remaining <= 0) break;
    const alloc = Math.min(remaining, c.sisa);
    allocations.push({ billId: c.billId, allocated: Math.round(alloc) });
    remaining -= alloc;
  }

  // Update bills
  const payId = _nextPayNumber();
  allocations.forEach(a => {
    const bill = PurchaseState.bills.find(b => b.id === a.billId);
    if (!bill) return;
    bill.paidAmount = (bill.paidAmount || 0) + a.allocated;
    bill.payments   = bill.payments || [];
    bill.payments.push({ paymentId: payId, amount: a.allocated, date });
    _updateBillStatus(bill);
  });

  const payment = {
    id: payId, date, vendorId, vendorName: vendor.name,
    payableCoa: vendor.payableCoa, paymentCoa, amount, ref, notes,
    allocations, journalId: null, journalEntry: null
  };
  PurchaseState.payments.push(payment);

  generatePaymentJournal(payment);
  savePurchaseData();
  _rebuildAfterPurchase();
  closePurchasePaymentModal();
  renderPaymentPage();
  showToast(`Payment ${payId} disimpan ✓`, 'success');
}

// ============================================================
// ===== LAPORAN VENDOR BILL =====
// ============================================================
function renderPurchaseReportPage() {
  const filterVendor = document.getElementById('reportFilterVendor')?.value || '';
  const filterStatus = document.getElementById('reportFilterStatus')?.value || '';
  const filterFrom   = document.getElementById('reportFilterFrom')?.value   || '';
  const filterTo     = document.getElementById('reportFilterTo')?.value     || '';

  // Populate vendor filter
  const vendorSel = document.getElementById('reportFilterVendor');
  if (vendorSel) {
    const cur = vendorSel.value;
    vendorSel.innerHTML = '<option value="">Semua Vendor</option>' +
      PurchaseState.vendors.map(v => `<option value="${v.id}" ${v.id===cur?'selected':''}>${_escPurchase(v.name)}</option>`).join('');
  }

  let bills = PurchaseState.bills.filter(b => b.status !== 'draft');
  if (filterVendor) bills = bills.filter(b => b.vendorId === filterVendor);
  if (filterStatus) bills = bills.filter(b => b.status  === filterStatus);
  if (filterFrom)   bills = bills.filter(b => b.date    >= filterFrom);
  if (filterTo)     bills = bills.filter(b => b.date    <= filterTo);
  bills.sort((a, b) => (b.date || '').localeCompare(a.date || ''));

  // KPI
  const totalTagihan     = bills.reduce((s, b) => s + (b.total || 0), 0);
  const totalLunas       = bills.filter(b => b.status === 'paid').reduce((s, b) => s + (b.total || 0), 0);
  const totalOutstanding = bills.filter(b => b.status !== 'paid').reduce((s, b) => s + ((b.total||0) - (b.paidAmount||0)), 0);
  const kpiEl = document.getElementById('purchaseReportKpi');
  if (kpiEl) {
    kpiEl.innerHTML = `
      <div class="kpi-card"><div class="kpi-label">Total Tagihan</div><div class="kpi-value">${_fmtRp(totalTagihan)}</div></div>
      <div class="kpi-card"><div class="kpi-label">Sudah Lunas</div><div class="kpi-value" style="color:#10b981">${_fmtRp(totalLunas)}</div></div>
      <div class="kpi-card"><div class="kpi-label">Belum Lunas</div><div class="kpi-value" style="color:#f59e0b">${_fmtRp(totalOutstanding)}</div></div>`;
  }

  const wrap = document.getElementById('purchaseReportTableWrap');
  if (!wrap) return;
  if (!bills.length) {
    wrap.innerHTML = `<div style="padding:48px;text-align:center;color:#6b7280">Tidak ada data untuk filter ini.</div>`;
    return;
  }
  const today = _todayStr();
  wrap.innerHTML = `
    <table class="data-table">
      <thead><tr>
        <th>Nomor Bill</th><th>Tanggal</th><th>Vendor</th><th>Jatuh Tempo</th>
        <th style="text-align:right">Subtotal</th>
        <th style="text-align:right">Total</th>
        <th style="text-align:right">Dibayar</th>
        <th style="text-align:right">Sisa</th>
        <th>Status</th>
      </tr></thead>
      <tbody>
      ${bills.map(b => {
        const sisa    = (b.total || 0) - (b.paidAmount || 0);
        const overdue = b.dueDate && b.dueDate < today && b.status !== 'paid';
        return `<tr>
          <td><code>${_escPurchase(b.id)}</code></td>
          <td>${b.date || '-'}</td>
          <td>${_escPurchase(b.vendorName)}</td>
          <td style="${overdue ? 'color:#ef4444;font-weight:600' : ''}">${b.dueDate || '-'}${overdue ? ' ⚠' : ''}</td>
          <td style="text-align:right">${_fmtRp(b.subtotal)}</td>
          <td style="text-align:right"><strong>${_fmtRp(b.total)}</strong></td>
          <td style="text-align:right">${_fmtRp(b.paidAmount)}</td>
          <td style="text-align:right${sisa > 0 ? ';color:#f59e0b;font-weight:600' : ''}">${_fmtRp(sisa)}</td>
          <td>${_billStatusBadge(b.status)}</td>
        </tr>`;
      }).join('')}
      </tbody>
    </table>`;
}

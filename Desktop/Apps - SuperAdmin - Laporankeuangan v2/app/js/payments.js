/**
 * PAYMENTS.JS — Payments Management (Customer Receipt + Supplier Disbursement)
 * via backend FastAPI (/api/v1/payments)
 */

// ─── State ────────────────────────────────────────────────────
const PaymentsState = {
  payments: [],
  activeTab: 'list', // list | new
};

// ─── Formatters ───────────────────────────────────────────────
function _fmtPay(n) {
  return 'Rp ' + Math.round(n || 0).toLocaleString('id-ID');
}
function _escPay(s) {
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

const PAY_TYPE_LABELS = {
  receipt:           'Penerimaan',
  disbursement:      'Pembayaran',
  customer_refund:   'Refund Customer',
  supplier_refund:   'Refund Supplier',
};

const PAY_STATUS_CLASS = {
  posted: 'badge-success',
  void:   'badge-danger',
  draft:  'badge-secondary',
};

// ─── Load data ────────────────────────────────────────────────
async function loadPaymentsData(params = {}) {
  try {
    const data = await Api.payments.list({ limit: 100, ...params });
    PaymentsState.payments = data.items || data || [];
  } catch (e) {
    showToast('Gagal memuat data pembayaran: ' + e.message, 'error');
  }
}

// ─── Render: Main page ────────────────────────────────────────
async function renderPaymentsPage() {
  if (!document.getElementById('page-payments')) return;

  await loadPaymentsData();
  renderPaymentsList();
  if (typeof feather !== 'undefined') feather.replace();
}

// ─── Render: Payments list ────────────────────────────────────
function renderPaymentsList() {
  const wrap = document.getElementById('paymentsTableWrap');
  if (!wrap) return;

  const pays = PaymentsState.payments;
  if (!pays.length) {
    wrap.innerHTML = `<div class="empty-state">
      <i data-feather="dollar-sign" style="width:48px;height:48px;opacity:.3"></i>
      <p>Belum ada pembayaran.</p>
      <button class="btn btn-primary" onclick="showPaymentModal(null)">
        <i data-feather="plus"></i> Buat Pembayaran
      </button>
    </div>`;
    if (typeof feather !== 'undefined') feather.replace();
    return;
  }

  // KPI summary
  const receipts     = pays.filter(p => p.payment_type === 'receipt' && p.status !== 'void');
  const disbursements = pays.filter(p => p.payment_type === 'disbursement' && p.status !== 'void');
  const totalReceipt = receipts.reduce((s, p) => s + parseFloat(p.amount || 0), 0);
  const totalDisb    = disbursements.reduce((s, p) => s + parseFloat(p.amount || 0), 0);

  wrap.innerHTML = `
    <div class="kpi-cards" style="margin-bottom:16px">
      <div class="kpi-card">
        <div class="kpi-label">Total Penerimaan</div>
        <div class="kpi-value" style="color:var(--success)">${_fmtPay(totalReceipt)}</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Total Pembayaran</div>
        <div class="kpi-value" style="color:var(--danger)">${_fmtPay(totalDisb)}</div>
      </div>
    </div>
    <table class="data-table">
      <thead><tr>
        <th>No. Pembayaran</th>
        <th>Tanggal</th>
        <th>Tipe</th>
        <th>Keterangan</th>
        <th class="text-right">Jumlah</th>
        <th>Status</th>
        <th>Aksi</th>
      </tr></thead>
      <tbody>
        ${pays.map(p => `<tr>
          <td><strong>${_escPay(p.payment_no)}</strong></td>
          <td>${p.payment_date || '-'}</td>
          <td>${PAY_TYPE_LABELS[p.payment_type] || _escPay(p.payment_type)}</td>
          <td>${_escPay(p.description || p.notes || '-')}</td>
          <td class="text-right"><strong>${_fmtPay(p.amount)}</strong></td>
          <td><span class="badge ${PAY_STATUS_CLASS[p.status] || 'badge-secondary'}">${_escPay(p.status)}</span></td>
          <td style="display:flex;gap:4px">
            <button class="btn btn-sm btn-outline" onclick="viewPaymentDetail('${p.id}')">
              <i data-feather="eye"></i>
            </button>
            ${p.status !== 'void' ? `<button class="btn btn-sm btn-danger" onclick="voidPayment('${p.id}','${_escPay(p.payment_no)}')">Void</button>` : ''}
          </td>
        </tr>`).join('')}
      </tbody>
    </table>`;
  if (typeof feather !== 'undefined') feather.replace();
}

// ─── View detail ──────────────────────────────────────────────
async function viewPaymentDetail(id) {
  let pay;
  try { pay = await Api.payments.get(id); } catch (e) { showToast(e.message, 'error'); return; }

  const html = `
    <div class="modal-backdrop" id="payDetailModal" onclick="if(event.target===this)document.getElementById('payDetailModal').remove()">
      <div class="modal-dialog" style="max-width:520px">
        <div class="modal-header">
          <h3>Detail Pembayaran — ${_escPay(pay.payment_no)}</h3>
          <button class="modal-close" onclick="document.getElementById('payDetailModal').remove()">×</button>
        </div>
        <div class="modal-body">
          <table class="data-table" style="font-size:14px">
            <tr><td style="width:40%"><strong>No. Pembayaran</strong></td><td>${_escPay(pay.payment_no)}</td></tr>
            <tr><td><strong>Tipe</strong></td><td>${PAY_TYPE_LABELS[pay.payment_type] || pay.payment_type}</td></tr>
            <tr><td><strong>Tanggal</strong></td><td>${pay.payment_date || '-'}</td></tr>
            <tr><td><strong>Jumlah</strong></td><td><strong>${_fmtPay(pay.amount)}</strong></td></tr>
            <tr><td><strong>Status</strong></td><td><span class="badge ${PAY_STATUS_CLASS[pay.status] || ''}">${pay.status}</span></td></tr>
            <tr><td><strong>Keterangan</strong></td><td>${_escPay(pay.description || pay.notes || '-')}</td></tr>
          </table>
          ${pay.applications?.length ? `
            <h4 style="margin-top:16px">Aplikasi ke Invoice</h4>
            <table class="data-table" style="font-size:13px">
              <thead><tr><th>Invoice</th><th class="text-right">Jumlah</th></tr></thead>
              <tbody>
                ${pay.applications.map(a => `<tr>
                  <td>${_escPay(a.invoice_no || a.invoice_id)}</td>
                  <td class="text-right">${_fmtPay(a.amount)}</td>
                </tr>`).join('')}
              </tbody>
            </table>` : ''}
        </div>
        <div class="modal-footer">
          <button class="btn btn-outline" onclick="document.getElementById('payDetailModal').remove()">Tutup</button>
        </div>
      </div>
    </div>`;
  document.body.insertAdjacentHTML('beforeend', html);
  if (typeof feather !== 'undefined') feather.replace();
}

// ─── Void payment ─────────────────────────────────────────────
async function voidPayment(id, no) {
  if (!confirm(`Void pembayaran ${no}? Tindakan ini tidak dapat dibatalkan.`)) return;
  try {
    await Api.payments.void(id);
    showToast(`Pembayaran ${no} berhasil di-void`, 'success');
    await renderPaymentsPage();
  } catch (e) {
    showToast(e.message, 'error');
  }
}

// ─── Modal: New payment ───────────────────────────────────────
// Form state for allocations (multi-invoice)
let _payAllocations = [];
function _genAllocId() { return 'a_' + Date.now() + '_' + Math.random().toString(36).slice(2, 5); }

async function showPaymentModal(id) {
  // Pre-load reference data (parallel)
  const [customers, suppliers, accounts] = await Promise.all([
    Api.customers.list().catch(() => []),
    Api.suppliers.list().catch(() => []),
    Api.accounts.list().catch(() => []),
  ]);
  const cashAccounts = accounts.filter(a => a.is_cash && a.is_active);
  window.__payCache = { customers, suppliers, cashAccounts };

  _payAllocations = [{tempId: _genAllocId(), invoiceId: '', amount: 0}];

  const cashOptions = cashAccounts
    .sort((a,b) => a.code.localeCompare(b.code))
    .map(a => `<option value="${a.id}">${_escPay(a.code)} — ${_escPay(a.name)}</option>`).join('');

  document.getElementById('paymentFormTitle').textContent = 'Buat Pembayaran Baru';
  document.getElementById('paymentFormSaveBtn').innerHTML = '💾 Simpan';
  const body = document.getElementById('paymentFormBody');
  if (!body) { showToast('Form pembayaran tidak tersedia', 'error'); return; }
  body.innerHTML = `
    <div class="form-row">
      <div class="form-group" style="flex:1"><label>Direction *</label>
        <select class="form-control" id="payDirection" onchange="onPayDirectionChange()">
          <option value="receipt">📥 Receipt (Penerimaan dari Customer)</option>
          <option value="disbursement">📤 Disbursement (Bayar Supplier)</option>
          <option value="customer_refund">↩️ Customer Refund (Kembalikan ke Customer)</option>
          <option value="supplier_refund">↪️ Supplier Refund (Terima dari Supplier)</option>
        </select></div>
      <div class="form-group" style="flex:1"><label>Tanggal *</label>
        <input class="form-control" id="payDate" type="date" value="${new Date().toISOString().slice(0,10)}"></div>
    </div>

    <div class="form-row">
      <div class="form-group" style="flex:1"><label id="payPartyLabel">Customer *</label>
        <select class="form-control" id="payParty"><option value="">— Pilih —</option></select></div>
      <div class="form-group" style="flex:1"><label>Akun Kas *</label>
        <select class="form-control" id="payCash">
          ${cashAccounts.length === 0
            ? '<option value="">⚠ Belum ada akun is_cash=true</option>'
            : '<option value="">— Pilih akun kas —</option>' + cashOptions}
        </select>
        ${cashAccounts.length === 0
          ? '<small style="color:#b91c1c">Set <code>is_cash=true</code> di akun via COA</small>'
          : ''}
      </div>
    </div>

    <div class="form-row">
      <div class="form-group" style="flex:1"><label>Jumlah *</label>
        <input class="form-control" id="payAmount" type="number" min="0" step="0.01" oninput="updateAllocationSum()"></div>
      <div class="form-group" style="flex:1"><label>Reference</label>
        <input class="form-control" id="payRef" placeholder="No. cek / no. transfer / dst"></div>
    </div>

    <div id="payAllocSection" class="form-group">
      <label>
        <span id="payAllocTitle">Alokasi ke Invoice</span>
        <small style="color:#6b7280">(opsional — sisa = unallocated credit ke party)</small>
      </label>
      <div id="payAllocLines"></div>
      <button type="button" class="btn btn-sm btn-outline" onclick="addPayAllocation()" style="margin-top:6px">+ Tambah Alokasi</button>
      <div id="payAllocSummary" style="font-size:12px;color:#6b7280;margin-top:4px"></div>
    </div>

    <div class="form-group"><label>Catatan</label>
      <input class="form-control" id="payDesc" placeholder="Opsional"></div>

    <div class="form-group">
      <label><input type="checkbox" id="payPostNow" checked> Post langsung (kalau di-uncheck → simpan sebagai Draft, post manual nanti)</label>
    </div>

    <div id="payErr" class="form-error" style="display:none"></div>
  `;
  navigateTo('payment-form');
  onPayDirectionChange();
  if (typeof feather !== 'undefined') feather.replace();
}

function savePayFromForm() { return savePayment(); }

function closePayModal() {
  _payAllocations = [];
  if (typeof navigateTo === 'function') navigateTo('payments');
}

// Triggered when direction picker changes — refresh party dropdown + alloc section
function onPayDirectionChange() {
  const direction = document.getElementById('payDirection').value;
  const isCustomer = ['receipt', 'customer_refund'].includes(direction);
  const isRefund = ['customer_refund', 'supplier_refund'].includes(direction);
  const cache = window.__payCache || {};

  document.getElementById('payPartyLabel').textContent = isCustomer ? 'Customer *' : 'Supplier *';
  const partyEl = document.getElementById('payParty');
  const list = isCustomer ? (cache.customers || []) : (cache.suppliers || []);
  partyEl.innerHTML = '<option value="">— Pilih —</option>' +
    list.sort((a,b)=>a.code.localeCompare(b.code))
        .map(p => `<option value="${p.id}">${_escPay(p.code)} — ${_escPay(p.name)}</option>`).join('');
  partyEl.onchange = _refreshAllocationInvoiceOptions;

  // Refunds don't allow allocations (per backend schema)
  document.getElementById('payAllocSection').style.display = isRefund ? 'none' : '';
  document.getElementById('payAllocTitle').textContent = isCustomer ? 'Alokasi ke Sales Invoice' : 'Alokasi ke Purchase Invoice';
  _renderPayAllocLines();
}

async function _refreshAllocationInvoiceOptions() {
  const direction = document.getElementById('payDirection').value;
  const isCustomer = ['receipt', 'customer_refund'].includes(direction);
  const partyId = document.getElementById('payParty').value;
  if (!partyId) { window.__payInvoices = []; _renderPayAllocLines(); return; }
  try {
    if (isCustomer) {
      const list = await Api.salesInvoices.list({customer_id: partyId});
      window.__payInvoices = list.filter(i => ['posted','partial','outstanding'].includes(i.status) && Number(i.outstanding ?? (Number(i.total)-Number(i.paid_amount||0))) > 0);
    } else {
      const list = await Api.purchaseInvoices.list({supplier_id: partyId});
      window.__payInvoices = list.filter(i => ['posted','partial','outstanding'].includes(i.status) && Number(i.outstanding ?? (Number(i.total)-Number(i.paid_amount||0))) > 0);
    }
  } catch { window.__payInvoices = []; }
  _renderPayAllocLines();
}

function _renderPayAllocLines() {
  const wrap = document.getElementById('payAllocLines');
  if (!wrap) return;
  const invoices = window.__payInvoices || [];
  const invOpts = invoices.map(i => {
    const outstanding = Number(i.outstanding ?? (Number(i.total) - Number(i.paid_amount || 0)));
    return `<option value="${i.id}" data-outstanding="${outstanding}">${_escPay(i.invoice_no)} — sisa ${_fmtPay(outstanding)}</option>`;
  }).join('');

  wrap.innerHTML = _payAllocations.map((a, idx) => `
    <div class="form-row" style="margin-bottom:6px;align-items:flex-end">
      <div class="form-group" style="flex:3;margin-bottom:0">
        ${idx === 0 ? '<small style="color:#6b7280">Invoice</small>' : ''}
        <select class="form-control" onchange="updatePayAllocation('${a.tempId}', 'invoiceId', this.value); _autofillPayAllocAmount('${a.tempId}', this)">
          <option value="">— Pilih invoice —</option>${invOpts}
        </select></div>
      <div class="form-group" style="flex:1;margin-bottom:0">
        ${idx === 0 ? '<small style="color:#6b7280">Amount</small>' : ''}
        <input class="form-control" type="number" min="0" step="0.01" value="${a.amount || ''}"
               oninput="updatePayAllocation('${a.tempId}', 'amount', this.value); updateAllocationSum()"></div>
      <div style="margin-bottom:0">
        <button type="button" class="btn btn-sm btn-danger" onclick="removePayAllocation('${a.tempId}')" ${_payAllocations.length<=1?'disabled':''}>×</button>
      </div>
    </div>`).join('');
  updateAllocationSum();
}

function _autofillPayAllocAmount(tempId, selEl) {
  // When user picks an invoice, prefill amount with outstanding (if not yet set)
  const a = _payAllocations.find(x => x.tempId === tempId);
  if (!a) return;
  const opt = selEl.options[selEl.selectedIndex];
  const outstanding = Number(opt?.dataset?.outstanding || 0);
  if (outstanding > 0 && (!a.amount || a.amount <= 0)) {
    a.amount = outstanding;
    _renderPayAllocLines();
  }
}

function addPayAllocation() {
  _payAllocations.push({tempId: _genAllocId(), invoiceId: '', amount: 0});
  _renderPayAllocLines();
}
function removePayAllocation(tempId) {
  _payAllocations = _payAllocations.filter(x => x.tempId !== tempId);
  _renderPayAllocLines();
}
function updatePayAllocation(tempId, key, value) {
  const a = _payAllocations.find(x => x.tempId === tempId);
  if (a) a[key] = key === 'amount' ? Number(value) : value;
}

function updateAllocationSum() {
  const totalPay = parseFloat(document.getElementById('payAmount')?.value) || 0;
  const totalAlloc = _payAllocations.reduce((s, a) => s + (Number(a.amount) || 0), 0);
  const diff = totalPay - totalAlloc;
  const sumEl = document.getElementById('payAllocSummary');
  if (!sumEl) return;
  if (totalAlloc > totalPay) {
    sumEl.innerHTML = `<strong style="color:#b91c1c">⚠ Total alokasi (${_fmtPay(totalAlloc)}) melebihi jumlah payment (${_fmtPay(totalPay)})</strong>`;
  } else if (totalAlloc === totalPay && totalAlloc > 0) {
    sumEl.innerHTML = `<strong style="color:#15803d">✓ Fully allocated: ${_fmtPay(totalAlloc)}</strong>`;
  } else {
    sumEl.innerHTML = `Allocated: ${_fmtPay(totalAlloc)} / ${_fmtPay(totalPay)} · Sisa unallocated: <strong>${_fmtPay(diff)}</strong>`;
  }
}

async function savePayment() {
  const errEl  = document.getElementById('payErr');
  errEl.style.display = 'none';

  const direction = document.getElementById('payDirection').value;
  const isCustomer = ['receipt', 'customer_refund'].includes(direction);
  const isRefund = ['customer_refund', 'supplier_refund'].includes(direction);

  const date    = document.getElementById('payDate').value;
  const partyId = document.getElementById('payParty').value;
  const cashId  = document.getElementById('payCash').value;
  const amount  = parseFloat(document.getElementById('payAmount').value);
  const ref     = document.getElementById('payRef').value.trim();
  const notes   = document.getElementById('payDesc').value.trim();
  const postNow = document.getElementById('payPostNow').checked;

  if (!direction || !date || !partyId || !cashId || !amount || amount <= 0) {
    errEl.textContent = 'Direction, Tanggal, Party, Akun Kas, dan Jumlah > 0 wajib diisi';
    errEl.style.display = 'block'; return;
  }

  // Build applications array (only for non-refund)
  const apps = [];
  if (!isRefund) {
    for (const a of _payAllocations) {
      if (!a.invoiceId || !(Number(a.amount) > 0)) continue;
      apps.push(isCustomer
        ? { sales_invoice_id: a.invoiceId, amount: Number(a.amount) }
        : { purchase_invoice_id: a.invoiceId, amount: Number(a.amount) });
    }
    const allocSum = apps.reduce((s, a) => s + a.amount, 0);
    if (allocSum > amount + 0.001) {
      errEl.textContent = `Total alokasi (${allocSum}) melebihi jumlah payment (${amount})`;
      errEl.style.display = 'block'; return;
    }
    if (apps.length === 0) {
      errEl.textContent = 'Untuk receipt/disbursement, minimal 1 alokasi invoice wajib (kecuali jika belum ada invoice)';
      errEl.style.display = 'block'; return;
    }
  }

  const body = {
    payment_date: date,
    direction,
    amount,
    cash_account_id: cashId,
    reference: ref || null,
    notes: notes || null,
    applications: apps,
  };
  if (isCustomer) body.customer_id = partyId;
  else            body.supplier_id = partyId;

  try {
    await Api.payments.create(body, { post_now: postNow });
    showToast(postNow ? 'Pembayaran posted' : 'Pembayaran disimpan sebagai draft', 'success');
    closePayModal();
    await renderPaymentsPage();
    // Refresh sales/purchase state if applicable
    if (typeof BackendLoader !== 'undefined') {
      if (isCustomer) await BackendLoader.loadSalesInvoices();
      else            await BackendLoader.loadPurchaseBills();
    }
  } catch (e) {
    errEl.textContent = e.message; errEl.style.display = 'block';
  }
}

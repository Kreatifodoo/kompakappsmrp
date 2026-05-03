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
async function showPaymentModal(id) {
  const html = `
    <div class="modal-backdrop" id="payNewModal" onclick="if(event.target===this)closePayModal()">
      <div class="modal-dialog" style="max-width:520px">
        <div class="modal-header">
          <h3>Buat Pembayaran Baru</h3>
          <button class="modal-close" onclick="closePayModal()">×</button>
        </div>
        <div class="modal-body">
          <div class="form-group"><label>Tipe Pembayaran *</label>
            <select class="form-control" id="payType">
              <option value="receipt">Penerimaan (Customer)</option>
              <option value="disbursement">Pembayaran (Supplier)</option>
              <option value="customer_refund">Refund Customer</option>
              <option value="supplier_refund">Refund Supplier</option>
            </select></div>
          <div class="form-group"><label>Tanggal *</label>
            <input class="form-control" id="payDate" type="date" value="${new Date().toISOString().slice(0,10)}"></div>
          <div class="form-group"><label>Jumlah *</label>
            <input class="form-control" id="payAmount" type="number" min="0" placeholder="0"></div>
          <div class="form-group"><label>Keterangan</label>
            <input class="form-control" id="payDesc" placeholder="Opsional"></div>
          <div id="payErr" class="form-error" style="display:none"></div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-outline" onclick="closePayModal()">Batal</button>
          <button class="btn btn-primary" onclick="savePayment()">Simpan</button>
        </div>
      </div>
    </div>`;
  document.body.insertAdjacentHTML('beforeend', html);
  if (typeof feather !== 'undefined') feather.replace();
}

function closePayModal() {
  document.getElementById('payNewModal')?.remove();
}

async function savePayment() {
  const amount = parseFloat(document.getElementById('payAmount').value);
  const date   = document.getElementById('payDate').value;
  const errEl  = document.getElementById('payErr');
  if (!amount || amount <= 0) { errEl.textContent='Jumlah harus lebih dari 0'; errEl.style.display='block'; return; }
  if (!date)                  { errEl.textContent='Tanggal wajib diisi'; errEl.style.display='block'; return; }

  const body = {
    payment_type: document.getElementById('payType').value,
    payment_date: date,
    amount,
    description: document.getElementById('payDesc').value.trim() || null,
  };

  try {
    await Api.payments.create(body);
    showToast('Pembayaran berhasil disimpan', 'success');
    closePayModal();
    await renderPaymentsPage();
  } catch (e) {
    errEl.textContent = e.message; errEl.style.display = 'block';
  }
}

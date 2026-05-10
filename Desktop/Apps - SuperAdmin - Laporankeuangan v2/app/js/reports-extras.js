/**
 * REPORTS-EXTRAS.JS — backend-driven reports (Aged AR/AP, Statements, Bank Rec, PPN)
 *                    + Async Export (PDF/Excel) flow
 *
 * Page renderers:
 *   renderAgedARPage()        → page-rep-aged-ar
 *   renderAgedAPPage()        → page-rep-aged-ap
 *   renderCustomerStatementPage() → page-rep-cust-stmt
 *   renderSupplierStatementPage() → page-rep-supp-stmt
 *   renderBankReconciliationPage()→ page-rep-bank-rec
 *   renderPPNReportPage()     → page-rep-ppn
 *
 * Async export: pakai backend `submitAsync` → poll `jobStatus` → download via
 * `downloadUrl` (atau via Realtime event `report.ready`).
 */

// ─── Helpers ──────────────────────────────────────────────────
function _escRep(s) {
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}
function _fmtRep(n) {
  if (n === null || n === undefined) return '-';
  return 'Rp ' + Math.round(Number(n) || 0).toLocaleString('id-ID');
}
function _fmtDateRep(d) { return d ? String(d).slice(0, 10) : '-'; }

function _todayISO() { return new Date().toISOString().slice(0, 10); }
function _firstOfMonth() {
  const d = new Date(); d.setDate(1);
  return d.toISOString().slice(0, 10);
}

function _badge(text, color) {
  return `<span style="background:${color};color:#fff;padding:1px 8px;border-radius:999px;font-size:10px;font-weight:600">${_escRep(text)}</span>`;
}

// ═══════════════════════════════════════════════════════════════════
// ASYNC EXPORT (PDF / Excel) — reusable across all reports
// ═══════════════════════════════════════════════════════════════════
async function exportReportAsync(reportType, params, format /* 'pdf'|'excel' */) {
  showToast(`📨 Submitting ${format.toUpperCase()} export job...`, 'info');
  let job;
  try {
    job = await Api.reports.submitAsync(reportType, { params: params || {}, format });
  } catch (e) {
    showToast('Submit failed: ' + e.message, 'error');
    return;
  }
  const jobId = job.job_id || job.id;
  if (!jobId) { showToast('No job ID returned', 'error'); return; }
  showToast(`Job ${jobId.slice(0,8)} queued. Polling...`, 'info');

  // Poll status
  const maxPoll = 30; // 30 × 2s = 60s
  for (let i = 0; i < maxPoll; i++) {
    await new Promise(r => setTimeout(r, 2000));
    const status = await Api.reports.jobStatus(jobId).catch(() => null);
    if (!status) continue;
    if (status.status === 'done' || status.state === 'success' || status.state === 'completed') {
      const url = Api.reports.downloadUrl(jobId, format);
      window.open(url, '_blank');
      showToast(`✓ Download dimulai (${format.toUpperCase()})`, 'success');
      return;
    }
    if (status.status === 'failed' || status.state === 'failure') {
      showToast(`❌ Job gagal: ${status.error || 'unknown'}`, 'error');
      return;
    }
  }
  showToast('⏱ Timeout — coba refresh halaman dan cek log', 'warning');
}

// Subscribe to realtime report.ready (auto-toast when async report finishes)
if (typeof Realtime !== 'undefined') {
  Realtime.on('report.ready', (d) => {
    if (d?.download_url) {
      showToast(`✓ ${d.report_type || 'Report'} siap — <a href="${_escRep(d.download_url)}" target="_blank">download</a>`, 'success');
    }
  });
}

// ═══════════════════════════════════════════════════════════════════
// 1. AGED RECEIVABLES (#page-rep-aged-ar)
// ═══════════════════════════════════════════════════════════════════
async function renderAgedARPage() {
  const wrap = document.getElementById('page-rep-aged-ar');
  if (!wrap) return;
  const today = _todayISO();
  wrap.innerHTML = `
    <div class="page-header">
      <h2>Aged Receivables (Aged AR)</h2>
      <p class="page-subtitle">Outstanding sales invoice di-bucket berdasar hari overdue.</p>
    </div>
    <div class="report-filter-bar" style="margin-bottom:12px;display:flex;gap:8px;align-items:end;flex-wrap:wrap">
      <div class="form-group" style="margin:0"><label>Per Tanggal</label>
        <input type="date" id="arAsOf" class="form-control" value="${today}"></div>
      <button class="btn btn-primary" onclick="loadAgedAR()">Tampilkan</button>
      <span style="flex:1"></span>
      <button class="btn btn-outline" onclick="exportReportAsync('aged-receivables', {as_of: document.getElementById('arAsOf').value}, 'excel')">📊 Export Excel</button>
      <button class="btn btn-outline" onclick="exportReportAsync('aged-receivables', {as_of: document.getElementById('arAsOf').value}, 'pdf')">📄 Export PDF</button>
    </div>
    <div id="arResult"><div class="empty-state">Klik Tampilkan untuk memuat.</div></div>
  `;
  await loadAgedAR();
}

async function loadAgedAR() {
  const out = document.getElementById('arResult'); if (!out) return;
  const asOf = document.getElementById('arAsOf').value;
  out.innerHTML = '<div class="empty-state">Memuat…</div>';
  try {
    const r = await Api.reports.agedReceivables({as_of: asOf});
    if (!r.lines.length) { out.innerHTML = '<div class="empty-state">✅ Tidak ada outstanding receivables.</div>'; return; }
    const totals = r.totals || {};
    out.innerHTML = `
      <table class="data-table">
        <thead><tr>
          <th>Customer</th><th class="text-right">Belum Jatuh Tempo</th>
          <th class="text-right">1-30 hari</th><th class="text-right">31-60 hari</th>
          <th class="text-right">61-90 hari</th><th class="text-right">&gt;90 hari</th>
          <th class="text-right">Total</th><th class="text-center">#Inv</th>
        </tr></thead>
        <tbody>${r.lines.map(l => `<tr>
          <td><strong>${_escRep(l.code)}</strong> — ${_escRep(l.name)}</td>
          <td class="text-right">${_fmtRep(l.buckets.current)}</td>
          <td class="text-right">${_fmtRep(l.buckets.days_1_30)}</td>
          <td class="text-right">${_fmtRep(l.buckets.days_31_60)}</td>
          <td class="text-right" style="color:#f59e0b">${_fmtRep(l.buckets.days_61_90)}</td>
          <td class="text-right" style="color:#b91c1c"><strong>${_fmtRep(l.buckets.days_over_90)}</strong></td>
          <td class="text-right"><strong>${_fmtRep(l.buckets.total)}</strong></td>
          <td class="text-center"><a href="#" onclick="renderCustomerStatementForId('${l.party_id}');return false">${l.invoice_count}</a></td>
        </tr>`).join('')}</tbody>
        <tfoot><tr style="font-weight:bold;background:#f3f4f6">
          <td>TOTAL</td>
          <td class="text-right">${_fmtRep(totals.current)}</td>
          <td class="text-right">${_fmtRep(totals.days_1_30)}</td>
          <td class="text-right">${_fmtRep(totals.days_31_60)}</td>
          <td class="text-right">${_fmtRep(totals.days_61_90)}</td>
          <td class="text-right">${_fmtRep(totals.days_over_90)}</td>
          <td class="text-right">${_fmtRep(totals.total)}</td>
          <td></td>
        </tr></tfoot>
      </table>`;
  } catch (e) { out.innerHTML = `<div class="empty-state error">Gagal: ${_escRep(e.message)}</div>`; }
}

// ═══════════════════════════════════════════════════════════════════
// 2. AGED PAYABLES (#page-rep-aged-ap)
// ═══════════════════════════════════════════════════════════════════
async function renderAgedAPPage() {
  const wrap = document.getElementById('page-rep-aged-ap');
  if (!wrap) return;
  const today = _todayISO();
  wrap.innerHTML = `
    <div class="page-header">
      <h2>Aged Payables (Aged AP)</h2>
      <p class="page-subtitle">Outstanding purchase invoice di-bucket berdasar hari overdue.</p>
    </div>
    <div class="report-filter-bar" style="margin-bottom:12px;display:flex;gap:8px;align-items:end;flex-wrap:wrap">
      <div class="form-group" style="margin:0"><label>Per Tanggal</label>
        <input type="date" id="apAsOf" class="form-control" value="${today}"></div>
      <button class="btn btn-primary" onclick="loadAgedAP()">Tampilkan</button>
      <span style="flex:1"></span>
      <button class="btn btn-outline" onclick="exportReportAsync('aged-payables', {as_of: document.getElementById('apAsOf').value}, 'excel')">📊 Export Excel</button>
      <button class="btn btn-outline" onclick="exportReportAsync('aged-payables', {as_of: document.getElementById('apAsOf').value}, 'pdf')">📄 Export PDF</button>
    </div>
    <div id="apResult"><div class="empty-state">Klik Tampilkan untuk memuat.</div></div>
  `;
  await loadAgedAP();
}

async function loadAgedAP() {
  const out = document.getElementById('apResult'); if (!out) return;
  const asOf = document.getElementById('apAsOf').value;
  out.innerHTML = '<div class="empty-state">Memuat…</div>';
  try {
    const r = await Api.reports.agedPayables({as_of: asOf});
    if (!r.lines.length) { out.innerHTML = '<div class="empty-state">✅ Tidak ada outstanding payables.</div>'; return; }
    const totals = r.totals || {};
    out.innerHTML = `
      <table class="data-table">
        <thead><tr>
          <th>Supplier</th><th class="text-right">Belum Jatuh Tempo</th>
          <th class="text-right">1-30 hari</th><th class="text-right">31-60 hari</th>
          <th class="text-right">61-90 hari</th><th class="text-right">&gt;90 hari</th>
          <th class="text-right">Total</th><th class="text-center">#Inv</th>
        </tr></thead>
        <tbody>${r.lines.map(l => `<tr>
          <td><strong>${_escRep(l.code)}</strong> — ${_escRep(l.name)}</td>
          <td class="text-right">${_fmtRep(l.buckets.current)}</td>
          <td class="text-right">${_fmtRep(l.buckets.days_1_30)}</td>
          <td class="text-right">${_fmtRep(l.buckets.days_31_60)}</td>
          <td class="text-right" style="color:#f59e0b">${_fmtRep(l.buckets.days_61_90)}</td>
          <td class="text-right" style="color:#b91c1c"><strong>${_fmtRep(l.buckets.days_over_90)}</strong></td>
          <td class="text-right"><strong>${_fmtRep(l.buckets.total)}</strong></td>
          <td class="text-center"><a href="#" onclick="renderSupplierStatementForId('${l.party_id}');return false">${l.invoice_count}</a></td>
        </tr>`).join('')}</tbody>
        <tfoot><tr style="font-weight:bold;background:#f3f4f6">
          <td>TOTAL</td>
          <td class="text-right">${_fmtRep(totals.current)}</td>
          <td class="text-right">${_fmtRep(totals.days_1_30)}</td>
          <td class="text-right">${_fmtRep(totals.days_31_60)}</td>
          <td class="text-right">${_fmtRep(totals.days_61_90)}</td>
          <td class="text-right">${_fmtRep(totals.days_over_90)}</td>
          <td class="text-right">${_fmtRep(totals.total)}</td>
          <td></td>
        </tr></tfoot>
      </table>`;
  } catch (e) { out.innerHTML = `<div class="empty-state error">Gagal: ${_escRep(e.message)}</div>`; }
}

// ═══════════════════════════════════════════════════════════════════
// 3. CUSTOMER STATEMENT (#page-rep-cust-stmt)
// ═══════════════════════════════════════════════════════════════════
async function renderCustomerStatementPage() {
  const wrap = document.getElementById('page-rep-cust-stmt');
  if (!wrap) return;
  let customers = [];
  try { customers = await Api.customers.list(); } catch {}
  const opts = customers.sort((a,b)=>a.code.localeCompare(b.code))
    .map(c => `<option value="${c.id}">${_escRep(c.code)} — ${_escRep(c.name)}</option>`).join('');
  wrap.innerHTML = `
    <div class="page-header">
      <h2>Customer Statement</h2>
      <p class="page-subtitle">Statement per customer: invoice + receipt + running balance.</p>
    </div>
    <div class="report-filter-bar" style="margin-bottom:12px;display:flex;gap:8px;align-items:end;flex-wrap:wrap">
      <div class="form-group" style="flex:2;margin:0;min-width:240px"><label>Customer *</label>
        <select id="csCustomer" class="form-control"><option value="">— Pilih customer —</option>${opts}</select></div>
      <div class="form-group" style="margin:0"><label>Dari</label>
        <input type="date" id="csFrom" class="form-control" value="${_firstOfMonth()}"></div>
      <div class="form-group" style="margin:0"><label>Sampai</label>
        <input type="date" id="csTo" class="form-control" value="${_todayISO()}"></div>
      <button class="btn btn-primary" onclick="loadCustomerStatement()">Tampilkan</button>
      <button class="btn btn-outline" onclick="exportCustomerStatement('excel')">📊 Excel</button>
      <button class="btn btn-outline" onclick="exportCustomerStatement('pdf')">📄 PDF</button>
    </div>
    <div id="csResult"><div class="empty-state">Pilih customer + klik Tampilkan.</div></div>
  `;
}

async function renderCustomerStatementForId(id) {
  if (typeof navigateTo === 'function') navigateTo('rep-cust-stmt');
  await new Promise(r => setTimeout(r, 200));
  const sel = document.getElementById('csCustomer');
  if (sel && id) { sel.value = id; await loadCustomerStatement(); }
}

async function loadCustomerStatement() {
  const out = document.getElementById('csResult'); if (!out) return;
  const customerId = document.getElementById('csCustomer').value;
  const dateFrom = document.getElementById('csFrom').value;
  const dateTo = document.getElementById('csTo').value;
  if (!customerId) { out.innerHTML = '<div class="empty-state">Pilih customer dulu.</div>'; return; }
  out.innerHTML = '<div class="empty-state">Memuat…</div>';
  try {
    const r = await Api.reports.customerStatement(customerId, {date_from: dateFrom, date_to: dateTo});
    out.innerHTML = `
      <div style="background:#f9fafb;padding:12px 16px;border-radius:6px;margin-bottom:12px;display:grid;grid-template-columns:repeat(4,1fr);gap:8px;font-size:13px">
        <div><strong>${_escRep(r.code)}</strong> — ${_escRep(r.name)}</div>
        <div>Saldo Awal: <strong>${_fmtRep(r.opening_balance)}</strong></div>
        <div>Periode Debit: <strong style="color:#b91c1c">${_fmtRep(r.period_debit_total)}</strong></div>
        <div>Saldo Akhir: <strong>${_fmtRep(r.closing_balance)}</strong></div>
      </div>
      <table class="data-table">
        <thead><tr>
          <th>Tanggal</th><th>Type</th><th>Reference</th><th>Description</th>
          <th class="text-right">Debit</th><th class="text-right">Kredit</th><th class="text-right">Saldo</th>
        </tr></thead>
        <tbody>${(r.lines || []).map(l => `<tr ${l.type==='payment'?'style="background:#f0fdf4"':''}>
          <td>${_fmtDateRep(l.date)}</td>
          <td>${_badge(l.type, l.type==='invoice'?'#f59e0b':'#15803d')}</td>
          <td>${_escRep(l.reference)}</td>
          <td>${_escRep(l.description || '')}</td>
          <td class="text-right">${l.debit ? _fmtRep(l.debit) : ''}</td>
          <td class="text-right">${l.credit ? _fmtRep(l.credit) : ''}</td>
          <td class="text-right"><strong>${_fmtRep(l.balance)}</strong></td>
        </tr>`).join('')}</tbody>
      </table>`;
  } catch (e) { out.innerHTML = `<div class="empty-state error">Gagal: ${_escRep(e.message)}</div>`; }
}

function exportCustomerStatement(format) {
  const customerId = document.getElementById('csCustomer').value;
  if (!customerId) { showToast('Pilih customer dulu', 'warning'); return; }
  const params = {
    customer_id: customerId,
    date_from: document.getElementById('csFrom').value,
    date_to: document.getElementById('csTo').value,
  };
  exportReportAsync('customer-statement', params, format);
}

// ═══════════════════════════════════════════════════════════════════
// 4. SUPPLIER STATEMENT (#page-rep-supp-stmt)
// ═══════════════════════════════════════════════════════════════════
async function renderSupplierStatementPage() {
  const wrap = document.getElementById('page-rep-supp-stmt');
  if (!wrap) return;
  let suppliers = [];
  try { suppliers = await Api.suppliers.list(); } catch {}
  const opts = suppliers.sort((a,b)=>a.code.localeCompare(b.code))
    .map(s => `<option value="${s.id}">${_escRep(s.code)} — ${_escRep(s.name)}</option>`).join('');
  wrap.innerHTML = `
    <div class="page-header">
      <h2>Supplier Statement</h2>
      <p class="page-subtitle">Statement per supplier: bill + disbursement + running balance.</p>
    </div>
    <div class="report-filter-bar" style="margin-bottom:12px;display:flex;gap:8px;align-items:end;flex-wrap:wrap">
      <div class="form-group" style="flex:2;margin:0;min-width:240px"><label>Supplier *</label>
        <select id="ssSupplier" class="form-control"><option value="">— Pilih supplier —</option>${opts}</select></div>
      <div class="form-group" style="margin:0"><label>Dari</label>
        <input type="date" id="ssFrom" class="form-control" value="${_firstOfMonth()}"></div>
      <div class="form-group" style="margin:0"><label>Sampai</label>
        <input type="date" id="ssTo" class="form-control" value="${_todayISO()}"></div>
      <button class="btn btn-primary" onclick="loadSupplierStatement()">Tampilkan</button>
      <button class="btn btn-outline" onclick="exportSupplierStatement('excel')">📊 Excel</button>
      <button class="btn btn-outline" onclick="exportSupplierStatement('pdf')">📄 PDF</button>
    </div>
    <div id="ssResult"><div class="empty-state">Pilih supplier + klik Tampilkan.</div></div>
  `;
}

async function renderSupplierStatementForId(id) {
  if (typeof navigateTo === 'function') navigateTo('rep-supp-stmt');
  await new Promise(r => setTimeout(r, 200));
  const sel = document.getElementById('ssSupplier');
  if (sel && id) { sel.value = id; await loadSupplierStatement(); }
}

async function loadSupplierStatement() {
  const out = document.getElementById('ssResult'); if (!out) return;
  const supplierId = document.getElementById('ssSupplier').value;
  const dateFrom = document.getElementById('ssFrom').value;
  const dateTo = document.getElementById('ssTo').value;
  if (!supplierId) { out.innerHTML = '<div class="empty-state">Pilih supplier dulu.</div>'; return; }
  out.innerHTML = '<div class="empty-state">Memuat…</div>';
  try {
    const r = await Api.reports.supplierStatement(supplierId, {date_from: dateFrom, date_to: dateTo});
    out.innerHTML = `
      <div style="background:#f9fafb;padding:12px 16px;border-radius:6px;margin-bottom:12px;display:grid;grid-template-columns:repeat(4,1fr);gap:8px;font-size:13px">
        <div><strong>${_escRep(r.code)}</strong> — ${_escRep(r.name)}</div>
        <div>Saldo Awal: <strong>${_fmtRep(r.opening_balance)}</strong></div>
        <div>Periode Kredit: <strong style="color:#15803d">${_fmtRep(r.period_credit_total)}</strong></div>
        <div>Saldo Akhir: <strong>${_fmtRep(r.closing_balance)}</strong></div>
      </div>
      <table class="data-table">
        <thead><tr>
          <th>Tanggal</th><th>Type</th><th>Reference</th><th>Description</th>
          <th class="text-right">Debit</th><th class="text-right">Kredit</th><th class="text-right">Saldo</th>
        </tr></thead>
        <tbody>${(r.lines || []).map(l => `<tr ${l.type==='payment'?'style="background:#fef9f9"':''}>
          <td>${_fmtDateRep(l.date)}</td>
          <td>${_badge(l.type, l.type==='invoice'?'#f59e0b':'#b91c1c')}</td>
          <td>${_escRep(l.reference)}</td>
          <td>${_escRep(l.description || '')}</td>
          <td class="text-right">${l.debit ? _fmtRep(l.debit) : ''}</td>
          <td class="text-right">${l.credit ? _fmtRep(l.credit) : ''}</td>
          <td class="text-right"><strong>${_fmtRep(l.balance)}</strong></td>
        </tr>`).join('')}</tbody>
      </table>`;
  } catch (e) { out.innerHTML = `<div class="empty-state error">Gagal: ${_escRep(e.message)}</div>`; }
}

function exportSupplierStatement(format) {
  const supplierId = document.getElementById('ssSupplier').value;
  if (!supplierId) { showToast('Pilih supplier dulu', 'warning'); return; }
  const params = {
    supplier_id: supplierId,
    date_from: document.getElementById('ssFrom').value,
    date_to: document.getElementById('ssTo').value,
  };
  exportReportAsync('supplier-statement', params, format);
}

// ═══════════════════════════════════════════════════════════════════
// 5. BANK RECONCILIATION (#page-rep-bank-rec)
// ═══════════════════════════════════════════════════════════════════
async function renderBankReconciliationPage() {
  const wrap = document.getElementById('page-rep-bank-rec');
  if (!wrap) return;
  let accounts = [];
  try { accounts = await Api.accounts.list(); } catch {}
  const cashAccounts = accounts.filter(a => a.is_cash && a.is_active);
  const opts = cashAccounts.sort((a,b)=>a.code.localeCompare(b.code))
    .map(a => `<option value="${a.id}">${_escRep(a.code)} — ${_escRep(a.name)}</option>`).join('');

  wrap.innerHTML = `
    <div class="page-header">
      <h2>Bank Reconciliation</h2>
      <p class="page-subtitle">Cocokkan bank statement dengan book entries di akun cash. Upload baris statement untuk match.</p>
    </div>
    <div style="background:#fff;padding:16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);margin-bottom:16px">
      <div class="form-row">
        <div class="form-group" style="flex:1"><label>Cash Account *</label>
          <select id="brAccount" class="form-control">
            ${cashAccounts.length === 0 ? '<option value="">⚠ Belum ada akun is_cash=true</option>' : '<option value="">— Pilih akun kas —</option>' + opts}
          </select></div>
        <div class="form-group" style="flex:1"><label>Dari</label>
          <input type="date" id="brFrom" class="form-control" value="${_firstOfMonth()}"></div>
        <div class="form-group" style="flex:1"><label>Sampai</label>
          <input type="date" id="brTo" class="form-control" value="${_todayISO()}"></div>
        <div class="form-group" style="flex:0;width:100px"><label>Tolerance (hari)</label>
          <input type="number" id="brTolerance" class="form-control" value="2" min="0" max="30"></div>
      </div>
      <div class="form-group">
        <label>Bank Statement (CSV — date,amount,reference,description per line)</label>
        <textarea id="brStmtText" class="form-control" rows="6" style="font-family:monospace;font-size:12px"
          placeholder="2026-05-01,1500000,REF123,Setoran Customer Acme&#10;2026-05-02,-500000,REF124,Bayar listrik&#10;2026-05-03,2000000,,Transfer masuk"></textarea>
        <small style="color:#6b7280">Format: <code>YYYY-MM-DD,amount,ref,description</code> per baris. Amount positif = uang masuk, negatif = keluar.</small>
      </div>
      <button class="btn btn-primary" onclick="runBankReconciliation()">🔍 Run Reconciliation</button>
    </div>
    <div id="brResult"></div>
  `;
}

async function runBankReconciliation() {
  const out = document.getElementById('brResult');
  const accountId = document.getElementById('brAccount').value;
  const dateFrom = document.getElementById('brFrom').value;
  const dateTo = document.getElementById('brTo').value;
  const tolerance = parseInt(document.getElementById('brTolerance').value) || 2;
  const stmtText = document.getElementById('brStmtText').value.trim();

  if (!accountId) { showToast('Pilih cash account dulu', 'warning'); return; }
  if (!stmtText) { showToast('Paste bank statement dulu', 'warning'); return; }

  // Parse CSV
  const stmtLines = stmtText.split('\n').map(l => l.trim()).filter(Boolean).map(line => {
    const [date, amount, reference, ...descParts] = line.split(',');
    return {
      date: date.trim(),
      amount: Number((amount || '0').trim()),
      reference: (reference || '').trim() || null,
      description: descParts.join(',').trim() || null,
    };
  });

  out.innerHTML = '<div class="empty-state">Memuat…</div>';
  try {
    const r = await Api.reports.bankReconciliation({
      cash_account_id: accountId,
      date_from: dateFrom,
      date_to: dateTo,
      statement_lines: stmtLines,
      date_tolerance_days: tolerance,
    });
    out.innerHTML = `
      <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:16px">
        <div style="background:#dcfce7;padding:12px;border-radius:6px">
          <div style="font-size:11px;color:#15803d">MATCHED</div>
          <div style="font-size:20px;font-weight:600">${(r.matched||[]).length}</div>
        </div>
        <div style="background:#fef3c7;padding:12px;border-radius:6px">
          <div style="font-size:11px;color:#92400e">BOOK-ONLY</div>
          <div style="font-size:20px;font-weight:600">${(r.book_only||[]).length}</div>
          <div style="font-size:12px">${_fmtRep(r.book_only_total)}</div>
        </div>
        <div style="background:#fee2e2;padding:12px;border-radius:6px">
          <div style="font-size:11px;color:#991b1b">STATEMENT-ONLY</div>
          <div style="font-size:20px;font-weight:600">${(r.statement_only||[]).length}</div>
          <div style="font-size:12px">${_fmtRep(r.statement_only_total)}</div>
        </div>
        <div style="background:#${Math.abs(Number(r.difference||0))<0.01?'dcfce7':'fee2e2'};padding:12px;border-radius:6px">
          <div style="font-size:11px">DIFFERENCE</div>
          <div style="font-size:18px;font-weight:600">${_fmtRep(r.difference)}</div>
        </div>
      </div>

      ${(r.matched||[]).length ? `
        <h3 style="font-size:14px;color:#15803d;margin-top:16px">✓ Matched (${r.matched.length})</h3>
        <table class="data-table">
          <thead><tr><th>Book Date</th><th>Book Ref</th><th class="text-right">Book Amount</th><th>Stmt Date</th><th>Stmt Ref</th><th class="text-right">Stmt Amount</th></tr></thead>
          <tbody>${r.matched.map(m => `<tr style="background:#f0fdf4">
            <td>${_fmtDateRep(m.book.entry_date)}</td>
            <td>${_escRep(m.book.entry_no)}</td>
            <td class="text-right">${_fmtRep(m.book.amount)}</td>
            <td>${_fmtDateRep(m.statement.date)}</td>
            <td>${_escRep(m.statement.reference || '')}</td>
            <td class="text-right">${_fmtRep(m.statement.amount)}</td>
          </tr>`).join('')}</tbody>
        </table>` : ''}

      ${(r.book_only||[]).length ? `
        <h3 style="font-size:14px;color:#92400e;margin-top:16px">⚠ Book Only — ada di buku, belum di statement (${r.book_only.length})</h3>
        <table class="data-table">
          <thead><tr><th>Date</th><th>Entry No</th><th>Description</th><th class="text-right">Amount</th></tr></thead>
          <tbody>${r.book_only.map(b => `<tr>
            <td>${_fmtDateRep(b.entry_date)}</td>
            <td>${_escRep(b.entry_no)}</td>
            <td>${_escRep(b.description || b.line_description || '')}</td>
            <td class="text-right">${_fmtRep(b.amount)}</td>
          </tr>`).join('')}</tbody>
        </table>` : ''}

      ${(r.statement_only||[]).length ? `
        <h3 style="font-size:14px;color:#991b1b;margin-top:16px">❌ Statement Only — di statement, belum di buku (${r.statement_only.length})</h3>
        <table class="data-table">
          <thead><tr><th>Date</th><th>Reference</th><th>Description</th><th class="text-right">Amount</th></tr></thead>
          <tbody>${r.statement_only.map(s => `<tr>
            <td>${_fmtDateRep(s.date)}</td>
            <td>${_escRep(s.reference || '')}</td>
            <td>${_escRep(s.description || '')}</td>
            <td class="text-right">${_fmtRep(s.amount)}</td>
          </tr>`).join('')}</tbody>
        </table>` : ''}
    `;
  } catch (e) { out.innerHTML = `<div class="empty-state error">Gagal: ${_escRep(e.message)}</div>`; }
}

// ═══════════════════════════════════════════════════════════════════
// 6. PPN REPORT (#page-rep-ppn)
// ═══════════════════════════════════════════════════════════════════
async function renderPPNReportPage() {
  const wrap = document.getElementById('page-rep-ppn');
  if (!wrap) return;
  const now = new Date();
  wrap.innerHTML = `
    <div class="page-header">
      <h2>Laporan PPN (Pajak Pertambahan Nilai)</h2>
      <p class="page-subtitle">PPN Keluaran (sales) − PPN Masukan (purchase) = Net VAT Payable.</p>
    </div>
    <div class="report-filter-bar" style="margin-bottom:12px;display:flex;gap:8px;align-items:end;flex-wrap:wrap">
      <div class="form-group" style="margin:0"><label>Tahun</label>
        <input type="number" id="ppnYear" class="form-control" value="${now.getFullYear()}" min="2000" max="2100"></div>
      <div class="form-group" style="margin:0"><label>Bulan</label>
        <select id="ppnMonth" class="form-control">
          ${Array.from({length:12}, (_, i) => `<option value="${i+1}" ${i+1===now.getMonth()+1?'selected':''}>${(i+1).toString().padStart(2,'0')} — ${['Januari','Februari','Maret','April','Mei','Juni','Juli','Agustus','September','Oktober','November','Desember'][i]}</option>`).join('')}
        </select></div>
      <button class="btn btn-primary" onclick="loadPPNReport()">Tampilkan</button>
      <span style="flex:1"></span>
      <button class="btn btn-outline" onclick="exportPPN('excel')">📊 Excel</button>
      <button class="btn btn-outline" onclick="exportPPN('pdf')">📄 PDF</button>
    </div>
    <div id="ppnResult"><div class="empty-state">Klik Tampilkan untuk memuat.</div></div>
  `;
  await loadPPNReport();
}

async function loadPPNReport() {
  const out = document.getElementById('ppnResult'); if (!out) return;
  const year = parseInt(document.getElementById('ppnYear').value);
  const month = parseInt(document.getElementById('ppnMonth').value);
  out.innerHTML = '<div class="empty-state">Memuat…</div>';
  try {
    const r = await Api.reports.ppn({year, month});
    const t = r.totals || {};
    out.innerHTML = `
      <div style="background:#fff;padding:16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);margin-bottom:16px">
        <h3 style="margin-top:0">Periode ${_escRep(r.period)}</h3>
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-top:12px">
          <div>
            <div style="font-size:11px;color:#6b7280">PPN KELUARAN (Output)</div>
            <div style="font-size:18px;font-weight:600;color:#15803d">${_fmtRep(t.output_vat_total)}</div>
            <div style="font-size:11px;color:#6b7280">DPP: ${_fmtRep(t.sales_base_total)}</div>
          </div>
          <div>
            <div style="font-size:11px;color:#6b7280">PPN MASUKAN (Input)</div>
            <div style="font-size:18px;font-weight:600;color:#b91c1c">${_fmtRep(t.input_vat_total)}</div>
            <div style="font-size:11px;color:#6b7280">DPP: ${_fmtRep(t.purchase_base_total)}</div>
          </div>
          <div style="border-left:2px solid #e5e7eb;padding-left:16px">
            <div style="font-size:11px;color:#6b7280">NET VAT PAYABLE</div>
            <div style="font-size:24px;font-weight:700;color:${Number(t.net_vat_payable||0) >= 0 ? '#1a56db' : '#15803d'}">${_fmtRep(t.net_vat_payable)}</div>
            <div style="font-size:11px;color:#6b7280">${Number(t.net_vat_payable||0) >= 0 ? 'Bayar ke negara' : 'Lebih bayar (kredit)'}</div>
          </div>
        </div>
      </div>

      <h3 style="font-size:14px;margin-top:16px">PPN Keluaran (Sales) — ${(r.sales||[]).length} faktur</h3>
      ${(r.sales||[]).length ? `<table class="data-table">
        <thead><tr><th>Tanggal</th><th>No. Faktur</th><th>Customer</th><th>NPWP</th><th class="text-right">DPP</th><th class="text-right">PPN</th></tr></thead>
        <tbody>${r.sales.map(l => `<tr>
          <td>${_fmtDateRep(l.invoice_date)}</td>
          <td>${_escRep(l.invoice_no)}</td>
          <td>${_escRep(l.customer_code)} — ${_escRep(l.customer_name)}</td>
          <td>${_escRep(l.customer_tax_id || '-')}</td>
          <td class="text-right">${_fmtRep(l.base)}</td>
          <td class="text-right"><strong>${_fmtRep(l.tax)}</strong></td>
        </tr>`).join('')}</tbody></table>` : '<div class="empty-state">Tidak ada PPN Keluaran.</div>'}

      <h3 style="font-size:14px;margin-top:16px">PPN Masukan (Purchase) — ${(r.purchases||[]).length} faktur</h3>
      ${(r.purchases||[]).length ? `<table class="data-table">
        <thead><tr><th>Tanggal</th><th>No. Inv Internal</th><th>No. Faktur Supplier</th><th>Supplier</th><th>NPWP</th><th class="text-right">DPP</th><th class="text-right">PPN</th></tr></thead>
        <tbody>${r.purchases.map(l => `<tr>
          <td>${_fmtDateRep(l.invoice_date)}</td>
          <td>${_escRep(l.invoice_no)}</td>
          <td>${_escRep(l.supplier_invoice_no || '-')}</td>
          <td>${_escRep(l.supplier_code)} — ${_escRep(l.supplier_name)}</td>
          <td>${_escRep(l.supplier_tax_id || '-')}</td>
          <td class="text-right">${_fmtRep(l.base)}</td>
          <td class="text-right"><strong>${_fmtRep(l.tax)}</strong></td>
        </tr>`).join('')}</tbody></table>` : '<div class="empty-state">Tidak ada PPN Masukan.</div>'}
    `;
  } catch (e) { out.innerHTML = `<div class="empty-state error">Gagal: ${_escRep(e.message)}</div>`; }
}

function exportPPN(format) {
  const year = parseInt(document.getElementById('ppnYear').value);
  const month = parseInt(document.getElementById('ppnMonth').value);
  exportReportAsync('ppn', {year, month}, format);
}

/**
 * ACCOUNTING-EXTRAS.JS — Account Mappings + Periods UI
 *
 * 2 halaman baru:
 *   - renderAccountMappingsPage()  → page-account-mappings
 *   - renderPeriodsPage()          → page-periods
 */

const WELL_KNOWN_MAPPING_KEYS = [
  {key:'ar',                label:'Accounts Receivable (Piutang Usaha)',    desc:'Akun yang di-Dr saat invoice penjualan di-post', expectedType:'asset'},
  {key:'ap',                label:'Accounts Payable (Utang Usaha)',         desc:'Akun yang di-Cr saat purchase bill di-post',     expectedType:'liability'},
  {key:'sales_revenue',     label:'Sales Revenue (Pendapatan Penjualan)',   desc:'Akun pendapatan default invoice',                expectedType:'income'},
  {key:'purchase_expense',  label:'Purchase Expense (Beban Pembelian)',     desc:'Akun beban default purchase non-inventory',      expectedType:'expense'},
  {key:'tax_payable',       label:'Tax Payable (Utang PPN/Pajak)',          desc:'PPN keluaran (output VAT)',                      expectedType:'liability'},
  {key:'tax_receivable',    label:'Tax Receivable (PPN Masukan)',           desc:'PPN masukan (input VAT)',                        expectedType:'asset'},
  {key:'cash_default',      label:'Cash Default (Kas Default)',             desc:'Akun kas default untuk receipts/disbursements',  expectedType:'asset'},
  {key:'inventory',         label:'Inventory (Persediaan)',                 desc:'Akun aset persediaan (stock-tracked items)',     expectedType:'asset'},
  {key:'cogs',              label:'COGS (Harga Pokok Penjualan)',           desc:'Akun beban HPP saat stock-out untuk penjualan',  expectedType:'expense'},
];

// ═══════════════════════════════════════════════════════════════════
// 1. ACCOUNT MAPPINGS (#page-account-mappings)
// ═══════════════════════════════════════════════════════════════════
async function renderAccountMappingsPage() {
  const wrap = document.getElementById('page-account-mappings');
  if (!wrap) return;
  wrap.innerHTML = `
    <div class="page-header">
      <div>
        <h2>Account Mappings</h2>
        <p class="page-subtitle">Bind well-known accounting keys ke akun spesifik. Wajib di-set sebelum bisa post invoice/payment dari backend.</p>
      </div>
      <button class="btn btn-outline" onclick="seedStarterCOA()">⚡ Auto-Seed Starter COA</button>
    </div>
    <div id="amResult"><div class="empty-state">Memuat…</div></div>
  `;
  await _loadAccountMappings();
}

async function _loadAccountMappings() {
  const out = document.getElementById('amResult');
  if (!out) return;
  try {
    const [mappings, accounts] = await Promise.all([
      Api.accountMappings.list().catch(() => []),
      Api.accounts.list(),
    ]);
    const accById = Object.fromEntries(accounts.map(a => [a.id, a]));
    const mapByKey = Object.fromEntries(mappings.map(m => [m.key, m]));

    const accOptionsByType = {};
    for (const a of accounts) {
      if (!accOptionsByType[a.type]) accOptionsByType[a.type] = [];
      accOptionsByType[a.type].push(a);
    }

    const rows = WELL_KNOWN_MAPPING_KEYS.map(spec => {
      const current = mapByKey[spec.key];
      const acct = current ? accById[current.account_id] : null;
      const filtered = (accOptionsByType[spec.expectedType] || []).sort((a,b) => a.code.localeCompare(b.code));
      const options = filtered.map(a => `<option value="${a.id}" ${current?.account_id===a.id?'selected':''}>${_escAm(a.code)} — ${_escAm(a.name)}</option>`).join('');
      const status = acct
        ? `<span class="badge badge-success">✓ ${_escAm(acct.code)} ${_escAm(acct.name)}</span>`
        : '<span class="badge badge-warning">⚠ Belum di-set</span>';
      return `<tr>
        <td><strong>${spec.key}</strong><br><small style="color:#6b7280">${_escAm(spec.expectedType)}</small></td>
        <td><div>${_escAm(spec.label)}</div><small style="color:#6b7280">${_escAm(spec.desc)}</small></td>
        <td>${status}</td>
        <td>
          <select class="form-control" id="am-${spec.key}" style="min-width:280px">
            <option value="">— Pilih akun —</option>${options}
          </select>
        </td>
        <td><button class="btn btn-sm btn-primary" onclick="setMapping('${spec.key}')">Simpan</button></td>
      </tr>`;
    }).join('');

    out.innerHTML = `
      <table class="data-table">
        <thead><tr>
          <th>Key</th><th>Label & Penjelasan</th><th>Status Sekarang</th><th>Set Akun</th><th>Aksi</th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>
      <div style="background:#fefce8;border-left:4px solid #eab308;padding:12px 16px;margin-top:16px;border-radius:4px">
        <strong>💡 Tips:</strong> Klik <em>"⚡ Auto-Seed Starter COA"</em> di kanan atas untuk auto-buat 30+ akun standar Indonesia + auto-bind semua mapping. Cocok untuk tenant baru yang belum punya COA.
      </div>
    `;
  } catch (e) {
    out.innerHTML = `<div class="empty-state error">Gagal memuat: ${_escAm(e.message)}</div>`;
  }
}

function _escAm(s) {
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

async function setMapping(key) {
  const sel = document.getElementById('am-' + key);
  const accountId = sel?.value;
  if (!accountId) { showToast('Pilih akun dulu', 'warning'); return; }
  try {
    await Api.accountMappings.set({key, account_id: accountId});
    showToast(`Mapping "${key}" berhasil di-set`, 'success');
    await _loadAccountMappings();
  } catch (e) { showToast('Gagal: ' + e.message, 'error'); }
}

async function seedStarterCOA() {
  if (!confirm('Auto-seed starter COA? Akan buat ~30 akun standar Indonesia + bind semua mapping. Akun yang sudah ada akan di-skip.')) return;
  try {
    const r = await Api.seedStarterCOA(true);
    showToast(`Seeded ${r.created || 0} akun, ${r.mappings_set || 0} mapping`, 'success');
    if (typeof BackendLoader !== 'undefined') await BackendLoader.loadCOA();
    await _loadAccountMappings();
  } catch (e) { showToast('Gagal seed: ' + e.message, 'error'); }
}

// ═══════════════════════════════════════════════════════════════════
// 2. PERIODS CLOSE/REOPEN (#page-periods)
// ═══════════════════════════════════════════════════════════════════
async function renderPeriodsPage() {
  const wrap = document.getElementById('page-periods');
  if (!wrap) return;
  wrap.innerHTML = `
    <div class="page-header">
      <h2>Manajemen Periode</h2>
      <p class="page-subtitle">Tutup periode akuntansi (lock journal entries di tanggal sebelum/sama dengan tanggal close). Bisa di-reopen kalau perlu koreksi.</p>
    </div>
    <div id="periodsResult"><div class="empty-state">Memuat…</div></div>
  `;
  await _loadPeriodsStatus();
}

async function _loadPeriodsStatus() {
  const out = document.getElementById('periodsResult');
  if (!out) return;
  try {
    const status = await Api.periods.status();
    const events = await Api.periods.events({limit: 30}).catch(() => []);
    const today = new Date().toISOString().slice(0, 10);
    const lastMonthEnd = (() => {
      const d = new Date();
      d.setDate(0); // last day of previous month
      return d.toISOString().slice(0, 10);
    })();

    out.innerHTML = `
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:24px">
        <div style="background:#fff;padding:16px;border-radius:6px;box-shadow:0 1px 3px rgba(0,0,0,.05)">
          <h3 style="margin-top:0">Status Saat Ini</h3>
          <p>Tertutup sampai: <strong>${status.closed_through ? _escAm(status.closed_through) : '<em style="color:#6b7280">Belum pernah ditutup</em>'}</strong></p>
          ${status.closed_through ? `<p style="font-size:13px;color:#6b7280">Journal entry dengan tanggal ≤ ${_escAm(status.closed_through)} dikunci. Sales/purchase invoice posting di tanggal yang ditutup akan ditolak.</p>` : ''}
        </div>

        <div style="background:#fff;padding:16px;border-radius:6px;box-shadow:0 1px 3px rgba(0,0,0,.05)">
          <h3 style="margin-top:0">Tutup Periode</h3>
          <div class="form-group"><label>Tutup sampai (inclusive)</label>
            <input type="date" id="closeDate" class="form-control" value="${lastMonthEnd}" max="${today}"></div>
          <div class="form-group"><label>Catatan (opsional)</label>
            <input type="text" id="closeNote" class="form-control" placeholder="Bulan-end Apr 2026"></div>
          <button class="btn btn-primary" onclick="closeperiod()" style="margin-right:8px">🔒 Tutup Periode</button>
          ${status.closed_through ? `<button class="btn btn-outline btn-danger" onclick="reopenPeriod()">🔓 Reopen</button>` : ''}
        </div>
      </div>

      <div style="background:#fff;padding:16px;border-radius:6px;box-shadow:0 1px 3px rgba(0,0,0,.05)">
        <h3 style="margin-top:0">Riwayat Close/Reopen</h3>
        ${events.length === 0 ? '<p style="color:#6b7280">Belum ada riwayat.</p>' : `
          <table class="data-table">
            <thead><tr><th>Tanggal</th><th>Action</th><th>Closed Through</th><th>User</th><th>Catatan</th></tr></thead>
            <tbody>${events.map(e => `<tr>
              <td>${new Date(e.created_at).toLocaleString('id-ID')}</td>
              <td><span class="badge badge-${e.action==='close'?'warning':'success'}">${_escAm(e.action)}</span></td>
              <td>${_escAm(e.closed_through_after || '-')}</td>
              <td>${_escAm(e.actor_email || e.actor_id || '-')}</td>
              <td>${_escAm(e.note || '')}</td>
            </tr>`).join('')}</tbody>
          </table>`}
      </div>
    `;
  } catch (e) {
    out.innerHTML = `<div class="empty-state error">Gagal memuat: ${_escAm(e.message)}</div>`;
  }
}

async function closeperiod() {
  const date = document.getElementById('closeDate').value;
  const note = document.getElementById('closeNote').value.trim();
  if (!date) { showToast('Tanggal wajib diisi', 'warning'); return; }
  if (!confirm(`Tutup periode sampai ${date}? Journal entry tanggal ≤ ${date} akan dikunci.`)) return;
  try {
    await Api.periods.close({closed_through: date, note: note || null});
    showToast('Periode ditutup', 'success');
    await _loadPeriodsStatus();
  } catch (e) { showToast('Gagal: ' + e.message, 'error'); }
}

async function reopenPeriod() {
  const reason = prompt('Alasan reopen periode (wajib diisi):');
  if (!reason || !reason.trim()) return;
  try {
    await Api.periods.reopen({note: reason.trim()});
    showToast('Periode di-reopen', 'success');
    await _loadPeriodsStatus();
  } catch (e) { showToast('Gagal: ' + e.message, 'error'); }
}

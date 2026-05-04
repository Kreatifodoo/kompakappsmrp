/**
 * INVENTORY-EXTRAS.JS — Halaman tambahan untuk modul Inventory
 *
 * 7 halaman baru yang panggil backend FastAPI langsung:
 *   - renderTransfersPage()        → page-inventory-transfers
 *   - renderStockOnHandPage()      → page-inv-onhand
 *   - renderStockValuationPage()   → page-inv-valuation
 *   - renderStockCardPage()        → page-inv-stockcard
 *   - renderReorderPage()          → page-inv-reorder
 *   - renderSlowMovingPage()       → page-inv-slowmoving
 *   - renderCostingMethodPage()    → page-inv-costing
 *
 * Reuse: _escInv, _fmtInv dari inventory.js. Picker dropdowns baca
 * InventoryState.items + InventoryState.warehouses (sudah di-load).
 */

// ─── Helpers ──────────────────────────────────────────────────
function _invFmtDate(d) {
  if (!d) return '-';
  return String(d).slice(0, 10);
}
function _invFmtQty(q) {
  if (q === null || q === undefined) return '-';
  return Number(q).toLocaleString('id-ID', {maximumFractionDigits: 4});
}
function _invErrBox(wrap, msg) {
  if (!wrap) return;
  wrap.innerHTML = `<div class="empty-state error" style="padding:24px;color:#b91c1c;background:#fee2e2;border-radius:6px">
    ❌ ${_escInv(msg)}
  </div>`;
}

async function _ensureInvMastersLoaded() {
  if (typeof InventoryState === 'undefined') return;
  if (!InventoryState.items?.length || !InventoryState.warehouses?.length) {
    try {
      const [items, whs] = await Promise.all([
        Api.items.list({active_only: true}),
        Api.warehouses.list(),
      ]);
      InventoryState.items = items;
      InventoryState.warehouses = whs;
    } catch (e) {
      console.warn('[inv-extras] failed to load masters', e);
    }
  }
}

function _itemPickerOptions(selected) {
  const items = InventoryState?.items || [];
  return items.map(i => `<option value="${i.id}" ${i.id===selected?'selected':''}>${_escInv(i.sku)} — ${_escInv(i.name)}</option>`).join('');
}
function _whPickerOptions(selected, includeAll = true) {
  const whs = InventoryState?.warehouses || [];
  let html = includeAll ? `<option value="">— Semua Gudang —</option>` : '';
  html += whs.map(w => `<option value="${w.id}" ${w.id===selected?'selected':''}>${_escInv(w.code)} — ${_escInv(w.name)}</option>`).join('');
  return html;
}
function _itemNameById(id) {
  const it = (InventoryState?.items || []).find(i => i.id === id);
  return it ? `${it.sku} — ${it.name}` : id;
}
function _whCodeById(id) {
  const w = (InventoryState?.warehouses || []).find(x => x.id === id);
  return w ? w.code : id;
}

// ═══════════════════════════════════════════════════════════════════
// 1. STOCK TRANSFER PAGE (#page-inventory-transfers)
// ═══════════════════════════════════════════════════════════════════
async function renderTransfersPage() {
  const wrap = document.getElementById('page-inventory-transfers');
  if (!wrap) return;
  await _ensureInvMastersLoaded();

  wrap.innerHTML = `
    <div class="page-header">
      <div>
        <h2>Transfer Stok</h2>
        <p class="page-subtitle">Pindah barang antar gudang. Backend otomatis pasangkan stock-out di asal + stock-in di tujuan dengan unit cost yang sama.</p>
      </div>
      <button class="btn btn-primary" onclick="showTransferModal()">+ Transfer Baru</button>
    </div>
    <div id="trfTableWrap"><div class="empty-state">Memuat…</div></div>
  `;

  try {
    const transfers = await Api.stockTransfers.list({limit: 100});
    const tw = document.getElementById('trfTableWrap');
    if (!transfers.length) {
      tw.innerHTML = `<div class="empty-state"><p>Belum ada transfer. <button class="btn btn-primary btn-sm" onclick="showTransferModal()">+ Transfer Baru</button></p></div>`;
      return;
    }
    tw.innerHTML = `
      <table class="data-table">
        <thead><tr>
          <th>No.</th><th>Tanggal</th><th>Dari</th><th>Ke</th>
          <th>Jumlah Item</th><th>Status</th><th>Aksi</th>
        </tr></thead>
        <tbody>
          ${transfers.map(t => `<tr>
            <td><strong>${_escInv(t.transfer_no)}</strong></td>
            <td>${_invFmtDate(t.transfer_date)}</td>
            <td>${_escInv(_whCodeById(t.source_warehouse_id))}</td>
            <td>${_escInv(_whCodeById(t.destination_warehouse_id))}</td>
            <td class="text-right">${(t.lines || []).length}</td>
            <td>${t.status === 'posted'
                  ? '<span class="badge badge-success">Posted</span>'
                  : '<span class="badge badge-danger">Void</span>'}</td>
            <td>
              <button class="btn btn-sm btn-outline" onclick="viewTransferDetail('${t.id}')">Lihat</button>
              ${t.status === 'posted' ? `<button class="btn btn-sm btn-danger" onclick="voidTransfer('${t.id}')">Void</button>` : ''}
            </td>
          </tr>`).join('')}
        </tbody>
      </table>`;
  } catch (e) {
    _invErrBox(document.getElementById('trfTableWrap'), 'Gagal memuat transfer: ' + e.message);
  }
}

let _trfLines = [];
function _trfNewLine() { return {tempId: 'l_'+Date.now()+'_'+Math.random().toString(36).slice(2,5), itemId:'', qty:1, notes:''}; }

async function showTransferModal() {
  await _ensureInvMastersLoaded();
  _trfLines = [_trfNewLine()];
  const today = new Date().toISOString().slice(0, 10);
  const html = `
    <div class="modal-backdrop" id="trfModal" onclick="if(event.target===this)closeTransferModal()">
      <div class="modal-dialog" style="max-width:680px">
        <div class="modal-header">
          <h3>Transfer Stok Baru</h3>
          <button class="modal-close" onclick="closeTransferModal()">×</button>
        </div>
        <div class="modal-body">
          <div class="form-row">
            <div class="form-group"><label>Tanggal *</label>
              <input class="form-control" type="date" id="trfDate" value="${today}"></div>
            <div class="form-group"><label>No. Transfer (opsional)</label>
              <input class="form-control" id="trfNo" placeholder="Auto-generate kalau kosong"></div>
          </div>
          <div class="form-row">
            <div class="form-group"><label>Dari Gudang *</label>
              <select class="form-control" id="trfSrc">${_whPickerOptions('', false)}</select></div>
            <div class="form-group"><label>Ke Gudang *</label>
              <select class="form-control" id="trfDst">${_whPickerOptions('', false)}</select></div>
          </div>
          <div class="form-group"><label>Catatan</label>
            <input class="form-control" id="trfNotes" placeholder="Opsional"></div>

          <div class="form-group">
            <label>Item & Qty *</label>
            <div id="trfLinesWrap"></div>
            <button class="btn btn-sm btn-outline" type="button" onclick="addTrfLine()" style="margin-top:8px">+ Tambah Item</button>
          </div>

          <div id="trfErr" class="form-error" style="display:none"></div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-outline" onclick="closeTransferModal()">Batal</button>
          <button class="btn btn-primary" onclick="saveTransfer()">Simpan & Post</button>
        </div>
      </div>
    </div>`;
  document.body.insertAdjacentHTML('beforeend', html);
  _renderTrfLines();
}

function _renderTrfLines() {
  const wrap = document.getElementById('trfLinesWrap');
  if (!wrap) return;
  wrap.innerHTML = _trfLines.map((l, idx) => `
    <div class="form-row" style="margin-bottom:6px;align-items:flex-end">
      <div class="form-group" style="flex:3;margin-bottom:0">
        ${idx === 0 ? '<label style="font-size:11px;color:#6b7280">Item</label>' : ''}
        <select class="form-control" onchange="updateTrfLine('${l.tempId}','itemId',this.value)">
          <option value="">— Pilih item —</option>
          ${_itemPickerOptions(l.itemId)}
        </select></div>
      <div class="form-group" style="flex:1;margin-bottom:0">
        ${idx === 0 ? '<label style="font-size:11px;color:#6b7280">Qty</label>' : ''}
        <input class="form-control" type="number" min="0.001" step="0.001" value="${l.qty}"
               onchange="updateTrfLine('${l.tempId}','qty',this.value)"></div>
      <div class="form-group" style="flex:2;margin-bottom:0">
        ${idx === 0 ? '<label style="font-size:11px;color:#6b7280">Catatan baris</label>' : ''}
        <input class="form-control" placeholder="opsional" value="${_escInv(l.notes)}"
               onchange="updateTrfLine('${l.tempId}','notes',this.value)"></div>
      <div style="margin-bottom:0">
        <button class="btn btn-sm btn-danger" type="button" onclick="removeTrfLine('${l.tempId}')" ${_trfLines.length<=1?'disabled':''}>×</button>
      </div>
    </div>`).join('');
}

function addTrfLine()        { _trfLines.push(_trfNewLine()); _renderTrfLines(); }
function removeTrfLine(id)   { _trfLines = _trfLines.filter(l => l.tempId !== id); _renderTrfLines(); }
function updateTrfLine(id, k, v) { const l = _trfLines.find(x => x.tempId === id); if (l) l[k] = v; }
function closeTransferModal() { document.getElementById('trfModal')?.remove(); _trfLines = []; }

async function saveTransfer() {
  const errEl = document.getElementById('trfErr');
  errEl.style.display = 'none';
  const transferDate = document.getElementById('trfDate').value;
  const transferNo   = document.getElementById('trfNo').value.trim();
  const sourceWh     = document.getElementById('trfSrc').value;
  const destWh       = document.getElementById('trfDst').value;
  const notes        = document.getElementById('trfNotes').value.trim();
  if (!transferDate || !sourceWh || !destWh) {
    errEl.textContent = 'Tanggal + Gudang asal + Gudang tujuan wajib diisi'; errEl.style.display='block'; return;
  }
  if (sourceWh === destWh) {
    errEl.textContent = 'Gudang asal dan tujuan tidak boleh sama'; errEl.style.display='block'; return;
  }
  const goodLines = _trfLines.filter(l => l.itemId && Number(l.qty) > 0);
  if (!goodLines.length) {
    errEl.textContent = 'Tambahkan minimal 1 item dengan qty > 0'; errEl.style.display='block'; return;
  }
  try {
    await Api.stockTransfers.create({
      transfer_no: transferNo || null,
      transfer_date: transferDate,
      source_warehouse_id: sourceWh,
      destination_warehouse_id: destWh,
      notes: notes || null,
      lines: goodLines.map(l => ({item_id: l.itemId, qty: Number(l.qty), notes: l.notes || null})),
    });
    showToast('Transfer berhasil di-post', 'success');
    closeTransferModal();
    await renderTransfersPage();
  } catch (e) {
    errEl.textContent = e.message; errEl.style.display = 'block';
  }
}

async function viewTransferDetail(id) {
  try {
    const t = await Api.stockTransfers.get(id);
    const linesHtml = (t.lines || []).map((l, i) => `
      <tr><td>${i+1}</td><td>${_escInv(_itemNameById(l.item_id))}</td>
      <td class="text-right">${_invFmtQty(l.qty)}</td>
      <td class="text-right">${_fmtInv(l.unit_cost)}</td>
      <td>${_escInv(l.notes || '')}</td></tr>`).join('');
    const html = `
      <div class="modal-backdrop" id="trfDetailModal" onclick="if(event.target===this)document.getElementById('trfDetailModal').remove()">
        <div class="modal-dialog" style="max-width:700px">
          <div class="modal-header">
            <h3>Transfer ${_escInv(t.transfer_no)}</h3>
            <button class="modal-close" onclick="document.getElementById('trfDetailModal').remove()">×</button>
          </div>
          <div class="modal-body">
            <p><strong>Tanggal:</strong> ${_invFmtDate(t.transfer_date)}<br>
            <strong>Dari:</strong> ${_escInv(_whCodeById(t.source_warehouse_id))} →
            <strong>Ke:</strong> ${_escInv(_whCodeById(t.destination_warehouse_id))}<br>
            <strong>Status:</strong> ${t.status === 'posted' ? '<span class="badge badge-success">Posted</span>' : '<span class="badge badge-danger">Void</span>'}<br>
            ${t.notes ? '<strong>Catatan:</strong> ' + _escInv(t.notes) : ''}</p>
            <table class="data-table">
              <thead><tr><th>#</th><th>Item</th><th>Qty</th><th>Unit Cost</th><th>Notes</th></tr></thead>
              <tbody>${linesHtml}</tbody>
            </table>
          </div>
        </div>
      </div>`;
    document.body.insertAdjacentHTML('beforeend', html);
  } catch (e) { showToast('Gagal: '+e.message, 'error'); }
}

async function voidTransfer(id) {
  const reason = prompt('Alasan void transfer ini:');
  if (!reason || !reason.trim()) return;
  try {
    await Api.stockTransfers.void(id, {reason: reason.trim()});
    showToast('Transfer di-void', 'success');
    await renderTransfersPage();
  } catch (e) { showToast('Gagal void: '+e.message, 'error'); }
}

// ═══════════════════════════════════════════════════════════════════
// 2. STOCK ON-HAND REPORT (#page-inv-onhand)
// ═══════════════════════════════════════════════════════════════════
async function renderStockOnHandPage() {
  const wrap = document.getElementById('page-inv-onhand');
  if (!wrap) return;
  await _ensureInvMastersLoaded();
  wrap.innerHTML = `
    <div class="page-header">
      <h2>Stock On-Hand</h2>
      <p class="page-subtitle">Posisi qty + nilai persediaan saat ini, per gudang.</p>
    </div>
    <div class="report-filter-bar" style="margin-bottom:12px;display:flex;gap:8px;align-items:center">
      <label>Gudang:</label>
      <select id="onhandWh" onchange="renderStockOnHandPage()" class="form-control" style="max-width:300px">
        ${_whPickerOptions('', true)}
      </select>
    </div>
    <div id="onhandResult"><div class="empty-state">Memuat…</div></div>
  `;
  // After re-render the select gets reset; preserve via closure of last value
  // by reading it BEFORE we overwrite innerHTML on subsequent calls is not possible.
  // Workaround: fetch using URL hash state. Simpler: skip filter-on-change recursion.
  await _renderOnHandTable(null);

  // Re-attach onchange properly (innerHTML wipe lost it — but it's still set since we just wrote it). OK.
  document.getElementById('onhandWh').addEventListener('change', async (e) => {
    await _renderOnHandTable(e.target.value || null);
  });
}

async function _renderOnHandTable(warehouseId) {
  const out = document.getElementById('onhandResult');
  if (!out) return;
  out.innerHTML = '<div class="empty-state">Memuat…</div>';
  try {
    const r = await Api.inventoryReports.stockOnHand(warehouseId ? {warehouse_id: warehouseId} : {});
    if (!r.lines.length) { out.innerHTML = '<div class="empty-state">Tidak ada stok.</div>'; return; }
    out.innerHTML = `
      <table class="data-table">
        <thead><tr>
          <th>SKU</th><th>Nama</th><th>Gudang</th><th>Unit</th>
          <th class="text-right">Qty</th><th class="text-right">Avg Cost</th>
          <th class="text-right">Nilai</th><th>Status</th>
        </tr></thead>
        <tbody>
          ${r.lines.map(l => `<tr ${l.below_min_stock?'style="background:#fef3c7"':''}>
            <td><strong>${_escInv(l.sku)}</strong></td>
            <td>${_escInv(l.name)}</td>
            <td>${_escInv(l.warehouse_code)}</td>
            <td>${_escInv(l.unit)}</td>
            <td class="text-right">${_invFmtQty(l.on_hand_qty)}</td>
            <td class="text-right">${_fmtInv(l.avg_cost)}</td>
            <td class="text-right"><strong>${_fmtInv(l.value)}</strong></td>
            <td>${l.below_min_stock ? '<span class="badge badge-warning">⚠ Min Stock</span>' : '<span class="badge badge-success">OK</span>'}</td>
          </tr>`).join('')}
        </tbody>
        <tfoot><tr style="font-weight:bold;background:#f3f4f6">
          <td colspan="6" class="text-right">TOTAL NILAI:</td>
          <td class="text-right">${_fmtInv(r.total_value)}</td>
          <td></td>
        </tr></tfoot>
      </table>`;
  } catch (e) { _invErrBox(out, 'Gagal memuat: ' + e.message); }
}

// ═══════════════════════════════════════════════════════════════════
// 3. STOCK VALUATION REPORT (#page-inv-valuation)
// ═══════════════════════════════════════════════════════════════════
async function renderStockValuationPage() {
  const wrap = document.getElementById('page-inv-valuation');
  if (!wrap) return;
  wrap.innerHTML = `
    <div class="page-header">
      <h2>Stock Valuation</h2>
      <p class="page-subtitle">Total nilai persediaan, agregat lintas semua gudang. Satu baris per item.</p>
    </div>
    <div id="valResult"><div class="empty-state">Memuat…</div></div>
  `;
  try {
    const r = await Api.inventoryReports.stockValuation();
    const out = document.getElementById('valResult');
    if (!r.lines.length) { out.innerHTML = '<div class="empty-state">Belum ada stok.</div>'; return; }
    out.innerHTML = `
      <table class="data-table">
        <thead><tr>
          <th>SKU</th><th>Nama</th><th>Unit</th>
          <th class="text-right">Total Qty</th>
          <th class="text-right">Wt. Avg Cost</th>
          <th class="text-right">Nilai</th>
        </tr></thead>
        <tbody>
          ${r.lines.map(l => `<tr>
            <td><strong>${_escInv(l.sku)}</strong></td>
            <td>${_escInv(l.name)}</td>
            <td>${_escInv(l.unit)}</td>
            <td class="text-right">${_invFmtQty(l.on_hand_qty)}</td>
            <td class="text-right">${_fmtInv(l.weighted_avg_cost)}</td>
            <td class="text-right"><strong>${_fmtInv(l.value)}</strong></td>
          </tr>`).join('')}
        </tbody>
        <tfoot><tr style="font-weight:bold;background:#f3f4f6">
          <td colspan="5" class="text-right">TOTAL NILAI PERSEDIAAN:</td>
          <td class="text-right">${_fmtInv(r.total_value)}</td>
        </tr></tfoot>
      </table>`;
  } catch (e) { _invErrBox(document.getElementById('valResult'), 'Gagal memuat: ' + e.message); }
}

// ═══════════════════════════════════════════════════════════════════
// 4. STOCK CARD REPORT (#page-inv-stockcard)
// ═══════════════════════════════════════════════════════════════════
async function renderStockCardPage() {
  const wrap = document.getElementById('page-inv-stockcard');
  if (!wrap) return;
  await _ensureInvMastersLoaded();
  const today = new Date().toISOString().slice(0, 10);
  const aMonthAgo = new Date(Date.now() - 30*86400000).toISOString().slice(0, 10);
  wrap.innerHTML = `
    <div class="page-header">
      <h2>Kartu Stok (Stock Card)</h2>
      <p class="page-subtitle">Pergerakan kronologis per item × gudang dengan saldo awal & akhir.</p>
    </div>
    <div class="report-filter-bar" style="margin-bottom:12px;display:flex;gap:8px;align-items:end;flex-wrap:wrap">
      <div class="form-group" style="margin:0;flex:2;min-width:240px"><label>Item *</label>
        <select id="scItem" class="form-control"><option value="">— Pilih item —</option>${_itemPickerOptions('')}</select></div>
      <div class="form-group" style="margin:0;flex:1;min-width:160px"><label>Gudang *</label>
        <select id="scWh" class="form-control">${_whPickerOptions('', false)}</select></div>
      <div class="form-group" style="margin:0;flex:1;min-width:140px"><label>Dari</label>
        <input type="date" id="scFrom" class="form-control" value="${aMonthAgo}"></div>
      <div class="form-group" style="margin:0;flex:1;min-width:140px"><label>Sampai</label>
        <input type="date" id="scTo" class="form-control" value="${today}"></div>
      <button class="btn btn-primary" onclick="loadStockCard()">Tampilkan</button>
    </div>
    <div id="scResult"><div class="empty-state">Pilih item + gudang lalu klik Tampilkan.</div></div>
  `;
}

async function loadStockCard() {
  const itemId = document.getElementById('scItem').value;
  const whId   = document.getElementById('scWh').value;
  const dateFrom = document.getElementById('scFrom').value;
  const dateTo   = document.getElementById('scTo').value;
  const out = document.getElementById('scResult');
  if (!itemId || !whId) { out.innerHTML = '<div class="empty-state">Pilih item + gudang dulu.</div>'; return; }
  out.innerHTML = '<div class="empty-state">Memuat…</div>';
  try {
    const r = await Api.items.stockCard(itemId, {warehouse_id: whId, date_from: dateFrom, date_to: dateTo});
    out.innerHTML = `
      <div style="background:#f9fafb;padding:12px 16px;border-radius:6px;margin-bottom:12px;display:grid;grid-template-columns:repeat(4,1fr);gap:8px;font-size:13px">
        <div><strong>${_escInv(r.sku)}</strong> — ${_escInv(r.name)} (${_escInv(r.unit)})</div>
        <div>Gudang: <strong>${_escInv(r.warehouse_code)}</strong></div>
        <div>Saldo Awal: <strong>${_invFmtQty(r.opening_qty)}</strong> @ ${_fmtInv(r.opening_avg_cost)}</div>
        <div>Saldo Akhir: <strong>${_invFmtQty(r.closing_qty)}</strong> @ ${_fmtInv(r.closing_avg_cost)}</div>
      </div>
      <table class="data-table">
        <thead><tr>
          <th>Tanggal</th><th>Direction</th><th>Source</th>
          <th class="text-right">Qty</th><th class="text-right">Unit Cost</th><th class="text-right">Total</th>
          <th class="text-right">Qty After</th><th class="text-right">Avg After</th><th class="text-right">Value After</th>
          <th>Notes</th>
        </tr></thead>
        <tbody>
          ${(r.lines || []).map(l => `<tr>
            <td>${_invFmtDate(l.movement_date)}</td>
            <td><span class="badge badge-${l.direction.includes('in')?'success':'danger'}">${_escInv(l.direction)}</span></td>
            <td>${_escInv(l.source)}</td>
            <td class="text-right">${_invFmtQty(l.qty)}</td>
            <td class="text-right">${_fmtInv(l.unit_cost)}</td>
            <td class="text-right">${_fmtInv(l.total_cost)}</td>
            <td class="text-right">${_invFmtQty(l.qty_after)}</td>
            <td class="text-right">${_fmtInv(l.avg_cost_after)}</td>
            <td class="text-right">${_fmtInv(l.value_after)}</td>
            <td>${_escInv(l.notes || '')}</td>
          </tr>`).join('')}
        </tbody>
        <tfoot><tr style="font-weight:bold;background:#f3f4f6">
          <td colspan="3" class="text-right">PERIODE:</td>
          <td class="text-right" style="color:#15803d">+ ${_invFmtQty(r.period_in_qty)}</td>
          <td></td>
          <td class="text-right" style="color:#15803d">+ ${_fmtInv(r.period_in_value)}</td>
          <td class="text-right" style="color:#b91c1c">- ${_invFmtQty(r.period_out_qty)}</td>
          <td></td>
          <td class="text-right" style="color:#b91c1c">- ${_fmtInv(r.period_out_value)}</td>
          <td></td>
        </tr></tfoot>
      </table>`;
  } catch (e) { _invErrBox(out, 'Gagal memuat: ' + e.message); }
}

// ═══════════════════════════════════════════════════════════════════
// 5. REORDER REPORT (#page-inv-reorder)
// ═══════════════════════════════════════════════════════════════════
async function renderReorderPage() {
  const wrap = document.getElementById('page-inv-reorder');
  if (!wrap) return;
  await _ensureInvMastersLoaded();
  wrap.innerHTML = `
    <div class="page-header">
      <h2>Reorder Report</h2>
      <p class="page-subtitle">Item yang on-hand qty-nya di bawah min_stock — perlu di-restock.</p>
    </div>
    <div class="report-filter-bar" style="margin-bottom:12px;display:flex;gap:8px;align-items:center">
      <label>Gudang:</label>
      <select id="roWh" class="form-control" style="max-width:300px">${_whPickerOptions('', true)}</select>
      <button class="btn btn-primary" onclick="loadReorder()">Tampilkan</button>
    </div>
    <div id="roResult"><div class="empty-state">Klik Tampilkan untuk memuat.</div></div>
  `;
  await loadReorder();
}

async function loadReorder() {
  const whId = document.getElementById('roWh')?.value || '';
  const out = document.getElementById('roResult');
  out.innerHTML = '<div class="empty-state">Memuat…</div>';
  try {
    const r = await Api.inventoryReports.reorder(whId ? {warehouse_id: whId} : {});
    if (!r.lines.length) { out.innerHTML = '<div class="empty-state">✅ Tidak ada item yang perlu reorder.</div>'; return; }
    out.innerHTML = `
      <table class="data-table">
        <thead><tr>
          <th>SKU</th><th>Nama</th><th>Unit</th>
          <th class="text-right">Min Stock</th>
          <th class="text-right">On Hand</th>
          <th class="text-right">Shortage</th>
          <th class="text-right">Avg Cost</th>
          <th class="text-right">Shortage Value</th>
        </tr></thead>
        <tbody>
          ${r.lines.map(l => `<tr style="background:#fef3c7">
            <td><strong>${_escInv(l.sku)}</strong></td>
            <td>${_escInv(l.name)}</td>
            <td>${_escInv(l.unit)}</td>
            <td class="text-right">${_invFmtQty(l.min_stock)}</td>
            <td class="text-right">${_invFmtQty(l.on_hand_qty)}</td>
            <td class="text-right" style="color:#b91c1c"><strong>${_invFmtQty(l.shortage)}</strong></td>
            <td class="text-right">${_fmtInv(l.avg_cost)}</td>
            <td class="text-right">${_fmtInv(l.shortage_value)}</td>
          </tr>`).join('')}
        </tbody>
        <tfoot><tr style="font-weight:bold;background:#f3f4f6">
          <td colspan="7" class="text-right">TOTAL SHORTAGE VALUE:</td>
          <td class="text-right">${_fmtInv(r.total_shortage_value)}</td>
        </tr></tfoot>
      </table>`;
  } catch (e) { _invErrBox(out, 'Gagal memuat: ' + e.message); }
}

// ═══════════════════════════════════════════════════════════════════
// 6. SLOW-MOVING REPORT (#page-inv-slowmoving)
// ═══════════════════════════════════════════════════════════════════
async function renderSlowMovingPage() {
  const wrap = document.getElementById('page-inv-slowmoving');
  if (!wrap) return;
  await _ensureInvMastersLoaded();
  wrap.innerHTML = `
    <div class="page-header">
      <h2>Slow-Moving Items</h2>
      <p class="page-subtitle">Item yang tidak ada outflow dalam N hari terakhir (default 90).</p>
    </div>
    <div class="report-filter-bar" style="margin-bottom:12px;display:flex;gap:8px;align-items:center">
      <label>Periode (hari):</label>
      <input type="number" id="smDays" class="form-control" value="90" min="1" max="3650" style="max-width:100px">
      <label>Gudang:</label>
      <select id="smWh" class="form-control" style="max-width:280px">${_whPickerOptions('', true)}</select>
      <button class="btn btn-primary" onclick="loadSlowMoving()">Tampilkan</button>
    </div>
    <div id="smResult"><div class="empty-state">Klik Tampilkan untuk memuat.</div></div>
  `;
  await loadSlowMoving();
}

async function loadSlowMoving() {
  const days = document.getElementById('smDays')?.value || 90;
  const whId = document.getElementById('smWh')?.value || '';
  const out  = document.getElementById('smResult');
  out.innerHTML = '<div class="empty-state">Memuat…</div>';
  try {
    const params = {days: parseInt(days)};
    if (whId) params.warehouse_id = whId;
    const r = await Api.inventoryReports.slowMoving(params);
    if (!r.lines.length) { out.innerHTML = '<div class="empty-state">✅ Tidak ada slow-moving items dalam periode ini.</div>'; return; }
    out.innerHTML = `
      <p style="color:#6b7280;font-size:13px">Lookback ${r.lookback_days} hari · Per ${_invFmtDate(r.as_of_today)}</p>
      <table class="data-table">
        <thead><tr>
          <th>SKU</th><th>Nama</th><th>Gudang</th>
          <th class="text-right">On Hand</th>
          <th class="text-right">Out (periode)</th>
          <th>Last Outflow</th>
          <th class="text-right">Days Since</th>
          <th class="text-right">Nilai On Hand</th>
        </tr></thead>
        <tbody>
          ${r.lines.map(l => `<tr>
            <td><strong>${_escInv(l.sku)}</strong></td>
            <td>${_escInv(l.name)}</td>
            <td>${_escInv(l.warehouse_code)}</td>
            <td class="text-right">${_invFmtQty(l.on_hand_qty)}</td>
            <td class="text-right">${_invFmtQty(l.period_out_qty)}</td>
            <td>${l.last_outflow_date ? _invFmtDate(l.last_outflow_date) : '<em style="color:#9ca3af">never</em>'}</td>
            <td class="text-right">${l.days_since_last_outflow !== null ? l.days_since_last_outflow : '∞'}</td>
            <td class="text-right">${_fmtInv(l.on_hand_value)}</td>
          </tr>`).join('')}
        </tbody>
        <tfoot><tr style="font-weight:bold;background:#f3f4f6">
          <td colspan="7" class="text-right">TOTAL NILAI ON HAND:</td>
          <td class="text-right">${_fmtInv(r.total_on_hand_value)}</td>
        </tr></tfoot>
      </table>`;
  } catch (e) { _invErrBox(out, 'Gagal memuat: ' + e.message); }
}

// ═══════════════════════════════════════════════════════════════════
// 7. COSTING METHOD + COST LAYERS (#page-inv-costing)
// ═══════════════════════════════════════════════════════════════════
async function renderCostingMethodPage() {
  const wrap = document.getElementById('page-inv-costing');
  if (!wrap) return;
  await _ensureInvMastersLoaded();
  let current = 'avg';
  try { current = (await Api.costingMethod.get()).method; } catch {}
  wrap.innerHTML = `
    <div class="page-header">
      <h2>Costing Method & Cost Layers</h2>
      <p class="page-subtitle">Atur metode costing tenant + lihat layer FIFO/LIFO per item.</p>
    </div>

    <div style="background:#fff;padding:16px;border-radius:6px;margin-bottom:24px;box-shadow:0 1px 3px rgba(0,0,0,0.05)">
      <h3 style="margin-top:0">Metode Saat Ini: <span class="badge badge-info" id="cmCurrent">${_escInv(current)}</span></h3>
      <div style="display:flex;gap:12px;align-items:end;margin-top:12px;flex-wrap:wrap">
        <div class="form-group" style="margin:0;min-width:160px"><label>Ganti ke</label>
          <select id="cmNew" class="form-control">
            <option value="avg" ${current==='avg'?'selected':''}>Weighted Average</option>
            <option value="fifo" ${current==='fifo'?'selected':''}>FIFO</option>
            <option value="lifo" ${current==='lifo'?'selected':''}>LIFO</option>
          </select></div>
        <div class="form-group" style="margin:0">
          <label><input type="checkbox" id="cmSeed" checked> Seed opening layers (rekomendasi saat switch dari avg→FIFO/LIFO)</label>
        </div>
        <button class="btn btn-primary" onclick="changeCostingMethod()">Simpan</button>
      </div>
      <p style="font-size:12px;color:#6b7280;margin-top:8px">
        ⚠ Switching mempengaruhi semua perhitungan cost masa depan. Layer yang sudah ada tetap.
      </p>
    </div>

    <div style="background:#fff;padding:16px;border-radius:6px;box-shadow:0 1px 3px rgba(0,0,0,0.05)">
      <h3 style="margin-top:0">Cost Layers (Drill-down per Item)</h3>
      <div style="display:flex;gap:8px;align-items:end;margin-bottom:12px;flex-wrap:wrap">
        <div class="form-group" style="margin:0;flex:2;min-width:240px"><label>Item</label>
          <select id="clItem" class="form-control"><option value="">— Pilih item —</option>${_itemPickerOptions('')}</select></div>
        <div class="form-group" style="margin:0">
          <label><input type="checkbox" id="clExhausted"> Sertakan layer yang habis</label>
        </div>
        <button class="btn btn-primary" onclick="loadCostLayers()">Tampilkan</button>
      </div>
      <div id="clResult"><div class="empty-state">Pilih item lalu klik Tampilkan.</div></div>
    </div>
  `;
}

async function changeCostingMethod() {
  const method = document.getElementById('cmNew').value;
  const seed   = document.getElementById('cmSeed').checked;
  if (!confirm(`Ganti costing method ke "${method}"?`)) return;
  try {
    await Api.costingMethod.set({method, seed_opening_layers: seed});
    showToast(`Metode di-set ke ${method}`, 'success');
    await renderCostingMethodPage();
  } catch (e) { showToast('Gagal: '+e.message, 'error'); }
}

async function loadCostLayers() {
  const itemId    = document.getElementById('clItem').value;
  const exhausted = document.getElementById('clExhausted').checked;
  const out = document.getElementById('clResult');
  if (!itemId) { out.innerHTML = '<div class="empty-state">Pilih item dulu.</div>'; return; }
  out.innerHTML = '<div class="empty-state">Memuat…</div>';
  try {
    const r = await Api.items.costLayers(itemId, {include_exhausted: exhausted});
    if (!r.layers.length) {
      out.innerHTML = '<div class="empty-state">Tidak ada layer (mungkin tenant pakai metode <strong>avg</strong>, atau item belum ada stock-in).</div>';
      return;
    }
    out.innerHTML = `
      <table class="data-table">
        <thead><tr>
          <th>Received</th><th>Gudang</th>
          <th class="text-right">Original Qty</th>
          <th class="text-right">Remaining Qty</th>
          <th class="text-right">Unit Cost</th>
          <th class="text-right">Remaining Value</th>
          <th>Status</th>
        </tr></thead>
        <tbody>
          ${r.layers.map(l => `<tr ${l.is_exhausted?'style="opacity:0.5"':''}>
            <td>${new Date(l.received_at).toLocaleString('id-ID')}</td>
            <td>${_escInv(_whCodeById(l.warehouse_id))}</td>
            <td class="text-right">${_invFmtQty(l.original_qty)}</td>
            <td class="text-right">${_invFmtQty(l.remaining_qty)}</td>
            <td class="text-right">${_fmtInv(l.unit_cost)}</td>
            <td class="text-right">${_fmtInv(l.remaining_value)}</td>
            <td>${l.is_exhausted ? '<span class="badge">Exhausted</span>' : '<span class="badge badge-success">Active</span>'}</td>
          </tr>`).join('')}
        </tbody>
        <tfoot><tr style="font-weight:bold;background:#f3f4f6">
          <td colspan="3" class="text-right">TOTAL:</td>
          <td class="text-right">${_invFmtQty(r.total_remaining_qty)}</td>
          <td></td>
          <td class="text-right">${_fmtInv(r.total_remaining_value)}</td>
          <td></td>
        </tr></tfoot>
      </table>`;
  } catch (e) { _invErrBox(out, 'Gagal memuat: ' + e.message); }
}

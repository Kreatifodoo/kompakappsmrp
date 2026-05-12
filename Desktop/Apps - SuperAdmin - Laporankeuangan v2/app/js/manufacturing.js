/**
 * MANUFACTURING.JS — BOM + Manufacturing Order UI (Sprint M7)
 *
 * Pages:
 *   page-bom-master  — list BOMs, create with line editor, activate / obsolete
 *   page-mfg-orders  — list MO, create from active BOM, confirm/start/complete/cancel
 *
 * Each MO completion triggers (backend):
 *   stock-out raw materials  +  Journal Dr WIP / Cr Inventory
 *   stock-in finished good   +  Journal Dr Inventory FG / Cr WIP
 */

const MfgState = {
  boms: [],
  mos: [],
  items: [],
  warehouses: [],
};

const _mfgFmtRp = (n) => 'Rp ' + Math.round(n || 0).toLocaleString('id-ID');
const _mfgEsc   = (s) => String(s ?? '').replace(/[<>&"]/g, c => ({'<':'&lt;','>':'&gt;','&':'&amp;','"':'&quot;'}[c]));
const _mfgToday = () => new Date().toISOString().slice(0,10);

async function _mfgEnsureMasters() {
  if (!MfgState.items.length || !MfgState.warehouses.length) {
    try {
      const [items, whs] = await Promise.all([
        Api.items.list({limit: 500}),
        Api.warehouses.list(),
      ]);
      MfgState.items      = Array.isArray(items) ? items : [];
      MfgState.warehouses = Array.isArray(whs)   ? whs   : [];
    } catch (e) {
      console.warn('[mfg] load masters failed', e);
    }
  }
}

function _bomStatusBadge(status) {
  const map = {
    draft:    ['#6b7280', 'Draft'],
    active:   ['#10b981', 'Active'],
    obsolete: ['#ef4444', 'Obsolete'],
  };
  const [c, label] = map[status] || ['#6b7280', status || '-'];
  return `<span style="display:inline-block;padding:2px 8px;background:${c}20;color:${c};border-radius:6px;font-size:11px;font-weight:600">${label}</span>`;
}

function _moStatusBadge(status) {
  const map = {
    draft:       ['#6b7280', 'Draft'],
    confirmed:   ['#3b82f6', 'Confirmed'],
    in_progress: ['#f59e0b', 'In Progress'],
    done:        ['#10b981', 'Done'],
    cancelled:   ['#ef4444', 'Cancelled'],
  };
  const [c, label] = map[status] || ['#6b7280', status || '-'];
  return `<span style="display:inline-block;padding:2px 8px;background:${c}20;color:${c};border-radius:6px;font-size:11px;font-weight:600">${label}</span>`;
}

// ════════════════════════════════════════════════════════════════
// BOM
// ════════════════════════════════════════════════════════════════

async function renderBOMPage() {
  await _mfgEnsureMasters();
  const filterStatus = document.getElementById('bomFilterStatus')?.value || '';
  const filterItem   = document.getElementById('bomFilterItem')?.value || '';
  try {
    const list = await Api.boms.list({
      status: filterStatus || undefined,
      item_id: filterItem || undefined,
      limit: 200,
    });
    MfgState.boms = Array.isArray(list) ? list : [];
  } catch (e) {
    showToast('Gagal load BOM: ' + e.message, 'error');
    MfgState.boms = [];
  }

  // Item filter dropdown (stock items only)
  const itemSel = document.getElementById('bomFilterItem');
  if (itemSel) {
    const cur = itemSel.value;
    const stockItems = MfgState.items.filter(i => i.type === 'stock');
    itemSel.innerHTML = '<option value="">Semua Output Item</option>' +
      stockItems.map(i => `<option value="${i.id}" ${i.id===cur?'selected':''}>${_mfgEsc(i.name)}</option>`).join('');
  }

  const wrap = document.getElementById('bomTableWrap');
  if (!wrap) return;
  if (!MfgState.boms.length) {
    wrap.innerHTML = `<div style="padding:48px;text-align:center;color:#6b7280">Belum ada BOM. Klik <strong>"Buat BOM"</strong>.</div>`;
    return;
  }
  const itemMap = Object.fromEntries(MfgState.items.map(i => [i.id, i.name]));
  wrap.innerHTML = `
    <table class="data-table">
      <thead><tr>
        <th>BOM Code</th><th>Output Item</th>
        <th style="text-align:right">Qty Output</th>
        <th style="text-align:right">Components</th>
        <th>Status</th><th>Created</th>
        <th style="text-align:center">Aksi</th>
      </tr></thead>
      <tbody>
      ${MfgState.boms.map(b => `
        <tr>
          <td><code>${_mfgEsc(b.bom_code)}</code></td>
          <td>${_mfgEsc(itemMap[b.item_id] || b.item_id?.slice(0,8))}</td>
          <td style="text-align:right">${b.qty_output}</td>
          <td style="text-align:right">${(b.lines || []).length}</td>
          <td>${_bomStatusBadge(b.status)}</td>
          <td>${(b.created_at || '').slice(0,10)}</td>
          <td style="text-align:center;white-space:nowrap">
            <button class="btn btn-sm btn-outline" onclick="showBOMDetail('${b.id}')">Detail</button>
            ${b.status === 'draft' ? `<button class="btn btn-sm btn-primary" style="margin-left:4px" onclick="activateBOM('${b.id}')">Activate</button>` : ''}
            ${b.status === 'active' ? `<button class="btn btn-sm btn-warning" style="margin-left:4px" onclick="obsoleteBOM('${b.id}')">Obsolete</button>` : ''}
            ${b.status === 'draft' ? `<button class="btn btn-sm btn-danger" style="margin-left:4px" onclick="deleteBOM('${b.id}')">Hapus</button>` : ''}
          </td>
        </tr>`).join('')}
      </tbody>
    </table>`;
}

let _bomLines = [];

function showBOMModal() {
  _bomLines = [{ item_id: '', qty_required: 1, scrap_pct: 0, std_unit_cost: '', notes: '' }];
  const stockItems = MfgState.items.filter(i => i.type === 'stock');
  const itemOpts = stockItems.map(i => `<option value="${i.id}">${_mfgEsc(i.name)} (${_mfgEsc(i.sku || '-')})</option>`).join('');

  const html = `
  <div class="modal-backdrop" id="bomModalBackdrop" onclick="if(event.target===this)closeBOMModal()">
    <div class="modal-content" style="max-width:900px">
      <div class="modal-header">
        <h3>Buat BOM</h3>
        <button class="modal-close" onclick="closeBOMModal()">×</button>
      </div>
      <div class="modal-body">
        <div style="display:grid;grid-template-columns:2fr 1fr 1fr;gap:12px;margin-bottom:16px">
          <div><label>Output Item (yang dihasilkan)</label>
            <select id="bomOutputItem" class="form-control"><option value="">— pilih —</option>${itemOpts}</select>
          </div>
          <div><label>Qty Output (per resep)</label>
            <input type="number" step="0.01" id="bomQtyOutput" value="1" class="form-control">
          </div>
          <div><label>BOM Code (opsional)</label>
            <input type="text" id="bomCode" placeholder="otomatis dari SKU" class="form-control">
          </div>
        </div>
        <h4 style="margin:12px 0 8px">Komponen (Bahan Baku)</h4>
        <p style="font-size:12px;color:#6b7280;margin-bottom:8px">
          💡 Isi <strong>Std Unit Cost</strong> di SEMUA baris untuk mengaktifkan
          standard costing + variance journal. Kosongkan semua untuk mode actual cost (default).
        </p>
        <table class="data-table">
          <thead><tr>
            <th style="width:32%">Item</th>
            <th style="width:90px">Qty Required</th>
            <th style="width:75px">Scrap %</th>
            <th style="width:120px">Std Unit Cost</th>
            <th>Notes</th>
            <th></th>
          </tr></thead>
          <tbody id="bomLinesBody"></tbody>
        </table>
        <button class="btn btn-sm btn-outline" onclick="_bomAddLine()" style="margin-top:8px">+ Tambah komponen</button>
        <div style="margin-top:16px"><label>Catatan</label><textarea id="bomNotes" class="form-control" rows="2"></textarea></div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-outline" onclick="closeBOMModal()">Tutup</button>
        <button class="btn btn-primary" onclick="saveBOM(false)">Simpan Draft</button>
        <button class="btn btn-success" onclick="saveBOM(true)">Simpan + Activate</button>
      </div>
    </div>
  </div>`;
  document.body.insertAdjacentHTML('beforeend', html);
  _bomRenderLines();
}

function _bomRenderLines() {
  const stockItems = MfgState.items.filter(i => i.type === 'stock');
  const itemOpts = stockItems.map(i => `<option value="${i.id}">${_mfgEsc(i.name)}</option>`).join('');
  const body = document.getElementById('bomLinesBody');
  if (!body) return;
  body.innerHTML = _bomLines.map((ln, idx) => `
    <tr>
      <td><select class="form-control" onchange="_bomUpdateLine(${idx},'item_id',this.value)"><option value="">— pilih —</option>${itemOpts.replace(`value="${ln.item_id}"`, `value="${ln.item_id}" selected`)}</select></td>
      <td><input type="number" step="0.01" value="${ln.qty_required}" class="form-control" onchange="_bomUpdateLine(${idx},'qty_required',parseFloat(this.value)||0)"></td>
      <td><input type="number" step="0.1" value="${ln.scrap_pct}" min="0" max="99" class="form-control" onchange="_bomUpdateLine(${idx},'scrap_pct',parseFloat(this.value)||0)"></td>
      <td><input type="number" step="100" value="${ln.std_unit_cost ?? ''}" placeholder="opsional" class="form-control" onchange="_bomUpdateLine(${idx},'std_unit_cost',this.value === '' ? null : (parseFloat(this.value)||0))"></td>
      <td><input type="text" value="${_mfgEsc(ln.notes || '')}" class="form-control" onchange="_bomUpdateLine(${idx},'notes',this.value)"></td>
      <td><button class="btn btn-sm btn-danger" onclick="_bomRemoveLine(${idx})">×</button></td>
    </tr>`).join('');
}

function _bomUpdateLine(idx, field, value) { _bomLines[idx][field] = value; }
function _bomAddLine() { _bomLines.push({ item_id:'', qty_required:1, scrap_pct:0, std_unit_cost:'', notes:'' }); _bomRenderLines(); }
function _bomRemoveLine(idx) { _bomLines.splice(idx,1); if (!_bomLines.length) _bomAddLine(); else _bomRenderLines(); }
function closeBOMModal() { document.getElementById('bomModalBackdrop')?.remove(); }

async function saveBOM(activate) {
  const item_id    = document.getElementById('bomOutputItem').value;
  const qty_output = parseFloat(document.getElementById('bomQtyOutput').value) || 1;
  const bom_code   = document.getElementById('bomCode').value.trim();
  const notes      = document.getElementById('bomNotes').value;
  if (!item_id) { showToast('Output item wajib dipilih', 'error'); return; }
  const valid = _bomLines.filter(l => l.item_id && l.qty_required > 0);
  if (!valid.length) { showToast('Minimal 1 komponen valid', 'error'); return; }
  // Validate no self-ref locally too
  if (valid.some(l => l.item_id === item_id)) {
    showToast('Output item tidak boleh muncul sebagai komponen sendiri', 'error');
    return;
  }
  // Sprint M4: all-or-nothing std_unit_cost validation client-side
  const withStd    = valid.filter(l => l.std_unit_cost !== null && l.std_unit_cost !== '' && !isNaN(parseFloat(l.std_unit_cost)));
  const withoutStd = valid.filter(l => !(l.std_unit_cost !== null && l.std_unit_cost !== '' && !isNaN(parseFloat(l.std_unit_cost))));
  if (withStd.length && withoutStd.length) {
    showToast('Standard cost harus diisi di SEMUA baris atau KOSONG semua. Saat ini: '
              + `${withStd.length} dengan std, ${withoutStd.length} tanpa.`, 'error');
    return;
  }

  const payload = {
    item_id, qty_output, notes: notes || null,
    bom_code: bom_code || null,
    lines: valid.map(l => ({
      item_id: l.item_id,
      qty_required: l.qty_required,
      scrap_pct: l.scrap_pct || 0,
      std_unit_cost: (l.std_unit_cost === null || l.std_unit_cost === '' || isNaN(parseFloat(l.std_unit_cost)))
        ? null : parseFloat(l.std_unit_cost),
      notes: l.notes || null,
    })),
  };
  try {
    const res = await Api.boms.create(payload, activate ? {activate:'true'} : {});
    showToast(`BOM ${res.bom_code} ${activate?'di-activate':'tersimpan'}`, 'success');
    closeBOMModal();
    renderBOMPage();
  } catch (e) { showToast('Gagal: ' + e.message, 'error'); }
}

async function activateBOM(id) {
  if (!confirm('Activate BOM ini? BOM lain untuk item yang sama akan otomatis obsolete.')) return;
  try {
    await Api.boms.activate(id);
    showToast('BOM di-activate', 'success');
    renderBOMPage();
  } catch (e) { showToast('Gagal: ' + e.message, 'error'); }
}

async function obsoleteBOM(id) {
  if (!confirm('Obsolete BOM ini? Status tidak bisa di-activate lagi (clone untuk versi baru).')) return;
  try {
    await Api.boms.obsolete(id);
    showToast('BOM di-obsolete', 'warning');
    renderBOMPage();
  } catch (e) { showToast('Gagal: ' + e.message, 'error'); }
}

async function deleteBOM(id) {
  if (!confirm('Hapus BOM ini? Hanya draft yang bisa dihapus.')) return;
  try {
    await Api.boms.delete(id);
    showToast('BOM dihapus', 'warning');
    renderBOMPage();
  } catch (e) { showToast('Gagal: ' + e.message, 'error'); }
}

async function showBOMDetail(id) {
  try {
    const b = await Api.boms.get(id);
    const itemMap = Object.fromEntries(MfgState.items.map(i => [i.id, i.name]));
    const linesHtml = (b.lines || []).map(ln => `
      <tr>
        <td>${ln.line_no}</td>
        <td>${_mfgEsc(itemMap[ln.item_id] || ln.item_id?.slice(0,8))}</td>
        <td style="text-align:right">${ln.qty_required}</td>
        <td style="text-align:right">${ln.scrap_pct}%</td>
        <td style="text-align:right">${ln.std_unit_cost != null ? _mfgFmtRp(ln.std_unit_cost) : '<span style="color:#9ca3af">—</span>'}</td>
        <td>${_mfgEsc(ln.notes || '-')}</td>
      </tr>`).join('');
    const hasStd = (b.lines || []).every(l => l.std_unit_cost != null);
    const costingBadge = hasStd
      ? '<span style="display:inline-block;padding:2px 8px;background:#06b6d420;color:#06b6d4;border-radius:6px;font-size:11px;font-weight:600">📊 Standard Cost</span>'
      : '<span style="display:inline-block;padding:2px 8px;background:#6b728020;color:#6b7280;border-radius:6px;font-size:11px;font-weight:600">Actual Cost</span>';
    const html = `
    <div class="modal-backdrop" id="bomDetailBackdrop" onclick="if(event.target===this)this.remove()">
      <div class="modal-content" style="max-width:780px">
        <div class="modal-header">
          <h3>${_mfgEsc(b.bom_code)} — ${_bomStatusBadge(b.status)} ${costingBadge}</h3>
          <button class="modal-close" onclick="document.getElementById('bomDetailBackdrop').remove()">×</button>
        </div>
        <div class="modal-body">
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px">
            <div><strong>Output:</strong> ${_mfgEsc(itemMap[b.item_id] || b.item_id?.slice(0,8))}</div>
            <div><strong>Qty Output:</strong> ${b.qty_output}</div>
            <div><strong>Version:</strong> ${b.version}</div>
            <div><strong>Created:</strong> ${(b.created_at || '').slice(0,10)}</div>
          </div>
          <table class="data-table">
            <thead><tr><th>#</th><th>Komponen</th><th>Qty Required</th><th>Scrap%</th><th>Std Unit Cost</th><th>Notes</th></tr></thead>
            <tbody>${linesHtml}</tbody>
          </table>
          ${b.notes ? `<p style="margin-top:12px"><strong>Notes:</strong> ${_mfgEsc(b.notes)}</p>` : ''}
        </div>
      </div>
    </div>`;
    document.body.insertAdjacentHTML('beforeend', html);
  } catch (e) { showToast('Gagal: ' + e.message, 'error'); }
}

// ════════════════════════════════════════════════════════════════
// MANUFACTURING ORDER
// ════════════════════════════════════════════════════════════════

async function renderMfgOrderPage() {
  await _mfgEnsureMasters();
  const filterStatus = document.getElementById('moFilterStatus')?.value || '';
  try {
    const list = await Api.manufacturingOrders.list({
      status: filterStatus || undefined,
      limit: 200,
    });
    MfgState.mos = Array.isArray(list) ? list : [];
  } catch (e) {
    showToast('Gagal load MO: ' + e.message, 'error');
    MfgState.mos = [];
  }

  const wrap = document.getElementById('moTableWrap');
  if (!wrap) return;
  if (!MfgState.mos.length) {
    wrap.innerHTML = `<div style="padding:48px;text-align:center;color:#6b7280">Belum ada Manufacturing Order. Klik <strong>"Buat MO"</strong>.</div>`;
    return;
  }
  const itemMap = Object.fromEntries(MfgState.items.map(i => [i.id, i.name]));
  const whMap   = Object.fromEntries(MfgState.warehouses.map(w => [w.id, w.name]));
  wrap.innerHTML = `
    <table class="data-table">
      <thead><tr>
        <th>No MO</th><th>Output</th><th>Warehouse</th>
        <th style="text-align:right">Qty Plan</th>
        <th style="text-align:right">Produced</th>
        <th>Status</th>
        <th>Planned Start</th>
        <th style="text-align:center">Aksi</th>
      </tr></thead>
      <tbody>
      ${MfgState.mos.map(m => `
        <tr>
          <td><code>${_mfgEsc(m.mo_no)}</code></td>
          <td>${_mfgEsc(itemMap[m.item_id] || m.item_id?.slice(0,8))}</td>
          <td>${_mfgEsc(whMap[m.warehouse_id] || '-')}</td>
          <td style="text-align:right">${m.qty_planned}</td>
          <td style="text-align:right">${m.qty_produced || 0}</td>
          <td>${_moStatusBadge(m.status)}</td>
          <td>${m.planned_start || '-'}</td>
          <td style="text-align:center;white-space:nowrap">
            <button class="btn btn-sm btn-outline" onclick="showMODetail('${m.id}')">Detail</button>
            ${m.status === 'draft'     ? `<button class="btn btn-sm btn-primary" style="margin-left:4px" onclick="confirmMO('${m.id}')">Confirm</button>` : ''}
            ${m.status === 'confirmed' ? `<button class="btn btn-sm btn-info" style="margin-left:4px" onclick="startMO('${m.id}')">Start</button>` : ''}
            ${m.status === 'in_progress' ? `<button class="btn btn-sm btn-warning" style="margin-left:4px" onclick="showIssueModal('${m.id}')">Issue</button>` : ''}
            ${m.status === 'in_progress' ? `<button class="btn btn-sm btn-success" style="margin-left:4px" onclick="showCompleteModal('${m.id}')">Complete</button>` : ''}
            ${['draft','confirmed','in_progress'].includes(m.status) ? `<button class="btn btn-sm btn-danger" style="margin-left:4px" onclick="cancelMO('${m.id}')">Cancel</button>` : ''}
          </td>
        </tr>`).join('')}
      </tbody>
    </table>`;
}

async function showMOModal() {
  await _mfgEnsureMasters();
  // Load active BOMs for the picker
  let activeBoms = [];
  try {
    activeBoms = await Api.boms.list({status: 'active', limit: 200});
  } catch (e) { activeBoms = []; }
  if (!activeBoms.length) {
    showToast('Belum ada BOM active. Activate BOM dulu di Master BOM.', 'error');
    return;
  }
  const itemMap = Object.fromEntries(MfgState.items.map(i => [i.id, i.name]));
  const bomOpts = activeBoms.map(b =>
    `<option value="${b.id}" data-item="${b.item_id}">${_mfgEsc(b.bom_code)} — ${_mfgEsc(itemMap[b.item_id] || '?')}</option>`).join('');
  const whOpts = MfgState.warehouses.map(w => `<option value="${w.id}">${_mfgEsc(w.name)}</option>`).join('');

  const html = `
  <div class="modal-backdrop" id="moModalBackdrop" onclick="if(event.target===this)closeMOModal()">
    <div class="modal-content" style="max-width:700px">
      <div class="modal-header">
        <h3>Buat Manufacturing Order</h3>
        <button class="modal-close" onclick="closeMOModal()">×</button>
      </div>
      <div class="modal-body">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px">
          <div><label>BOM (Active)</label>
            <select id="moBom" class="form-control" onchange="_moPreviewBOM()"><option value="">— pilih —</option>${bomOpts}</select>
          </div>
          <div><label>Qty Plan (output)</label>
            <input type="number" step="1" id="moQtyPlanned" value="1" class="form-control" oninput="_moPreviewBOM()">
          </div>
          <div><label>Warehouse</label>
            <select id="moWarehouse" class="form-control">${whOpts}</select>
          </div>
          <div><label>Tanggal Mulai (planned)</label>
            <input type="date" id="moPlannedStart" value="${_mfgToday()}" class="form-control">
          </div>
          <div><label>Tanggal Selesai (planned)</label>
            <input type="date" id="moPlannedEnd" class="form-control">
          </div>
          <div><label style="display:flex;align-items:center;gap:8px;margin-top:24px"><input type="checkbox" id="moBackflush" checked> <span>Backflush (auto-issue saat complete)</span></label></div>
        </div>
        <h4 style="margin:12px 0 8px">Komponen yang akan dibutuhkan (pratampil)</h4>
        <div id="moBomPreview" style="font-size:13px;color:#6b7280;padding:12px;border:1px solid #e5e7eb;border-radius:6px;background:#fafafa">Pilih BOM dulu</div>
        <div style="margin-top:12px"><label>Notes</label><textarea id="moNotes" class="form-control" rows="2"></textarea></div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-outline" onclick="closeMOModal()">Tutup</button>
        <button class="btn btn-primary" onclick="saveMO(false)">Simpan Draft</button>
        <button class="btn btn-success" onclick="saveMO(true)">Simpan + Confirm</button>
      </div>
    </div>
  </div>`;
  document.body.insertAdjacentHTML('beforeend', html);
  // Cache BOM data for preview
  window._activeBoms = activeBoms;
}

async function _moPreviewBOM() {
  const bomId = document.getElementById('moBom').value;
  const qty   = parseFloat(document.getElementById('moQtyPlanned').value) || 0;
  const preview = document.getElementById('moBomPreview');
  if (!preview) return;
  if (!bomId || !qty) {
    preview.innerHTML = 'Pilih BOM dan qty dulu';
    return;
  }
  const bom = (window._activeBoms || []).find(b => b.id === bomId);
  if (!bom) { preview.innerHTML = 'BOM tidak ditemukan'; return; }
  const ratio = qty / parseFloat(bom.qty_output);
  const itemMap = Object.fromEntries(MfgState.items.map(i => [i.id, i.name]));
  const rows = (bom.lines || []).map(ln => {
    const need = ln.qty_required * ratio * (1 + (ln.scrap_pct || 0)/100);
    return `<tr><td>${_mfgEsc(itemMap[ln.item_id] || ln.item_id?.slice(0,8))}</td><td style="text-align:right">${ln.qty_required} × ${ratio.toFixed(2)}</td><td style="text-align:right">${ln.scrap_pct}%</td><td style="text-align:right"><strong>${need.toFixed(2)}</strong></td></tr>`;
  }).join('');
  preview.innerHTML = `<table style="width:100%;font-size:13px">
    <thead><tr><th>Item</th><th style="text-align:right">Base</th><th style="text-align:right">Scrap</th><th style="text-align:right">Qty Dibutuhkan</th></tr></thead>
    <tbody>${rows}</tbody>
  </table>`;
}

function closeMOModal() { document.getElementById('moModalBackdrop')?.remove(); }

async function saveMO(confirmNow) {
  const bom_id        = document.getElementById('moBom').value;
  const qty_planned   = parseFloat(document.getElementById('moQtyPlanned').value) || 0;
  const warehouse_id  = document.getElementById('moWarehouse').value;
  const planned_start = document.getElementById('moPlannedStart').value;
  const planned_end   = document.getElementById('moPlannedEnd').value;
  const backflush     = document.getElementById('moBackflush').checked;
  const notes         = document.getElementById('moNotes').value;

  if (!bom_id) { showToast('BOM wajib dipilih', 'error'); return; }
  if (qty_planned <= 0) { showToast('Qty plan harus > 0', 'error'); return; }
  if (!warehouse_id) { showToast('Warehouse wajib', 'error'); return; }

  const payload = {
    bom_id, warehouse_id, qty_planned, backflush,
    planned_start: planned_start || null,
    planned_end:   planned_end   || null,
    notes: notes || null,
  };
  try {
    const res = await Api.manufacturingOrders.create(payload, confirmNow ? {confirm:'true'} : {});
    showToast(`MO ${res.mo_no} ${confirmNow?'di-confirm':'tersimpan'}`, 'success');
    closeMOModal();
    renderMfgOrderPage();
  } catch (e) { showToast('Gagal: ' + e.message, 'error'); }
}

async function confirmMO(id) {
  if (!confirm('Confirm MO ini? Komponen ter-snapshot dari BOM.')) return;
  try {
    await Api.manufacturingOrders.confirm(id);
    showToast('MO di-confirm', 'success');
    renderMfgOrderPage();
  } catch (e) { showToast('Gagal: ' + e.message, 'error'); }
}

async function startMO(id) {
  if (!confirm('Start MO? Status → in_progress.')) return;
  try {
    await Api.manufacturingOrders.start(id);
    showToast('MO started', 'success');
    renderMfgOrderPage();
  } catch (e) { showToast('Gagal: ' + e.message, 'error'); }
}

async function cancelMO(id) {
  const reason = prompt('Alasan cancel?');
  if (!reason) return;
  try {
    await Api.manufacturingOrders.cancel(id, {reason});
    showToast('MO di-cancel (stock + journal reverted bila ada)', 'warning');
    renderMfgOrderPage();
  } catch (e) { showToast('Gagal: ' + e.message, 'error'); }
}

async function showIssueModal(moId) {
  try {
    const mo = await Api.manufacturingOrders.get(moId);
    const itemMap = Object.fromEntries(MfgState.items.map(i => [i.id, i.name]));
    const rows = (mo.components || []).map((c, idx) => {
      const remaining = parseFloat(c.qty_planned) - parseFloat(c.qty_issued || 0);
      return `
        <tr>
          <td><label><input type="checkbox" class="moi-cb" data-comp-id="${c.id}" data-max="${remaining}" ${remaining > 0 ? 'checked' : 'disabled'}> ${_mfgEsc(itemMap[c.item_id] || c.item_id?.slice(0,8))}</label></td>
          <td style="text-align:right">${c.qty_planned}</td>
          <td style="text-align:right">${c.qty_issued || 0}</td>
          <td style="text-align:right;color:#f59e0b"><strong>${remaining}</strong></td>
          <td><input type="number" step="0.01" class="moi-qty form-control" data-comp-id="${c.id}" value="${remaining}" ${remaining <= 0 ? 'disabled' : ''} style="width:90px"></td>
        </tr>`;
    }).join('');
    const html = `
    <div class="modal-backdrop" id="issueModalBackdrop" onclick="if(event.target===this)this.remove()">
      <div class="modal-content" style="max-width:720px">
        <div class="modal-header">
          <h3>Issue Materials — ${_mfgEsc(mo.mo_no)}</h3>
          <button class="modal-close" onclick="document.getElementById('issueModalBackdrop').remove()">×</button>
        </div>
        <div class="modal-body">
          <p style="color:#6b7280;font-size:13px">Stock akan keluar dari warehouse + journal <strong>Dr WIP / Cr Inventory</strong> otomatis dibuat.</p>
          <table class="data-table">
            <thead><tr><th>Komponen (centang)</th><th>Plan</th><th>Issued</th><th>Remaining</th><th>Qty Issue</th></tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
        <div class="modal-footer">
          <button class="btn btn-outline" onclick="document.getElementById('issueModalBackdrop').remove()">Tutup</button>
          <button class="btn btn-primary" onclick="submitIssue('${mo.id}')">Issue Materials</button>
        </div>
      </div>
    </div>`;
    document.body.insertAdjacentHTML('beforeend', html);
  } catch (e) { showToast('Gagal load MO: ' + e.message, 'error'); }
}

async function submitIssue(moId) {
  const lines = [];
  document.querySelectorAll('.moi-cb').forEach(cb => {
    if (cb.checked) {
      const id = cb.dataset.compId;
      const qty = parseFloat(document.querySelector(`.moi-qty[data-comp-id="${id}"]`).value) || 0;
      const max = parseFloat(cb.dataset.max);
      if (qty > 0 && qty <= max + 0.0001) lines.push({ component_id: id, qty });
    }
  });
  if (!lines.length) { showToast('Pilih minimal 1 komponen dengan qty > 0', 'error'); return; }
  try {
    await Api.manufacturingOrders.issue(moId, { lines });
    showToast('Materials di-issue + journal posted', 'success');
    document.getElementById('issueModalBackdrop')?.remove();
    renderMfgOrderPage();
  } catch (e) { showToast('Gagal: ' + e.message, 'error'); }
}

async function showCompleteModal(moId) {
  try {
    const mo = await Api.manufacturingOrders.get(moId);
    const html = `
    <div class="modal-backdrop" id="completeModalBackdrop" onclick="if(event.target===this)this.remove()">
      <div class="modal-content" style="max-width:560px">
        <div class="modal-header">
          <h3>Complete MO — ${_mfgEsc(mo.mo_no)}</h3>
          <button class="modal-close" onclick="document.getElementById('completeModalBackdrop').remove()">×</button>
        </div>
        <div class="modal-body">
          <p style="color:#6b7280;font-size:13px">Backflush <strong>${mo.backflush ? 'AKTIF' : 'OFF'}</strong> — ${mo.backflush ? 'sisa komponen akan auto-di-issue.' : 'pastikan semua komponen sudah di-issue manual.'}</p>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:12px">
            <div><label>Qty Diproduksi</label>
              <input type="number" step="0.01" id="moCompleteQty" value="${mo.qty_planned}" class="form-control">
              <small style="color:#6b7280">Plan: ${mo.qty_planned} · Toleransi: ${(parseFloat(mo.qty_planned) * 1.2).toFixed(2)}</small>
            </div>
            <div><label>Tanggal Selesai</label>
              <input type="date" id="moCompleteDate" value="${_mfgToday()}" class="form-control">
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-outline" onclick="document.getElementById('completeModalBackdrop').remove()">Tutup</button>
          <button class="btn btn-success" onclick="submitComplete('${mo.id}')">Complete MO</button>
        </div>
      </div>
    </div>`;
    document.body.insertAdjacentHTML('beforeend', html);
  } catch (e) { showToast('Gagal: ' + e.message, 'error'); }
}

async function submitComplete(moId) {
  const qty_produced  = parseFloat(document.getElementById('moCompleteQty').value) || 0;
  const complete_date = document.getElementById('moCompleteDate').value || _mfgToday();
  if (qty_produced <= 0) { showToast('Qty produced wajib > 0', 'error'); return; }
  try {
    const res = await Api.manufacturingOrders.complete(moId, { qty_produced, complete_date });
    showToast(`MO ${res.mo_no} selesai · ${res.qty_produced} unit produced`, 'success');
    document.getElementById('completeModalBackdrop')?.remove();
    renderMfgOrderPage();
  } catch (e) { showToast('Gagal: ' + e.message, 'error'); }
}

async function showMODetail(id) {
  try {
    const m = await Api.manufacturingOrders.get(id);
    const itemMap = Object.fromEntries(MfgState.items.map(i => [i.id, i.name]));
    const whMap   = Object.fromEntries(MfgState.warehouses.map(w => [w.id, w.name]));
    const hasStd = (m.components || []).every(c => c.std_unit_cost != null);
    const rows = (m.components || []).map((c, idx) => {
      const actTotal = parseFloat(c.qty_issued||0) * parseFloat(c.unit_cost||0);
      const stdTotal = c.std_unit_cost != null
        ? parseFloat(c.qty_issued||0) * parseFloat(c.std_unit_cost)
        : null;
      return `
      <tr>
        <td>${idx+1}</td>
        <td>${_mfgEsc(itemMap[c.item_id] || c.item_id?.slice(0,8))}</td>
        <td style="text-align:right">${c.qty_planned}</td>
        <td style="text-align:right">${c.qty_issued || 0}</td>
        <td style="text-align:right">${_mfgFmtRp(c.unit_cost)}</td>
        <td style="text-align:right">${c.std_unit_cost != null ? _mfgFmtRp(c.std_unit_cost) : '—'}</td>
        <td style="text-align:right">${_mfgFmtRp(actTotal)}</td>
        <td style="text-align:right">${stdTotal != null ? _mfgFmtRp(stdTotal) : '—'}</td>
      </tr>`;
    }).join('');
    const totalWip = (m.components || []).reduce(
      (s, c) => s + parseFloat(c.qty_issued||0) * parseFloat(c.unit_cost||0), 0
    );
    const variance   = m.variance_amount != null ? parseFloat(m.variance_amount) : null;
    const stdTotal   = m.std_total_cost != null  ? parseFloat(m.std_total_cost)  : null;
    const varColor   = variance == null ? '#6b7280' : (variance > 0 ? '#ef4444' : '#10b981');
    const varLabel   = variance == null ? '' : (variance > 0 ? ' (unfavorable)' : variance < 0 ? ' (favorable)' : '');
    const html = `
    <div class="modal-backdrop" id="moDetailBackdrop" onclick="if(event.target===this)this.remove()">
      <div class="modal-content" style="max-width:880px">
        <div class="modal-header">
          <h3>${_mfgEsc(m.mo_no)} — ${_moStatusBadge(m.status)}</h3>
          <button class="modal-close" onclick="document.getElementById('moDetailBackdrop').remove()">×</button>
        </div>
        <div class="modal-body">
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px">
            <div><strong>Output:</strong> ${_mfgEsc(itemMap[m.item_id] || m.item_id?.slice(0,8))}</div>
            <div><strong>Warehouse:</strong> ${_mfgEsc(whMap[m.warehouse_id] || '-')}</div>
            <div><strong>Qty Plan:</strong> ${m.qty_planned}</div>
            <div><strong>Qty Produced:</strong> ${m.qty_produced || 0}</div>
            <div><strong>Backflush:</strong> ${m.backflush ? 'ON' : 'OFF'}</div>
            <div><strong>Planned Start:</strong> ${m.planned_start || '-'}</div>
            <div><strong>Actual Start:</strong> ${m.actual_start ? new Date(m.actual_start).toLocaleString() : '-'}</div>
            <div><strong>Done At:</strong> ${m.done_at ? new Date(m.done_at).toLocaleString() : '-'}</div>
            <div><strong>Issue Journal:</strong> ${m.issue_journal_entry_id ? `<code>${_mfgEsc(m.issue_journal_entry_id.slice(0,8))}</code>` : '-'}</div>
            <div><strong>Receipt Journal:</strong> ${m.receipt_journal_entry_id ? `<code>${_mfgEsc(m.receipt_journal_entry_id.slice(0,8))}</code>` : '-'}</div>
            ${m.variance_journal_entry_id ? `<div><strong>Variance Journal:</strong> <code>${_mfgEsc(m.variance_journal_entry_id.slice(0,8))}</code></div>` : ''}
          </div>
          <h4>Komponen ${hasStd ? '<span style="font-size:11px;color:#06b6d4">📊 Standard Cost mode</span>' : '<span style="font-size:11px;color:#6b7280">Actual Cost mode</span>'}</h4>
          <table class="data-table">
            <thead><tr>
              <th>#</th><th>Item</th><th>Plan</th><th>Issued</th>
              <th>Actual Unit</th><th>Std Unit</th>
              <th>Actual Total</th><th>Std Total</th>
            </tr></thead>
            <tbody>${rows}</tbody>
            <tfoot>
              <tr>
                <th colspan="6" style="text-align:right">Total Actual (WIP)</th>
                <th colspan="2" style="text-align:right">${_mfgFmtRp(totalWip)}</th>
              </tr>
              ${stdTotal != null ? `<tr>
                <th colspan="6" style="text-align:right">Total Standard</th>
                <th colspan="2" style="text-align:right">${_mfgFmtRp(stdTotal)}</th>
              </tr>` : ''}
              ${variance != null ? `<tr>
                <th colspan="6" style="text-align:right;color:${varColor}">Variance${varLabel}</th>
                <th colspan="2" style="text-align:right;color:${varColor};font-weight:700">${variance >= 0 ? '+' : ''}${_mfgFmtRp(variance)}</th>
              </tr>` : ''}
            </tfoot>
          </table>
          ${m.cancel_reason ? `<p style="margin-top:12px;color:#ef4444"><strong>Cancel reason:</strong> ${_mfgEsc(m.cancel_reason)}</p>` : ''}
          ${m.notes ? `<p style="margin-top:12px"><strong>Notes:</strong> ${_mfgEsc(m.notes)}</p>` : ''}
        </div>
      </div>
    </div>`;
    document.body.insertAdjacentHTML('beforeend', html);
  } catch (e) { showToast('Gagal: ' + e.message, 'error'); }
}

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
  workCenters: [],
};

const _mfgFmtRp = (n) => 'Rp ' + Math.round(n || 0).toLocaleString('id-ID');
const _mfgEsc   = (s) => String(s ?? '').replace(/[<>&"]/g, c => ({'<':'&lt;','>':'&gt;','&':'&amp;','"':'&quot;'}[c]));
const _mfgToday = () => new Date().toISOString().slice(0,10);

async function _mfgEnsureMasters(force) {
  if (force || !MfgState.items.length || !MfgState.warehouses.length || !MfgState.workCenters.length) {
    try {
      const [items, whs, wcs] = await Promise.all([
        Api.items.list({limit: 500}),
        Api.warehouses.list(),
        Api.workCenters ? Api.workCenters.list({is_active: 'true'}).catch(() => []) : Promise.resolve([]),
      ]);
      MfgState.items       = Array.isArray(items) ? items : [];
      MfgState.warehouses  = Array.isArray(whs)   ? whs   : [];
      MfgState.workCenters = Array.isArray(wcs)   ? wcs   : [];
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
            ${b.status === 'draft' ? `<button class="btn btn-sm btn-info" style="margin-left:4px" onclick="showBOMForm('${b.id}')">Edit</button>` : ''}
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
            ${['confirmed','in_progress'].includes(m.status) && (m.operations || []).length > 0 ? `<button class="btn btn-sm btn-info" style="margin-left:4px" onclick="showOperationsModal('${m.id}')">Ops</button>` : ''}
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
            ${m.labor_journal_entry_id ? `<div><strong>Labor Journal:</strong> <code>${_mfgEsc(m.labor_journal_entry_id.slice(0,8))}</code></div>` : ''}
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
              ${m.labor_total_cost != null && parseFloat(m.labor_total_cost) > 0 ? `<tr>
                <th colspan="6" style="text-align:right;color:#06b6d4">🔧 Labor Cost (Cr mfg_labor_applied)</th>
                <th colspan="2" style="text-align:right;color:#06b6d4;font-weight:700">${_mfgFmtRp(m.labor_total_cost)}</th>
              </tr>` : ''}
            </tfoot>
          </table>
          ${(m.operations || []).length > 0 ? `
          <h4 style="margin-top:16px">Operations / Routing</h4>
          <table class="data-table">
            <thead><tr>
              <th>#</th><th>Operasi</th>
              <th style="text-align:right">Planned (min)</th>
              <th style="text-align:right">Actual (min)</th>
              <th style="text-align:right">Cost/Hour</th>
              <th style="text-align:right">Total</th>
              <th>Status</th>
            </tr></thead>
            <tbody>
              ${m.operations.map(op => {
                const cost = (parseFloat(op.actual_time_min || 0) * parseFloat(op.cost_per_hour_snapshot || 0)) / 60;
                return `<tr>
                  <td>${op.seq}</td>
                  <td>${_mfgEsc(op.name)}</td>
                  <td style="text-align:right">${op.planned_time_min}</td>
                  <td style="text-align:right">${op.actual_time_min}</td>
                  <td style="text-align:right">${_mfgFmtRp(op.cost_per_hour_snapshot)}</td>
                  <td style="text-align:right">${_mfgFmtRp(cost)}</td>
                  <td>${op.status}</td>
                </tr>`;
              }).join('')}
            </tbody>
          </table>
          ` : ''}
          ${m.cancel_reason ? `<p style="margin-top:12px;color:#ef4444"><strong>Cancel reason:</strong> ${_mfgEsc(m.cancel_reason)}</p>` : ''}
          ${m.notes ? `<p style="margin-top:12px"><strong>Notes:</strong> ${_mfgEsc(m.notes)}</p>` : ''}
        </div>
      </div>
    </div>`;
    document.body.insertAdjacentHTML('beforeend', html);
  } catch (e) { showToast('Gagal: ' + e.message, 'error'); }
}


// ════════════════════════════════════════════════════════════════
// WORK CENTER (Sprint M5)
// ════════════════════════════════════════════════════════════════

async function renderWorkCenterPage() {
  await _mfgEnsureMasters(true);
  try {
    const list = await Api.workCenters.list({});
    MfgState.workCenters = Array.isArray(list) ? list : [];
  } catch (e) {
    showToast('Gagal load Work Center: ' + e.message, 'error');
    MfgState.workCenters = [];
  }
  const wrap = document.getElementById('wcTableWrap');
  if (!wrap) return;
  if (!MfgState.workCenters.length) {
    wrap.innerHTML = `<div style="padding:48px;text-align:center;color:#6b7280">Belum ada Work Center. Klik <strong>"Buat Work Center"</strong>.</div>`;
    return;
  }
  wrap.innerHTML = `
    <table class="data-table">
      <thead><tr>
        <th>Code</th><th>Name</th>
        <th style="text-align:right">Cost/Hour</th>
        <th style="text-align:right">Capacity/Day</th>
        <th>Status</th>
        <th style="text-align:center">Aksi</th>
      </tr></thead>
      <tbody>
      ${MfgState.workCenters.map(w => `
        <tr>
          <td><code>${_mfgEsc(w.code)}</code></td>
          <td>${_mfgEsc(w.name)}</td>
          <td style="text-align:right">${_mfgFmtRp(w.cost_per_hour)}</td>
          <td style="text-align:right">${w.capacity_hours_per_day} jam</td>
          <td>${w.is_active ? '<span style="color:#10b981;font-weight:600">Active</span>' : '<span style="color:#ef4444">Inactive</span>'}</td>
          <td style="text-align:center;white-space:nowrap">
            <button class="btn btn-sm btn-outline" onclick="showWorkCenterModal('${w.id}')">Edit</button>
            ${w.is_active ? `<button class="btn btn-sm btn-warning" style="margin-left:4px" onclick="toggleWorkCenter('${w.id}',false)">Nonaktifkan</button>` : `<button class="btn btn-sm btn-success" style="margin-left:4px" onclick="toggleWorkCenter('${w.id}',true)">Aktifkan</button>`}
          </td>
        </tr>`).join('')}
      </tbody>
    </table>`;
}

function showWorkCenterModal(id) {
  const wc = id ? MfgState.workCenters.find(w => w.id === id) : null;
  const html = `
  <div class="modal-backdrop" id="wcModalBackdrop" onclick="if(event.target===this)this.remove()">
    <div class="modal-content" style="max-width:560px">
      <div class="modal-header">
        <h3>${id ? 'Edit' : 'Buat'} Work Center</h3>
        <button class="modal-close" onclick="document.getElementById('wcModalBackdrop').remove()">×</button>
      </div>
      <div class="modal-body">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
          <div><label>Code</label><input type="text" id="wcCode" value="${_mfgEsc(wc?.code || '')}" class="form-control" ${id?'readonly':''}></div>
          <div><label>Name</label><input type="text" id="wcName" value="${_mfgEsc(wc?.name || '')}" class="form-control"></div>
          <div><label>Cost per Hour (Rp)</label><input type="number" step="500" id="wcCost" value="${wc?.cost_per_hour || 0}" class="form-control"></div>
          <div><label>Capacity (jam/hari)</label><input type="number" step="0.5" id="wcCap" value="${wc?.capacity_hours_per_day || 8}" class="form-control"></div>
        </div>
        <div style="margin-top:12px"><label>Notes</label><textarea id="wcNotes" rows="2" class="form-control">${_mfgEsc(wc?.notes || '')}</textarea></div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-outline" onclick="document.getElementById('wcModalBackdrop').remove()">Tutup</button>
        <button class="btn btn-primary" onclick="saveWorkCenter('${id || ''}')">Simpan</button>
      </div>
    </div>
  </div>`;
  document.body.insertAdjacentHTML('beforeend', html);
}

async function saveWorkCenter(id) {
  const code = document.getElementById('wcCode').value.trim();
  const name = document.getElementById('wcName').value.trim();
  const cost = parseFloat(document.getElementById('wcCost').value) || 0;
  const cap  = parseFloat(document.getElementById('wcCap').value) || 8;
  const notes = document.getElementById('wcNotes').value;
  if (!code || !name) { showToast('Code & name wajib', 'error'); return; }
  try {
    if (id) {
      await Api.workCenters.update(id, { name, cost_per_hour: cost, capacity_hours_per_day: cap, notes: notes || null });
      showToast('Work center diperbarui', 'success');
    } else {
      await Api.workCenters.create({ code, name, cost_per_hour: cost, capacity_hours_per_day: cap, notes: notes || null });
      showToast('Work center dibuat', 'success');
    }
    document.getElementById('wcModalBackdrop')?.remove();
    renderWorkCenterPage();
  } catch (e) { showToast('Gagal: ' + e.message, 'error'); }
}

async function toggleWorkCenter(id, active) {
  if (!confirm(active ? 'Aktifkan WC ini?' : 'Nonaktifkan WC ini? BOM yang pakai WC ini tidak bisa di-activate sampai diaktifkan lagi.')) return;
  try {
    await Api.workCenters.update(id, { is_active: active });
    showToast(active ? 'WC aktif' : 'WC nonaktif', 'success');
    renderWorkCenterPage();
  } catch (e) { showToast('Gagal: ' + e.message, 'error'); }
}

// ════════════════════════════════════════════════════════════════
// BOM operations editor (extends Sprint M1/M4 modal)
// ════════════════════════════════════════════════════════════════

let _bomOps = [];

function _bomOpsRender() {
  const body = document.getElementById('bomOpsBody');
  if (!body) return;
  const wcOpts = MfgState.workCenters.map(w =>
    `<option value="${w.id}" data-cph="${w.cost_per_hour}">${_mfgEsc(w.code)} — ${_mfgEsc(w.name)} (Rp ${Math.round(w.cost_per_hour).toLocaleString('id-ID')}/jam)</option>`
  ).join('');
  body.innerHTML = _bomOps.map((op, idx) => `
    <tr>
      <td>${idx+1}</td>
      <td><input type="text" value="${_mfgEsc(op.name || '')}" placeholder="cth: Cutting" class="form-control" onchange="_bomOpsUpdate(${idx},'name',this.value)"></td>
      <td><select class="form-control" onchange="_bomOpsUpdate(${idx},'work_center_id',this.value)"><option value="">— pilih —</option>${wcOpts.replace(`value="${op.work_center_id}"`, `value="${op.work_center_id}" selected`)}</select></td>
      <td><input type="number" step="0.5" value="${op.time_minutes ?? 0}" class="form-control" onchange="_bomOpsUpdate(${idx},'time_minutes',parseFloat(this.value)||0)"></td>
      <td><input type="number" step="0.5" value="${op.setup_minutes ?? 0}" class="form-control" onchange="_bomOpsUpdate(${idx},'setup_minutes',parseFloat(this.value)||0)"></td>
      <td><button class="btn btn-sm btn-danger" onclick="_bomOpsRemove(${idx})">×</button></td>
    </tr>`).join('');
}
function _bomOpsUpdate(idx, field, value) { _bomOps[idx][field] = value; }
function _bomOpsAdd() { _bomOps.push({ name:'', work_center_id:'', time_minutes:0, setup_minutes:0 }); _bomOpsRender(); }
function _bomOpsRemove(idx) { _bomOps.splice(idx,1); _bomOpsRender(); }

// Hook into the existing showBOMModal: re-render after it inserts, then add the
// Operations section if not present. We do this with a wrapper.
const _origShowBOMModal = window.showBOMModal;
window.showBOMModal = function() {
  _bomOps = [];
  _origShowBOMModal();
  // Inject operations section below components if WC list is available
  setTimeout(() => {
    const modal = document.getElementById('bomModalBackdrop');
    if (!modal) return;
    const body = modal.querySelector('.modal-body');
    if (!body) return;
    if (!MfgState.workCenters.length) {
      const warn = document.createElement('p');
      warn.style.cssText = 'font-size:12px;color:#9ca3af;margin-top:12px;border-top:1px dashed #e5e7eb;padding-top:8px';
      warn.innerHTML = '💡 Tambahkan <strong>Work Center</strong> dulu (sidebar Manufacturing → Work Center) untuk mengaktifkan routing operations & labor cost.';
      body.appendChild(warn);
      return;
    }
    const opsBlock = document.createElement('div');
    opsBlock.innerHTML = `
      <h4 style="margin:16px 0 8px;border-top:1px solid #e5e7eb;padding-top:12px">Operations / Routing (opsional)</h4>
      <p style="font-size:12px;color:#6b7280;margin-bottom:8px">
        💡 Tambahkan langkah produksi untuk track labor cost. Kosongkan untuk mode tanpa labor.
      </p>
      <table class="data-table">
        <thead><tr>
          <th style="width:30px">#</th>
          <th>Nama Operasi</th>
          <th>Work Center</th>
          <th style="width:90px">Time/unit (menit)</th>
          <th style="width:90px">Setup (menit)</th>
          <th></th>
        </tr></thead>
        <tbody id="bomOpsBody"></tbody>
      </table>
      <button class="btn btn-sm btn-outline" onclick="_bomOpsAdd()" style="margin-top:8px">+ Tambah operasi</button>`;
    body.appendChild(opsBlock);
    _bomOpsRender();
  }, 50);
};

// Wrap saveBOM to include operations payload
const _origSaveBOM = window.saveBOM;
window.saveBOM = async function(activate) {
  // Build operations payload separately, then call original saveBOM
  // but we need to inject ops into the payload. The cleanest way: monkey-patch
  // Api.boms.create to add ops once.
  const validOps = _bomOps.filter(o => o.name && o.work_center_id);
  if (validOps.length && _bomOps.some(o => !o.name || !o.work_center_id)) {
    showToast('Setiap operation butuh nama + work center', 'error');
    return;
  }
  const origCreate = Api.boms.create;
  Api.boms.create = (body, opts) => origCreate({ ...body, operations: validOps.map(o => ({
    name: o.name,
    work_center_id: o.work_center_id,
    time_minutes: parseFloat(o.time_minutes) || 0,
    setup_minutes: parseFloat(o.setup_minutes) || 0,
  })) }, opts);
  try {
    await _origSaveBOM(activate);
  } finally {
    Api.boms.create = origCreate;
  }
};

// ════════════════════════════════════════════════════════════════
// MO operations modal (update actual_time)
// ════════════════════════════════════════════════════════════════

async function showOperationsModal(moId) {
  try {
    const mo = await Api.manufacturingOrders.get(moId);
    if (!mo.operations || mo.operations.length === 0) {
      showToast('MO ini tidak punya operations (BOM-nya tidak punya routing)', 'info');
      return;
    }
    const wcMap = Object.fromEntries(MfgState.workCenters.map(w => [w.id, w]));
    const rows = mo.operations.map(op => {
      const wc = wcMap[op.work_center_id];
      return `
        <tr>
          <td>${op.seq}</td>
          <td>${_mfgEsc(op.name)}</td>
          <td>${wc ? _mfgEsc(wc.code) : op.work_center_id.slice(0,8)}</td>
          <td style="text-align:right">${op.planned_time_min}</td>
          <td><input type="number" step="0.5" class="moop-actual form-control" data-op-id="${op.id}" value="${op.actual_time_min || 0}" style="width:80px"></td>
          <td style="text-align:right">${_mfgFmtRp(op.cost_per_hour_snapshot)}</td>
          <td>
            <select class="moop-status form-control" data-op-id="${op.id}">
              <option value="pending"     ${op.status==='pending'?'selected':''}>Pending</option>
              <option value="in_progress" ${op.status==='in_progress'?'selected':''}>In Progress</option>
              <option value="done"        ${op.status==='done'?'selected':''}>Done</option>
            </select>
          </td>
        </tr>`;
    }).join('');
    const html = `
    <div class="modal-backdrop" id="opsModalBackdrop" onclick="if(event.target===this)this.remove()">
      <div class="modal-content" style="max-width:880px">
        <div class="modal-header">
          <h3>Operations — ${_mfgEsc(mo.mo_no)}</h3>
          <button class="modal-close" onclick="document.getElementById('opsModalBackdrop').remove()">×</button>
        </div>
        <div class="modal-body">
          <p style="color:#6b7280;font-size:13px">Isi <strong>Actual Time (menit)</strong> untuk setiap operasi. Saat MO complete, total labor = Σ(actual × cost_per_hour ÷ 60) → journal <strong>Dr WIP / Cr Labor Applied</strong>.</p>
          <table class="data-table">
            <thead><tr>
              <th>#</th><th>Operasi</th><th>WC</th>
              <th style="text-align:right">Planned (min)</th>
              <th>Actual (min)</th>
              <th style="text-align:right">Rate/hr</th>
              <th>Status</th>
            </tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
        <div class="modal-footer">
          <button class="btn btn-outline" onclick="document.getElementById('opsModalBackdrop').remove()">Tutup</button>
          <button class="btn btn-primary" onclick="submitOperationsUpdate('${mo.id}')">Simpan</button>
        </div>
      </div>
    </div>`;
    document.body.insertAdjacentHTML('beforeend', html);
  } catch (e) { showToast('Gagal load MO: ' + e.message, 'error'); }
}

async function submitOperationsUpdate(moId) {
  const ops = [];
  document.querySelectorAll('.moop-actual').forEach(inp => {
    const id = inp.dataset.opId;
    const status = document.querySelector(`.moop-status[data-op-id="${id}"]`)?.value;
    ops.push({
      id,
      actual_time_min: parseFloat(inp.value) || 0,
      status,
    });
  });
  try {
    await Api.manufacturingOrders.updateOperations(moId, { operations: ops });
    showToast('Operations updated', 'success');
    document.getElementById('opsModalBackdrop')?.remove();
    if (AppState.currentPage === 'mfg-orders') renderMfgOrderPage();
  } catch (e) { showToast('Gagal: ' + e.message, 'error'); }
}


// ════════════════════════════════════════════════════════════════
// Sprint F1: Form-page pattern for BOM + MO (replaces modals)
// ════════════════════════════════════════════════════════════════

let _bomFormEditId = null;   // null = create mode
let _moFormPrefill = null;   // any pre-fill state for MO create

// ── BOM ─────────────────────────────────────────────────
function showBOMForm(id) {
  _bomFormEditId = id || null;
  navigateTo('bom-form');
  // renderBOMForm will be called by the route handler.
}

function exitBOMForm() {
  // Lightweight dirty check: warn if any line has data
  const hasData = (_bomLines || []).some(l => l.item_id || (l.qty_required && l.qty_required !== 1));
  if (hasData && !confirm('Perubahan belum disimpan. Yakin keluar?')) return;
  _bomFormEditId = null;
  _bomLines = [];
  _bomOps = [];
  navigateTo('bom-master');
}

async function renderBOMForm() {
  await _mfgEnsureMasters();
  const id = _bomFormEditId;
  let bom = null;
  if (id) {
    try { bom = await Api.boms.get(id); } catch (e) { /* not found */ }
    if (!bom) {
      showToast('BOM tidak ditemukan', 'error');
      navigateTo('bom-master');
      return;
    }
    if (bom.status !== 'draft') {
      showToast(`BOM status "${bom.status}" tidak bisa diedit. Membuka detail saja.`, 'info');
      navigateTo('bom-master');
      showBOMDetail(id);
      return;
    }
  }

  // Initialize state
  _bomLines = bom?.lines?.length ? bom.lines.map(l => ({
    item_id: l.item_id,
    qty_required: parseFloat(l.qty_required),
    scrap_pct: parseFloat(l.scrap_pct || 0),
    std_unit_cost: l.std_unit_cost ?? '',
    notes: l.notes || '',
  })) : [{ item_id:'', qty_required:1, scrap_pct:0, std_unit_cost:'', notes:'' }];

  _bomOps = (bom?.operations || []).map(o => ({
    name: o.name,
    work_center_id: o.work_center_id,
    time_minutes: parseFloat(o.time_minutes || 0),
    setup_minutes: parseFloat(o.setup_minutes || 0),
    notes: o.notes || '',
  }));

  // Set title
  const titleEl = document.getElementById('bomFormTitle');
  if (titleEl) titleEl.textContent = id ? `Edit BOM — ${bom.bom_code}` : 'Buat BOM';

  // Render form body
  const stockItems = MfgState.items.filter(i => i.type === 'stock');
  const itemOpts = stockItems.map(i => `<option value="${i.id}">${_mfgEsc(i.name)} (${_mfgEsc(i.sku || '-')})</option>`).join('');
  const body = document.getElementById('bomFormBody');
  if (!body) return;
  body.innerHTML = `
    <div style="display:grid;grid-template-columns:2fr 1fr 1fr;gap:12px;margin-bottom:16px">
      <div><label>Output Item (yang dihasilkan)</label>
        <select id="bomOutputItem" class="form-control" ${id?'disabled':''}><option value="">— pilih —</option>${itemOpts}</select>
      </div>
      <div><label>Qty Output (per resep)</label>
        <input type="number" step="0.01" id="bomQtyOutput" value="${bom?.qty_output || 1}" class="form-control">
      </div>
      <div><label>BOM Code (opsional)</label>
        <input type="text" id="bomCode" placeholder="otomatis dari SKU" value="${_mfgEsc(bom?.bom_code || '')}" class="form-control" ${id?'readonly':''}>
      </div>
    </div>
    <h4>Komponen (Bahan Baku)</h4>
    <p style="font-size:12px;color:#6b7280;margin-bottom:8px">
      💡 Isi <strong>Std Unit Cost</strong> di SEMUA baris untuk mengaktifkan standard costing + variance journal. Kosongkan semua untuk mode actual cost (default).
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
    ${MfgState.workCenters.length ? `
      <h4 style="margin-top:24px;border-top:1px solid #e5e7eb;padding-top:16px">Operations / Routing (opsional)</h4>
      <p style="font-size:12px;color:#6b7280;margin-bottom:8px">
        💡 Tambahkan langkah produksi untuk track labor cost. Kosongkan untuk mode tanpa labor.
      </p>
      <table class="data-table">
        <thead><tr>
          <th style="width:30px">#</th>
          <th>Nama Operasi</th>
          <th>Work Center</th>
          <th style="width:120px">Time/unit (menit)</th>
          <th style="width:100px">Setup (menit)</th>
          <th></th>
        </tr></thead>
        <tbody id="bomOpsBody"></tbody>
      </table>
      <button class="btn btn-sm btn-outline" onclick="_bomOpsAdd()" style="margin-top:8px">+ Tambah operasi</button>
    ` : `
      <p style="font-size:12px;color:#9ca3af;margin-top:16px;border-top:1px dashed #e5e7eb;padding-top:12px">
        💡 Tambahkan <strong>Work Center</strong> dulu (sidebar Manufacturing → Work Center) untuk mengaktifkan routing operations & labor cost.
      </p>
    `}
    <div style="margin-top:16px"><label>Catatan</label><textarea id="bomNotes" class="form-control" rows="2">${_mfgEsc(bom?.notes || '')}</textarea></div>
  `;

  if (bom) {
    document.getElementById('bomOutputItem').value = bom.item_id;
  }

  _bomRenderLines();
  if (MfgState.workCenters.length) _bomOpsRender();
  if (typeof feather !== 'undefined') feather.replace();
}

async function submitBOMForm(activate) {
  const item_id    = document.getElementById('bomOutputItem').value;
  const qty_output = parseFloat(document.getElementById('bomQtyOutput').value) || 1;
  const bom_code   = document.getElementById('bomCode').value.trim();
  const notes      = document.getElementById('bomNotes').value;
  if (!item_id) { showToast('Output item wajib dipilih', 'error'); return; }
  const valid = _bomLines.filter(l => l.item_id && l.qty_required > 0);
  if (!valid.length) { showToast('Minimal 1 komponen valid', 'error'); return; }
  if (valid.some(l => l.item_id === item_id)) {
    showToast('Output item tidak boleh muncul sebagai komponen sendiri', 'error');
    return;
  }
  const withStd    = valid.filter(l => l.std_unit_cost !== null && l.std_unit_cost !== '' && !isNaN(parseFloat(l.std_unit_cost)));
  const withoutStd = valid.filter(l => !(l.std_unit_cost !== null && l.std_unit_cost !== '' && !isNaN(parseFloat(l.std_unit_cost))));
  if (withStd.length && withoutStd.length) {
    showToast('Standard cost harus diisi di SEMUA baris atau KOSONG semua.', 'error');
    return;
  }
  const validOps = (_bomOps || []).filter(o => o.name && o.work_center_id);
  if (validOps.length !== (_bomOps || []).length) {
    showToast('Setiap operasi butuh nama + work center', 'error');
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
    operations: validOps.map(o => ({
      name: o.name,
      work_center_id: o.work_center_id,
      time_minutes: parseFloat(o.time_minutes) || 0,
      setup_minutes: parseFloat(o.setup_minutes) || 0,
      notes: o.notes || null,
    })),
  };

  try {
    let res;
    if (_bomFormEditId) {
      res = await Api.boms.update(_bomFormEditId, payload);
      if (activate) await Api.boms.activate(_bomFormEditId);
      showToast(`BOM ${res.bom_code} ${activate?'di-activate':'diperbarui'}`, 'success');
    } else {
      res = await Api.boms.create(payload, activate ? {activate:'true'} : {});
      showToast(`BOM ${res.bom_code} ${activate?'di-activate':'tersimpan'}`, 'success');
    }
    _bomFormEditId = null;
    _bomLines = [];
    _bomOps = [];
    navigateTo('bom-master');
  } catch (e) { showToast('Gagal: ' + e.message, 'error'); }
}


// ── Manufacturing Order ─────────────────────────────────
function showMOForm() {
  _moFormPrefill = null;
  navigateTo('mo-form');
}

function exitMOForm() {
  if (!confirm('Yakin keluar tanpa simpan?')) return;
  navigateTo('mfg-orders');
}

async function renderMOForm() {
  await _mfgEnsureMasters();
  // Load active BOMs for the picker
  let activeBoms = [];
  try {
    activeBoms = await Api.boms.list({status: 'active', limit: 200});
  } catch (e) { activeBoms = []; }
  if (!activeBoms.length) {
    const body = document.getElementById('moFormBody');
    if (body) body.innerHTML = `
      <div style="padding:48px;text-align:center;color:#6b7280">
        <p>Belum ada BOM <strong>active</strong>. Buat & aktifkan BOM dulu di <a href="#" onclick="navigateTo('bom-master');return false">BOM Master</a>.</p>
      </div>`;
    return;
  }
  const itemMap = Object.fromEntries(MfgState.items.map(i => [i.id, i.name]));
  const bomOpts = activeBoms.map(b =>
    `<option value="${b.id}" data-item="${b.item_id}">${_mfgEsc(b.bom_code)} — ${_mfgEsc(itemMap[b.item_id] || '?')}</option>`).join('');
  const whOpts = MfgState.warehouses.map(w => `<option value="${w.id}">${_mfgEsc(w.name)}</option>`).join('');

  document.getElementById('moFormTitle').textContent = 'Buat Manufacturing Order';
  const body = document.getElementById('moFormBody');
  if (!body) return;
  body.innerHTML = `
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px">
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
    <h4>Komponen yang akan dibutuhkan (pratampil)</h4>
    <div id="moBomPreview" style="font-size:13px;color:#6b7280;padding:12px;border:1px solid #e5e7eb;border-radius:6px;background:#fafafa">Pilih BOM dulu</div>
    <div style="margin-top:16px"><label>Notes</label><textarea id="moNotes" class="form-control" rows="2"></textarea></div>
  `;
  window._activeBoms = activeBoms;
  if (typeof feather !== 'undefined') feather.replace();
}

async function submitMOForm(confirmNow) {
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
    navigateTo('mfg-orders');
  } catch (e) { showToast('Gagal: ' + e.message, 'error'); }
}

// ── Update BOM detail "Edit" handler to go to form page ───
//     Old `showBOMDetail` stays as read-only viewer; "Edit" button
//     inside detail (for draft) is wired via _bomFormEditId.


// ════════════════════════════════════════════════════════════════
// SCRAP / SPOILAGE (Sprint M6)
// ════════════════════════════════════════════════════════════════

let _scrapLines = [];

async function renderScrapPage() {
  await _mfgEnsureMasters();
  const status = document.getElementById('scrapFilterStatus')?.value || '';
  let list = [];
  try {
    list = await Api.mfgScraps.list({ status: status || undefined, limit: 200 });
  } catch (e) {
    showToast('Gagal load Scrap: ' + e.message, 'error');
  }
  const wrap = document.getElementById('scrapTableWrap');
  if (!wrap) return;
  if (!list.length) {
    wrap.innerHTML = `<div style="padding:48px;text-align:center;color:#6b7280">Belum ada Scrap. Klik <strong>"Buat Scrap"</strong>.</div>`;
    return;
  }
  const itemMap = Object.fromEntries(MfgState.items.map(i => [i.id, i.name]));
  const whMap   = Object.fromEntries(MfgState.warehouses.map(w => [w.id, w.name]));
  wrap.innerHTML = `
    <table class="data-table">
      <thead><tr>
        <th>No</th><th>Tanggal</th><th>Warehouse</th>
        <th style="text-align:right">Lines</th>
        <th>Reason</th><th>MO</th>
        <th>Status</th><th style="text-align:center">Aksi</th>
      </tr></thead>
      <tbody>
      ${list.map(s => `
        <tr>
          <td><code>${_mfgEsc(s.scrap_no)}</code></td>
          <td>${s.scrap_date || '-'}</td>
          <td>${_mfgEsc(whMap[s.warehouse_id] || '-')}</td>
          <td style="text-align:right">${(s.lines || []).length}</td>
          <td>${_mfgEsc(s.reason || '-')}</td>
          <td>${s.mo_id ? `<code>${_mfgEsc(s.mo_id.slice(0,8))}</code>` : '-'}</td>
          <td>${_ffStatusBadge ? _ffStatusBadge(s.status) : s.status}</td>
          <td style="text-align:center;white-space:nowrap">
            <button class="btn btn-sm btn-outline" onclick="showScrapDetail('${s.id}')">Detail</button>
            ${s.status === 'draft'  ? `<button class="btn btn-sm btn-primary" style="margin-left:4px" onclick="postScrap('${s.id}')">Post</button>` : ''}
            ${s.status !== 'void'   ? `<button class="btn btn-sm btn-danger"  style="margin-left:4px" onclick="voidScrap('${s.id}')">Void</button>` : ''}
          </td>
        </tr>`).join('')}
      </tbody>
    </table>`;
}

// shim for status badge (fulfillment.js exposes _ffStatusBadge; if unavailable use inline)
if (typeof _ffStatusBadge !== 'function') {
  window._ffStatusBadge = function(status) {
    const map = { draft:['#6b7280','Draft'], posted:['#10b981','Posted'], void:['#ef4444','Void'] };
    const [c,l] = map[status] || ['#6b7280',status||'-'];
    return `<span style="display:inline-block;padding:2px 8px;background:${c}20;color:${c};border-radius:6px;font-size:11px;font-weight:600">${l}</span>`;
  };
}

function showScrapForm() {
  _scrapLines = [{ item_id: '', qty: 1, unit_cost: '', notes: '' }];
  navigateTo('scrap-form');
}

function exitScrapForm() {
  if (_scrapLines.some(l => l.item_id) && !confirm('Perubahan belum disimpan. Yakin keluar?')) return;
  _scrapLines = [];
  navigateTo('mfg-scraps');
}

async function renderScrapForm() {
  await _mfgEnsureMasters();
  let mos = [];
  try { mos = await Api.manufacturingOrders.list({limit: 100}); } catch {}
  const itemOpts = MfgState.items.filter(i => i.type === 'stock')
    .map(i => `<option value="${i.id}">${_mfgEsc(i.name)} (${_mfgEsc(i.sku || '-')})</option>`).join('');
  const whOpts = MfgState.warehouses.map(w => `<option value="${w.id}">${_mfgEsc(w.name)}</option>`).join('');
  const moOpts = mos.map(m => `<option value="${m.id}">${_mfgEsc(m.mo_no)} — status ${m.status}</option>`).join('');

  document.getElementById('scrapFormTitle').textContent = 'Buat Scrap / Spoilage';
  const body = document.getElementById('scrapFormBody');
  if (!body) return;
  body.innerHTML = `
    <p style="font-size:12px;color:#6b7280;margin-bottom:12px">
      💡 Saat di-post: stock berkurang + journal otomatis <strong>Dr Beban Scrap / Cr Persediaan</strong>.
      Unit cost otomatis diambil dari avg cost inventory bila dikosongkan.
    </p>
    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:16px">
      <div><label>Tanggal</label><input type="date" id="scrapDate" value="${_mfgToday()}" class="form-control"></div>
      <div><label>Warehouse</label>
        <select id="scrapWarehouse" class="form-control">${whOpts}</select>
      </div>
      <div><label>MO terkait <small style="color:#6b7280">(opsional)</small></label>
        <select id="scrapMo" class="form-control"><option value="">— tidak terkait MO —</option>${moOpts}</select>
      </div>
    </div>
    <div style="margin-bottom:12px"><label>Reason</label>
      <input type="text" id="scrapReason" class="form-control" placeholder="cth: Rusak saat handling / QC reject">
    </div>
    <h4>Items yang di-scrap</h4>
    <table class="data-table">
      <thead><tr>
        <th style="width:36%">Item</th>
        <th style="width:90px">Qty</th>
        <th style="width:130px">Unit Cost <small>(opsional)</small></th>
        <th>Notes</th>
        <th></th>
      </tr></thead>
      <tbody id="scrapLinesBody"></tbody>
    </table>
    <button class="btn btn-sm btn-outline" onclick="_scrapAddLine()" style="margin-top:8px">+ Tambah baris</button>
    <div style="margin-top:16px"><label>Notes (header)</label><textarea id="scrapNotes" class="form-control" rows="2"></textarea></div>
  `;
  _scrapRenderLines(itemOpts);
  if (typeof feather !== 'undefined') feather.replace();
}

function _scrapRenderLines(itemOpts) {
  const opts = itemOpts || MfgState.items.filter(i => i.type === 'stock')
    .map(i => `<option value="${i.id}">${_mfgEsc(i.name)}</option>`).join('');
  const body = document.getElementById('scrapLinesBody');
  if (!body) return;
  body.innerHTML = _scrapLines.map((ln, idx) => `
    <tr>
      <td><select class="form-control" onchange="_scrapUpdLine(${idx},'item_id',this.value)"><option value="">— pilih —</option>${opts.replace(`value="${ln.item_id}"`, `value="${ln.item_id}" selected`)}</select></td>
      <td><input type="number" step="0.01" value="${ln.qty}" class="form-control" onchange="_scrapUpdLine(${idx},'qty',parseFloat(this.value)||0)"></td>
      <td><input type="number" step="100" value="${ln.unit_cost ?? ''}" placeholder="auto" class="form-control" onchange="_scrapUpdLine(${idx},'unit_cost',this.value === '' ? null : (parseFloat(this.value)||0))"></td>
      <td><input type="text" value="${_mfgEsc(ln.notes || '')}" class="form-control" onchange="_scrapUpdLine(${idx},'notes',this.value)"></td>
      <td><button class="btn btn-sm btn-danger" onclick="_scrapRmLine(${idx})">×</button></td>
    </tr>`).join('');
}

function _scrapUpdLine(i, k, v) { _scrapLines[i][k] = v; }
function _scrapAddLine() { _scrapLines.push({item_id:'', qty:1, unit_cost:'', notes:''}); _scrapRenderLines(); }
function _scrapRmLine(i)  { _scrapLines.splice(i,1); if (!_scrapLines.length) _scrapAddLine(); else _scrapRenderLines(); }

async function submitScrapForm(postNow) {
  const scrap_date   = document.getElementById('scrapDate').value;
  const warehouse_id = document.getElementById('scrapWarehouse').value;
  const mo_id        = document.getElementById('scrapMo').value || null;
  const reason       = document.getElementById('scrapReason').value;
  const notes        = document.getElementById('scrapNotes').value;
  if (!scrap_date || !warehouse_id) { showToast('Tanggal & warehouse wajib', 'error'); return; }
  const valid = _scrapLines.filter(l => l.item_id && l.qty > 0);
  if (!valid.length) { showToast('Minimal 1 baris valid', 'error'); return; }

  const payload = {
    scrap_date, warehouse_id, mo_id,
    reason: reason || null, notes: notes || null,
    lines: valid.map(l => ({
      item_id: l.item_id, qty: l.qty,
      unit_cost: (l.unit_cost === null || l.unit_cost === '' || isNaN(parseFloat(l.unit_cost))) ? null : parseFloat(l.unit_cost),
      notes: l.notes || null,
    })),
  };
  try {
    const res = await Api.mfgScraps.create(payload, postNow ? {post_now: 'true'} : {});
    showToast(`Scrap ${res.scrap_no} ${postNow?'di-post':'tersimpan'}`, 'success');
    _scrapLines = [];
    navigateTo('mfg-scraps');
  } catch (e) { showToast('Gagal: ' + e.message, 'error'); }
}

async function postScrap(id) {
  if (!confirm('Post scrap ini? Stock akan keluar + journal Dr Scrap-Loss / Cr Inventory.')) return;
  try {
    await Api.mfgScraps.post(id);
    showToast('Scrap di-post', 'success');
    renderScrapPage();
  } catch (e) { showToast('Gagal: ' + e.message, 'error'); }
}

async function voidScrap(id) {
  const reason = prompt('Alasan void?');
  if (!reason) return;
  try {
    await Api.mfgScraps.void(id, {reason});
    showToast('Scrap di-void', 'warning');
    renderScrapPage();
  } catch (e) { showToast('Gagal: ' + e.message, 'error'); }
}

async function showScrapDetail(id) {
  try {
    const s = await Api.mfgScraps.get(id);
    const itemMap = Object.fromEntries(MfgState.items.map(i => [i.id, i.name]));
    const rows = (s.lines || []).map((ln, idx) => `
      <tr>
        <td>${idx+1}</td>
        <td>${_mfgEsc(itemMap[ln.item_id] || ln.item_id?.slice(0,8))}</td>
        <td style="text-align:right">${ln.qty}</td>
        <td style="text-align:right">${_mfgFmtRp(ln.unit_cost)}</td>
        <td style="text-align:right">${_mfgFmtRp((parseFloat(ln.qty)||0) * (parseFloat(ln.unit_cost)||0))}</td>
        <td>${_mfgEsc(ln.notes || '-')}</td>
      </tr>`).join('');
    const total = (s.lines || []).reduce((acc,l) => acc + (parseFloat(l.qty)||0)*(parseFloat(l.unit_cost)||0), 0);
    const html = `
    <div class="modal-backdrop" id="scrapDetailBackdrop" onclick="if(event.target===this)this.remove()">
      <div class="modal-content" style="max-width:760px">
        <div class="modal-header">
          <h3>${_mfgEsc(s.scrap_no)} — ${_ffStatusBadge(s.status)}</h3>
          <button class="modal-close" onclick="document.getElementById('scrapDetailBackdrop').remove()">×</button>
        </div>
        <div class="modal-body">
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px">
            <div><strong>Date:</strong> ${s.scrap_date}</div>
            <div><strong>MO:</strong> ${s.mo_id ? `<code>${_mfgEsc(s.mo_id.slice(0,8))}</code>` : '-'}</div>
            <div><strong>Reason:</strong> ${_mfgEsc(s.reason || '-')}</div>
            <div><strong>Journal:</strong> ${s.journal_entry_id ? `<code>${_mfgEsc(s.journal_entry_id.slice(0,8))}</code>` : '-'}</div>
          </div>
          <table class="data-table">
            <thead><tr><th>#</th><th>Item</th><th>Qty</th><th>Unit Cost</th><th>Total</th><th>Notes</th></tr></thead>
            <tbody>${rows}</tbody>
            <tfoot><tr><th colspan="4" style="text-align:right">Total Loss</th><th colspan="2" style="text-align:right">${_mfgFmtRp(total)}</th></tr></tfoot>
          </table>
          ${s.void_reason ? `<p style="margin-top:12px;color:#ef4444"><strong>Void:</strong> ${_mfgEsc(s.void_reason)}</p>` : ''}
        </div>
      </div>
    </div>`;
    document.body.insertAdjacentHTML('beforeend', html);
  } catch (e) { showToast('Gagal: ' + e.message, 'error'); }
}


// ════════════════════════════════════════════════════════════════
// MO Cost Analysis Report
// ════════════════════════════════════════════════════════════════

let _moCostLastReport = null;

async function renderMOCostReport() {
  await _mfgEnsureMasters();
  // Default date range: last 90 days
  const fromEl = document.getElementById('moCostFrom');
  const toEl   = document.getElementById('moCostTo');
  if (fromEl && !fromEl.value) {
    const d = new Date(); d.setDate(d.getDate() - 90);
    fromEl.value = d.toISOString().slice(0,10);
  }
  if (toEl && !toEl.value) {
    toEl.value = new Date().toISOString().slice(0,10);
  }
  const params = {
    date_from: fromEl?.value || undefined,
    date_to:   toEl?.value   || undefined,
    status:    document.getElementById('moCostStatus')?.value || undefined,
    limit:     500,
  };
  let resp;
  try {
    resp = await Api.mfgReports.moCostAnalysis(params);
  } catch (e) {
    showToast('Gagal load report: ' + e.message, 'error');
    return;
  }
  _moCostLastReport = resp;

  const itemMap = Object.fromEntries(MfgState.items.map(i => [i.id, i.name]));
  const t = resp.totals || {};

  // KPI cards
  const kpiEl = document.getElementById('moCostKpi');
  if (kpiEl) {
    kpiEl.innerHTML = `
      <div class="kpi-card"><div class="kpi-label">MO terhitung</div><div class="kpi-value">${resp.count}</div></div>
      <div class="kpi-card"><div class="kpi-label">Total Material (Actual)</div><div class="kpi-value" style="color:#3b82f6">${_mfgFmtRp(t.material_actual)}</div></div>
      <div class="kpi-card"><div class="kpi-label">Total Labor</div><div class="kpi-value" style="color:#06b6d4">${_mfgFmtRp(t.labor)}</div></div>
      <div class="kpi-card"><div class="kpi-label">Total Scrap Loss</div><div class="kpi-value" style="color:#ef4444">${_mfgFmtRp(t.scrap_total)}</div></div>
      <div class="kpi-card"><div class="kpi-label">Variance</div><div class="kpi-value" style="color:${(t.variance||0) > 0 ? '#ef4444' : '#10b981'}">${(t.variance||0) >= 0 ? '+' : ''}${_mfgFmtRp(t.variance)}</div></div>
      <div class="kpi-card"><div class="kpi-label">Total HPP Produksi</div><div class="kpi-value" style="color:#10b981">${_mfgFmtRp(t.total_cost)}</div></div>
    `;
  }

  const wrap = document.getElementById('moCostTableWrap');
  if (!wrap) return;
  if (!resp.rows.length) {
    wrap.innerHTML = `<div style="padding:48px;text-align:center;color:#6b7280">Tidak ada MO dalam rentang tanggal/filter ini.</div>`;
    return;
  }
  wrap.innerHTML = `
    <table class="data-table">
      <thead><tr>
        <th>No MO</th><th>Output Item</th>
        <th style="text-align:right">Qty Plan</th>
        <th style="text-align:right">Qty Produced</th>
        <th>Mode</th>
        <th style="text-align:right">Material Actual</th>
        <th style="text-align:right">Material Std</th>
        <th style="text-align:right">Variance</th>
        <th style="text-align:right">Var %</th>
        <th style="text-align:right">Labor</th>
        <th style="text-align:right">Scrap Loss</th>
        <th style="text-align:right">Total HPP</th>
        <th style="text-align:right">Unit Cost</th>
        <th>Done At</th>
      </tr></thead>
      <tbody>
      ${resp.rows.map(r => {
        const varColor = r.variance == null ? '#6b7280' : (r.variance > 0 ? '#ef4444' : r.variance < 0 ? '#10b981' : '#6b7280');
        return `<tr>
          <td><code style="cursor:pointer" onclick="showMODetail('${r.mo_id}')">${_mfgEsc(r.mo_no)}</code></td>
          <td>${_mfgEsc(itemMap[r.item_id] || r.item_id?.slice(0,8))}</td>
          <td style="text-align:right">${r.qty_planned}</td>
          <td style="text-align:right">${r.qty_produced}</td>
          <td>${r.costing_mode === 'standard' ? '<span style="color:#06b6d4;font-size:11px">📊 std</span>' : '<span style="color:#6b7280;font-size:11px">actual</span>'}</td>
          <td style="text-align:right">${_mfgFmtRp(r.material_actual)}</td>
          <td style="text-align:right">${r.material_std != null ? _mfgFmtRp(r.material_std) : '—'}</td>
          <td style="text-align:right;color:${varColor}">${r.variance != null ? (r.variance >= 0 ? '+' : '') + _mfgFmtRp(r.variance) : '—'}</td>
          <td style="text-align:right;color:${varColor}">${r.variance_pct != null ? r.variance_pct.toFixed(2) + '%' : '—'}</td>
          <td style="text-align:right">${_mfgFmtRp(r.labor)}</td>
          <td style="text-align:right;color:${r.scrap_total > 0 ? '#ef4444' : '#9ca3af'}">${_mfgFmtRp(r.scrap_total)}</td>
          <td style="text-align:right;font-weight:600">${_mfgFmtRp(r.total_cost)}</td>
          <td style="text-align:right">${r.unit_cost != null ? _mfgFmtRp(r.unit_cost) : '—'}</td>
          <td>${r.done_at ? r.done_at.slice(0,10) : '-'}</td>
        </tr>`;
      }).join('')}
      </tbody>
      <tfoot>
        <tr style="background:#f8fafc;font-weight:600">
          <th colspan="5" style="text-align:right">TOTAL</th>
          <th style="text-align:right">${_mfgFmtRp(t.material_actual)}</th>
          <th style="text-align:right">${_mfgFmtRp(t.material_std)}</th>
          <th style="text-align:right">${(t.variance || 0) >= 0 ? '+' : ''}${_mfgFmtRp(t.variance)}</th>
          <th></th>
          <th style="text-align:right">${_mfgFmtRp(t.labor)}</th>
          <th style="text-align:right">${_mfgFmtRp(t.scrap_total)}</th>
          <th style="text-align:right">${_mfgFmtRp(t.total_cost)}</th>
          <th colspan="2"></th>
        </tr>
      </tfoot>
    </table>`;
  if (typeof feather !== 'undefined') feather.replace();
}

function exportMOCostReportCSV() {
  if (!_moCostLastReport || !_moCostLastReport.rows.length) {
    showToast('Tidak ada data untuk di-export', 'error');
    return;
  }
  const itemMap = Object.fromEntries(MfgState.items.map(i => [i.id, i.name]));
  const headers = ['MO No','Output Item','Qty Plan','Qty Produced','Mode','Material Actual','Material Std','Variance','Var %','Labor','Scrap Loss','Total HPP','Unit Cost','Done At'];
  const rows = _moCostLastReport.rows.map(r => [
    r.mo_no, itemMap[r.item_id] || r.item_id?.slice(0,8),
    r.qty_planned, r.qty_produced, r.costing_mode,
    r.material_actual, r.material_std ?? '', r.variance ?? '', r.variance_pct ?? '',
    r.labor, r.scrap_total, r.total_cost, r.unit_cost ?? '',
    r.done_at?.slice(0,10) || '',
  ]);
  const csv = [headers, ...rows].map(r => r.map(c => {
    const s = String(c ?? '');
    return s.includes(',') || s.includes('"') ? `"${s.replace(/"/g,'""')}"` : s;
  }).join(',')).join('\n');
  const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = `mo-cost-analysis-${new Date().toISOString().slice(0,10)}.csv`;
  document.body.appendChild(a); a.click(); a.remove();
  URL.revokeObjectURL(url);
}

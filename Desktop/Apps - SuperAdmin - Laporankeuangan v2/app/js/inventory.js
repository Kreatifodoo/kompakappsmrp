/**
 * INVENTORY.JS — Inventory Management
 * Items, Warehouses, Stock Movements, Stock Transfers via backend API
 */

// ─── State ────────────────────────────────────────────────────
const InventoryState = {
  items: [],
  warehouses: [],
  movements: [],
  activeTab: 'items', // items | warehouses | movements | transfers
};

// ─── Formatters ───────────────────────────────────────────────
function _fmtInv(n) {
  return (n || 0).toLocaleString('id-ID');
}
function _escInv(s) {
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ─── Load data ────────────────────────────────────────────────
async function loadInventoryData() {
  try {
    const [items, warehouses] = await Promise.all([
      Api.items.list(),
      Api.warehouses.list(),
    ]);
    InventoryState.items = items.items || items || [];
    InventoryState.warehouses = warehouses.warehouses || warehouses || [];
  } catch (e) {
    showToast('Gagal memuat data inventory: ' + e.message, 'error');
  }
}

// ─── Render: Items table ───────────────────────────────────────
function renderItemsTable() {
  const wrap = document.getElementById('invItemsWrap');
  if (!wrap) return;
  const items = InventoryState.items;
  if (!items.length) {
    wrap.innerHTML = `<div class="empty-state"><p>Belum ada item. <button class="btn btn-primary btn-sm" onclick="showItemModal(null)">Tambah Item</button></p></div>`;
    return;
  }
  wrap.innerHTML = `
    <table class="data-table">
      <thead><tr>
        <th>SKU</th><th>Nama</th><th>Tipe</th><th>Satuan</th><th>Harga Jual</th><th>Harga Beli</th><th>Aksi</th>
      </tr></thead>
      <tbody>
        ${items.map(it => `<tr>
          <td>${_escInv(it.sku)}</td>
          <td>${_escInv(it.name)}</td>
          <td><span class="badge">${_escInv(it.type || 'stock')}</span></td>
          <td>${_escInv(it.unit || '-')}</td>
          <td class="text-right">${_fmtInv(it.default_unit_price)}</td>
          <td class="text-right">${_fmtInv(it.default_unit_cost)}</td>
          <td><button class="btn btn-sm btn-outline" onclick="showItemModal('${it.id}')">Edit</button></td>
        </tr>`).join('')}
      </tbody>
    </table>`;
}

// ─── Render: Warehouses table ──────────────────────────────────
function renderWarehousesTable() {
  const wrap = document.getElementById('invWarehouseWrap');
  if (!wrap) return;
  const whs = InventoryState.warehouses;
  if (!whs.length) {
    wrap.innerHTML = `<div class="empty-state"><p>Belum ada gudang. <button class="btn btn-primary btn-sm" onclick="showWarehouseModal(null)">Tambah Gudang</button></p></div>`;
    return;
  }
  wrap.innerHTML = `
    <table class="data-table">
      <thead><tr><th>Kode</th><th>Nama</th><th>Default</th><th>Status</th><th>Aksi</th></tr></thead>
      <tbody>
        ${whs.map(w => `<tr>
          <td>${_escInv(w.code)}</td>
          <td>${_escInv(w.name)}</td>
          <td>${w.is_default ? '<span class="badge badge-success">✓ Default</span>' : '-'}</td>
          <td>${w.is_active ? '<span class="badge">Aktif</span>' : '<span class="badge badge-danger">Nonaktif</span>'}</td>
          <td><button class="btn btn-sm btn-outline" onclick="showWarehouseModal('${w.id}')">Edit</button></td>
        </tr>`).join('')}
      </tbody>
    </table>`;
}

// ─── Render: Main page ────────────────────────────────────────
async function renderInventoryPage() {
  if (!document.getElementById('page-inventory')) return;

  document.querySelectorAll('#page-inventory .inv-tab-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.tab === InventoryState.activeTab);
  });
  document.querySelectorAll('#page-inventory .inv-tab-panel').forEach(p => {
    p.style.display = p.dataset.tab === InventoryState.activeTab ? '' : 'none';
  });

  await loadInventoryData();

  if (InventoryState.activeTab === 'items')      renderItemsTable();
  if (InventoryState.activeTab === 'warehouses') renderWarehousesTable();
  if (InventoryState.activeTab === 'movements')  await renderMovementsTable();

  if (typeof feather !== 'undefined') feather.replace();
}

// ─── Render: Movements table ──────────────────────────────────
async function renderMovementsTable() {
  const wrap = document.getElementById('invMovementsWrap');
  if (!wrap) return;
  try {
    const moves = await Api.stockMovements.list({ limit: 100 });
    // Resolve item + warehouse display names from already-loaded InventoryState
    const itemMap = Object.fromEntries((InventoryState.items || []).map(i => [i.id, `${i.sku} — ${i.name}`]));
    const whMap   = Object.fromEntries((InventoryState.warehouses || []).map(w => [w.id, `${w.code} — ${w.name}`]));

    const headerHtml = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
        <p class="page-subtitle" style="margin:0">Pergerakan stok terbaru. Yang dari invoice/transfer otomatis muncul; klik tombol untuk movement manual (opening, adjustment).</p>
        <button class="btn btn-primary btn-sm" onclick="showMovementModal()">+ Movement Manual</button>
      </div>`;

    if (!moves.length) {
      wrap.innerHTML = headerHtml + `<div class="empty-state"><p>Belum ada pergerakan stok.</p></div>`;
      return;
    }

    wrap.innerHTML = headerHtml + `
      <table class="data-table">
        <thead><tr>
          <th>Tanggal</th><th>Item</th><th>Gudang</th><th>Direction</th>
          <th class="text-right">Qty</th><th class="text-right">Unit Cost</th>
          <th class="text-right">Qty After</th><th class="text-right">Avg After</th>
          <th>Source</th><th>Notes</th>
        </tr></thead>
        <tbody>
          ${moves.map(m => `<tr>
            <td>${m.movement_date || (m.created_at||'').slice(0,10) || '-'}</td>
            <td>${_escInv(itemMap[m.item_id] || m.item_id)}</td>
            <td>${_escInv(whMap[m.warehouse_id] || m.warehouse_id)}</td>
            <td><span class="badge badge-${(m.direction||'').includes('in') ? 'success' : 'danger'}">${_escInv(m.direction)}</span></td>
            <td class="text-right">${_fmtInv(m.qty)}</td>
            <td class="text-right">${_fmtInv(m.unit_cost)}</td>
            <td class="text-right">${_fmtInv(m.qty_after)}</td>
            <td class="text-right">${_fmtInv(m.avg_cost_after)}</td>
            <td><span class="badge">${_escInv(m.source||'-')}</span></td>
            <td>${_escInv(m.notes || '')}</td>
          </tr>`).join('')}
        </tbody>
      </table>`;
  } catch (e) {
    wrap.innerHTML = `<div class="empty-state error">Gagal memuat: ${e.message}</div>`;
  }
}

// ─── Modal: Stock Movement Manual ─────────────────────────────
async function showMovementModal() {
  // Ensure masters loaded
  if (!InventoryState.items?.length || !InventoryState.warehouses?.length) {
    try {
      const [items, whs] = await Promise.all([Api.items.list({active_only: true}), Api.warehouses.list()]);
      InventoryState.items = items;
      InventoryState.warehouses = whs;
    } catch (e) { showToast('Gagal load master: '+e.message, 'error'); return; }
  }

  const today = new Date().toISOString().slice(0, 10);
  const itemOpts = InventoryState.items
    .filter(i => i.type === 'stock')
    .map(i => `<option value="${i.id}">${_escInv(i.sku)} — ${_escInv(i.name)}</option>`).join('');
  const whOpts = InventoryState.warehouses
    .map(w => `<option value="${w.id}">${_escInv(w.code)} — ${_escInv(w.name)}</option>`).join('');

  document.getElementById('movFormTitle').textContent = 'Pergerakan Stok Manual';
  document.getElementById('movFormSaveBtn').textContent = 'Simpan & Post';
  const body = document.getElementById('movFormBody');
  if (!body) { showToast('Form movement tidak tersedia', 'error'); return; }
  body.innerHTML = `
    <div class="form-group"><label>Item *</label>
      <select class="form-control" id="mvItem"><option value="">— Pilih item (stock-type) —</option>${itemOpts}</select></div>
    <div class="form-group"><label>Gudang *</label>
      <select class="form-control" id="mvWh"><option value="">— Pilih gudang —</option>${whOpts}</select></div>
    <div class="form-row">
      <div class="form-group"><label>Tanggal *</label>
        <input class="form-control" type="date" id="mvDate" value="${today}"></div>
      <div class="form-group"><label>Direction *</label>
        <select class="form-control" id="mvDir">
          <option value="in">In (terima barang / opening)</option>
          <option value="out">Out (keluar non-invoice)</option>
          <option value="adjust_in">Adjust In (cycle count surplus)</option>
          <option value="adjust_out">Adjust Out (cycle count loss)</option>
        </select></div>
    </div>
    <div class="form-row">
      <div class="form-group"><label>Qty *</label>
        <input class="form-control" type="number" min="0.001" step="0.001" id="mvQty" value="1"></div>
      <div class="form-group"><label>Unit Cost</label>
        <input class="form-control" type="number" min="0" step="0.01" id="mvCost" value="0">
        <small style="color:#6b7280">Hanya dipakai untuk in/adjust_in. Out pakai avg_cost otomatis.</small>
      </div>
    </div>
    <div class="form-group"><label>Catatan</label>
      <input class="form-control" id="mvNotes" placeholder="opsional"></div>
    <div id="mvErr" class="form-error" style="display:none"></div>
  `;
  navigateTo('movement-form');
  if (typeof feather !== 'undefined') feather.replace();
}

function saveMovementFromForm() { return saveMovement(); }
function closeMovementModal() {
  if (typeof navigateTo === 'function') navigateTo('inventory-movements');
}

async function saveMovement() {
  const errEl = document.getElementById('mvErr');
  errEl.style.display = 'none';
  const itemId = document.getElementById('mvItem').value;
  const whId   = document.getElementById('mvWh').value;
  const date   = document.getElementById('mvDate').value;
  const dir    = document.getElementById('mvDir').value;
  const qty    = parseFloat(document.getElementById('mvQty').value);
  const cost   = parseFloat(document.getElementById('mvCost').value) || 0;
  const notes  = document.getElementById('mvNotes').value.trim();

  if (!itemId || !whId || !date || !qty || qty <= 0) {
    errEl.textContent = 'Item, Gudang, Tanggal, dan Qty > 0 wajib diisi'; errEl.style.display='block'; return;
  }
  try {
    await Api.stockMovements.create({
      item_id: itemId,
      warehouse_id: whId,
      movement_date: date,
      direction: dir,
      qty,
      unit_cost: cost,
      notes: notes || null,
    });
    showToast('Movement berhasil di-post', 'success');
    closeMovementModal();
    await renderMovementsTable();
  } catch (e) {
    errEl.textContent = e.message; errEl.style.display = 'block';
  }
}

// ─── Modal: Item ──────────────────────────────────────────────
async function showItemModal(id) {
  let item = null;
  if (id) {
    try { item = await Api.items.get(id); } catch { showToast('Gagal memuat item', 'error'); return; }
  }
  window._itemFormEditId = id || '';
  document.getElementById('itemFormTitle').textContent = item ? 'Edit Item' : 'Tambah Item';
  const body = document.getElementById('itemFormBody');
  if (!body) { showToast('Form item tidak tersedia', 'error'); return; }
  body.innerHTML = `
    <div class="form-group"><label>SKU *</label>
      <input class="form-control" id="iCode" value="${_escInv(item?.sku)}" placeholder="ITM-001" ${id?'disabled':''}></div>
    <div class="form-group"><label>Nama *</label>
      <input class="form-control" id="iName" value="${_escInv(item?.name)}" placeholder="Nama item"></div>
    <div class="form-group"><label>Satuan</label>
      <input class="form-control" id="iUnit" value="${_escInv(item?.unit||'pcs')}" placeholder="pcs / kg / box"></div>
    <div class="form-group"><label>Tipe</label>
      <select class="form-control" id="iType" ${id?'disabled':''}>
        <option value="stock"   ${item?.type==='stock'  ?'selected':''}>Stok (kelola persediaan)</option>
        <option value="service" ${item?.type==='service'?'selected':''}>Jasa / Service</option>
      </select></div>
    <div class="form-row">
      <div class="form-group"><label>Harga Beli (default)</label>
        <input class="form-control" id="iPurchasePrice" type="number" min="0" step="0.01" value="${item?.default_unit_cost||0}"></div>
      <div class="form-group"><label>Harga Jual (default)</label>
        <input class="form-control" id="iSalePrice" type="number" min="0" step="0.01" value="${item?.default_unit_price||0}"></div>
    </div>
    <hr style="margin:16px 0;border:0;border-top:1px solid #e5e7eb">
    <div class="form-row">
      <div class="form-group" style="flex:1">
        <label style="display:flex;align-items:center;gap:8px">
          <input type="checkbox" id="iLotTracked" ${item?.is_lot_tracked?'checked':''}>
          <span>Lot / Batch tracked</span>
        </label>
        <small style="color:#6b7280;font-size:11px">Setiap penerimaan otomatis buat lot; outflow pakai FEFO.</small>
      </div>
      <div class="form-group" style="flex:1">
        <label>Shelf Life (hari) <small style="color:#6b7280">— opsional</small></label>
        <input class="form-control" id="iShelfLife" type="number" min="0" step="1" value="${item?.shelf_life_days ?? ''}" placeholder="cth: 7">
      </div>
    </div>
    <div id="iErr" class="form-error" style="display:none"></div>
  `;
  navigateTo('item-form');
  if (typeof feather !== 'undefined') feather.replace();
}

function saveItemFromForm() { return saveItem(window._itemFormEditId || ''); }

function closeItemModal() {
  window._itemFormEditId = null;
  if (typeof navigateTo === 'function') navigateTo('inventory');
}

async function saveItem(id) {
  const sku   = document.getElementById('iCode').value.trim();
  const name  = document.getElementById('iName').value.trim();
  const errEl = document.getElementById('iErr');
  if (!sku || !name) { errEl.textContent='SKU dan Nama wajib diisi'; errEl.style.display='block'; return; }

  const unit  = document.getElementById('iUnit').value.trim() || 'pcs';
  const cost  = parseFloat(document.getElementById('iPurchasePrice').value) || 0;
  const price = parseFloat(document.getElementById('iSalePrice').value) || 0;
  const isLot = document.getElementById('iLotTracked').checked;
  const shelfRaw = document.getElementById('iShelfLife').value;
  const shelf = shelfRaw === '' ? null : (parseInt(shelfRaw, 10) || null);

  try {
    if (id) {
      await Api.items.update(id, {
        name, unit,
        default_unit_price: price,
        default_unit_cost:  cost,
        is_lot_tracked:     isLot,
        shelf_life_days:    shelf,
      });
    } else {
      const type = document.getElementById('iType').value || 'stock';
      await Api.items.create({
        sku, name, type, unit,
        default_unit_price: price,
        default_unit_cost:  cost,
        is_lot_tracked:     isLot,
        shelf_life_days:    shelf,
      });
    }
    showToast('Item berhasil disimpan', 'success');
    closeItemModal();
    await renderInventoryPage();
  } catch (e) {
    errEl.textContent = e.message; errEl.style.display = 'block';
  }
}

// ─── Warehouse form page (Sprint F6) ─────────────────────
async function showWarehouseModal(id) {
  let wh = null;
  if (id) {
    try { wh = await Api.warehouses.get(id); } catch { showToast('Gagal memuat gudang', 'error'); return; }
  }
  window._whFormEditId = id || '';
  document.getElementById('whFormTitle').textContent = wh ? 'Edit Gudang' : 'Tambah Gudang';
  const body = document.getElementById('whFormBody');
  if (!body) { showToast('Form gudang tidak tersedia', 'error'); return; }
  body.innerHTML = `
    <div class="form-group"><label>Kode *</label>
      <input class="form-control" id="whCode" value="${_escInv(wh?.code)}" placeholder="WH-01" ${id?'disabled':''}></div>
    <div class="form-group"><label>Nama *</label>
      <input class="form-control" id="whName" value="${_escInv(wh?.name)}" placeholder="Gudang Utama"></div>
    <div class="form-group">
      <label><input type="checkbox" id="whDefault" ${wh?.is_default?'checked':''}> Set sebagai gudang default</label>
    </div>
    <div id="whErr" class="form-error" style="display:none"></div>
  `;
  navigateTo('warehouse-form');
  if (typeof feather !== 'undefined') feather.replace();
}

function saveWarehouseFromForm() { return saveWarehouse(window._whFormEditId || ''); }

function closeWhModal() {
  window._whFormEditId = null;
  if (typeof navigateTo === 'function') navigateTo('inventory');
}

async function saveWarehouse(id) {
  const code   = document.getElementById('whCode').value.trim();
  const name   = document.getElementById('whName').value.trim();
  const isDflt = document.getElementById('whDefault')?.checked || false;
  const errEl  = document.getElementById('whErr');
  if (!code || !name) { errEl.textContent='Kode dan Nama wajib diisi'; errEl.style.display='block'; return; }

  try {
    if (id) {
      // Update: name + is_default only (code immutable)
      await Api.warehouses.update(id, { name, is_default: isDflt });
    } else {
      await Api.warehouses.create({ code, name, is_default: isDflt });
    }
    showToast('Gudang berhasil disimpan', 'success');
    closeWhModal();
    await renderInventoryPage();
  } catch (e) {
    errEl.textContent = e.message; errEl.style.display = 'block';
  }
}

// ─── Tab switch ───────────────────────────────────────────────
function switchInventoryTab(tab) {
  InventoryState.activeTab = tab;
  renderInventoryPage();
}


// ════════════════════════════════════════════════════════════════
// Master Gudang (Sprint F7) — separate page with locations
// ════════════════════════════════════════════════════════════════

async function renderWarehouseMaster() {
  const wrap = document.getElementById('page-warehouse-master');
  if (!wrap) return;
  let warehouses = [];
  try {
    warehouses = await Api.warehouses.list();
  } catch (e) {
    showToast('Gagal load gudang: ' + e.message, 'error');
    warehouses = [];
  }

  // Fetch location count for each warehouse (parallel)
  const locCounts = await Promise.all(
    warehouses.map(w => Api.warehouses.locations.list(w.id).then(l => l.length).catch(() => 0))
  );

  wrap.innerHTML = `
    <div class="page-header">
      <h2>Master Gudang <small style="font-size:11px;color:#15803d;font-weight:normal">⚡ live dari backend</small></h2>
      <div class="page-actions">
        <button class="btn btn-outline" onclick="renderWarehouseMaster()"><i data-feather="refresh-cw"></i> Refresh</button>
        <button class="btn btn-outline" onclick="openImportWizard(IMPORT_CONFIGS.warehouse)"><i data-feather="upload"></i> Import</button>
        <button class="btn btn-primary" onclick="showWarehouseModal(null)"><i data-feather="plus"></i> Tambah Gudang</button>
      </div>
    </div>
    ${warehouses.length === 0 ? `
      <div class="table-card" style="padding:48px;text-align:center;color:#6b7280">
        Belum ada gudang. Klik <strong>"Tambah Gudang"</strong>.
      </div>
    ` : `
      <div class="table-card">
        <table class="data-table">
          <thead><tr>
            <th>Kode</th><th>Nama</th>
            <th style="text-align:center">Default</th>
            <th style="text-align:center">Status</th>
            <th style="text-align:right">Locations</th>
            <th style="text-align:center">Aksi</th>
          </tr></thead>
          <tbody>
            ${warehouses.map((w, i) => `
              <tr>
                <td><code>${_escInv(w.code)}</code></td>
                <td>${_escInv(w.name)}</td>
                <td style="text-align:center">${w.is_default ? '<span style="color:#10b981">✓ Default</span>' : '—'}</td>
                <td style="text-align:center">${w.is_active ? '<span style="color:#10b981">Aktif</span>' : '<span style="color:#ef4444">Nonaktif</span>'}</td>
                <td style="text-align:right">${locCounts[i]}</td>
                <td style="text-align:center;white-space:nowrap">
                  <button class="btn btn-sm btn-outline" onclick="showWarehouseModal('${w.id}')">Edit</button>
                  <button class="btn btn-sm btn-info" style="margin-left:4px" onclick="showLocationsModal('${w.id}','${_escInv(w.name)}')">📍 Locations</button>
                </td>
              </tr>`).join('')}
          </tbody>
        </table>
      </div>
    `}
  `;
  if (typeof feather !== 'undefined') feather.replace();
}

// ─── Locations management modal (within a warehouse) ────
let _locWhId = null;
let _locList = [];

async function showLocationsModal(warehouseId, warehouseName) {
  _locWhId = warehouseId;
  try {
    _locList = await Api.warehouses.locations.list(warehouseId);
  } catch (e) {
    showToast('Gagal load locations: ' + e.message, 'error');
    _locList = [];
  }
  const html = `
    <div class="modal-backdrop" id="locModalBackdrop" onclick="if(event.target===this)closeLocationsModal()">
      <div class="modal-content" style="max-width:720px">
        <div class="modal-header">
          <h3>Locations / Rak — ${_escInv(warehouseName)}</h3>
          <button class="modal-close" onclick="closeLocationsModal()">×</button>
        </div>
        <div class="modal-body">
          <p style="font-size:12px;color:#6b7280;margin-bottom:12px">
            💡 Lokasi (rak / bin / zone) di dalam gudang ini. Stock balance tetap di level gudang;
            lokasi sebagai referensi organisasi.
          </p>
          <table class="data-table" id="locTable">
            <thead><tr>
              <th style="width:120px">Code</th>
              <th>Name</th>
              <th>Notes</th>
              <th style="text-align:center;width:80px">Aktif</th>
              <th style="width:80px"></th>
            </tr></thead>
            <tbody id="locTableBody"></tbody>
          </table>
          <button class="btn btn-sm btn-outline" onclick="addLocationLine()" style="margin-top:8px">+ Tambah Lokasi</button>
          <div id="locErr" class="form-error" style="display:none;margin-top:8px"></div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-outline" onclick="closeLocationsModal()">Tutup</button>
          <button class="btn btn-primary" onclick="saveAllLocations()">Simpan Semua</button>
        </div>
      </div>
    </div>`;
  document.body.insertAdjacentHTML('beforeend', html);
  _renderLocTable();
  if (typeof feather !== 'undefined') feather.replace();
}

function _renderLocTable() {
  const body = document.getElementById('locTableBody');
  if (!body) return;
  if (!_locList.length) {
    body.innerHTML = `<tr><td colspan="5" style="text-align:center;color:#9ca3af;padding:24px">— belum ada lokasi —</td></tr>`;
    return;
  }
  body.innerHTML = _locList.map((l, idx) => `
    <tr data-idx="${idx}">
      <td><input class="form-control" value="${_escInv(l.code || '')}" data-field="code" placeholder="RAK-A1" onchange="_locUpdField(${idx},'code',this.value)"></td>
      <td><input class="form-control" value="${_escInv(l.name || '')}" data-field="name" placeholder="Rak A baris 1" onchange="_locUpdField(${idx},'name',this.value)"></td>
      <td><input class="form-control" value="${_escInv(l.notes || '')}" data-field="notes" placeholder="opsional" onchange="_locUpdField(${idx},'notes',this.value)"></td>
      <td style="text-align:center"><input type="checkbox" ${l.is_active !== false ? 'checked' : ''} onchange="_locUpdField(${idx},'is_active',this.checked)"></td>
      <td style="text-align:center">
        ${l.id ? `<button class="btn btn-sm btn-danger" onclick="_locRemoveSaved(${idx})">Hapus</button>` : `<button class="btn btn-sm btn-outline" onclick="_locRemoveNew(${idx})">×</button>`}
      </td>
    </tr>`).join('');
}

function _locUpdField(idx, field, value) {
  if (!_locList[idx]) return;
  _locList[idx][field] = value;
  _locList[idx]._dirty = true;
}

function addLocationLine() {
  _locList.push({ code: '', name: '', notes: '', is_active: true, _new: true });
  _renderLocTable();
}

function _locRemoveNew(idx) {
  _locList.splice(idx, 1);
  _renderLocTable();
}

async function _locRemoveSaved(idx) {
  const loc = _locList[idx];
  if (!loc?.id) return _locRemoveNew(idx);
  if (!confirm(`Hapus lokasi ${loc.code}?`)) return;
  try {
    await Api.warehouses.locations.delete(_locWhId, loc.id);
    _locList.splice(idx, 1);
    _renderLocTable();
    showToast('Lokasi dihapus', 'warning');
  } catch (e) { showToast('Gagal hapus: ' + e.message, 'error'); }
}

async function saveAllLocations() {
  const errEl = document.getElementById('locErr');
  errEl.style.display = 'none';
  for (const loc of _locList) {
    if (!loc.code || !loc.name) {
      errEl.textContent = 'Setiap baris butuh Code & Name'; errEl.style.display='block';
      return;
    }
  }
  // Process: new → POST, dirty existing → PATCH
  let created = 0, updated = 0;
  try {
    for (let i = 0; i < _locList.length; i++) {
      const l = _locList[i];
      if (l._new) {
        const res = await Api.warehouses.locations.create(_locWhId, {
          code: l.code, name: l.name, notes: l.notes || null, is_active: l.is_active !== false,
        });
        _locList[i] = res;
        created++;
      } else if (l._dirty && l.id) {
        await Api.warehouses.locations.update(_locWhId, l.id, {
          code: l.code, name: l.name, notes: l.notes || null, is_active: l.is_active !== false,
        });
        delete l._dirty;
        updated++;
      }
    }
    showToast(`Locations saved: ${created} baru, ${updated} update`, 'success');
    closeLocationsModal();
    renderWarehouseMaster();
  } catch (e) {
    errEl.textContent = e.message; errEl.style.display='block';
  }
}

function closeLocationsModal() {
  document.getElementById('locModalBackdrop')?.remove();
  _locWhId = null;
  _locList = [];
}

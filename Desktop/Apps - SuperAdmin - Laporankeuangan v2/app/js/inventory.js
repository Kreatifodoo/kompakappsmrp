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
    const data = await Api.stockMovements.list({ limit: 50 });
    const moves = data.items || data || [];
    if (!moves.length) { wrap.innerHTML = '<div class="empty-state"><p>Belum ada pergerakan stok.</p></div>'; return; }
    wrap.innerHTML = `
      <table class="data-table">
        <thead><tr><th>Tanggal</th><th>Item</th><th>Gudang</th><th>Tipe</th><th class="text-right">Qty</th><th class="text-right">Biaya/Unit</th></tr></thead>
        <tbody>
          ${moves.map(m => `<tr>
            <td>${m.movement_date || m.created_at?.slice(0,10) || '-'}</td>
            <td>${_escInv(m.item_name || m.item_id)}</td>
            <td>${_escInv(m.warehouse_name || m.warehouse_id)}</td>
            <td><span class="badge badge-${m.movement_type === 'in' ? 'success' : 'danger'}">${_escInv(m.movement_type)}</span></td>
            <td class="text-right">${_fmtInv(m.qty)}</td>
            <td class="text-right">${_fmtInv(m.unit_cost)}</td>
          </tr>`).join('')}
        </tbody>
      </table>`;
  } catch (e) {
    wrap.innerHTML = `<div class="empty-state error">Gagal memuat: ${e.message}</div>`;
  }
}

// ─── Modal: Item ──────────────────────────────────────────────
async function showItemModal(id) {
  let item = null;
  if (id) {
    try { item = await Api.items.get(id); } catch { showToast('Gagal memuat item', 'error'); return; }
  }

  const html = `
    <div class="modal-backdrop" id="invItemModal" onclick="if(event.target===this)closeItemModal()">
      <div class="modal-dialog" style="max-width:480px">
        <div class="modal-header">
          <h3>${item ? 'Edit Item' : 'Tambah Item'}</h3>
          <button class="modal-close" onclick="closeItemModal()">×</button>
        </div>
        <div class="modal-body">
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
          <div id="iErr" class="form-error" style="display:none"></div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-outline" onclick="closeItemModal()">Batal</button>
          <button class="btn btn-primary" onclick="saveItem('${id||''}')">Simpan</button>
        </div>
      </div>
    </div>`;
  document.body.insertAdjacentHTML('beforeend', html);
  if (typeof feather !== 'undefined') feather.replace();
}

function closeItemModal() {
  document.getElementById('invItemModal')?.remove();
}

async function saveItem(id) {
  const sku   = document.getElementById('iCode').value.trim();
  const name  = document.getElementById('iName').value.trim();
  const errEl = document.getElementById('iErr');
  if (!sku || !name) { errEl.textContent='SKU dan Nama wajib diisi'; errEl.style.display='block'; return; }

  const unit  = document.getElementById('iUnit').value.trim() || 'pcs';
  const cost  = parseFloat(document.getElementById('iPurchasePrice').value) || 0;
  const price = parseFloat(document.getElementById('iSalePrice').value) || 0;

  try {
    if (id) {
      // Update: partial body (sku & type cannot change)
      await Api.items.update(id, {
        name, unit,
        default_unit_price: price,
        default_unit_cost:  cost,
      });
    } else {
      const type = document.getElementById('iType').value || 'stock';
      await Api.items.create({
        sku, name, type, unit,
        default_unit_price: price,
        default_unit_cost:  cost,
      });
    }
    showToast('Item berhasil disimpan', 'success');
    closeItemModal();
    await renderInventoryPage();
  } catch (e) {
    errEl.textContent = e.message; errEl.style.display = 'block';
  }
}

// ─── Modal: Warehouse ─────────────────────────────────────────
async function showWarehouseModal(id) {
  let wh = null;
  if (id) {
    try { wh = await Api.warehouses.get(id); } catch { showToast('Gagal memuat gudang', 'error'); return; }
  }

  const html = `
    <div class="modal-backdrop" id="invWhModal" onclick="if(event.target===this)closeWhModal()">
      <div class="modal-dialog" style="max-width:420px">
        <div class="modal-header">
          <h3>${wh ? 'Edit Gudang' : 'Tambah Gudang'}</h3>
          <button class="modal-close" onclick="closeWhModal()">×</button>
        </div>
        <div class="modal-body">
          <div class="form-group"><label>Kode *</label>
            <input class="form-control" id="whCode" value="${_escInv(wh?.code)}" placeholder="WH-01" ${id?'disabled':''}></div>
          <div class="form-group"><label>Nama *</label>
            <input class="form-control" id="whName" value="${_escInv(wh?.name)}" placeholder="Gudang Utama"></div>
          <div class="form-group">
            <label><input type="checkbox" id="whDefault" ${wh?.is_default?'checked':''}> Set sebagai gudang default</label>
          </div>
          <div id="whErr" class="form-error" style="display:none"></div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-outline" onclick="closeWhModal()">Batal</button>
          <button class="btn btn-primary" onclick="saveWarehouse('${id||''}')">Simpan</button>
        </div>
      </div>
    </div>`;
  document.body.insertAdjacentHTML('beforeend', html);
  if (typeof feather !== 'undefined') feather.replace();
}

function closeWhModal() {
  document.getElementById('invWhModal')?.remove();
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

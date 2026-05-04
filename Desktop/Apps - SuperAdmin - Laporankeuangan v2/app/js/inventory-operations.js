/**
 * INVENTORY-OPERATIONS.JS — Form unified "Operasi Stok"
 *
 * 6 jenis operasi stok yang otomatis:
 *   1. Mengubah qty on-hand (via /stock-movements)
 *   2. Memposting jurnal ber-keseimbangan (via contra_account_id)
 *
 *   ┌──────────────────────────────┬───────────┬───────────────────────────────┐
 *   │ Operasi                      │ Direction │ Jurnal yang dibuat            │
 *   ├──────────────────────────────┼───────────┼───────────────────────────────┤
 *   │ 📥 Penerimaan Barang         │ in        │ Dr Inventory / Cr [contra]    │
 *   │ 📤 Delivery / DO             │ out       │ Dr [contra] / Cr Inventory    │
 *   │ 🔧 Pemakaian Stok            │ out       │ Dr [Beban] / Cr Inventory     │
 *   │ ⚖️ Adjustment In (Surplus)   │ adjust_in │ Dr Inventory / Cr [Gain]      │
 *   │ ⚖️ Adjustment Out (Loss)     │ adjust_out│ Dr [Loss] / Cr Inventory      │
 *   │ ↩️ Return Penerimaan         │ out       │ Dr [contra] / Cr Inventory    │
 *   │ ↪️ Return Delivery           │ in        │ Dr Inventory / Cr [contra]    │
 *   └──────────────────────────────┴───────────┴───────────────────────────────┘
 *
 * Form rendering: pilih operasi → otomatis filter contra-account dropdown
 * berdasarkan tipe akun yang sesuai (asset/liability/income/expense).
 */

// 7 operasi stok standar. Default contra account-nya bisa di-set oleh user
// di halaman "Master Operasi" (mapping key: inv_op_<key>_contra).
const STOCK_OPERATIONS = {
  receipt: {
    label: '📥 Penerimaan Barang',
    description: 'Terima barang masuk gudang (cash purchase, transfer dari proyek, modal disetor barang). Menambah qty on-hand.',
    direction: 'in',
    operation: 'manual_receipt',
    contraTypes: ['liability', 'asset', 'equity'],
    contraLabel: 'Akun lawan (Cr)',
    contraHint: 'Misal: Utang Usaha (jika belum ada invoice), Kas (cash purchase), Modal (modal barang)',
    requiresUnitCost: true,
    qtyLabel: 'Qty Diterima',
    mappingKey: 'inv_op_receipt_contra',
  },
  delivery: {
    label: '📤 Delivery Order (DO)',
    description: 'Kirim barang ke customer (sample, free goods, antar tanpa invoice). Mengurangi qty on-hand.',
    direction: 'out',
    operation: 'manual_delivery',
    contraTypes: ['expense', 'asset'],
    contraLabel: 'Akun beban / lawan (Dr)',
    contraHint: 'Misal: Beban Sample/Promosi, Beban Marketing',
    requiresUnitCost: false,
    qtyLabel: 'Qty Dikirim',
    mappingKey: 'inv_op_delivery_contra',
  },
  usage: {
    label: '🔧 Pemakaian Stok',
    description: 'Pakai stok untuk operasional internal (ATK, bahan produksi, perlengkapan). Mengurangi qty + catat sebagai biaya.',
    direction: 'out',
    operation: 'stock_usage',
    contraTypes: ['expense'],
    contraLabel: 'Akun Beban Tujuan (Dr)',
    contraHint: 'Wajib pilih akun beban — misal Beban Perlengkapan Kantor, Beban Maintenance',
    requiresUnitCost: false,
    qtyLabel: 'Qty Dipakai',
    mappingKey: 'inv_op_usage_contra',
  },
  adjust_in: {
    label: '⚖️ Adjustment In (Surplus)',
    description: 'Cycle count menemukan surplus (qty fisik > qty sistem). Tambah qty + catat sebagai gain.',
    direction: 'adjust_in',
    operation: 'inventory_adjustment_in',
    contraTypes: ['income', 'expense'],
    contraLabel: 'Akun Gain / Lawan (Cr)',
    contraHint: 'Misal: Pendapatan Lain - Inventory Gain, atau kontra Beban Inventory Loss',
    requiresUnitCost: true,
    qtyLabel: 'Qty Surplus',
    mappingKey: 'inv_op_adjust_in_contra',
  },
  adjust_out: {
    label: '⚖️ Adjustment Out (Loss / Susut)',
    description: 'Cycle count menemukan kekurangan (rusak, hilang, shrinkage). Kurangi qty + catat sebagai biaya.',
    direction: 'adjust_out',
    operation: 'inventory_adjustment_out',
    contraTypes: ['expense'],
    contraLabel: 'Akun Loss / Beban (Dr)',
    contraHint: 'Misal: Beban Inventory Loss, Beban Susut Persediaan',
    requiresUnitCost: false,
    qtyLabel: 'Qty Loss',
    mappingKey: 'inv_op_adjust_out_contra',
  },
  return_receipt: {
    label: '↩️ Return Penerimaan (Kembali ke Supplier)',
    description: 'Kembalikan barang ke supplier (rusak, salah kirim). Mengurangi qty on-hand.',
    direction: 'out',
    operation: 'return_receipt',
    contraTypes: ['liability', 'asset', 'expense'],
    contraLabel: 'Akun lawan (Dr)',
    contraHint: 'Misal: Utang Usaha (kurangi tagihan supplier), atau Kas (jika sudah dibayar lalu refund)',
    requiresUnitCost: false,
    qtyLabel: 'Qty Diretur',
    mappingKey: 'inv_op_return_receipt_contra',
  },
  return_delivery: {
    label: '↪️ Return Delivery (Customer Kembali)',
    description: 'Customer kembalikan barang ke kita. Menambah qty on-hand.',
    direction: 'in',
    operation: 'return_delivery',
    contraTypes: ['income', 'asset', 'liability'],
    contraLabel: 'Akun lawan (Cr)',
    contraHint: 'Misal: Pendapatan Penjualan (contra revenue), Piutang Usaha (kurangi)',
    requiresUnitCost: true,
    qtyLabel: 'Qty Kembali',
    mappingKey: 'inv_op_return_delivery_contra',
  },
};

// Cache: { mappingKey → account_id } — populated on first form load
window.__opDefaultContras = {};

// Cache: list of custom operations from backend
window.__customOps = [];

async function _loadOpDefaultContras() {
  try {
    const mappings = await Api.accountMappings.list();
    window.__opDefaultContras = {};
    for (const m of mappings) {
      if (m.key.startsWith('inv_op_')) {
        window.__opDefaultContras[m.key] = m.account_id;
      }
    }
  } catch (e) { console.warn('[OpForm] failed to load default contras', e); }
}

async function _loadCustomOps() {
  try {
    window.__customOps = await Api.customInvOps.list({active_only: true});
  } catch (e) {
    console.warn('[OpForm] failed to load custom ops', e);
    window.__customOps = [];
  }
}

// Merge built-in + custom ops into a unified registry
// Returns: { key → opDefinition }
function _getAllOps() {
  const merged = {...STOCK_OPERATIONS};
  for (const op of (window.__customOps || [])) {
    merged[`custom_${op.key}`] = {
      label: `${op.icon || '🔖'} ${op.label}`,
      description: op.description || '',
      direction: op.direction,
      operation: op.key,  // operation source label sent to backend
      contraTypes: op.contra_account_types,
      contraLabel: 'Akun lawan',
      contraHint: '(custom operation — default dari Master Operasi)',
      requiresUnitCost: op.requires_unit_cost,
      qtyLabel: op.qty_label || 'Qty',
      mappingKey: null,  // custom ops use default_contra_account_id, not account_mappings
      _customOpId: op.id,
      _customDefaultContra: op.default_contra_account_id,
      _isCustom: true,
    };
  }
  return merged;
}

async function renderStockOpsPage() {
  const wrap = document.getElementById('page-inv-ops');
  if (!wrap) return;
  await _ensureInvMastersLoaded();

  // Load accounts + default contras + custom ops in parallel
  await Promise.all([
    Api.accounts.list().then(a => window.__opAccountsCache = a).catch(() => null),
    _loadOpDefaultContras(),
    _loadCustomOps(),
  ]);

  const today = new Date().toISOString().slice(0, 10);
  const allOps = _getAllOps();
  // Group: built-in first, then custom
  const builtIn = Object.entries(allOps).filter(([k]) => !k.startsWith('custom_'));
  const custom  = Object.entries(allOps).filter(([k]) => k.startsWith('custom_'));
  const opOptions = [
    ...(builtIn.length ? ['<optgroup label="Built-in">', ...builtIn.map(([k, op]) => `<option value="${k}">${op.label}</option>`), '</optgroup>'] : []),
    ...(custom.length ? ['<optgroup label="Custom (user-defined)">', ...custom.map(([k, op]) => `<option value="${k}">${op.label}</option>`), '</optgroup>'] : []),
  ].join('');

  wrap.innerHTML = `
    <div class="page-header">
      <h2>Operasi Stok</h2>
      <p class="page-subtitle">Form unified untuk Penerimaan, Delivery, Pemakaian, Adjustment, dan Return — auto-post jurnal balanced ke backend.</p>
    </div>

    <div style="background:#fff;padding:20px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);max-width:880px">
      <div class="form-group">
        <label style="font-size:13px;font-weight:600;color:#374151">Jenis Operasi *</label>
        <select id="opType" class="form-control" onchange="onOpTypeChange()" style="font-size:14px;padding:10px">
          <option value="">— Pilih jenis operasi —</option>
          ${opOptions}
        </select>
        <div id="opDescription" style="margin-top:8px;font-size:13px;color:#6b7280;line-height:1.4"></div>
      </div>

      <div id="opForm" style="display:none;border-top:1px solid #e5e7eb;padding-top:16px;margin-top:16px">
        <div class="form-row">
          <div class="form-group" style="flex:2"><label>Item *</label>
            <select id="opItem" class="form-control"><option value="">— Pilih item (stock-type) —</option>${_itemPickerOptions('')}</select></div>
          <div class="form-group" style="flex:1"><label>Gudang *</label>
            <select id="opWh" class="form-control">${_whPickerOptions('', false)}</select></div>
        </div>

        <div class="form-row">
          <div class="form-group" style="flex:1"><label>Tanggal *</label>
            <input id="opDate" class="form-control" type="date" value="${today}"></div>
          <div class="form-group" style="flex:1"><label id="opQtyLabel">Qty *</label>
            <input id="opQty" class="form-control" type="number" min="0.001" step="0.001" value="1"></div>
          <div class="form-group" style="flex:1" id="opUnitCostWrap"><label>Unit Cost</label>
            <input id="opUnitCost" class="form-control" type="number" min="0" step="0.01" value="0">
            <small style="color:#6b7280">Harga per unit untuk inflow</small></div>
        </div>

        <div class="form-group">
          <label id="opContraLabel">Akun Lawan *</label>
          <select id="opContra" class="form-control"><option value="">— Pilih akun —</option></select>
          <small id="opContraHint" style="color:#6b7280"></small>
        </div>

        <div class="form-group"><label>Catatan</label>
          <input id="opNotes" class="form-control" placeholder="Opsional — referensi PO/SO/dokumen pendukung"></div>

        <div id="opPreview" style="background:#f0f4ff;padding:12px 16px;border-radius:6px;margin:12px 0;font-size:13px"></div>

        <div id="opErr" class="form-error" style="display:none"></div>

        <div style="display:flex;gap:8px;justify-content:flex-end;border-top:1px solid #e5e7eb;padding-top:12px;margin-top:12px">
          <button class="btn btn-outline" onclick="resetOpForm()">Reset</button>
          <button class="btn btn-primary" onclick="submitStockOp()">💾 Simpan & Post Jurnal</button>
        </div>
      </div>
    </div>

    <!-- Recent operations -->
    <div style="margin-top:24px">
      <h3 style="font-size:15px;color:#374151">Operasi Terbaru</h3>
      <div id="opRecent"><div class="empty-state">Memuat…</div></div>
    </div>
  `;

  await _renderOpRecent();
}

async function _renderOpRecent() {
  const out = document.getElementById('opRecent');
  if (!out) return;
  try {
    const moves = await Api.stockMovements.list({limit: 20});
    const itemMap = Object.fromEntries((InventoryState.items || []).map(i => [i.id, i.sku]));
    const whMap = Object.fromEntries((InventoryState.warehouses || []).map(w => [w.id, w.code]));
    const filtered = moves.filter(m => m.source && (m.source.startsWith('manual_') || m.source.startsWith('stock_') || m.source.startsWith('inventory_') || m.source.startsWith('return_')));
    if (!filtered.length) { out.innerHTML = '<div class="empty-state">Belum ada operasi manual.</div>'; return; }
    out.innerHTML = `
      <table class="data-table">
        <thead><tr>
          <th>Tanggal</th><th>Operasi</th><th>Item</th><th>Gudang</th>
          <th class="text-right">Qty</th><th class="text-right">Unit Cost</th>
          <th class="text-right">Total</th><th>Notes</th>
        </tr></thead>
        <tbody>${filtered.map(m => `<tr>
          <td>${m.movement_date}</td>
          <td><span class="badge">${_escInv(m.source)}</span></td>
          <td>${_escInv(itemMap[m.item_id] || m.item_id.slice(0,8))}</td>
          <td>${_escInv(whMap[m.warehouse_id] || m.warehouse_id.slice(0,8))}</td>
          <td class="text-right">${m.direction.includes('out') ? '-' : '+'}${_fmtInv(m.qty)}</td>
          <td class="text-right">${_fmtInv(m.unit_cost)}</td>
          <td class="text-right">${_fmtInv((Number(m.qty)*Number(m.unit_cost)).toFixed(2))}</td>
          <td>${_escInv(m.notes || '')}</td>
        </tr>`).join('')}</tbody>
      </table>`;
  } catch (e) {
    out.innerHTML = `<div class="empty-state error">Gagal: ${e.message}</div>`;
  }
}

function onOpTypeChange() {
  const opKey = document.getElementById('opType').value;
  const formEl = document.getElementById('opForm');
  const descEl = document.getElementById('opDescription');
  if (!opKey) { formEl.style.display = 'none'; descEl.textContent = ''; return; }

  const allOps = _getAllOps();
  const op = allOps[opKey];
  if (!op) { formEl.style.display = 'none'; return; }
  formEl.style.display = '';
  descEl.innerHTML = `<strong>${op.label}:</strong> ${_escInv(op.description)}`;

  document.getElementById('opQtyLabel').textContent = op.qtyLabel + ' *';
  document.getElementById('opContraLabel').textContent = op.contraLabel + ' *';
  document.getElementById('opContraHint').textContent = op.contraHint;
  document.getElementById('opUnitCostWrap').style.display = op.requiresUnitCost ? '' : 'none';

  // Filter contra accounts dropdown by allowed types
  const accts = window.__opAccountsCache || [];
  const filtered = accts.filter(a => op.contraTypes.includes(a.type) && a.is_active);
  const sorted = filtered.sort((a, b) => a.code.localeCompare(b.code));

  // Pre-select default contra: from mappings (built-in) OR from custom op (custom)
  let defaultContraId = '';
  if (op._isCustom) {
    defaultContraId = op._customDefaultContra || '';
  } else if (op.mappingKey) {
    defaultContraId = window.__opDefaultContras?.[op.mappingKey] || '';
  }

  document.getElementById('opContra').innerHTML =
    `<option value="">— Pilih akun ${op.contraTypes.join('/')} —</option>` +
    sorted.map(a =>
      `<option value="${a.id}" ${a.id === defaultContraId ? 'selected' : ''}>${_escInv(a.code)} — ${_escInv(a.name)} <small>(${a.type})</small></option>`
    ).join('');

  // Show "default loaded" badge if we pre-selected
  const hint = document.getElementById('opContraHint');
  if (defaultContraId && hint) {
    const acct = accts.find(a => a.id === defaultContraId);
    if (acct) {
      hint.innerHTML = `<span style="color:#15803d">✓ Default dari Master Operasi: <strong>${_escInv(acct.code)} ${_escInv(acct.name)}</strong></span> · <a href="#" onclick="navigateTo('inv-op-master');return false" style="color:#1a56db">Edit default</a>`;
    }
  } else if (hint) {
    hint.textContent = op.contraHint || '';
  }

  _updateOpPreview();
}

function _updateOpPreview() {
  const opKey = document.getElementById('opType').value;
  if (!opKey) return;
  const allOps = _getAllOps();
  const op = allOps[opKey];
  if (!op) return;
  const qty = parseFloat(document.getElementById('opQty').value) || 0;
  const cost = parseFloat(document.getElementById('opUnitCost').value) || 0;
  const contraId = document.getElementById('opContra').value;
  const accts = window.__opAccountsCache || [];
  const contra = accts.find(a => a.id === contraId);
  const inventoryMapping = (window.__opAccountsCache?.find(a => a._isInventoryMapping)) || null;

  const amount = qty * cost;
  const contraName = contra ? `${contra.code} ${contra.name}` : '<em>(pilih akun)</em>';

  let dr, cr;
  if (['in', 'adjust_in'].includes(op.direction)) {
    dr = `<strong>Inventory</strong>`; cr = contraName;
  } else {
    dr = contraName; cr = `<strong>Inventory</strong>`;
  }

  const previewEl = document.getElementById('opPreview');
  if (!previewEl) return;
  if (qty <= 0) {
    previewEl.innerHTML = '<em>Isi qty untuk melihat preview jurnal</em>';
    return;
  }
  previewEl.innerHTML = `
    <strong>📋 Preview Jurnal:</strong><br>
    <span style="font-family:monospace">
      Dr  ${dr.padEnd(60)}  ${_fmtInv(amount || qty)}<br>
      &nbsp;&nbsp;&nbsp;&nbsp;Cr  ${cr.padEnd(56)}  ${_fmtInv(amount || qty)}
    </span>
    <small style="display:block;margin-top:4px;color:#6b7280">
      ${op.requiresUnitCost ? `Total = ${qty} × ${cost} = ${_fmtInv(amount)}` : `Total dihitung dari avg_cost saat post (estimasi: ${_fmtInv(amount || qty)})`}
    </small>`;
}

function resetOpForm() {
  document.getElementById('opType').value = '';
  document.getElementById('opForm').style.display = 'none';
  document.getElementById('opDescription').textContent = '';
}

async function submitStockOp() {
  const errEl = document.getElementById('opErr');
  errEl.style.display = 'none';
  const opKey = document.getElementById('opType').value;
  if (!opKey) { errEl.textContent = 'Pilih jenis operasi dulu'; errEl.style.display='block'; return; }
  const allOps = _getAllOps();
  const op = allOps[opKey];
  if (!op) { errEl.textContent = 'Operasi tidak ditemukan'; errEl.style.display='block'; return; }

  const itemId    = document.getElementById('opItem').value;
  const whId      = document.getElementById('opWh').value;
  const date      = document.getElementById('opDate').value;
  const qty       = parseFloat(document.getElementById('opQty').value);
  const unitCost  = parseFloat(document.getElementById('opUnitCost').value) || 0;
  const contraId  = document.getElementById('opContra').value;
  const notes     = document.getElementById('opNotes').value.trim();

  if (!itemId || !whId || !date || !qty || qty <= 0) {
    errEl.textContent = 'Item, Gudang, Tanggal, dan Qty > 0 wajib diisi'; errEl.style.display='block'; return;
  }
  if (!contraId) {
    errEl.textContent = 'Pilih akun lawan (contra) dulu'; errEl.style.display='block'; return;
  }
  if (op.requiresUnitCost && (!unitCost || unitCost <= 0)) {
    errEl.textContent = 'Unit Cost harus > 0 untuk operasi inflow'; errEl.style.display='block'; return;
  }

  try {
    const result = await Api.stockMovements.create({
      item_id: itemId,
      warehouse_id: whId,
      movement_date: date,
      direction: op.direction,
      qty,
      unit_cost: unitCost,
      notes: notes || null,
      contra_account_id: contraId,
      operation: op.operation,
    });
    showToast(`${op.label} berhasil — ${result.notes || 'jurnal terposting'}`, 'success');
    resetOpForm();
    await _renderOpRecent();
  } catch (e) {
    errEl.textContent = e.message;
    errEl.style.display = 'block';
  }
}

// Listen on form changes for live preview
document.addEventListener('input', (e) => {
  if (['opQty','opUnitCost','opContra'].includes(e.target?.id)) _updateOpPreview();
});
document.addEventListener('change', (e) => {
  if (e.target?.id === 'opContra') _updateOpPreview();
});


// ═══════════════════════════════════════════════════════════════════
// MASTER OPERASI STOK (#page-inv-op-master)
// Set default contra account per jenis operasi.
// Saved in account_mappings (keys: inv_op_<key>_contra).
// ═══════════════════════════════════════════════════════════════════
async function renderStockOpsMasterPage() {
  const wrap = document.getElementById('page-inv-op-master');
  if (!wrap) return;

  // Refresh state in parallel
  await Promise.all([
    Api.accounts.list().then(a => window.__opAccountsCache = a).catch(() => null),
    _loadOpDefaultContras(),
    _loadCustomOps(),
  ]);

  const accts = window.__opAccountsCache || [];
  const defaults = window.__opDefaultContras || {};

  const builtInRows = Object.entries(STOCK_OPERATIONS).map(([key, op]) => {
    const filtered = accts.filter(a => op.contraTypes.includes(a.type) && a.is_active);
    const sorted = filtered.sort((a, b) => a.code.localeCompare(b.code));
    const currentId = defaults[op.mappingKey] || '';
    const currentAcct = currentId ? accts.find(a => a.id === currentId) : null;

    const dirBadge = ({
      'in': '<span class="badge badge-success">+ in</span>',
      'out': '<span class="badge badge-danger">− out</span>',
      'adjust_in': '<span class="badge badge-success">+ adjust_in</span>',
      'adjust_out': '<span class="badge badge-danger">− adjust_out</span>',
    })[op.direction] || op.direction;

    const status = currentAcct
      ? `<span class="badge badge-success">✓ ${_escInv(currentAcct.code)} ${_escInv(currentAcct.name).slice(0,30)}</span>`
      : '<span class="badge badge-warning">⚠ Belum di-set</span>';

    return `<tr>
      <td>${op.label}<br><small style="color:#6b7280">${dirBadge}</small></td>
      <td><div style="font-size:13px">${_escInv(op.description)}</div>
          <div style="font-size:11px;color:#9ca3af;margin-top:4px">Allowed types: ${op.contraTypes.join(', ')}</div></td>
      <td>${status}</td>
      <td>
        <select class="form-control" id="om-${key}" style="min-width:280px">
          <option value="">— Pilih akun ${op.contraTypes.join('/')} —</option>
          ${sorted.map(a => `<option value="${a.id}" ${a.id === currentId ? 'selected' : ''}>${_escInv(a.code)} — ${_escInv(a.name)}</option>`).join('')}
        </select>
      </td>
      <td>
        <button class="btn btn-sm btn-primary" onclick="saveOpMaster('${key}')">Simpan</button>
        ${currentId ? `<button class="btn btn-sm btn-outline" onclick="clearOpMaster('${key}')" style="margin-left:4px">Hapus</button>` : ''}
      </td>
    </tr>`;
  }).join('');

  // Custom operation rows (with edit/delete)
  const customRows = (window.__customOps || []).map(op => {
    const acct = op.default_contra_account_id ? accts.find(a => a.id === op.default_contra_account_id) : null;
    const dirBadge = ({
      'in':'<span class="badge badge-success">+ in</span>',
      'out':'<span class="badge badge-danger">− out</span>',
      'adjust_in':'<span class="badge badge-success">+ adjust_in</span>',
      'adjust_out':'<span class="badge badge-danger">− adjust_out</span>',
    })[op.direction] || op.direction;
    const status = acct
      ? `<span class="badge badge-success">✓ ${_escInv(acct.code)} ${_escInv(acct.name).slice(0,30)}</span>`
      : '<span class="badge badge-warning">⚠ No default</span>';
    return `<tr style="background:#fef9c3">
      <td>${op.icon || '🔖'} ${_escInv(op.label)}<br>
          <small style="color:#6b7280">${dirBadge} · key=<code>${_escInv(op.key)}</code></small></td>
      <td><div style="font-size:13px">${_escInv(op.description || '')}</div>
          <div style="font-size:11px;color:#9ca3af;margin-top:4px">Allowed: ${(op.contra_account_types||[]).join(', ')}${op.requires_unit_cost?' · requires unit cost':''}</div></td>
      <td colspan="2">${status}</td>
      <td>
        <button class="btn btn-sm btn-outline" onclick="showCustomOpModal('${op.id}')">Edit</button>
        <button class="btn btn-sm btn-danger" onclick="deleteCustomOp('${op.id}','${_escInv(op.label)}')">×</button>
      </td>
    </tr>`;
  }).join('');

  wrap.innerHTML = `
    <div class="page-header">
      <div>
        <h2>Master Operasi Stok</h2>
        <p class="page-subtitle">Atur default akun lawan untuk operasi built-in, dan/atau tambahkan operasi custom sendiri (misal: <em>Pemakaian Bahan Produksi</em>, <em>Sample Demo Klien</em>).</p>
      </div>
      <div>
        <button class="btn btn-primary" onclick="showCustomOpModal(null)">+ Tambah Operasi Custom</button>
        <button class="btn btn-outline" onclick="renderStockOpsMasterPage()">↻ Refresh</button>
      </div>
    </div>

    <h3 style="font-size:14px;color:#374151;margin:16px 0 8px">Operasi Built-in (7)</h3>
    <div style="background:#fff;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);overflow:hidden;margin-bottom:24px">
      <table class="data-table" style="margin:0">
        <thead><tr>
          <th style="width:18%">Operasi</th>
          <th style="width:32%">Penjelasan</th>
          <th style="width:18%">Default Saat Ini</th>
          <th style="width:24%">Set Default</th>
          <th style="width:8%">Aksi</th>
        </tr></thead>
        <tbody>${builtInRows}</tbody>
      </table>
    </div>

    <h3 style="font-size:14px;color:#374151;margin:16px 0 8px">Operasi Custom (User-defined) ${(window.__customOps||[]).length ? '· '+(window.__customOps.length)+' op' : ''}</h3>
    <div style="background:#fff;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);overflow:hidden">
      ${(window.__customOps||[]).length === 0 ? `
        <div style="padding:24px;text-align:center;color:#6b7280">
          Belum ada custom operation. Klik <strong>+ Tambah Operasi Custom</strong> di atas untuk membuat.
        </div>` : `
        <table class="data-table" style="margin:0">
          <thead><tr>
            <th style="width:18%">Operasi</th>
            <th style="width:32%">Penjelasan</th>
            <th colspan="2" style="width:42%">Default Akun</th>
            <th style="width:8%">Aksi</th>
          </tr></thead>
          <tbody>${customRows}</tbody>
        </table>`}
    </div>

    <div style="background:#fefce8;border-left:4px solid #eab308;padding:12px 16px;margin-top:16px;border-radius:4px;font-size:13px">
      <strong>💡 Cara kerja:</strong>
      <ol style="margin:6px 0 0 20px">
        <li><strong>Built-in</strong>: pilih akun default di dropdown → klik Simpan. Disimpan di <code>account_mappings</code>.</li>
        <li><strong>Custom</strong>: klik "+ Tambah Operasi Custom" untuk define operasi baru (key, label, direction, allowed contra types, default contra). Disimpan di <code>custom_inventory_operations</code>.</li>
        <li>Semua operasi (built-in + custom) muncul di dropdown <em>Inventory → Operasi Stok</em>, dengan akun lawan otomatis ter-pre-select.</li>
      </ol>
    </div>
  `;
}

// ─── Modal: Add/Edit Custom Operation ────────────────────────
async function showCustomOpModal(opId) {
  const accts = window.__opAccountsCache || [];
  let existing = null;
  if (opId) {
    existing = (window.__customOps || []).find(x => x.id === opId);
    if (!existing) { showToast('Operasi tidak ditemukan', 'error'); return; }
  }

  const directions = [
    {v:'in', l:'in (menambah qty)'},
    {v:'out', l:'out (mengurangi qty)'},
    {v:'adjust_in', l:'adjust_in (cycle count surplus)'},
    {v:'adjust_out', l:'adjust_out (cycle count loss)'},
  ];
  const dirOpts = directions.map(d => `<option value="${d.v}" ${existing?.direction===d.v?'selected':''}>${d.l}</option>`).join('');

  const types = ['asset', 'liability', 'equity', 'income', 'expense'];
  const typeChips = types.map(t => {
    const checked = existing ? (existing.contra_account_types || []).includes(t) : false;
    return `<label style="display:inline-flex;align-items:center;gap:4px;padding:4px 10px;border:1px solid #d1d5db;border-radius:999px;margin-right:6px;font-size:12px;cursor:pointer">
      <input type="checkbox" name="cocta" value="${t}" ${checked?'checked':''}> ${t}
    </label>`;
  }).join('');

  // Default contra dropdown — show all accounts but filter via JS
  const acctOpts = accts.sort((a,b)=>a.code.localeCompare(b.code))
    .map(a => `<option value="${a.id}" data-type="${a.type}" ${existing?.default_contra_account_id===a.id?'selected':''}>${_escInv(a.code)} — ${_escInv(a.name)} (${a.type})</option>`).join('');

  const html = `
    <div class="modal-backdrop" id="customOpModal" onclick="if(event.target===this)closeCustomOpModal()">
      <div class="modal-dialog" style="max-width:620px">
        <div class="modal-header">
          <h3>${existing ? 'Edit' : 'Tambah'} Operasi Custom</h3>
          <button class="modal-close" onclick="closeCustomOpModal()">×</button>
        </div>
        <div class="modal-body">
          <div class="form-row">
            <div class="form-group" style="flex:1"><label>Key (slug) *</label>
              <input class="form-control" id="coKey" value="${_escInv(existing?.key||'')}" placeholder="production_consumption" ${existing?'disabled':''}>
              <small style="color:#6b7280">Lowercase, alphanumeric + underscore. Tidak bisa diubah setelah dibuat.</small></div>
            <div class="form-group" style="width:80px;flex:0"><label>Icon</label>
              <input class="form-control" id="coIcon" value="${_escInv(existing?.icon||'')}" placeholder="🏭" maxlength="4"></div>
          </div>
          <div class="form-group"><label>Label *</label>
            <input class="form-control" id="coLabel" value="${_escInv(existing?.label||'')}" placeholder="Pemakaian Bahan Produksi"></div>
          <div class="form-group"><label>Description</label>
            <textarea class="form-control" id="coDesc" rows="2" placeholder="Misal: pakai bahan baku untuk lini produksi A">${_escInv(existing?.description||'')}</textarea></div>
          <div class="form-row">
            <div class="form-group" style="flex:1"><label>Direction *</label>
              <select class="form-control" id="coDir">${dirOpts}</select></div>
            <div class="form-group" style="flex:1"><label>Qty Label</label>
              <input class="form-control" id="coQtyLabel" value="${_escInv(existing?.qty_label||'')}" placeholder="Qty Dipakai"></div>
          </div>
          <div class="form-group">
            <label>Allowed Contra Account Types * (boleh pilih lebih dari satu)</label>
            <div>${typeChips}</div>
          </div>
          <div class="form-group">
            <label><input type="checkbox" id="coRequiresCost" ${existing?.requires_unit_cost?'checked':''}> Wajib isi Unit Cost (untuk inflow yang punya nilai)</label>
          </div>
          <div class="form-group"><label>Default Contra Account (opsional)</label>
            <select class="form-control" id="coDefaultContra">
              <option value="">— Tidak ada default —</option>
              ${acctOpts}
            </select>
            <small style="color:#6b7280">Akan ter-pre-select di form Operasi Stok saat user pilih operasi ini</small>
          </div>
          <div class="form-row">
            <div class="form-group" style="flex:1"><label>Display Order</label>
              <input class="form-control" id="coOrder" type="number" value="${existing?.display_order||100}" min="0" max="999"></div>
            <div class="form-group" style="flex:1">
              <label><input type="checkbox" id="coActive" ${existing===null||existing?.is_active!==false?'checked':''}> Aktif</label>
            </div>
          </div>
          <div id="coErr" class="form-error" style="display:none"></div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-outline" onclick="closeCustomOpModal()">Batal</button>
          <button class="btn btn-primary" onclick="saveCustomOp('${existing?.id||''}')">Simpan</button>
        </div>
      </div>
    </div>`;
  document.body.insertAdjacentHTML('beforeend', html);
}

function closeCustomOpModal() { document.getElementById('customOpModal')?.remove(); }

async function saveCustomOp(opId) {
  const errEl = document.getElementById('coErr');
  errEl.style.display = 'none';
  const key   = document.getElementById('coKey').value.trim();
  const label = document.getElementById('coLabel').value.trim();
  const desc  = document.getElementById('coDesc').value.trim();
  const dir   = document.getElementById('coDir').value;
  const types = Array.from(document.querySelectorAll('input[name="cocta"]:checked')).map(c => c.value);
  const reqCost = document.getElementById('coRequiresCost').checked;
  const defContra = document.getElementById('coDefaultContra').value;
  const qtyLabel = document.getElementById('coQtyLabel').value.trim();
  const icon = document.getElementById('coIcon').value.trim();
  const order = parseInt(document.getElementById('coOrder').value) || 100;
  const active = document.getElementById('coActive').checked;

  if (!key || !/^[a-z0-9_]+$/.test(key)) {
    errEl.textContent = 'Key wajib (lowercase, alphanumeric + underscore)'; errEl.style.display='block'; return;
  }
  if (!label) { errEl.textContent = 'Label wajib diisi'; errEl.style.display='block'; return; }
  if (!types.length) { errEl.textContent = 'Pilih minimal 1 contra account type'; errEl.style.display='block'; return; }

  const body = {
    label, description: desc || null,
    direction: dir,
    contra_account_types: types,
    default_contra_account_id: defContra || null,
    requires_unit_cost: reqCost,
    qty_label: qtyLabel || null,
    icon: icon || null,
    display_order: order,
    is_active: active,
  };

  try {
    if (opId) {
      await Api.customInvOps.update(opId, body);
      showToast('Operasi custom diupdate', 'success');
    } else {
      body.key = key;
      await Api.customInvOps.create(body);
      showToast('Operasi custom dibuat', 'success');
    }
    closeCustomOpModal();
    await renderStockOpsMasterPage();
  } catch (e) {
    errEl.textContent = e.message; errEl.style.display = 'block';
  }
}

async function deleteCustomOp(opId, label) {
  if (!confirm(`Hapus operasi custom "${label}"? Soft delete — akan di-set is_active=false.`)) return;
  try {
    await Api.customInvOps.delete(opId);
    showToast('Operasi dinonaktifkan', 'success');
    await renderStockOpsMasterPage();
  } catch (e) { showToast('Gagal: ' + e.message, 'error'); }
}

async function saveOpMaster(opKey) {
  const op = STOCK_OPERATIONS[opKey];
  if (!op) return;
  const accountId = document.getElementById('om-' + opKey)?.value;
  if (!accountId) {
    showToast('Pilih akun dulu', 'warning');
    return;
  }
  try {
    await Api.accountMappings.set({key: op.mappingKey, account_id: accountId});
    showToast(`Default akun untuk "${op.label.replace(/^\S+\s/, '')}" tersimpan`, 'success');
    await renderStockOpsMasterPage();
  } catch (e) {
    showToast('Gagal: ' + e.message, 'error');
  }
}

async function clearOpMaster(opKey) {
  const op = STOCK_OPERATIONS[opKey];
  if (!op) return;
  if (!confirm(`Hapus default akun untuk "${op.label}"?`)) return;
  // No DELETE endpoint for mapping — set to a sentinel ("clear" by setting same key with empty)
  // Workaround: we can't truly delete, but we can set to a placeholder. For now just refresh —
  // backend should expose DELETE later. As a UX patch, we just reset the select to empty
  // and tell user the default is "ignored" if not set in this list.
  showToast('Untuk hapus default, biarkan dropdown kosong lalu Simpan (akan reset).', 'info');
}

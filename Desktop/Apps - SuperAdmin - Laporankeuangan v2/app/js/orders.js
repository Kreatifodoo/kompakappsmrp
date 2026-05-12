/**
 * ORDERS.JS — Sales Order + Purchase Order UI
 *
 * Pages:
 *   - page-sales-orders     → list SO, create modal, confirm/cancel
 *   - page-purchase-orders  → list PO, create modal, confirm/cancel
 *
 * Each order has a "Buat DO/GR" button on confirmed status that opens a
 * pre-filled fulfillment modal (delegated to fulfillment.js).
 *
 * Backend-only: no localStorage fallback. SO/PO are pure backend constructs.
 */

const OrdersState = {
  sos: [],
  pos: [],
  customers: [],
  suppliers: [],
  items: [],
  warehouses: [],
};

const _ordFmtRp = (n) => 'Rp ' + Math.round(n || 0).toLocaleString('id-ID');
const _ordEsc   = (s) => String(s ?? '').replace(/[<>&"]/g, c => ({'<':'&lt;','>':'&gt;','&':'&amp;','"':'&quot;'}[c]));
const _ordToday = () => new Date().toISOString().slice(0,10);

async function _ordEnsureMasters() {
  // Lazy-load supporting masters once
  if (!OrdersState.customers.length || !OrdersState.suppliers.length ||
      !OrdersState.items.length     || !OrdersState.warehouses.length) {
    try {
      const [c, s, i, w] = await Promise.all([
        Api.customers.list({limit: 500}),
        Api.suppliers.list({limit: 500}),
        Api.items.list({limit: 500}),
        Api.warehouses.list(),
      ]);
      OrdersState.customers  = Array.isArray(c) ? c : [];
      OrdersState.suppliers  = Array.isArray(s) ? s : [];
      OrdersState.items      = Array.isArray(i) ? i : [];
      OrdersState.warehouses = Array.isArray(w) ? w : [];
    } catch (e) {
      console.warn('[orders] load masters failed', e);
    }
  }
}

function _ordStatusBadge(status) {
  const map = {
    draft:               ['#6b7280', 'Draft'],
    confirmed:           ['#3b82f6', 'Confirmed'],
    partially_delivered: ['#f59e0b', 'Partial Delivered'],
    partially_received:  ['#f59e0b', 'Partial Received'],
    fulfilled:           ['#10b981', 'Fulfilled'],
    cancelled:           ['#ef4444', 'Cancelled'],
  };
  const [c, label] = map[status] || ['#6b7280', status || '-'];
  return `<span style="display:inline-block;padding:2px 8px;background:${c}20;color:${c};border-radius:6px;font-size:11px;font-weight:600">${label}</span>`;
}

// ════════════════════════════════════════════════════════════════
// SALES ORDERS
// ════════════════════════════════════════════════════════════════

async function renderSalesOrderPage() {
  await _ordEnsureMasters();
  const filterStatus = document.getElementById('soFilterStatus')?.value || '';
  const filterCust   = document.getElementById('soFilterCustomer')?.value || '';
  try {
    const sos = await Api.salesOrders.list({
      status: filterStatus || undefined,
      customer_id: filterCust || undefined,
      limit: 200,
    });
    OrdersState.sos = Array.isArray(sos) ? sos : [];
  } catch (e) {
    showToast('Gagal load Sales Order: ' + e.message, 'error');
    OrdersState.sos = [];
  }

  // Customer filter options
  const custSel = document.getElementById('soFilterCustomer');
  if (custSel) {
    const cur = custSel.value;
    custSel.innerHTML = '<option value="">Semua Customer</option>' +
      OrdersState.customers.map(c => `<option value="${c.id}" ${c.id===cur?'selected':''}>${_ordEsc(c.name)}</option>`).join('');
  }

  const wrap = document.getElementById('soTableWrap');
  if (!wrap) return;
  if (!OrdersState.sos.length) {
    wrap.innerHTML = `<div style="padding:48px;text-align:center;color:#6b7280">Belum ada Sales Order. Klik <strong>"Buat SO"</strong>.</div>`;
    return;
  }

  const custMap = Object.fromEntries(OrdersState.customers.map(c => [c.id, c.name]));
  wrap.innerHTML = `
    <table class="data-table">
      <thead><tr>
        <th>No SO</th><th>Tanggal</th><th>Customer</th>
        <th style="text-align:right">Total</th>
        <th>Status</th><th style="text-align:center">Aksi</th>
      </tr></thead>
      <tbody>
      ${OrdersState.sos.map(so => `
        <tr>
          <td><code>${_ordEsc(so.so_no)}</code></td>
          <td>${so.order_date || '-'}</td>
          <td>${_ordEsc(custMap[so.customer_id] || so.customer_id)}</td>
          <td style="text-align:right"><strong>${_ordFmtRp(so.total)}</strong></td>
          <td>${_ordStatusBadge(so.status)}</td>
          <td style="text-align:center;white-space:nowrap">
            <button class="btn btn-sm btn-outline" onclick="showSalesOrderDetail('${so.id}')">Detail</button>
            ${so.status === 'draft' ? `<button class="btn btn-sm btn-primary" style="margin-left:4px" onclick="confirmSalesOrder('${so.id}')">Confirm</button>` : ''}
            ${(so.status==='confirmed' || so.status==='partially_delivered') ? `<button class="btn btn-sm btn-success" style="margin-left:4px" onclick="createDOFromSO('${so.id}')">Buat DO</button>` : ''}
            ${(so.status==='draft' || so.status==='confirmed' || so.status==='partially_delivered') ? `<button class="btn btn-sm btn-danger" style="margin-left:4px" onclick="cancelSalesOrder('${so.id}')">Cancel</button>` : ''}
          </td>
        </tr>`).join('')}
      </tbody>
    </table>`;
}

let _soLines = [];

function showSalesOrderModal() {
  _soLines = [{ item_id: '', warehouse_id: '', qty_ordered: 1, unit_price: 0, tax_rate: 0 }];
  const itemOpts = OrdersState.items.map(i => `<option value="${i.id}" data-price="${i.sale_price || 0}">${_ordEsc(i.name)} (${_ordEsc(i.sku || '-')})</option>`).join('');
  const whOpts   = OrdersState.warehouses.map(w => `<option value="${w.id}">${_ordEsc(w.name)}</option>`).join('');
  const custOpts = OrdersState.customers.map(c => `<option value="${c.id}">${_ordEsc(c.name)}</option>`).join('');

  const html = `
  <div class="modal-backdrop" id="soModalBackdrop" onclick="if(event.target===this)closeSOModal()">
    <div class="modal-content" style="max-width:900px">
      <div class="modal-header">
        <h3>Buat Sales Order</h3>
        <button class="modal-close" onclick="closeSOModal()">×</button>
      </div>
      <div class="modal-body">
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:16px">
          <div><label>Tanggal Order</label><input type="date" id="soDate" value="${_ordToday()}" class="form-control" /></div>
          <div><label>Expected Delivery</label><input type="date" id="soExpDate" class="form-control" /></div>
          <div><label>Customer</label>
            <select id="soCustomer" class="form-control"><option value="">— pilih —</option>${custOpts}</select>
          </div>
        </div>
        <h4 style="margin:12px 0 8px">Items</h4>
        <table class="data-table" id="soLinesTable">
          <thead><tr>
            <th style="width:30%">Item</th><th>Warehouse</th>
            <th style="width:80px">Qty</th><th style="width:120px">Harga</th>
            <th style="width:60px">Tax %</th><th style="width:120px">Subtotal</th><th></th>
          </tr></thead>
          <tbody id="soLinesBody"></tbody>
        </table>
        <button class="btn btn-sm btn-outline" onclick="_soAddLine()" style="margin-top:8px">+ Tambah baris</button>
        <div style="margin-top:16px"><label>Notes</label><textarea id="soNotes" class="form-control" rows="2"></textarea></div>
        <div style="margin-top:16px;text-align:right;font-size:16px"><strong>Total: <span id="soTotalDisplay">Rp 0</span></strong></div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-outline" onclick="closeSOModal()">Tutup</button>
        <button class="btn btn-primary" onclick="saveSalesOrder(false)">Simpan Draft</button>
        <button class="btn btn-success" onclick="saveSalesOrder(true)">Simpan + Confirm</button>
      </div>
    </div>
  </div>`;
  document.body.insertAdjacentHTML('beforeend', html);
  _soRenderLines(itemOpts, whOpts);
}

function _soRenderLines(itemOpts, whOpts) {
  itemOpts = itemOpts || OrdersState.items.map(i => `<option value="${i.id}" data-price="${i.sale_price || 0}">${_ordEsc(i.name)}</option>`).join('');
  whOpts   = whOpts   || OrdersState.warehouses.map(w => `<option value="${w.id}">${_ordEsc(w.name)}</option>`).join('');
  const body = document.getElementById('soLinesBody');
  if (!body) return;
  body.innerHTML = _soLines.map((ln, idx) => `
    <tr>
      <td><select class="form-control" onchange="_soUpdateLine(${idx},'item_id',this.value); _soMaybeFillPrice(${idx}, this)"><option value="">— pilih —</option>${itemOpts.replace(`value="${ln.item_id}"`, `value="${ln.item_id}" selected`)}</select></td>
      <td><select class="form-control" onchange="_soUpdateLine(${idx},'warehouse_id',this.value)"><option value="">— pilih —</option>${whOpts.replace(`value="${ln.warehouse_id}"`, `value="${ln.warehouse_id}" selected`)}</select></td>
      <td><input type="number" step="0.01" value="${ln.qty_ordered}" class="form-control" onchange="_soUpdateLine(${idx},'qty_ordered',parseFloat(this.value)||0)" /></td>
      <td><input type="number" step="100" value="${ln.unit_price}" class="form-control" onchange="_soUpdateLine(${idx},'unit_price',parseFloat(this.value)||0)" /></td>
      <td><input type="number" step="0.01" value="${ln.tax_rate}" class="form-control" onchange="_soUpdateLine(${idx},'tax_rate',parseFloat(this.value)||0)" /></td>
      <td style="text-align:right">${_ordFmtRp(ln.qty_ordered * ln.unit_price * (1 + (ln.tax_rate||0)/100))}</td>
      <td><button class="btn btn-sm btn-danger" onclick="_soRemoveLine(${idx})">×</button></td>
    </tr>`).join('');
  _soUpdateTotal();
}

function _soMaybeFillPrice(idx, sel) {
  const opt = sel.options[sel.selectedIndex];
  const price = parseFloat(opt?.dataset?.price || 0);
  if (price > 0 && (!_soLines[idx].unit_price || _soLines[idx].unit_price === 0)) {
    _soLines[idx].unit_price = price;
    _soRenderLines();
  }
}

function _soUpdateLine(idx, field, value) { _soLines[idx][field] = value; _soUpdateTotal(); }
function _soAddLine() { _soLines.push({ item_id:'', warehouse_id:'', qty_ordered:1, unit_price:0, tax_rate:0 }); _soRenderLines(); }
function _soRemoveLine(idx) { _soLines.splice(idx,1); if (!_soLines.length) _soAddLine(); else _soRenderLines(); }
function _soUpdateTotal() {
  const total = _soLines.reduce((s,l) => s + (l.qty_ordered||0) * (l.unit_price||0) * (1 + (l.tax_rate||0)/100), 0);
  const el = document.getElementById('soTotalDisplay');
  if (el) el.textContent = _ordFmtRp(total);
}

function closeSOModal() { document.getElementById('soModalBackdrop')?.remove(); }

async function saveSalesOrder(confirmNow) {
  const customer_id = document.getElementById('soCustomer').value;
  const order_date  = document.getElementById('soDate').value;
  const exp_date    = document.getElementById('soExpDate').value;
  const notes       = document.getElementById('soNotes').value;
  if (!customer_id) { showToast('Customer wajib dipilih', 'error'); return; }
  if (!order_date)  { showToast('Tanggal wajib diisi', 'error'); return; }
  const valid = _soLines.filter(l => l.item_id && l.warehouse_id && l.qty_ordered > 0);
  if (!valid.length) { showToast('Minimal 1 baris item valid', 'error'); return; }

  const payload = {
    order_date, customer_id, notes: notes || null,
    expected_delivery_date: exp_date || null,
    lines: valid.map(l => ({
      item_id: l.item_id, warehouse_id: l.warehouse_id,
      qty_ordered: l.qty_ordered, unit_price: l.unit_price, tax_rate: l.tax_rate || 0,
    })),
  };
  try {
    const res = await Api.salesOrders.create(payload, confirmNow ? {confirm:'true'} : {});
    showToast(`SO ${res.so_no} ${confirmNow?'di-confirm':'tersimpan'}`, 'success');
    closeSOModal();
    renderSalesOrderPage();
  } catch (e) {
    showToast('Gagal: ' + e.message, 'error');
  }
}

async function confirmSalesOrder(id) {
  if (!confirm('Confirm SO ini? Setelah confirm, line tidak bisa diubah.')) return;
  try {
    await Api.salesOrders.confirm(id);
    showToast('SO di-confirm', 'success');
    renderSalesOrderPage();
  } catch (e) { showToast('Gagal: ' + e.message, 'error'); }
}

async function cancelSalesOrder(id) {
  const reason = prompt('Alasan cancel?');
  if (!reason) return;
  try {
    await Api.salesOrders.cancel(id, {reason});
    showToast('SO di-cancel', 'warning');
    renderSalesOrderPage();
  } catch (e) { showToast('Gagal: ' + e.message, 'error'); }
}

async function showSalesOrderDetail(id) {
  try {
    const so = await Api.salesOrders.get(id);
    const custName = OrdersState.customers.find(c => c.id === so.customer_id)?.name || so.customer_id;
    const itemMap  = Object.fromEntries(OrdersState.items.map(i => [i.id, i]));
    const whMap    = Object.fromEntries(OrdersState.warehouses.map(w => [w.id, w.name]));
    const linesHtml = (so.lines || []).map((ln, idx) => `
      <tr>
        <td>${idx+1}</td>
        <td>${_ordEsc(itemMap[ln.item_id]?.name || ln.item_id)}</td>
        <td>${_ordEsc(whMap[ln.warehouse_id] || '-')}</td>
        <td style="text-align:right">${ln.qty_ordered}</td>
        <td style="text-align:right">${ln.qty_delivered || 0}</td>
        <td style="text-align:right">${ln.qty_invoiced || 0}</td>
        <td style="text-align:right">${_ordFmtRp(ln.unit_price)}</td>
        <td style="text-align:right">${_ordFmtRp(ln.line_total || (ln.qty_ordered * ln.unit_price))}</td>
      </tr>`).join('');
    const html = `
    <div class="modal-backdrop" id="soDetailBackdrop" onclick="if(event.target===this)this.remove()">
      <div class="modal-content" style="max-width:900px">
        <div class="modal-header">
          <h3>${_ordEsc(so.so_no)} — ${_ordStatusBadge(so.status)}</h3>
          <button class="modal-close" onclick="document.getElementById('soDetailBackdrop').remove()">×</button>
        </div>
        <div class="modal-body">
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px">
            <div><strong>Customer:</strong> ${_ordEsc(custName)}</div>
            <div><strong>Tanggal:</strong> ${so.order_date}</div>
            <div><strong>Expected Delivery:</strong> ${so.expected_delivery_date || '-'}</div>
            <div><strong>Total:</strong> ${_ordFmtRp(so.total)}</div>
          </div>
          <table class="data-table">
            <thead><tr><th>#</th><th>Item</th><th>WH</th><th>Qty Ordered</th><th>Delivered</th><th>Invoiced</th><th>Harga</th><th>Subtotal</th></tr></thead>
            <tbody>${linesHtml}</tbody>
          </table>
          ${so.notes ? `<p style="margin-top:12px"><strong>Notes:</strong> ${_ordEsc(so.notes)}</p>` : ''}
        </div>
      </div>
    </div>`;
    document.body.insertAdjacentHTML('beforeend', html);
  } catch (e) {
    showToast('Gagal load detail: ' + e.message, 'error');
  }
}

// Sprint F2: navigate to DO form page instead of opening modal
function createDOFromSO(soId) {
  if (typeof showDOForm === 'function') showDOForm(soId);
  else showToast('fulfillment.js belum dimuat', 'error');
}

// ════════════════════════════════════════════════════════════════
// PURCHASE ORDERS
// ════════════════════════════════════════════════════════════════

async function renderPurchaseOrderPage() {
  await _ordEnsureMasters();
  const filterStatus = document.getElementById('poFilterStatus')?.value || '';
  const filterSup    = document.getElementById('poFilterSupplier')?.value || '';
  try {
    const pos = await Api.purchaseOrders.list({
      status: filterStatus || undefined,
      supplier_id: filterSup || undefined,
      limit: 200,
    });
    OrdersState.pos = Array.isArray(pos) ? pos : [];
  } catch (e) {
    showToast('Gagal load Purchase Order: ' + e.message, 'error');
    OrdersState.pos = [];
  }

  const supSel = document.getElementById('poFilterSupplier');
  if (supSel) {
    const cur = supSel.value;
    supSel.innerHTML = '<option value="">Semua Supplier</option>' +
      OrdersState.suppliers.map(s => `<option value="${s.id}" ${s.id===cur?'selected':''}>${_ordEsc(s.name)}</option>`).join('');
  }

  const wrap = document.getElementById('poTableWrap');
  if (!wrap) return;
  if (!OrdersState.pos.length) {
    wrap.innerHTML = `<div style="padding:48px;text-align:center;color:#6b7280">Belum ada Purchase Order. Klik <strong>"Buat PO"</strong>.</div>`;
    return;
  }

  const supMap = Object.fromEntries(OrdersState.suppliers.map(s => [s.id, s.name]));
  wrap.innerHTML = `
    <table class="data-table">
      <thead><tr>
        <th>No PO</th><th>Tanggal</th><th>Supplier</th>
        <th style="text-align:right">Total</th>
        <th>Status</th><th style="text-align:center">Aksi</th>
      </tr></thead>
      <tbody>
      ${OrdersState.pos.map(po => `
        <tr>
          <td><code>${_ordEsc(po.po_no)}</code></td>
          <td>${po.order_date || '-'}</td>
          <td>${_ordEsc(supMap[po.supplier_id] || po.supplier_id)}</td>
          <td style="text-align:right"><strong>${_ordFmtRp(po.total)}</strong></td>
          <td>${_ordStatusBadge(po.status)}</td>
          <td style="text-align:center;white-space:nowrap">
            <button class="btn btn-sm btn-outline" onclick="showPurchaseOrderDetail('${po.id}')">Detail</button>
            ${po.status === 'draft' ? `<button class="btn btn-sm btn-primary" style="margin-left:4px" onclick="confirmPurchaseOrder('${po.id}')">Confirm</button>` : ''}
            ${(po.status==='confirmed' || po.status==='partially_received') ? `<button class="btn btn-sm btn-success" style="margin-left:4px" onclick="createGRFromPO('${po.id}')">Buat GR</button>` : ''}
            ${(po.status==='draft' || po.status==='confirmed' || po.status==='partially_received') ? `<button class="btn btn-sm btn-danger" style="margin-left:4px" onclick="cancelPurchaseOrder('${po.id}')">Cancel</button>` : ''}
          </td>
        </tr>`).join('')}
      </tbody>
    </table>`;
}

let _poLines = [];

function showPurchaseOrderModal() {
  _poLines = [{ item_id: '', warehouse_id: '', qty_ordered: 1, unit_price: 0 }];
  const itemOpts = OrdersState.items.map(i => `<option value="${i.id}" data-price="${i.cost_price || 0}">${_ordEsc(i.name)} (${_ordEsc(i.sku || '-')})</option>`).join('');
  const whOpts   = OrdersState.warehouses.map(w => `<option value="${w.id}">${_ordEsc(w.name)}</option>`).join('');
  const supOpts  = OrdersState.suppliers.map(s => `<option value="${s.id}">${_ordEsc(s.name)}</option>`).join('');

  const html = `
  <div class="modal-backdrop" id="poModalBackdrop" onclick="if(event.target===this)closePOModal()">
    <div class="modal-content" style="max-width:900px">
      <div class="modal-header">
        <h3>Buat Purchase Order</h3>
        <button class="modal-close" onclick="closePOModal()">×</button>
      </div>
      <div class="modal-body">
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:16px">
          <div><label>Tanggal Order</label><input type="date" id="poDate" value="${_ordToday()}" class="form-control" /></div>
          <div><label>Expected Receipt</label><input type="date" id="poExpDate" class="form-control" /></div>
          <div><label>Supplier</label>
            <select id="poSupplier" class="form-control"><option value="">— pilih —</option>${supOpts}</select>
          </div>
        </div>
        <h4 style="margin:12px 0 8px">Items</h4>
        <table class="data-table">
          <thead><tr>
            <th style="width:30%">Item</th><th>Warehouse</th>
            <th style="width:80px">Qty</th><th style="width:120px">Harga</th>
            <th style="width:120px">Subtotal</th><th></th>
          </tr></thead>
          <tbody id="poLinesBody"></tbody>
        </table>
        <button class="btn btn-sm btn-outline" onclick="_poAddLine()" style="margin-top:8px">+ Tambah baris</button>
        <div style="margin-top:16px"><label>Notes</label><textarea id="poNotes" class="form-control" rows="2"></textarea></div>
        <div style="margin-top:16px;text-align:right;font-size:16px"><strong>Total: <span id="poTotalDisplay">Rp 0</span></strong></div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-outline" onclick="closePOModal()">Tutup</button>
        <button class="btn btn-primary" onclick="savePurchaseOrder(false)">Simpan Draft</button>
        <button class="btn btn-success" onclick="savePurchaseOrder(true)">Simpan + Confirm</button>
      </div>
    </div>
  </div>`;
  document.body.insertAdjacentHTML('beforeend', html);
  _poRenderLines();
}

function _poRenderLines() {
  const itemOpts = OrdersState.items.map(i => `<option value="${i.id}" data-price="${i.cost_price || 0}">${_ordEsc(i.name)}</option>`).join('');
  const whOpts   = OrdersState.warehouses.map(w => `<option value="${w.id}">${_ordEsc(w.name)}</option>`).join('');
  const body = document.getElementById('poLinesBody');
  if (!body) return;
  body.innerHTML = _poLines.map((ln, idx) => `
    <tr>
      <td><select class="form-control" onchange="_poUpdateLine(${idx},'item_id',this.value); _poMaybeFillPrice(${idx}, this)"><option value="">— pilih —</option>${itemOpts.replace(`value="${ln.item_id}"`, `value="${ln.item_id}" selected`)}</select></td>
      <td><select class="form-control" onchange="_poUpdateLine(${idx},'warehouse_id',this.value)"><option value="">— pilih —</option>${whOpts.replace(`value="${ln.warehouse_id}"`, `value="${ln.warehouse_id}" selected`)}</select></td>
      <td><input type="number" step="0.01" value="${ln.qty_ordered}" class="form-control" onchange="_poUpdateLine(${idx},'qty_ordered',parseFloat(this.value)||0)" /></td>
      <td><input type="number" step="100" value="${ln.unit_price}" class="form-control" onchange="_poUpdateLine(${idx},'unit_price',parseFloat(this.value)||0)" /></td>
      <td style="text-align:right">${_ordFmtRp((ln.qty_ordered||0) * (ln.unit_price||0))}</td>
      <td><button class="btn btn-sm btn-danger" onclick="_poRemoveLine(${idx})">×</button></td>
    </tr>`).join('');
  _poUpdateTotal();
}

function _poMaybeFillPrice(idx, sel) {
  const opt = sel.options[sel.selectedIndex];
  const price = parseFloat(opt?.dataset?.price || 0);
  if (price > 0 && (!_poLines[idx].unit_price || _poLines[idx].unit_price === 0)) {
    _poLines[idx].unit_price = price;
    _poRenderLines();
  }
}

function _poUpdateLine(idx, field, value) { _poLines[idx][field] = value; _poUpdateTotal(); }
function _poAddLine() { _poLines.push({ item_id:'', warehouse_id:'', qty_ordered:1, unit_price:0 }); _poRenderLines(); }
function _poRemoveLine(idx) { _poLines.splice(idx,1); if (!_poLines.length) _poAddLine(); else _poRenderLines(); }
function _poUpdateTotal() {
  const total = _poLines.reduce((s,l) => s + (l.qty_ordered||0) * (l.unit_price||0), 0);
  const el = document.getElementById('poTotalDisplay');
  if (el) el.textContent = _ordFmtRp(total);
}

function closePOModal() { document.getElementById('poModalBackdrop')?.remove(); }

async function savePurchaseOrder(confirmNow) {
  const supplier_id = document.getElementById('poSupplier').value;
  const order_date  = document.getElementById('poDate').value;
  const exp_date    = document.getElementById('poExpDate').value;
  const notes       = document.getElementById('poNotes').value;
  if (!supplier_id) { showToast('Supplier wajib dipilih', 'error'); return; }
  if (!order_date)  { showToast('Tanggal wajib diisi', 'error'); return; }
  const valid = _poLines.filter(l => l.item_id && l.warehouse_id && l.qty_ordered > 0);
  if (!valid.length) { showToast('Minimal 1 baris item valid', 'error'); return; }

  const payload = {
    order_date, supplier_id, notes: notes || null,
    expected_receipt_date: exp_date || null,
    lines: valid.map(l => ({
      item_id: l.item_id, warehouse_id: l.warehouse_id,
      qty_ordered: l.qty_ordered, unit_price: l.unit_price,
    })),
  };
  try {
    const res = await Api.purchaseOrders.create(payload, confirmNow ? {confirm:'true'} : {});
    showToast(`PO ${res.po_no} ${confirmNow?'di-confirm':'tersimpan'}`, 'success');
    closePOModal();
    renderPurchaseOrderPage();
  } catch (e) {
    showToast('Gagal: ' + e.message, 'error');
  }
}

async function confirmPurchaseOrder(id) {
  if (!confirm('Confirm PO ini?')) return;
  try {
    await Api.purchaseOrders.confirm(id);
    showToast('PO di-confirm', 'success');
    renderPurchaseOrderPage();
  } catch (e) { showToast('Gagal: ' + e.message, 'error'); }
}

async function cancelPurchaseOrder(id) {
  const reason = prompt('Alasan cancel?');
  if (!reason) return;
  try {
    await Api.purchaseOrders.cancel(id, {reason});
    showToast('PO di-cancel', 'warning');
    renderPurchaseOrderPage();
  } catch (e) { showToast('Gagal: ' + e.message, 'error'); }
}

async function showPurchaseOrderDetail(id) {
  try {
    const po = await Api.purchaseOrders.get(id);
    const supName = OrdersState.suppliers.find(s => s.id === po.supplier_id)?.name || po.supplier_id;
    const itemMap = Object.fromEntries(OrdersState.items.map(i => [i.id, i]));
    const whMap   = Object.fromEntries(OrdersState.warehouses.map(w => [w.id, w.name]));
    const linesHtml = (po.lines || []).map((ln, idx) => `
      <tr>
        <td>${idx+1}</td>
        <td>${_ordEsc(itemMap[ln.item_id]?.name || ln.item_id)}</td>
        <td>${_ordEsc(whMap[ln.warehouse_id] || '-')}</td>
        <td style="text-align:right">${ln.qty_ordered}</td>
        <td style="text-align:right">${ln.qty_received || 0}</td>
        <td style="text-align:right">${ln.qty_invoiced || 0}</td>
        <td style="text-align:right">${_ordFmtRp(ln.unit_price)}</td>
        <td style="text-align:right">${_ordFmtRp(ln.line_total || (ln.qty_ordered * ln.unit_price))}</td>
      </tr>`).join('');
    const html = `
    <div class="modal-backdrop" id="poDetailBackdrop" onclick="if(event.target===this)this.remove()">
      <div class="modal-content" style="max-width:900px">
        <div class="modal-header">
          <h3>${_ordEsc(po.po_no)} — ${_ordStatusBadge(po.status)}</h3>
          <button class="modal-close" onclick="document.getElementById('poDetailBackdrop').remove()">×</button>
        </div>
        <div class="modal-body">
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px">
            <div><strong>Supplier:</strong> ${_ordEsc(supName)}</div>
            <div><strong>Tanggal:</strong> ${po.order_date}</div>
            <div><strong>Expected Receipt:</strong> ${po.expected_receipt_date || '-'}</div>
            <div><strong>Total:</strong> ${_ordFmtRp(po.total)}</div>
          </div>
          <table class="data-table">
            <thead><tr><th>#</th><th>Item</th><th>WH</th><th>Qty Ordered</th><th>Received</th><th>Invoiced</th><th>Harga</th><th>Subtotal</th></tr></thead>
            <tbody>${linesHtml}</tbody>
          </table>
          ${po.notes ? `<p style="margin-top:12px"><strong>Notes:</strong> ${_ordEsc(po.notes)}</p>` : ''}
        </div>
      </div>
    </div>`;
    document.body.insertAdjacentHTML('beforeend', html);
  } catch (e) {
    showToast('Gagal load detail: ' + e.message, 'error');
  }
}

function createGRFromPO(poId) {
  if (typeof showGRForm === 'function') showGRForm(poId);
  else showToast('fulfillment.js belum dimuat', 'error');
}


// ════════════════════════════════════════════════════════════════
// Sprint F2: Form-page pattern for SO + PO (replaces modals)
// ════════════════════════════════════════════════════════════════

// ── Sales Order ─────────────────────────────────────────
function showSOForm() {
  _soLines = [{ item_id: '', warehouse_id: '', qty_ordered: 1, unit_price: 0, tax_rate: 0 }];
  navigateTo('so-form');
}

function exitSOForm() {
  const hasData = _soLines.some(l => l.item_id || l.unit_price > 0);
  if (hasData && !confirm('Perubahan belum disimpan. Yakin keluar?')) return;
  _soLines = [];
  navigateTo('sales-orders');
}

async function renderSOForm() {
  await _ordEnsureMasters();
  const itemOpts = OrdersState.items.map(i => `<option value="${i.id}" data-price="${i.sale_price || 0}">${_ordEsc(i.name)} (${_ordEsc(i.sku || '-')})</option>`).join('');
  const whOpts   = OrdersState.warehouses.map(w => `<option value="${w.id}">${_ordEsc(w.name)}</option>`).join('');
  const custOpts = OrdersState.customers.map(c => `<option value="${c.id}">${_ordEsc(c.name)}</option>`).join('');

  document.getElementById('soFormTitle').textContent = 'Buat Sales Order';
  const body = document.getElementById('soFormBody');
  if (!body) return;
  body.innerHTML = `
    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:16px">
      <div><label>Tanggal Order</label><input type="date" id="soDate" value="${_ordToday()}" class="form-control"></div>
      <div><label>Expected Delivery</label><input type="date" id="soExpDate" class="form-control"></div>
      <div><label>Customer</label>
        <select id="soCustomer" class="form-control"><option value="">— pilih —</option>${custOpts}</select>
      </div>
    </div>
    <h4>Items</h4>
    <table class="data-table" id="soLinesTable">
      <thead><tr>
        <th style="width:30%">Item</th><th>Warehouse</th>
        <th style="width:80px">Qty</th><th style="width:120px">Harga</th>
        <th style="width:60px">Tax %</th><th style="width:120px">Subtotal</th><th></th>
      </tr></thead>
      <tbody id="soLinesBody"></tbody>
    </table>
    <button class="btn btn-sm btn-outline" onclick="_soAddLine()" style="margin-top:8px">+ Tambah baris</button>
    <div style="margin-top:16px"><label>Notes</label><textarea id="soNotes" class="form-control" rows="2"></textarea></div>
    <div style="margin-top:16px;text-align:right;font-size:16px"><strong>Total: <span id="soTotalDisplay">Rp 0</span></strong></div>
  `;
  _soRenderLines(itemOpts, whOpts);
  if (typeof feather !== 'undefined') feather.replace();
}

async function submitSOForm(confirmNow) {
  const customer_id = document.getElementById('soCustomer').value;
  const order_date  = document.getElementById('soDate').value;
  const exp_date    = document.getElementById('soExpDate').value;
  const notes       = document.getElementById('soNotes').value;
  if (!customer_id) { showToast('Customer wajib dipilih', 'error'); return; }
  if (!order_date)  { showToast('Tanggal wajib diisi', 'error'); return; }
  const valid = _soLines.filter(l => l.item_id && l.warehouse_id && l.qty_ordered > 0);
  if (!valid.length) { showToast('Minimal 1 baris item valid', 'error'); return; }

  const payload = {
    order_date, customer_id, notes: notes || null,
    expected_delivery_date: exp_date || null,
    lines: valid.map(l => ({
      item_id: l.item_id, warehouse_id: l.warehouse_id,
      qty_ordered: l.qty_ordered, unit_price: l.unit_price, tax_rate: l.tax_rate || 0,
    })),
  };
  try {
    const res = await Api.salesOrders.create(payload, confirmNow ? {confirm:'true'} : {});
    showToast(`SO ${res.so_no} ${confirmNow?'di-confirm':'tersimpan'}`, 'success');
    _soLines = [];
    navigateTo('sales-orders');
  } catch (e) { showToast('Gagal: ' + e.message, 'error'); }
}

// ── Purchase Order ──────────────────────────────────────
function showPOForm() {
  _poLines = [{ item_id: '', warehouse_id: '', qty_ordered: 1, unit_price: 0 }];
  navigateTo('po-form');
}

function exitPOForm() {
  const hasData = _poLines.some(l => l.item_id || l.unit_price > 0);
  if (hasData && !confirm('Perubahan belum disimpan. Yakin keluar?')) return;
  _poLines = [];
  navigateTo('purchase-orders');
}

async function renderPOForm() {
  await _ordEnsureMasters();
  const supOpts  = OrdersState.suppliers.map(s => `<option value="${s.id}">${_ordEsc(s.name)}</option>`).join('');
  document.getElementById('poFormTitle').textContent = 'Buat Purchase Order';
  const body = document.getElementById('poFormBody');
  if (!body) return;
  body.innerHTML = `
    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:16px">
      <div><label>Tanggal Order</label><input type="date" id="poDate" value="${_ordToday()}" class="form-control"></div>
      <div><label>Expected Receipt</label><input type="date" id="poExpDate" class="form-control"></div>
      <div><label>Supplier</label>
        <select id="poSupplier" class="form-control"><option value="">— pilih —</option>${supOpts}</select>
      </div>
    </div>
    <h4>Items</h4>
    <table class="data-table">
      <thead><tr>
        <th style="width:30%">Item</th><th>Warehouse</th>
        <th style="width:80px">Qty</th><th style="width:120px">Harga</th>
        <th style="width:120px">Subtotal</th><th></th>
      </tr></thead>
      <tbody id="poLinesBody"></tbody>
    </table>
    <button class="btn btn-sm btn-outline" onclick="_poAddLine()" style="margin-top:8px">+ Tambah baris</button>
    <div style="margin-top:16px"><label>Notes</label><textarea id="poNotes" class="form-control" rows="2"></textarea></div>
    <div style="margin-top:16px;text-align:right;font-size:16px"><strong>Total: <span id="poTotalDisplay">Rp 0</span></strong></div>
  `;
  _poRenderLines();
  if (typeof feather !== 'undefined') feather.replace();
}

async function submitPOForm(confirmNow) {
  const supplier_id = document.getElementById('poSupplier').value;
  const order_date  = document.getElementById('poDate').value;
  const exp_date    = document.getElementById('poExpDate').value;
  const notes       = document.getElementById('poNotes').value;
  if (!supplier_id) { showToast('Supplier wajib dipilih', 'error'); return; }
  if (!order_date)  { showToast('Tanggal wajib diisi', 'error'); return; }
  const valid = _poLines.filter(l => l.item_id && l.warehouse_id && l.qty_ordered > 0);
  if (!valid.length) { showToast('Minimal 1 baris item valid', 'error'); return; }

  const payload = {
    order_date, supplier_id, notes: notes || null,
    expected_receipt_date: exp_date || null,
    lines: valid.map(l => ({
      item_id: l.item_id, warehouse_id: l.warehouse_id,
      qty_ordered: l.qty_ordered, unit_price: l.unit_price,
    })),
  };
  try {
    const res = await Api.purchaseOrders.create(payload, confirmNow ? {confirm:'true'} : {});
    showToast(`PO ${res.po_no} ${confirmNow?'di-confirm':'tersimpan'}`, 'success');
    _poLines = [];
    navigateTo('purchase-orders');
  } catch (e) { showToast('Gagal: ' + e.message, 'error'); }
}

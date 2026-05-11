/**
 * FULFILLMENT.JS — Delivery Order, Goods Receipt, RMA UI
 *
 * Pages:
 *   - page-delivery-orders  → list DO + post/void + create-from-SO
 *   - page-goods-receipts   → list GR + post/void + create-from-PO
 *   - page-rmas             → list RMA + create-from-DO/GR + post/void
 *
 * Each is a posting doc that triggers stock movement + journal on post.
 */

const FFState = { dos: [], grs: [], rmas: [] };

const _ffFmtRp = (n) => 'Rp ' + Math.round(n || 0).toLocaleString('id-ID');
const _ffEsc   = (s) => String(s ?? '').replace(/[<>&"]/g, c => ({'<':'&lt;','>':'&gt;','&':'&amp;','"':'&quot;'}[c]));
const _ffToday = () => new Date().toISOString().slice(0,10);

function _ffStatusBadge(status) {
  const map = {
    draft:  ['#6b7280', 'Draft'],
    posted: ['#10b981', 'Posted'],
    void:   ['#ef4444', 'Void'],
  };
  const [c, label] = map[status] || ['#6b7280', status || '-'];
  return `<span style="display:inline-block;padding:2px 8px;background:${c}20;color:${c};border-radius:6px;font-size:11px;font-weight:600">${label}</span>`;
}

// ════════════════════════════════════════════════════════════════
// DELIVERY ORDERS
// ════════════════════════════════════════════════════════════════

async function renderDeliveryOrderPage() {
  if (typeof _ordEnsureMasters === 'function') await _ordEnsureMasters();
  const status = document.getElementById('doFilterStatus')?.value || '';
  try {
    const dos = await Api.deliveryOrders.list({ status: status || undefined, limit: 200 });
    FFState.dos = Array.isArray(dos) ? dos : [];
  } catch (e) {
    showToast('Gagal load Delivery Order: ' + e.message, 'error');
    FFState.dos = [];
  }
  const wrap = document.getElementById('doTableWrap');
  if (!wrap) return;
  if (!FFState.dos.length) {
    wrap.innerHTML = `<div style="padding:48px;text-align:center;color:#6b7280">Belum ada Delivery Order. Buat dari Sales Order (sidebar Sales → Sales Order → "Buat DO").</div>`;
    return;
  }
  const soMap = Object.fromEntries((OrdersState?.sos || []).map(s => [s.id, s.so_no]));
  const whMap = Object.fromEntries((OrdersState?.warehouses || []).map(w => [w.id, w.name]));
  wrap.innerHTML = `
    <table class="data-table">
      <thead><tr>
        <th>No DO</th><th>Tanggal</th><th>SO</th><th>Warehouse</th>
        <th style="text-align:right">Total Lines</th>
        <th>Status</th><th style="text-align:center">Aksi</th>
      </tr></thead>
      <tbody>
      ${FFState.dos.map(d => `
        <tr>
          <td><code>${_ffEsc(d.do_no)}</code></td>
          <td>${d.delivery_date || '-'}</td>
          <td>${_ffEsc(soMap[d.so_id] || d.so_id?.slice(0,8))}</td>
          <td>${_ffEsc(whMap[d.warehouse_id] || '-')}</td>
          <td style="text-align:right">${(d.lines || []).length}</td>
          <td>${_ffStatusBadge(d.status)}</td>
          <td style="text-align:center;white-space:nowrap">
            <button class="btn btn-sm btn-outline" onclick="showDeliveryOrderDetail('${d.id}')">Detail</button>
            ${d.status === 'draft'  ? `<button class="btn btn-sm btn-primary" style="margin-left:4px" onclick="postDeliveryOrder('${d.id}')">Post</button>` : ''}
            ${d.status === 'posted' ? `<button class="btn btn-sm btn-success" style="margin-left:4px" onclick="createRMAFromDO('${d.id}')">Buat RMA</button>` : ''}
            ${d.status !== 'void'   ? `<button class="btn btn-sm btn-danger"  style="margin-left:4px" onclick="voidDeliveryOrder('${d.id}')">Void</button>` : ''}
          </td>
        </tr>`).join('')}
      </tbody>
    </table>`;
}

// Create DO from a confirmed SO
async function showCreateDOModal(soId) {
  try {
    const so = await Api.salesOrders.get(soId);
    if (!['confirmed','partially_delivered'].includes(so.status)) {
      showToast('SO harus confirmed/partially_delivered dulu', 'error');
      return;
    }
    const itemMap = Object.fromEntries((OrdersState?.items || []).map(i => [i.id, i.name]));
    const linesRows = (so.lines || []).map((ln, idx) => {
      const remaining = (parseFloat(ln.qty_ordered) || 0) - (parseFloat(ln.qty_delivered) || 0);
      return `
        <tr>
          <td><label><input type="checkbox" class="do-line-cb" data-idx="${idx}" data-line-id="${ln.id}" data-max="${remaining}" ${remaining > 0 ? 'checked' : 'disabled'}> ${_ffEsc(itemMap[ln.item_id] || ln.item_id?.slice(0,8))}</label></td>
          <td style="text-align:right">${ln.qty_ordered}</td>
          <td style="text-align:right">${ln.qty_delivered || 0}</td>
          <td style="text-align:right;color:#f59e0b"><strong>${remaining}</strong></td>
          <td><input type="number" step="0.01" class="do-line-qty form-control" data-idx="${idx}" value="${remaining}" ${remaining <= 0 ? 'disabled' : ''} style="width:90px"></td>
        </tr>`;
    }).join('');
    const html = `
    <div class="modal-backdrop" id="createDOBackdrop" onclick="if(event.target===this)this.remove()">
      <div class="modal-content" style="max-width:760px">
        <div class="modal-header">
          <h3>Buat Delivery Order dari ${_ffEsc(so.so_no)}</h3>
          <button class="modal-close" onclick="document.getElementById('createDOBackdrop').remove()">×</button>
        </div>
        <div class="modal-body">
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px">
            <div><label>Tanggal Delivery</label><input type="date" id="doDate" value="${_ffToday()}" class="form-control"></div>
            <div><label>Warehouse</label>
              <select id="doWarehouse" class="form-control">${(OrdersState?.warehouses || []).map(w => `<option value="${w.id}">${_ffEsc(w.name)}</option>`).join('')}</select>
            </div>
          </div>
          <table class="data-table">
            <thead><tr><th>Item (centang line yang dikirim)</th><th>Ordered</th><th>Delivered</th><th>Remaining</th><th>Qty Kirim</th></tr></thead>
            <tbody>${linesRows}</tbody>
          </table>
          <div style="margin-top:12px"><label>Notes</label><textarea id="doNotes" class="form-control" rows="2"></textarea></div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-outline" onclick="document.getElementById('createDOBackdrop').remove()">Tutup</button>
          <button class="btn btn-primary" onclick="saveDeliveryOrder('${so.id}', false)">Simpan Draft</button>
          <button class="btn btn-success" onclick="saveDeliveryOrder('${so.id}', true)">Simpan + Post</button>
        </div>
      </div>
    </div>`;
    document.body.insertAdjacentHTML('beforeend', html);
    // pre-select first warehouse from SO line
    const firstWh = so.lines?.[0]?.warehouse_id;
    if (firstWh) document.getElementById('doWarehouse').value = firstWh;
  } catch (e) {
    showToast('Gagal load SO: ' + e.message, 'error');
  }
}

async function saveDeliveryOrder(soId, postNow) {
  const delivery_date = document.getElementById('doDate').value;
  const warehouse_id  = document.getElementById('doWarehouse').value;
  const notes         = document.getElementById('doNotes').value;
  if (!delivery_date || !warehouse_id) { showToast('Tanggal & warehouse wajib', 'error'); return; }
  const lines = [];
  document.querySelectorAll('.do-line-cb').forEach(cb => {
    if (cb.checked) {
      const qty = parseFloat(document.querySelector(`.do-line-qty[data-idx="${cb.dataset.idx}"]`).value) || 0;
      const max = parseFloat(cb.dataset.max);
      if (qty > 0 && qty <= max) {
        lines.push({ so_line_id: cb.dataset.lineId, qty_delivered: qty });
      }
    }
  });
  if (!lines.length) { showToast('Pilih minimal 1 line dengan qty > 0', 'error'); return; }
  try {
    const res = await Api.deliveryOrders.create({
      delivery_date, so_id: soId, warehouse_id, notes: notes || null, lines,
    }, postNow ? {post_now:'true'} : {});
    showToast(`DO ${res.do_no} ${postNow?'di-post':'tersimpan'}`, 'success');
    document.getElementById('createDOBackdrop')?.remove();
    if (typeof renderSalesOrderPage === 'function' && AppState.currentPage === 'sales-orders') renderSalesOrderPage();
    if (AppState.currentPage === 'delivery-orders') renderDeliveryOrderPage();
  } catch (e) { showToast('Gagal: ' + e.message, 'error'); }
}

async function postDeliveryOrder(id) {
  if (!confirm('Post DO ini? Stock akan keluar + journal Dr COGS / Cr Inventory.')) return;
  try {
    await Api.deliveryOrders.post(id);
    showToast('DO di-post', 'success');
    renderDeliveryOrderPage();
  } catch (e) { showToast('Gagal post: ' + e.message, 'error'); }
}

async function voidDeliveryOrder(id) {
  const reason = prompt('Alasan void?');
  if (!reason) return;
  try {
    await Api.deliveryOrders.void(id, {reason});
    showToast('DO di-void', 'warning');
    renderDeliveryOrderPage();
  } catch (e) { showToast('Gagal: ' + e.message, 'error'); }
}

async function showDeliveryOrderDetail(id) {
  try {
    const d = await Api.deliveryOrders.get(id);
    const itemMap = Object.fromEntries((OrdersState?.items || []).map(i => [i.id, i.name]));
    const linesHtml = (d.lines || []).map((ln, idx) => `
      <tr>
        <td>${idx+1}</td>
        <td>${_ffEsc(itemMap[ln.item_id] || ln.item_id?.slice(0,8))}</td>
        <td style="text-align:right">${ln.qty_delivered}</td>
        <td style="text-align:right">${ln.unit_cost ? _ffFmtRp(ln.unit_cost) : '-'}</td>
      </tr>`).join('');
    const html = `
    <div class="modal-backdrop" id="doDetailBackdrop" onclick="if(event.target===this)this.remove()">
      <div class="modal-content" style="max-width:760px">
        <div class="modal-header">
          <h3>${_ffEsc(d.do_no)} — ${_ffStatusBadge(d.status)}</h3>
          <button class="modal-close" onclick="document.getElementById('doDetailBackdrop').remove()">×</button>
        </div>
        <div class="modal-body">
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px">
            <div><strong>Delivery Date:</strong> ${d.delivery_date}</div>
            <div><strong>SO ID:</strong> <code>${_ffEsc(d.so_id?.slice(0,8))}</code></div>
            <div><strong>Journal Entry:</strong> ${d.journal_entry_id ? `<code>${_ffEsc(d.journal_entry_id.slice(0,8))}</code>` : '-'}</div>
            <div><strong>Posted At:</strong> ${d.posted_at ? new Date(d.posted_at).toLocaleString() : '-'}</div>
          </div>
          <table class="data-table">
            <thead><tr><th>#</th><th>Item</th><th>Qty</th><th>Unit Cost</th></tr></thead>
            <tbody>${linesHtml}</tbody>
          </table>
          ${d.void_reason ? `<p style="margin-top:12px;color:#ef4444"><strong>Void reason:</strong> ${_ffEsc(d.void_reason)}</p>` : ''}
        </div>
      </div>
    </div>`;
    document.body.insertAdjacentHTML('beforeend', html);
  } catch (e) { showToast('Gagal: ' + e.message, 'error'); }
}

// ════════════════════════════════════════════════════════════════
// GOODS RECEIPTS
// ════════════════════════════════════════════════════════════════

async function renderGoodsReceiptPage() {
  if (typeof _ordEnsureMasters === 'function') await _ordEnsureMasters();
  const status = document.getElementById('grFilterStatus')?.value || '';
  try {
    const grs = await Api.goodsReceipts.list({ status: status || undefined, limit: 200 });
    FFState.grs = Array.isArray(grs) ? grs : [];
  } catch (e) {
    showToast('Gagal load Goods Receipt: ' + e.message, 'error');
    FFState.grs = [];
  }
  const wrap = document.getElementById('grTableWrap');
  if (!wrap) return;
  if (!FFState.grs.length) {
    wrap.innerHTML = `<div style="padding:48px;text-align:center;color:#6b7280">Belum ada Goods Receipt. Buat dari Purchase Order (sidebar Purchase → Purchase Order → "Buat GR").</div>`;
    return;
  }
  const poMap = Object.fromEntries((OrdersState?.pos || []).map(p => [p.id, p.po_no]));
  const whMap = Object.fromEntries((OrdersState?.warehouses || []).map(w => [w.id, w.name]));
  wrap.innerHTML = `
    <table class="data-table">
      <thead><tr>
        <th>No GR</th><th>Tanggal</th><th>PO</th><th>Warehouse</th>
        <th style="text-align:right">Total Lines</th>
        <th>Status</th><th style="text-align:center">Aksi</th>
      </tr></thead>
      <tbody>
      ${FFState.grs.map(g => `
        <tr>
          <td><code>${_ffEsc(g.gr_no)}</code></td>
          <td>${g.receipt_date || '-'}</td>
          <td>${_ffEsc(poMap[g.po_id] || g.po_id?.slice(0,8))}</td>
          <td>${_ffEsc(whMap[g.warehouse_id] || '-')}</td>
          <td style="text-align:right">${(g.lines || []).length}</td>
          <td>${_ffStatusBadge(g.status)}</td>
          <td style="text-align:center;white-space:nowrap">
            <button class="btn btn-sm btn-outline" onclick="showGoodsReceiptDetail('${g.id}')">Detail</button>
            ${g.status === 'draft'  ? `<button class="btn btn-sm btn-primary" style="margin-left:4px" onclick="postGoodsReceipt('${g.id}')">Post</button>` : ''}
            ${g.status === 'posted' ? `<button class="btn btn-sm btn-success" style="margin-left:4px" onclick="createRMAFromGR('${g.id}')">Buat RMA</button>` : ''}
            ${g.status !== 'void'   ? `<button class="btn btn-sm btn-danger"  style="margin-left:4px" onclick="voidGoodsReceipt('${g.id}')">Void</button>` : ''}
          </td>
        </tr>`).join('')}
      </tbody>
    </table>`;
}

async function showCreateGRModal(poId) {
  try {
    const po = await Api.purchaseOrders.get(poId);
    if (!['confirmed','partially_received'].includes(po.status)) {
      showToast('PO harus confirmed/partially_received dulu', 'error');
      return;
    }
    const itemMap = Object.fromEntries((OrdersState?.items || []).map(i => [i.id, i.name]));
    const linesRows = (po.lines || []).map((ln, idx) => {
      const remaining = (parseFloat(ln.qty_ordered) || 0) - (parseFloat(ln.qty_received) || 0);
      return `
        <tr>
          <td><label><input type="checkbox" class="gr-line-cb" data-idx="${idx}" data-line-id="${ln.id}" data-max="${remaining}" data-price="${ln.unit_price}" ${remaining > 0 ? 'checked' : 'disabled'}> ${_ffEsc(itemMap[ln.item_id] || ln.item_id?.slice(0,8))}</label></td>
          <td style="text-align:right">${ln.qty_ordered}</td>
          <td style="text-align:right">${ln.qty_received || 0}</td>
          <td style="text-align:right;color:#f59e0b"><strong>${remaining}</strong></td>
          <td><input type="number" step="0.01" class="gr-line-qty form-control" data-idx="${idx}" value="${remaining}" ${remaining <= 0 ? 'disabled' : ''} style="width:90px"></td>
          <td><input type="number" step="100" class="gr-line-cost form-control" data-idx="${idx}" value="${ln.unit_price}" style="width:110px"></td>
        </tr>`;
    }).join('');
    const html = `
    <div class="modal-backdrop" id="createGRBackdrop" onclick="if(event.target===this)this.remove()">
      <div class="modal-content" style="max-width:820px">
        <div class="modal-header">
          <h3>Buat Goods Receipt dari ${_ffEsc(po.po_no)}</h3>
          <button class="modal-close" onclick="document.getElementById('createGRBackdrop').remove()">×</button>
        </div>
        <div class="modal-body">
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px">
            <div><label>Tanggal Receipt</label><input type="date" id="grDate" value="${_ffToday()}" class="form-control"></div>
            <div><label>Warehouse</label>
              <select id="grWarehouse" class="form-control">${(OrdersState?.warehouses || []).map(w => `<option value="${w.id}">${_ffEsc(w.name)}</option>`).join('')}</select>
            </div>
          </div>
          <table class="data-table">
            <thead><tr><th>Item</th><th>Ordered</th><th>Received</th><th>Remaining</th><th>Qty Terima</th><th>Unit Cost</th></tr></thead>
            <tbody>${linesRows}</tbody>
          </table>
          <div style="margin-top:12px"><label>Notes</label><textarea id="grNotes" class="form-control" rows="2"></textarea></div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-outline" onclick="document.getElementById('createGRBackdrop').remove()">Tutup</button>
          <button class="btn btn-primary" onclick="saveGoodsReceipt('${po.id}', false)">Simpan Draft</button>
          <button class="btn btn-success" onclick="saveGoodsReceipt('${po.id}', true)">Simpan + Post</button>
        </div>
      </div>
    </div>`;
    document.body.insertAdjacentHTML('beforeend', html);
    const firstWh = po.lines?.[0]?.warehouse_id;
    if (firstWh) document.getElementById('grWarehouse').value = firstWh;
  } catch (e) { showToast('Gagal load PO: ' + e.message, 'error'); }
}

async function saveGoodsReceipt(poId, postNow) {
  const receipt_date = document.getElementById('grDate').value;
  const warehouse_id = document.getElementById('grWarehouse').value;
  const notes        = document.getElementById('grNotes').value;
  if (!receipt_date || !warehouse_id) { showToast('Tanggal & warehouse wajib', 'error'); return; }
  const lines = [];
  document.querySelectorAll('.gr-line-cb').forEach(cb => {
    if (cb.checked) {
      const idx = cb.dataset.idx;
      const qty = parseFloat(document.querySelector(`.gr-line-qty[data-idx="${idx}"]`).value) || 0;
      const cost = parseFloat(document.querySelector(`.gr-line-cost[data-idx="${idx}"]`).value) || 0;
      const max = parseFloat(cb.dataset.max);
      if (qty > 0 && qty <= max) {
        lines.push({ po_line_id: cb.dataset.lineId, qty_received: qty, unit_cost: cost });
      }
    }
  });
  if (!lines.length) { showToast('Pilih minimal 1 line dengan qty > 0', 'error'); return; }
  try {
    const res = await Api.goodsReceipts.create({
      receipt_date, po_id: poId, warehouse_id, notes: notes || null, lines,
    }, postNow ? {post_now:'true'} : {});
    showToast(`GR ${res.gr_no} ${postNow?'di-post':'tersimpan'}`, 'success');
    document.getElementById('createGRBackdrop')?.remove();
    if (typeof renderPurchaseOrderPage === 'function' && AppState.currentPage === 'purchase-orders') renderPurchaseOrderPage();
    if (AppState.currentPage === 'goods-receipts') renderGoodsReceiptPage();
  } catch (e) { showToast('Gagal: ' + e.message, 'error'); }
}

async function postGoodsReceipt(id) {
  if (!confirm('Post GR ini? Stock akan masuk + journal Dr Inventory / Cr GR-clearing.')) return;
  try {
    await Api.goodsReceipts.post(id);
    showToast('GR di-post', 'success');
    renderGoodsReceiptPage();
  } catch (e) { showToast('Gagal post: ' + e.message, 'error'); }
}

async function voidGoodsReceipt(id) {
  const reason = prompt('Alasan void?');
  if (!reason) return;
  try {
    await Api.goodsReceipts.void(id, {reason});
    showToast('GR di-void', 'warning');
    renderGoodsReceiptPage();
  } catch (e) { showToast('Gagal: ' + e.message, 'error'); }
}

async function showGoodsReceiptDetail(id) {
  try {
    const g = await Api.goodsReceipts.get(id);
    const itemMap = Object.fromEntries((OrdersState?.items || []).map(i => [i.id, i.name]));
    const linesHtml = (g.lines || []).map((ln, idx) => `
      <tr>
        <td>${idx+1}</td>
        <td>${_ffEsc(itemMap[ln.item_id] || ln.item_id?.slice(0,8))}</td>
        <td style="text-align:right">${ln.qty_received}</td>
        <td style="text-align:right">${_ffFmtRp(ln.unit_cost)}</td>
        <td style="text-align:right">${_ffFmtRp((ln.qty_received||0) * (ln.unit_cost||0))}</td>
      </tr>`).join('');
    const html = `
    <div class="modal-backdrop" id="grDetailBackdrop" onclick="if(event.target===this)this.remove()">
      <div class="modal-content" style="max-width:780px">
        <div class="modal-header">
          <h3>${_ffEsc(g.gr_no)} — ${_ffStatusBadge(g.status)}</h3>
          <button class="modal-close" onclick="document.getElementById('grDetailBackdrop').remove()">×</button>
        </div>
        <div class="modal-body">
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px">
            <div><strong>Receipt Date:</strong> ${g.receipt_date}</div>
            <div><strong>PO ID:</strong> <code>${_ffEsc(g.po_id?.slice(0,8))}</code></div>
            <div><strong>Journal:</strong> ${g.journal_entry_id ? `<code>${_ffEsc(g.journal_entry_id.slice(0,8))}</code>` : '-'}</div>
            <div><strong>Posted At:</strong> ${g.posted_at ? new Date(g.posted_at).toLocaleString() : '-'}</div>
          </div>
          <table class="data-table">
            <thead><tr><th>#</th><th>Item</th><th>Qty</th><th>Unit Cost</th><th>Subtotal</th></tr></thead>
            <tbody>${linesHtml}</tbody>
          </table>
          ${g.void_reason ? `<p style="margin-top:12px;color:#ef4444"><strong>Void reason:</strong> ${_ffEsc(g.void_reason)}</p>` : ''}
        </div>
      </div>
    </div>`;
    document.body.insertAdjacentHTML('beforeend', html);
  } catch (e) { showToast('Gagal: ' + e.message, 'error'); }
}

// ════════════════════════════════════════════════════════════════
// RMA
// ════════════════════════════════════════════════════════════════

async function renderRMAPage() {
  if (typeof _ordEnsureMasters === 'function') await _ordEnsureMasters();
  const type   = document.getElementById('rmaFilterType')?.value || '';
  const status = document.getElementById('rmaFilterStatus')?.value || '';
  try {
    const rmas = await Api.rmas.list({ rma_type: type || undefined, status: status || undefined, limit: 200 });
    FFState.rmas = Array.isArray(rmas) ? rmas : [];
  } catch (e) {
    showToast('Gagal load RMA: ' + e.message, 'error');
    FFState.rmas = [];
  }
  const wrap = document.getElementById('rmaTableWrap');
  if (!wrap) return;
  if (!FFState.rmas.length) {
    wrap.innerHTML = `<div style="padding:48px;text-align:center;color:#6b7280">Belum ada RMA. Buat dari Delivery Order posted (customer return) atau Goods Receipt posted (supplier return).</div>`;
    return;
  }
  wrap.innerHTML = `
    <table class="data-table">
      <thead><tr>
        <th>No RMA</th><th>Tanggal</th><th>Type</th><th>Source</th>
        <th style="text-align:right">Total Lines</th>
        <th>Status</th><th style="text-align:center">Aksi</th>
      </tr></thead>
      <tbody>
      ${FFState.rmas.map(r => `
        <tr>
          <td><code>${_ffEsc(r.rma_no)}</code></td>
          <td>${r.rma_date || '-'}</td>
          <td>${r.rma_type === 'customer_return' ? '<span style="color:#3b82f6">↩ Customer</span>' : '<span style="color:#f59e0b">↪ Supplier</span>'}</td>
          <td><code style="font-size:11px">${_ffEsc((r.source_do_id || r.source_gr_id || '').slice(0,8))}</code></td>
          <td style="text-align:right">${(r.lines || []).length}</td>
          <td>${_ffStatusBadge(r.status)}</td>
          <td style="text-align:center;white-space:nowrap">
            <button class="btn btn-sm btn-outline" onclick="showRMADetail('${r.id}')">Detail</button>
            ${r.status === 'draft'  ? `<button class="btn btn-sm btn-primary" style="margin-left:4px" onclick="postRMA('${r.id}')">Post</button>` : ''}
            ${r.status !== 'void'   ? `<button class="btn btn-sm btn-danger"  style="margin-left:4px" onclick="voidRMA('${r.id}')">Void</button>` : ''}
          </td>
        </tr>`).join('')}
      </tbody>
    </table>`;
}

async function createRMAFromDO(doId) { await _openRMAModal('customer_return', doId); }
async function createRMAFromGR(grId) { await _openRMAModal('supplier_return', grId); }

async function _openRMAModal(type, sourceId) {
  try {
    const source = type === 'customer_return'
      ? await Api.deliveryOrders.get(sourceId)
      : await Api.goodsReceipts.get(sourceId);
    if (source.status !== 'posted') {
      showToast(`Source ${type === 'customer_return' ? 'DO' : 'GR'} harus posted`, 'error');
      return;
    }
    const itemMap = Object.fromEntries((OrdersState?.items || []).map(i => [i.id, i.name]));
    const qtyField = type === 'customer_return' ? 'qty_delivered' : 'qty_received';
    const linesRows = (source.lines || []).map((ln, idx) => `
      <tr>
        <td><label><input type="checkbox" class="rma-line-cb" data-idx="${idx}" data-line-id="${ln.id}" data-max="${ln[qtyField]}" data-unit-cost="${ln.unit_cost || 0}"> ${_ffEsc(itemMap[ln.item_id] || ln.item_id?.slice(0,8))}</label></td>
        <td style="text-align:right">${ln[qtyField]}</td>
        <td style="text-align:right">${_ffFmtRp(ln.unit_cost || 0)}</td>
        <td><input type="number" step="0.01" class="rma-line-qty form-control" data-idx="${idx}" value="1" style="width:90px"></td>
      </tr>`).join('');
    const sourceLabel = type === 'customer_return' ? source.do_no : source.gr_no;
    const sourceKey   = type === 'customer_return' ? 'source_do_id' : 'source_gr_id';
    const html = `
    <div class="modal-backdrop" id="rmaModalBackdrop" onclick="if(event.target===this)this.remove()">
      <div class="modal-content" style="max-width:780px">
        <div class="modal-header">
          <h3>Buat RMA ${type === 'customer_return' ? '(Customer Return)' : '(Supplier Return)'} dari ${_ffEsc(sourceLabel)}</h3>
          <button class="modal-close" onclick="document.getElementById('rmaModalBackdrop').remove()">×</button>
        </div>
        <div class="modal-body">
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px">
            <div><label>Tanggal Return</label><input type="date" id="rmaDate" value="${_ffToday()}" class="form-control"></div>
            <div><label>Warehouse</label>
              <select id="rmaWarehouse" class="form-control">${(OrdersState?.warehouses || []).map(w => `<option value="${w.id}" ${w.id===source.warehouse_id?'selected':''}>${_ffEsc(w.name)}</option>`).join('')}</select>
            </div>
          </div>
          <div style="margin-bottom:12px"><label>Reason</label><input type="text" id="rmaReason" class="form-control" placeholder="Alasan return"></div>
          <table class="data-table">
            <thead><tr><th>Item (centang)</th><th>Qty asli</th><th>Unit Cost</th><th>Qty Return</th></tr></thead>
            <tbody>${linesRows}</tbody>
          </table>
          <div style="margin-top:12px"><label>Notes</label><textarea id="rmaNotes" class="form-control" rows="2"></textarea></div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-outline" onclick="document.getElementById('rmaModalBackdrop').remove()">Tutup</button>
          <button class="btn btn-primary" onclick="saveRMA('${type}', '${sourceKey}', '${sourceId}', false)">Simpan Draft</button>
          <button class="btn btn-success" onclick="saveRMA('${type}', '${sourceKey}', '${sourceId}', true)">Simpan + Post</button>
        </div>
      </div>
    </div>`;
    document.body.insertAdjacentHTML('beforeend', html);
  } catch (e) { showToast('Gagal load source: ' + e.message, 'error'); }
}

async function saveRMA(rma_type, sourceKey, sourceId, postNow) {
  const rma_date     = document.getElementById('rmaDate').value;
  const warehouse_id = document.getElementById('rmaWarehouse').value;
  const reason       = document.getElementById('rmaReason').value;
  const notes        = document.getElementById('rmaNotes').value;
  if (!rma_date || !warehouse_id) { showToast('Tanggal & warehouse wajib', 'error'); return; }
  const lineKey = rma_type === 'customer_return' ? 'source_do_line_id' : 'source_gr_line_id';
  const lines = [];
  document.querySelectorAll('.rma-line-cb').forEach(cb => {
    if (cb.checked) {
      const idx = cb.dataset.idx;
      const qty = parseFloat(document.querySelector(`.rma-line-qty[data-idx="${idx}"]`).value) || 0;
      const max = parseFloat(cb.dataset.max);
      if (qty > 0 && qty <= max) {
        lines.push({ [lineKey]: cb.dataset.lineId, qty_returned: qty, unit_cost: parseFloat(cb.dataset.unitCost) || undefined });
      }
    }
  });
  if (!lines.length) { showToast('Pilih minimal 1 line', 'error'); return; }
  const payload = {
    rma_type, rma_date, warehouse_id, reason: reason || null, notes: notes || null,
    [sourceKey]: sourceId, lines,
  };
  try {
    const res = await Api.rmas.create(payload, postNow ? {post_now:'true'} : {});
    showToast(`RMA ${res.rma_no} ${postNow?'di-post':'tersimpan'}`, 'success');
    document.getElementById('rmaModalBackdrop')?.remove();
    if (AppState.currentPage === 'rmas') renderRMAPage();
    else if (AppState.currentPage === 'delivery-orders') renderDeliveryOrderPage();
    else if (AppState.currentPage === 'goods-receipts')  renderGoodsReceiptPage();
  } catch (e) { showToast('Gagal: ' + e.message, 'error'); }
}

async function postRMA(id) {
  if (!confirm('Post RMA ini? Stock akan berubah + journal akan dibuat.')) return;
  try {
    await Api.rmas.post(id);
    showToast('RMA di-post', 'success');
    renderRMAPage();
  } catch (e) { showToast('Gagal post: ' + e.message, 'error'); }
}

async function voidRMA(id) {
  const reason = prompt('Alasan void?');
  if (!reason) return;
  try {
    await Api.rmas.void(id, {reason});
    showToast('RMA di-void', 'warning');
    renderRMAPage();
  } catch (e) { showToast('Gagal: ' + e.message, 'error'); }
}

// ════════════════════════════════════════════════════════════════
// Pipeline KPIs (Dashboard) — Sprint E
// ════════════════════════════════════════════════════════════════
async function refreshPipelineKPIs() {
  if (!Api.isLoggedIn || !Api.isLoggedIn()) return;
  try {
    const [sos, pos, dos, grs, rmas] = await Promise.all([
      Api.salesOrders.list({limit: 500}).catch(() => []),
      Api.purchaseOrders.list({limit: 500}).catch(() => []),
      Api.deliveryOrders.list({limit: 500}).catch(() => []),
      Api.goodsReceipts.list({limit: 500}).catch(() => []),
      Api.rmas.list({limit: 500}).catch(() => []),
    ]);
    const openSO  = (sos  || []).filter(s => ['draft','confirmed','partially_delivered'].includes(s.status)).length;
    const openPO  = (pos  || []).filter(p => ['draft','confirmed','partially_received'].includes(p.status)).length;
    const pendDO  = (dos  || []).filter(d => d.status === 'draft').length;
    const pendGR  = (grs  || []).filter(g => g.status === 'draft').length;
    const openRMA = (rmas || []).filter(r => r.status === 'draft').length;
    const setVal = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
    setVal('kpiOpenSO',     openSO);
    setVal('kpiOpenPO',     openPO);
    setVal('kpiPendingDO',  pendDO);
    setVal('kpiPendingGR',  pendGR);
    setVal('kpiOpenRMA',    openRMA);
  } catch (e) {
    console.warn('[pipeline KPI] refresh failed', e);
  }
}

// Auto-refresh KPIs whenever Dashboard is shown
document.addEventListener('DOMContentLoaded', () => {
  // Initial load when logged in
  if (Api?.isLoggedIn && Api.isLoggedIn()) {
    setTimeout(refreshPipelineKPIs, 500);
  }
  // Hook into navigation: refresh when entering dashboard
  const origNav = window.navigateTo;
  if (typeof origNav === 'function' && !origNav._pipelineHooked) {
    window.navigateTo = function(page) {
      const r = origNav.apply(this, arguments);
      if (page === 'dashboard') refreshPipelineKPIs();
      return r;
    };
    window.navigateTo._pipelineHooked = true;
  }
});

async function showRMADetail(id) {
  try {
    const r = await Api.rmas.get(id);
    const itemMap = Object.fromEntries((OrdersState?.items || []).map(i => [i.id, i.name]));
    const linesHtml = (r.lines || []).map((ln, idx) => `
      <tr>
        <td>${idx+1}</td>
        <td>${_ffEsc(itemMap[ln.item_id] || ln.item_id?.slice(0,8))}</td>
        <td style="text-align:right">${ln.qty_returned}</td>
        <td style="text-align:right">${_ffFmtRp(ln.unit_cost)}</td>
        <td style="text-align:right">${_ffFmtRp((ln.qty_returned||0) * (ln.unit_cost||0))}</td>
      </tr>`).join('');
    const sourceLabel = r.source_do_id ? `DO <code>${_ffEsc(r.source_do_id.slice(0,8))}</code>` :
                       r.source_gr_id ? `GR <code>${_ffEsc(r.source_gr_id.slice(0,8))}</code>` : '-';
    const html = `
    <div class="modal-backdrop" id="rmaDetailBackdrop" onclick="if(event.target===this)this.remove()">
      <div class="modal-content" style="max-width:780px">
        <div class="modal-header">
          <h3>${_ffEsc(r.rma_no)} — ${_ffStatusBadge(r.status)}</h3>
          <button class="modal-close" onclick="document.getElementById('rmaDetailBackdrop').remove()">×</button>
        </div>
        <div class="modal-body">
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px">
            <div><strong>Type:</strong> ${r.rma_type === 'customer_return' ? 'Customer Return' : 'Supplier Return'}</div>
            <div><strong>Source:</strong> ${sourceLabel}</div>
            <div><strong>Date:</strong> ${r.rma_date}</div>
            <div><strong>Journal:</strong> ${r.journal_entry_id ? `<code>${_ffEsc(r.journal_entry_id.slice(0,8))}</code>` : '-'}</div>
          </div>
          <table class="data-table">
            <thead><tr><th>#</th><th>Item</th><th>Qty</th><th>Unit Cost</th><th>Total</th></tr></thead>
            <tbody>${linesHtml}</tbody>
          </table>
          ${r.reason ? `<p style="margin-top:12px"><strong>Reason:</strong> ${_ffEsc(r.reason)}</p>` : ''}
          ${r.void_reason ? `<p style="color:#ef4444"><strong>Void:</strong> ${_ffEsc(r.void_reason)}</p>` : ''}
        </div>
      </div>
    </div>`;
    document.body.insertAdjacentHTML('beforeend', html);
  } catch (e) { showToast('Gagal: ' + e.message, 'error'); }
}

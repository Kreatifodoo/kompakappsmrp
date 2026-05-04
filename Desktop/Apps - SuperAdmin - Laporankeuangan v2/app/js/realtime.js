/**
 * REALTIME.JS — WebSocket client for live multi-user updates
 *
 * Connects to wss://<host>/api/v1/ws?token=<JWT> after backend login.
 * Receives tenant-scoped events (sales_invoice.posted, payment.received, ...)
 * and patches in-memory state + re-renders the current page.
 *
 * Auto-reconnect with exponential backoff (capped at 30s). Sends pong
 * back when server pings. Updates the "⚡ Live" indicator in the sidebar.
 *
 * Public API:
 *   Realtime.connect()        — open the WS (requires Api.isLoggedIn)
 *   Realtime.disconnect()     — clean shutdown
 *   Realtime.on(type, fn)     — subscribe to additional event types
 *   Realtime.isConnected()    — boolean status
 */

const Realtime = (() => {
  let _ws = null;
  let _retry = 0;
  let _intentionalClose = false;
  let _connected = false;
  const _subscribers = new Map();   // event type → [fn]

  function _wsUrl() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const token = encodeURIComponent(typeof ApiTokens !== 'undefined' ? (ApiTokens.access || '') : '');
    return `${proto}://${location.host}/api/v1/ws?token=${token}`;
  }

  function _setStatus(state) {
    const el = document.getElementById('rtIndicator');
    if (!el) return;
    if (state === 'connected') {
      el.innerHTML = '<span class="rt-dot rt-dot-on"></span> Live';
      el.title = 'Real-time sync aktif — perubahan dari user lain otomatis muncul';
      el.classList.add('rt-on'); el.classList.remove('rt-off');
    } else if (state === 'connecting') {
      el.innerHTML = '<span class="rt-dot rt-dot-pulse"></span> Connecting…';
      el.classList.remove('rt-on', 'rt-off');
    } else {
      el.innerHTML = '<span class="rt-dot rt-dot-off"></span> Offline';
      el.title = 'Real-time sync offline';
      el.classList.add('rt-off'); el.classList.remove('rt-on');
    }
  }

  function _emit(type, data) {
    const handlers = _subscribers.get(type) || [];
    for (const h of handlers) {
      try { h(data); } catch (e) { console.error('[Realtime] handler error', e); }
    }
    // Wildcard
    const allHandlers = _subscribers.get('*') || [];
    for (const h of allHandlers) {
      try { h({type, data}); } catch (e) { console.error('[Realtime] handler error', e); }
    }
  }

  // ─── Default handlers: refresh state from backend on relevant events ──
  function _registerDefaultHandlers() {
    // Sales invoice posted/voided → reload sales invoices + payments
    on('sales_invoice.posted', async (d) => {
      if (typeof BackendLoader !== 'undefined') await BackendLoader.loadSalesInvoices();
      _refreshCurrentPage(['customer-invoices', 'customer-report', 'dashboard']);
      _showToast(`📄 Invoice ${d.invoice_no || ''} di-post`, 'info');
    });
    on('sales_invoice.voided', async () => {
      if (typeof BackendLoader !== 'undefined') await BackendLoader.loadSalesInvoices();
      _refreshCurrentPage(['customer-invoices']);
    });

    // Payment received → reload payments + invoice status
    on('payment.received', async (d) => {
      if (typeof BackendLoader !== 'undefined') {
        await BackendLoader.loadPayments();
        await BackendLoader.loadSalesInvoices();
      }
      _refreshCurrentPage(['customer-payments', 'customer-invoices', 'dashboard']);
      _showToast(`💰 Pembayaran ${d.payment_no || ''} diterima`, 'success');
    });

    // Purchase invoice posted/voided
    on('purchase_invoice.posted', async () => {
      if (typeof BackendLoader !== 'undefined') await BackendLoader.loadPurchaseBills();
      _refreshCurrentPage(['purchase-bills']);
    });
    on('payment.disbursed', async () => {
      if (typeof BackendLoader !== 'undefined') {
        await BackendLoader.loadPayments();
        await BackendLoader.loadPurchaseBills();
      }
      _refreshCurrentPage(['purchase-payments', 'purchase-bills']);
    });

    // Journal events → reload journals + ledger-derived reports
    on('journal.posted', async () => {
      if (typeof BackendLoader !== 'undefined') await BackendLoader.loadJournals();
      _refreshCurrentPage(['journal']);
    });

    // Inventory events → re-render whichever inventory page is active
    on('stock_movement.posted', (d) => {
      _refreshCurrentPage([
        'inventory', 'inventory-movements', 'inventory-transfers',
        'inv-onhand', 'inv-valuation', 'inv-stockcard',
        'inv-reorder', 'inv-slowmoving',
      ]);
      _showToast(`📦 Stock ${d.direction || ''} ${d.qty || ''} ${d.item_sku || ''}`, 'info');
    });
    on('stock_transfer.posted', (d) => {
      _refreshCurrentPage(['inventory-transfers', 'inv-onhand', 'inv-valuation', 'inventory-movements']);
      _showToast(`🔁 Transfer ${d.transfer_no || ''} dipost`, 'info');
    });
    on('stock_transfer.voided', (d) => {
      _refreshCurrentPage(['inventory-transfers', 'inv-onhand', 'inv-valuation', 'inventory-movements']);
      _showToast(`↩️ Transfer ${d.transfer_no || ''} di-void`, 'warning');
    });

    // Async report ready → toast with download link
    on('report.ready', (d) => {
      _showToast(`✅ Laporan ${d.report_type || ''} siap`, 'success');
    });

    // Server ping → respond pong (keepalive)
    on('ping', () => {
      if (_ws && _ws.readyState === WebSocket.OPEN) {
        _ws.send(JSON.stringify({type: 'pong'}));
      }
    });

    on('connected', (d) => {
      console.log('[Realtime] connected to tenant', d.tenant_id);
    });
  }

  function _refreshCurrentPage(pages) {
    const cur = (typeof AppState !== 'undefined' && AppState.currentPage) || '';
    if (!pages.includes(cur)) return;
    if (typeof navigateTo === 'function') {
      try { navigateTo(cur); } catch {}
    }
  }

  function _showToast(msg, level) {
    if (typeof showToast === 'function') showToast(msg, level || 'info');
  }

  // ─── Connection management ──────────────────────────────────────────
  function connect() {
    if (typeof Api === 'undefined' || !Api.isLoggedIn || !Api.isLoggedIn()) {
      console.warn('[Realtime] Not logged in — skipping connect');
      return;
    }
    if (_ws && (_ws.readyState === WebSocket.OPEN || _ws.readyState === WebSocket.CONNECTING)) return;
    _intentionalClose = false;
    _setStatus('connecting');
    try {
      _ws = new WebSocket(_wsUrl());
    } catch (e) {
      console.error('[Realtime] WS construct failed:', e);
      _scheduleReconnect();
      return;
    }

    _ws.onopen = () => {
      _connected = true;
      _retry = 0;
      _setStatus('connected');
      console.log('[Realtime] ✅ connected');
    };

    _ws.onmessage = (ev) => {
      let msg;
      try { msg = JSON.parse(ev.data); } catch { return; }
      if (msg && msg.type) _emit(msg.type, msg.data || {});
    };

    _ws.onclose = (ev) => {
      _connected = false;
      _setStatus('disconnected');
      _ws = null;
      if (!_intentionalClose) {
        console.warn(`[Realtime] closed (code=${ev.code}) — reconnecting...`);
        _scheduleReconnect();
      }
    };

    _ws.onerror = (e) => {
      console.warn('[Realtime] error', e);
      // onclose will follow; reconnect handled there
    };
  }

  function _scheduleReconnect() {
    _retry = Math.min(_retry + 1, 8);
    const delay = Math.min(1000 * 2 ** _retry, 30_000);  // cap 30s
    console.log(`[Realtime] reconnect in ${delay}ms (attempt ${_retry})`);
    setTimeout(() => { if (!_intentionalClose) connect(); }, delay);
  }

  function disconnect() {
    _intentionalClose = true;
    if (_ws) { try { _ws.close(); } catch {} }
    _ws = null;
    _connected = false;
    _setStatus('disconnected');
  }

  function on(type, fn) {
    const arr = _subscribers.get(type) || [];
    arr.push(fn);
    _subscribers.set(type, arr);
    return () => {
      const a = _subscribers.get(type) || [];
      _subscribers.set(type, a.filter(h => h !== fn));
    };
  }

  function isConnected() { return _connected; }

  _registerDefaultHandlers();

  return { connect, disconnect, on, isConnected };
})();

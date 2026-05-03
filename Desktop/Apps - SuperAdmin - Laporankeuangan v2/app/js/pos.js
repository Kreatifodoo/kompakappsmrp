/**
 * POS.JS — Point of Sale Module v2
 * Handles products, cart, payment methods, orders, reports, Bluetooth printing
 */

// ===== POS STATE =====
const POS_STORAGE_KEY = 'pos_data_v1';

const PosState = {
  products:       [],
  cart:           [],   // [{ productId, qty, note }]
  orders:         [],   // completed transactions
  paymentMethods: [],   // master payment methods
  sessions:       [],   // POS sessions
  currentSession: null, // active session id or null
  feeMasters:     [],   // master pajak/service/diskon
  categories:     [],   // master kategori produk
  settings: {
    taxRate:          10,      // legacy — kept for migration only
    serviceRate:      0,       // legacy — kept for migration only
    taxCoaCode:       '2-1330', // Utang PPN
    discountCoaCode:  '4-5200', // Diskon Penjualan
    serviceCoaCode:   '4-5100', // Pendapatan Service
    cogsCoaCode:      '5-5100', // HPP Makanan & Minuman
    inventoryCoaCode: '1-1400', // Persediaan
  },
  btDevice:       null,
  activeCategory: 'all',
  searchQuery:    ''
};

// Chart instances (for cleanup before re-render)
const PosCharts = {};

// ===== DEFAULT DATA =====
const DEFAULT_CATEGORIES = [
  { id:'cat_main',    name:'Main Course', incomeAccount:'4-5000', cogsAccount:'5-5100', inventoryAccount:'1-1400', sortOrder:0 },
  { id:'cat_drink',   name:'Drink',       incomeAccount:'4-5000', cogsAccount:'5-5100', inventoryAccount:'1-1400', sortOrder:1 },
  { id:'cat_snack',   name:'Snack',       incomeAccount:'4-5000', cogsAccount:'5-5100', inventoryAccount:'1-1400', sortOrder:2 },
  { id:'cat_dessert', name:'Dessert',     incomeAccount:'4-5000', cogsAccount:'5-5100', inventoryAccount:'1-1400', sortOrder:3 },
];

const DEFAULT_PRODUCTS = [
  { id:'prod_001', name:'Nasi Goreng Spesial', desc:'Nasi goreng dengan telur & ayam', price:35000, categoryId:'cat_main', available:true,
    imageUrl:'https://images.unsplash.com/photo-1512058564366-18510be2db19?w=400&q=80', costPrice:15000, onhandQty:0 },
  { id:'prod_002', name:'Mie Ayam', desc:'Mie ayam kuah kaldu spesial', price:28000, categoryId:'cat_main', available:true,
    imageUrl:'https://images.unsplash.com/photo-1569050467447-ce54b3bbc37d?w=400&q=80', costPrice:12000, onhandQty:0 },
  { id:'prod_003', name:'Es Teh Manis', desc:'Teh manis segar dengan es batu', price:8000, categoryId:'cat_drink', available:true,
    imageUrl:'https://images.unsplash.com/photo-1556679343-c7306c1976bc?w=400&q=80', costPrice:3000, onhandQty:0 },
  { id:'prod_004', name:'Jus Alpukat', desc:'Jus alpukat segar dengan susu', price:20000, categoryId:'cat_drink', available:true,
    imageUrl:'https://images.unsplash.com/photo-1623065422902-30a2d299bbe4?w=400&q=80', costPrice:8000, onhandQty:0 },
  { id:'prod_005', name:'Martabak Manis', desc:'Martabak coklat keju lembut', price:45000, categoryId:'cat_dessert', available:true,
    imageUrl:'https://images.unsplash.com/photo-1558961363-fa8fdf82db35?w=400&q=80', costPrice:20000, onhandQty:0 }
];

const DEFAULT_PAYMENT_METHODS = [
  { id:'pm_cash',     name:'Cash',             icon:'dollar-sign', requiresCash:true,  active:true, coaCode:'1-1100' },
  { id:'pm_card',     name:'Kartu Debit/Kredit', icon:'credit-card', requiresCash:false, active:true, coaCode:'1-1120' },
  { id:'pm_transfer', name:'Transfer Bank',    icon:'smartphone',  requiresCash:false, active:true, coaCode:'1-1110' },
  { id:'pm_ewallet',  name:'E-Wallet',         icon:'zap',         requiresCash:false, active:true, coaCode:'1-1120' }
];

const DEFAULT_FEE_MASTERS = [
  { id:'fee_default_tax', name:'PPN', category:'tax', amountType:'percentage', amount:10, coaCode:'2-1330', active:true }
];

// ===== STORAGE =====
// Full-online mode: localStorage disabled. POS data lives in backend (items,
// pos_sessions, pos_orders). Loaded by BackendLoader on login.
const POS_MAX_ORDERS = 500;

function savePosData() {
  // No-op — saves go to backend via Api.posSessions/posOrders/items hooks.
  // Keep prune logic only to bound in-memory order list during long sessions.
  if (PosState.orders.length > POS_MAX_ORDERS) {
    PosState.orders = PosState.orders.slice(0, POS_MAX_ORDERS);
  }
}

function loadPosData() {
  // No-op for storage. Backend loads happen via BackendLoader. Just seed
  // defaults for the in-memory catalogues if backend hasn't populated them.
  if (!PosState.products.length)       { PosState.products       = [...DEFAULT_PRODUCTS]; }
  if (!PosState.paymentMethods.length) { PosState.paymentMethods = [...DEFAULT_PAYMENT_METHODS]; }
  if (!PosState.categories || !PosState.categories.length) { PosState.categories = DEFAULT_CATEGORIES.map(c => ({...c})); }

  // Migration: jika belum ada feeMasters, buat dari legacy taxRate/serviceRate
  if (!PosState.feeMasters || PosState.feeMasters.length === 0) {
    PosState.feeMasters = [...DEFAULT_FEE_MASTERS];
    if (PosState.settings.taxRate > 0) {
      PosState.feeMasters[0] = { ...PosState.feeMasters[0], amount: PosState.settings.taxRate, coaCode: PosState.settings.taxCoaCode };
    }
    if ((PosState.settings.serviceRate || 0) > 0) {
      PosState.feeMasters.unshift({ id:'fee_default_svc', name:'Service Charge', category:'service',
        amountType:'percentage', amount: PosState.settings.serviceRate,
        coaCode: PosState.settings.serviceCoaCode, active:true });
    }
    savePosData();
  }

  // Migrate: merge stored payment methods with defaults to fill any missing fields (e.g. coaCode)
  PosState.paymentMethods = PosState.paymentMethods.map(m => {
    const def = DEFAULT_PAYMENT_METHODS.find(d => d.id === m.id) || {};
    return { ...def, ...m, coaCode: m.coaCode || def.coaCode || '1-1100' };
  });

  // Migrate: konversi product.category slug → categoryId + tambah onhandQty + hapus akun dari produk
  const slugToId = { main:'cat_main', drink:'cat_drink', snack:'cat_snack', dessert:'cat_dessert' };
  let needsSave = false;
  PosState.products = PosState.products.map(p => {
    const u = { ...p };
    if (!u.categoryId) {
      u.categoryId = slugToId[u.category] || 'cat_main';
      needsSave = true;
    }
    if (u.onhandQty === undefined) { u.onhandQty = 0; needsSave = true; }
    if ('incomeAccount' in u) { delete u.incomeAccount; needsSave = true; }
    if ('cogsAccount'   in u) { delete u.cogsAccount;   needsSave = true; }
    return u;
  });
  if (needsSave) savePosData();

  // Restore POS journal entries from closed sessions into AppState
  // (loadFromStorage runs before loadPosData, so AppState.journals already has bank journals)
  _restorePosJournalsToState();
}

// ============================================================
//  POS → LAPORAN KEUANGAN INTEGRATION
// ============================================================

/** Kembalikan array journal entry dari semua sesi POS yang sudah ditutup,
 *  dengan optional filter tanggal (format YYYY-MM-DD) */
function _getPosJournals(fromStr, toStr) {
  const from = fromStr ? new Date(fromStr + 'T00:00:00') : null;
  const to   = toStr   ? new Date(toStr   + 'T23:59:59') : null;
  return (PosState.sessions || [])
    .filter(s => {
      if (s.status !== 'closed' || !s.journalEntry) return false;
      if (from && to) {
        const d = new Date(s.closedAt);
        return d >= from && d <= to;
      }
      return true;
    })
    .map(s => s.journalEntry);
}

/** Merge jurnal POS ke AppState.journals dan rebuild ledger + laporan */
function _restorePosJournalsToState() {
  if (typeof AppState === 'undefined' || typeof buildLedger !== 'function') return;
  // Hapus JE-POS lama agar tidak duplikat, lalu re-add dari sessions
  AppState.journals = (AppState.journals || []).filter(j => !j.id?.startsWith('JE-POS'));
  _getPosJournals().forEach(j => AppState.journals.push(j));
  if (typeof flattenJournalForTable === 'function') {
    AppState.journalRows = flattenJournalForTable(AppState.journals);
  }
  AppState.ledger = buildLedger(AppState.journals);
  _posRebuildReports();
}

/** Merge jurnal POS (dengan optional date filter) ke array journals lokal untuk report filter */
function _mergePosJournalsInto(journalsArray, fromStr, toStr) {
  _getPosJournals(fromStr, toStr).forEach(j => {
    if (!journalsArray.find(e => e.id === j.id)) journalsArray.push(j);
  });
}

/** Rebuild incomeData dan balanceData dari AppState.ledger yang sudah include POS */
function _posRebuildReports() {
  if (typeof AppState === 'undefined' || typeof generateIncomeStatement !== 'function') return;
  const merged = AppState.merged;
  const periods = merged?.periods?.filter(Boolean) || [];
  const periodLabel = periods.length > 1
    ? `Periode: ${periods[0]} s/d ${periods[periods.length - 1]}`
    : `Periode: ${periods[0] || new Date().toLocaleDateString('id-ID', { month: 'long', year: 'numeric' })}`;
  const company = 'PT Global Kreatif Inovasi';
  AppState.incomeData = generateIncomeStatement(AppState.ledger, periodLabel, company);
  if (typeof generateBalanceSheet === 'function') {
    let summary = AppState.summary;
    if (!summary) {
      // POS-only mode: tidak ada bank statement → buat synthetic summary dari ledger POS
      // Ini agar balance sheet bisa dirender dengan saldo kas/bank dari jurnal POS
      const bankAcct = AppState.ledger?.['1-1110'];
      summary = {
        saldoAwal:  0,
        saldoAkhir: bankAcct?.balance   || 0,
        mutasiCR:   bankAcct?.totalKredit || 0,
        mutasiDB:   bankAcct?.totalDebit  || 0
      };
    }
    AppState.balanceData = generateBalanceSheet(AppState.ledger, summary, periodLabel, company);
  }
}

// ===== HELPERS =====
function formatRupiahPos(n) {
  return 'Rp ' + Math.round(n || 0).toLocaleString('id-ID');
}
function escHtml(str) {
  return String(str || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function fIconSvg(name, size = 16) {
  if (typeof feather !== 'undefined' && feather.icons[name]) {
    return feather.icons[name].toSvg({ width: size, height: size });
  }
  return '';
}
function getCategoryById(id) {
  return PosState.categories.find(c => c.id === id) || null;
}
function getCategoryLabel(catId) {
  // Support both new categoryId and legacy slug
  const cat = getCategoryById(catId);
  if (cat) return cat.name;
  return { main:'Main Course', drink:'Drink', snack:'Snack', dessert:'Dessert' }[catId] || catId || '-';
}
function getCategoryColor(catId) {
  const colorMap = { cat_main:'main', cat_drink:'drink', cat_snack:'snack', cat_dessert:'dessert',
                     main:'main', drink:'drink', snack:'snack', dessert:'dessert' };
  return colorMap[catId] || 'other';
}

// Resolver akun dari kategori (dengan fallback ke settings)
function _getCategoryAccounts(categoryId) {
  const cat = getCategoryById(categoryId);
  return {
    incomeAccount:    cat?.incomeAccount    || '4-5000',
    cogsAccount:      cat?.cogsAccount      || PosState.settings.cogsCoaCode,
    inventoryAccount: cat?.inventoryAccount || PosState.settings.inventoryCoaCode,
  };
}

// Build HTML options untuk dropdown kategori di form produk
function _buildCategoryOptions(selectedId) {
  return PosState.categories
    .slice().sort((a,b) => (a.sortOrder||0) - (b.sortOrder||0))
    .map(c => `<option value="${escHtml(c.id)}"${c.id===selectedId?' selected':''}>${escHtml(c.name)}</option>`)
    .join('');
}

// Render tab kategori di halaman POS secara dinamis
function renderCategoryTabs() {
  const container = document.getElementById('posCategoryTabs');
  if (!container) return;
  const sorted = PosState.categories.slice().sort((a,b) => (a.sortOrder||0) - (b.sortOrder||0));
  container.innerHTML = `<button class="pos-cat-btn active" data-cat="all">Semua</button>` +
    sorted.map(c => `<button class="pos-cat-btn" data-cat="${escHtml(c.id)}">${escHtml(c.name)}</button>`).join('');
  container.querySelectorAll('.pos-cat-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      container.querySelectorAll('.pos-cat-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      PosState.activeCategory = btn.dataset.cat;
      renderProductGrid();
    });
  });
}

// ===== INIT =====
function initPOS() {
  loadPosData();
  renderCategoryTabs();
}

// ============================================================
//  POINT OF SALE — MAIN PAGE
// ============================================================
function renderPOSPage() {
  const now = new Date();
  const el = document.getElementById('posCurrentDate');
  if (el) el.textContent = now.toLocaleDateString('id-ID', { weekday:'long', year:'numeric', month:'long', day:'numeric' });

  const searchEl = document.getElementById('posSearch');
  if (searchEl) { searchEl.value = ''; PosState.searchQuery = ''; }

  PosState.activeCategory = 'all';
  renderCategoryTabs();

  updateSessionChip();
  renderProductGrid();
  renderCart();
  if (typeof feather !== 'undefined') feather.replace();
}

function updateSessionChip() {
  const chip = document.getElementById('posSessionChip');
  const btnOpen  = document.getElementById('btnOpenSession');
  const btnClose = document.getElementById('btnCloseSession');
  const sess = PosState.currentSession
    ? PosState.sessions.find(s => s.id === PosState.currentSession)
    : null;
  if (chip) {
    if (sess) {
      const elapsed = Math.floor((Date.now() - new Date(sess.openedAt).getTime()) / 60000);
      const orderCount = sess.orderIds.length;
      chip.textContent = `Sesi: ${elapsed}m | ${orderCount} order`;
      chip.className = 'pos-session-chip active';
    } else {
      chip.textContent = 'Tidak ada sesi aktif';
      chip.className = 'pos-session-chip inactive';
    }
  }
  if (btnOpen)  btnOpen.disabled  = !!sess;
  if (btnClose) btnClose.disabled = !sess;

  // Show/hide session overlay on product grid
  const overlay = document.getElementById('posSessionOverlay');
  if (overlay) overlay.style.display = sess ? 'none' : 'flex';
}

function filterPosProducts() {
  PosState.searchQuery = (document.getElementById('posSearch').value || '').toLowerCase();
  renderProductGrid();
}

// ===== MOBILE TAB TOGGLE (visible only at ≤768px via CSS) =====
function switchPosMobileTab(tab) {
  const left = document.querySelector('.pos-left');
  const right = document.querySelector('.pos-right');
  const tabProducts = document.getElementById('posTabProducts');
  const tabCart     = document.getElementById('posTabCart');
  if (!left || !right) return;
  if (tab === 'products') {
    left.classList.remove('mobile-hidden');
    right.classList.add('mobile-hidden');
    tabProducts?.classList.add('active');
    tabCart?.classList.remove('active');
  } else {
    left.classList.add('mobile-hidden');
    right.classList.remove('mobile-hidden');
    tabCart?.classList.add('active');
    tabProducts?.classList.remove('active');
  }
}

function renderProductGrid() {
  const grid = document.getElementById('posProductGrid');
  if (!grid) return;
  const products = PosState.products.filter(p => {
    const matchCat = PosState.activeCategory === 'all' || p.categoryId === PosState.activeCategory;
    const matchQ   = !PosState.searchQuery ||
      p.name.toLowerCase().includes(PosState.searchQuery) ||
      (p.desc && p.desc.toLowerCase().includes(PosState.searchQuery));
    return matchCat && matchQ;
  });

  if (!products.length) {
    grid.innerHTML = `<div class="pos-empty-products">
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
      <p>Tidak ada produk ditemukan</p>
      <button class="btn btn-outline btn-sm" onclick="showAddProductModal(null)">+ Tambah Produk</button>
    </div>`;
    return;
  }
  grid.innerHTML = products.map(p => {
    const imgHtml = p.imageUrl
      ? `<img src="${escHtml(p.imageUrl)}" class="pos-product-img" alt="${escHtml(p.name)}" onerror="this.style.display='none';this.nextSibling.style.display='flex'" /><div class="pos-product-img-placeholder" style="display:none">🍽️</div>`
      : `<div class="pos-product-img-placeholder">🍽️</div>`;
    const badge = p.available
      ? `<span class="pos-badge available">● Available</span>`
      : `<span class="pos-badge unavailable">✕ Not Available</span>`;
    return `
      <div class="pos-product-card${p.available ? '' : ' unavailable'}" onclick="${p.available ? `addToCart('${p.id}')` : ''}">
        ${imgHtml}
        <button class="pos-product-edit-btn" onclick="event.stopPropagation();showAddProductModal('${p.id}')" title="Edit produk">
          <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
        </button>
        <div class="pos-product-body">
          <div class="pos-product-name">${escHtml(p.name)}</div>
          ${p.desc ? `<div class="pos-product-desc">${escHtml(p.desc)}</div>` : ''}
          <div class="pos-product-footer">${badge}<span class="pos-price">${formatRupiahPos(p.price)}</span></div>
        </div>
      </div>`;
  }).join('');
}

// ===== CART =====
function addToCart(productId) {
  const existing = PosState.cart.find(c => c.productId === productId);
  if (existing) { existing.qty++; }
  else { PosState.cart.push({ productId, qty:1, note:'' }); }
  renderCart();
  // On mobile: auto-switch to cart tab so user sees added item
  if (window.innerWidth <= 768) switchPosMobileTab('cart');
  if (typeof showToast === 'function') showToast('Produk ditambahkan', 'success');
}
function updateCartQty(productId, delta) {
  const item = PosState.cart.find(c => c.productId === productId);
  if (!item) return;
  item.qty = Math.max(0, item.qty + delta);
  if (item.qty === 0) PosState.cart = PosState.cart.filter(c => c.productId !== productId);
  renderCart();
}
function updateCartNote(productId, note) {
  const item = PosState.cart.find(c => c.productId === productId);
  if (item) item.note = note;
}
function removeFromCart(productId) {
  PosState.cart = PosState.cart.filter(c => c.productId !== productId);
  renderCart();
}
function clearCart() {
  if (!PosState.cart.length) return;
  PosState.cart = [];
  const di = document.getElementById('posDiscountInput');
  if (di) di.value = 0;
  renderCart();
}
function renderCart() {
  const cartItems = document.getElementById('posCartItems');
  const emptyEl   = document.getElementById('posCartEmpty');
  const clearBtn  = document.getElementById('posClearCartBtn');
  const payBtn    = document.getElementById('posPayBtn');
  if (!cartItems) return;

  // Update mobile cart badge
  const badge = document.getElementById('posCartBadge');
  if (badge) badge.textContent = PosState.cart.length > 0 ? PosState.cart.length : '';

  if (!PosState.cart.length) {
    emptyEl.style.display  = 'flex';
    cartItems.innerHTML    = '';
    if (clearBtn) clearBtn.style.display = 'none';
    if (payBtn)   payBtn.disabled = true;
    renderCartSummary();
    return;
  }
  emptyEl.style.display  = 'none';
  if (clearBtn) clearBtn.style.display = 'flex';
  if (payBtn)   payBtn.disabled = false;

  cartItems.innerHTML = PosState.cart.map(item => {
    const prod = PosState.products.find(p => p.id === item.productId);
    if (!prod) return '';
    return `
      <div class="pos-cart-item">
        <div class="pos-cart-item-row1">
          <span class="pos-cart-item-name">${escHtml(prod.name)}</span>
          <span class="pos-cart-item-price">${formatRupiahPos(prod.price * item.qty)}</span>
        </div>
        <div class="pos-cart-item-row2">
          <div class="pos-qty-ctrl">
            <button class="pos-qty-btn" onclick="updateCartQty('${item.productId}',-1)">−</button>
            <span class="pos-qty-num">${item.qty}</span>
            <button class="pos-qty-btn" onclick="updateCartQty('${item.productId}',1)">+</button>
          </div>
          <input type="text" class="pos-cart-item-note" placeholder="Catatan..." value="${escHtml(item.note)}"
            onchange="updateCartNote('${item.productId}',this.value)" />
          <button class="pos-cart-remove-btn" onclick="removeFromCart('${item.productId}')" title="Hapus">
            <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4h6v2"/></svg>
          </button>
        </div>
      </div>`;
  }).join('');
  renderCartSummary();
}
// ===== FEE MASTER CALCULATION =====
function _computeFees(subtotal, adHocDiscount = 0) {
  const active = (PosState.feeMasters || [])
    .filter(f => f.active)
    .slice()
    .sort((a, b) => {
      const ord = { discount: 1, service: 2, tax: 3 };
      return (ord[a.category] || 9) - (ord[b.category] || 9);
    });

  const result = [];
  let totalMasterDiscount = 0, totalService = 0, totalTax = 0;

  active.forEach(fee => {
    let computed = 0;
    if (fee.category === 'discount') {
      const base = subtotal;
      computed = fee.amountType === 'percentage'
        ? Math.round(base * fee.amount / 100)
        : fee.amount;
      const remaining = Math.max(0, subtotal - adHocDiscount - totalMasterDiscount);
      computed = Math.min(computed, remaining);
      totalMasterDiscount += computed;
    } else if (fee.category === 'service') {
      const base = Math.max(0, subtotal - adHocDiscount - totalMasterDiscount);
      computed = fee.amountType === 'percentage'
        ? Math.round(base * fee.amount / 100)
        : fee.amount;
      totalService += computed;
    } else if (fee.category === 'tax') {
      const base = Math.max(0, subtotal - adHocDiscount - totalMasterDiscount + totalService);
      computed = fee.amountType === 'percentage'
        ? Math.round(base * fee.amount / 100)
        : fee.amount;
      totalTax += computed;
    }
    result.push({ ...fee, computed });
  });

  return { fees: result, totalMasterDiscount, totalService, totalTax };
}

function renderCartSummary() {
  const subtotal    = PosState.cart.reduce((s, item) => {
    const p = PosState.products.find(x => x.id === item.productId);
    return s + (p ? p.price * item.qty : 0);
  }, 0);
  const adHocDiscount = Math.min(parseFloat(document.getElementById('posDiscountInput')?.value) || 0, subtotal);
  const { fees, totalMasterDiscount, totalService, totalTax } = _computeFees(subtotal, adHocDiscount);
  const totalDiscount = adHocDiscount + totalMasterDiscount;
  const total = subtotal - totalDiscount + totalService + totalTax;

  const setEl = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
  setEl('posSubtotal', formatRupiahPos(subtotal));
  setEl('posDiscount', formatRupiahPos(adHocDiscount));
  setEl('posTotal',    formatRupiahPos(total));

  // Render fee lines dynamically
  const container = document.getElementById('posFeeLinesContainer');
  if (container) {
    container.innerHTML = fees.map(f => {
      const isDisc = f.category === 'discount';
      const amtLabel = f.amountType === 'percentage' ? `${f.amount}%` : formatRupiahPos(f.amount);
      const valStr = `${isDisc ? '-' : ''}${formatRupiahPos(f.computed)}`;
      return `<div class="pos-summary-row pos-fee-row${isDisc ? ' fee-discount' : ''}">
        <span class="pos-fee-label">${escHtml(f.name)} <small>(${amtLabel})</small></span>
        <span class="${isDisc ? 'pos-danger-text' : ''}">${valStr}</span>
      </div>`;
    }).join('');
  }

  // Update pay button state
  const payBtn = document.getElementById('posPayBtn');
  if (payBtn) payBtn.disabled = PosState.cart.length === 0 || !PosState.currentSession;

  return { subtotal, discount: totalDiscount, service: totalService, tax: totalTax, total };
}

// ===== PAYMENT =====
let _activePaymentMethod = null;

function showPaymentModal() {
  if (!PosState.currentSession) {
    if (typeof showToast === 'function') showToast('Buka sesi POS terlebih dahulu', 'error');
    return;
  }
  if (!PosState.cart.length) return;
  const { total } = renderCartSummary();
  document.getElementById('paymentTotalDisplay').textContent = formatRupiahPos(total);

  // Render dynamic payment methods
  const activeMethods = PosState.paymentMethods.filter(m => m.active);
  if (!activeMethods.length) {
    if (typeof showToast === 'function') showToast('Tidak ada metode pembayaran aktif', 'error');
    return;
  }
  const methodsContainer = document.querySelector('#posPaymentModal .pos-payment-methods');
  if (methodsContainer) {
    methodsContainer.innerHTML = activeMethods.map(m => `
      <button class="pos-method-btn${_activePaymentMethod === m.id || (!_activePaymentMethod && m.requiresCash) ? ' active' : ''}"
        data-method="${m.id}" data-requires-cash="${m.requiresCash}" onclick="selectPaymentMethod('${m.id}', ${m.requiresCash})">
        ${fIconSvg(m.icon, 20)}
        <span>${escHtml(m.name)}</span>
      </button>`).join('');
  }

  // Default to first method
  const defaultM = activeMethods[0];
  _activePaymentMethod = defaultM.id;
  document.querySelectorAll('.pos-method-btn').forEach(b => b.classList.toggle('active', b.dataset.method === defaultM.id));
  const cashSection = document.getElementById('cashSection');
  if (cashSection) cashSection.style.display = defaultM.requiresCash ? 'block' : 'none';

  document.getElementById('cashGivenInput').value = '';
  document.getElementById('cashChangeDisplay').textContent = formatRupiahPos(0);
  document.getElementById('btnConfirmPayment').disabled = defaultM.requiresCash;
  document.getElementById('posPaymentModal').classList.add('active');
  if (typeof feather !== 'undefined') feather.replace();
  setTimeout(() => { if (defaultM.requiresCash) document.getElementById('cashGivenInput').focus(); }, 150);
}
function closePaymentModal() {
  document.getElementById('posPaymentModal').classList.remove('active');
}
function selectPaymentMethod(methodId, requiresCash) {
  _activePaymentMethod = methodId;
  document.querySelectorAll('.pos-method-btn').forEach(b => b.classList.toggle('active', b.dataset.method === methodId));
  const cashSection = document.getElementById('cashSection');
  if (cashSection) cashSection.style.display = requiresCash ? 'block' : 'none';
  const btnConfirm = document.getElementById('btnConfirmPayment');
  if (btnConfirm) btnConfirm.disabled = requiresCash;
  if (!requiresCash && typeof feather !== 'undefined') feather.replace();
}
function calculateChange() {
  const { total } = renderCartSummary();
  const given  = parseFloat(document.getElementById('cashGivenInput').value) || 0;
  const change = Math.max(0, given - total);
  document.getElementById('cashChangeDisplay').textContent = formatRupiahPos(change);
  document.getElementById('btnConfirmPayment').disabled = given < total;
}
function confirmPayment() {
  const adHocDiscount = Math.min(parseFloat(document.getElementById('posDiscountInput')?.value) || 0,
    PosState.cart.reduce((s, i) => { const p = PosState.products.find(x => x.id === i.productId); return s + (p ? p.price * i.qty : 0); }, 0));
  const { subtotal, discount, service, tax, total } = renderCartSummary();
  const { fees } = _computeFees(subtotal, adHocDiscount);

  const method = PosState.paymentMethods.find(m => m.id === _activePaymentMethod);
  if (!method) { if (typeof showToast === 'function') showToast('Pilih metode pembayaran', 'error'); return; }

  const cashGiven = method.requiresCash
    ? (parseFloat(document.getElementById('cashGivenInput').value) || 0)
    : total;
  if (method.requiresCash && cashGiven < total) {
    if (typeof showToast === 'function') showToast('Uang yang diberikan kurang', 'error');
    return;
  }
  const items = PosState.cart.map(item => {
    const prod  = PosState.products.find(p => p.id === item.productId);
    const accts = _getCategoryAccounts(prod?.categoryId);
    return {
      productId:        item.productId,
      name:             prod?.name      || item.productId,
      price:            prod?.price     || 0,
      costPrice:        prod?.costPrice || 0,
      categoryId:       prod?.categoryId,
      incomeAccount:    accts.incomeAccount,
      cogsAccount:      accts.cogsAccount,
      inventoryAccount: accts.inventoryAccount,
      qty:              item.qty,
      note:             item.note,
      lineTotal:        (prod?.price||0) * item.qty,
      lineCost:         (prod?.costPrice||0) * item.qty
    };
  });
  const order = {
    id: 'ORD-' + Date.now(),
    date: new Date().toISOString(),
    items, subtotal, discount, service, tax, total,
    adHocDiscount,
    appliedFees: fees.map(f => ({
      feeId: f.id, name: f.name, category: f.category,
      amountType: f.amountType, amount: f.amount,
      coaCode: f.coaCode, computed: f.computed
    })),
    paymentMethodId:   method.id,
    paymentMethodName: method.name,
    paymentCoaCode:    method.coaCode || '1-1100',
    cashAmount:        cashGiven,
    change:            Math.max(0, cashGiven - total),
    sessionId:         PosState.currentSession,
    cashier:           (typeof getCurrentUser === 'function' && getCurrentUser()) ? getCurrentUser().username : 'Kasir'
  };
  PosState.orders.unshift(order);

  // Add to active session
  const sess = PosState.currentSession
    ? PosState.sessions.find(s => s.id === PosState.currentSession)
    : null;
  if (sess) sess.orderIds.push(order.id);

  savePosData();
  PosState.cart = [];
  const di = document.getElementById('posDiscountInput');
  if (di) di.value = 0;
  closePaymentModal();
  renderCart();
  updateSessionChip();
  if (typeof showToast === 'function') {
    showToast(
      `Order ${order.id} berhasil — ${formatRupiahPos(total)} ` +
      `<button onclick="printReceiptFallback(PosState.orders[0])" ` +
      `style="margin-left:8px;padding:2px 10px;border:1px solid rgba(255,255,255,0.5);border-radius:4px;background:rgba(255,255,255,0.15);color:inherit;cursor:pointer;font-size:12px">` +
      `🖨 Cetak Struk</button>`,
      'success'
    );
  }
}

// ===== ADD/EDIT PRODUCT MODAL =====
function showAddProductModal(productId) {
  const modal    = document.getElementById('posProductModal');
  const titleEl  = document.getElementById('posProductModalTitle');
  const deleteBtn = document.getElementById('btnDeleteProduct');
  // Selalu populate kategori dropdown dari PosState.categories
  const catEl = document.getElementById('posProductCategory');
  if (catEl) catEl.innerHTML = _buildCategoryOptions(null);

  if (productId) {
    const prod = PosState.products.find(p => p.id === productId);
    if (!prod) return;
    titleEl.textContent = 'Edit Produk';
    document.getElementById('posProductId').value          = prod.id;
    document.getElementById('posProductName').value        = prod.name;
    document.getElementById('posProductDesc').value        = prod.desc || '';
    document.getElementById('posProductPrice').value       = prod.price;
    document.getElementById('posProductCostPrice').value   = prod.costPrice || 0;
    document.getElementById('posProductOnhandQty').value   = prod.onhandQty ?? 0;
    if (catEl) catEl.innerHTML = _buildCategoryOptions(prod.categoryId);
    document.getElementById('posProductImage').value       = prod.imageUrl || '';
    document.getElementById('posProductAvailable').checked = prod.available;
    deleteBtn.style.display = 'inline-flex';
    previewProductImage();
  } else {
    titleEl.textContent = 'Tambah Produk';
    ['posProductId','posProductName','posProductDesc','posProductPrice','posProductImage'].forEach(id => {
      document.getElementById(id).value = '';
    });
    document.getElementById('posProductCostPrice').value   = 0;
    document.getElementById('posProductOnhandQty').value   = 0;
    if (catEl) catEl.innerHTML = _buildCategoryOptions(PosState.categories[0]?.id || '');
    document.getElementById('posProductAvailable').checked = true;
    deleteBtn.style.display = 'none';
    const pw = document.getElementById('posProductImagePreview');
    if (pw) { pw.style.display = 'none'; pw.innerHTML = ''; }
  }
  modal.classList.add('active');
  if (typeof feather !== 'undefined') feather.replace();
  setTimeout(() => document.getElementById('posProductName').focus(), 150);
}
function closeProductModal() {
  document.getElementById('posProductModal').classList.remove('active');
}
function previewProductImage() {
  const url  = document.getElementById('posProductImage').value.trim();
  const wrap = document.getElementById('posProductImagePreview');
  if (!wrap) return;
  if (url) { wrap.style.display = 'block'; wrap.innerHTML = `<img src="${escHtml(url)}" onerror="this.parentElement.style.display='none'" />`; }
  else     { wrap.style.display = 'none'; wrap.innerHTML = ''; }
}
function saveProductFromModal() {
  const name      = document.getElementById('posProductName').value.trim();
  const price     = parseFloat(document.getElementById('posProductPrice').value);
  const costPrice = parseFloat(document.getElementById('posProductCostPrice').value) || 0;
  if (!name)                 { if (typeof showToast==='function') showToast('Nama produk wajib diisi','error'); return; }
  if (isNaN(price)||price<0) { if (typeof showToast==='function') showToast('Harga tidak valid','error'); return; }
  const id   = document.getElementById('posProductId').value;
  const data = {
    name, price, costPrice,
    desc:       document.getElementById('posProductDesc').value.trim(),
    categoryId: document.getElementById('posProductCategory').value,
    onhandQty:  parseFloat(document.getElementById('posProductOnhandQty')?.value) || 0,
    imageUrl:   document.getElementById('posProductImage').value.trim(),
    available:  document.getElementById('posProductAvailable').checked,
  };
  if (id) { const idx = PosState.products.findIndex(p => p.id===id); if (idx>=0) PosState.products[idx] = {...PosState.products[idx],...data}; }
  else    { PosState.products.push({ id:'prod_'+Date.now(), ...data }); }
  savePosData();
  closeProductModal();
  renderProductGrid();
  renderMasterProductPage();
  if (typeof showToast==='function') showToast(id?'Produk diperbarui':'Produk ditambahkan','success');
}
function confirmDeleteProduct() {
  const id = document.getElementById('posProductId').value;
  if (!id) return;
  const prod = PosState.products.find(p => p.id === id);
  if (!prod || !confirm(`Hapus produk "${prod.name}"?`)) return;
  PosState.products = PosState.products.filter(p => p.id !== id);
  PosState.cart     = PosState.cart.filter(c => c.productId !== id);
  savePosData();
  closeProductModal();
  renderProductGrid();
  renderMasterProductPage();
  renderCart();
  if (typeof showToast==='function') showToast('Produk dihapus','success');
}

// ============================================================
//  MASTER PRODUK PAGE
// ============================================================
function renderMasterProductPage() {
  const tbody = document.getElementById('mpTableBody');
  if (!tbody) return;

  // Populate kategori filter secara dinamis
  const catFilterEl = document.getElementById('mpCatFilter');
  if (catFilterEl) {
    const prevVal = catFilterEl.value;
    const sorted  = PosState.categories.slice().sort((a,b) => (a.sortOrder||0) - (b.sortOrder||0));
    catFilterEl.innerHTML = `<option value="">Semua Kategori</option>` +
      sorted.map(c => `<option value="${escHtml(c.id)}"${c.id===prevVal?' selected':''}>${escHtml(c.name)}</option>`).join('');
  }

  const search = (document.getElementById('mpSearch')?.value || '').toLowerCase();
  const cat    = catFilterEl?.value || '';
  const status = document.getElementById('mpStatusFilter')?.value || '';

  let products = PosState.products.filter(p => {
    const matchSearch = !search || p.name.toLowerCase().includes(search) || (p.desc||'').toLowerCase().includes(search);
    const matchCat    = !cat    || p.categoryId === cat;
    const matchStatus = !status || (status==='available' ? p.available : !p.available);
    return matchSearch && matchCat && matchStatus;
  });

  if (!products.length) {
    tbody.innerHTML = `<tr><td colspan="7" class="empty-row">Tidak ada produk ditemukan</td></tr>`;
    if (typeof feather!=='undefined') feather.replace();
    return;
  }
  tbody.innerHTML = products.map(p => {
    const imgCell = p.imageUrl
      ? `<img src="${escHtml(p.imageUrl)}" class="mp-thumb" alt="${escHtml(p.name)}" onerror="this.outerHTML='<div class=mp-thumb-placeholder>🍽️</div>'">`
      : `<div class="mp-thumb-placeholder">🍽️</div>`;
    const catBadge    = `<span class="mp-cat-badge ${getCategoryColor(p.categoryId)}">${getCategoryLabel(p.categoryId)}</span>`;
    const statusBadge = p.available
      ? `<span class="mp-status-badge on">● Available</span>`
      : `<span class="mp-status-badge off">✕ Not Available</span>`;
    const stokInfo = `<div style="font-size:13px;font-weight:600;color:${(p.onhandQty||0)>0?'var(--primary)':'#94a3b8'}">${p.onhandQty ?? 0}</div><div style="font-size:10px;color:#94a3b8">unit</div>`;
    return `<tr>
      <td>${imgCell}</td>
      <td><div style="font-weight:600;font-size:13px">${escHtml(p.name)}</div>${p.desc?`<div style="font-size:11px;color:#94a3b8;margin-top:2px">${escHtml(p.desc)}</div>`:''}</td>
      <td>${catBadge}</td>
      <td><div style="font-weight:600;color:var(--primary)">${formatRupiahPos(p.price)}</div><div style="font-size:11px;color:#94a3b8">HPP: ${formatRupiahPos(p.costPrice||0)}</div></td>
      <td>${stokInfo}</td>
      <td>${statusBadge}</td>
      <td>
        <div class="action-cell">
          <button class="btn-icon" onclick="showAddProductModal('${p.id}')" title="Edit">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
          </button>
          <button class="btn-icon btn-icon-danger" onclick="quickDeleteProduct('${p.id}')" title="Hapus">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M9 6V4h6v2"/></svg>
          </button>
        </div>
      </td>
    </tr>`;
  }).join('');
  if (typeof feather!=='undefined') feather.replace();
}

function quickDeleteProduct(id) {
  const prod = PosState.products.find(p => p.id === id);
  if (!prod || !confirm(`Hapus produk "${prod.name}"?`)) return;
  PosState.products = PosState.products.filter(p => p.id !== id);
  PosState.cart     = PosState.cart.filter(c => c.productId !== id);
  savePosData();
  renderMasterProductPage();
  renderProductGrid();
  if (typeof showToast==='function') showToast('Produk dihapus','success');
}

// ============================================================
//  MASTER METODE PEMBAYARAN PAGE
// ============================================================
function renderMasterPaymentPage() {
  const tbody = document.getElementById('pmTableBody');
  if (!tbody) return;
  if (!PosState.paymentMethods.length) {
    tbody.innerHTML = `<tr><td colspan="6" class="empty-row">Belum ada metode pembayaran</td></tr>`;
    return;
  }
  tbody.innerHTML = PosState.paymentMethods.map(m => {
    const iconHtml    = `<div class="pm-icon-cell">${fIconSvg(m.icon, 18)}</div>`;
    const typeBadge   = m.requiresCash
      ? `<span class="mp-cat-badge main">Cash (ada kembalian)</span>`
      : `<span class="mp-cat-badge drink">Non-Cash</span>`;
    const statusBadge = m.active
      ? `<span class="mp-status-badge on">● Aktif</span>`
      : `<span class="mp-status-badge off">✕ Nonaktif</span>`;
    const coaCode     = m.coaCode || '-';
    const coaAcct     = (typeof COA !== 'undefined' && COA[coaCode]) ? COA[coaCode] : null;
    const coaLabel    = coaAcct ? `<span style="font-size:11px;color:#64748b">${coaCode} - ${coaAcct.name}</span>` : `<span style="font-size:11px;color:#94a3b8">${coaCode}</span>`;
    return `<tr>
      <td>${iconHtml}</td>
      <td style="font-weight:600;font-size:13px">${escHtml(m.name)}</td>
      <td>${typeBadge}</td>
      <td>${coaLabel}</td>
      <td>${statusBadge}</td>
      <td>
        <div class="action-cell">
          <button class="btn-icon" onclick="showAddPaymentMethodModal('${m.id}')" title="Edit">${fIconSvg('edit-2',14)}</button>
          <button class="btn-icon btn-icon-danger" onclick="quickDeletePaymentMethod('${m.id}')" title="Hapus">${fIconSvg('trash-2',14)}</button>
        </div>
      </td>
    </tr>`;
  }).join('');
  if (typeof feather!=='undefined') feather.replace();
}

function showAddPaymentMethodModal(methodId) {
  const modal     = document.getElementById('posPaymentMethodModal');
  const titleEl   = document.getElementById('pmModalTitle');
  const deleteBtn = document.getElementById('btnDeletePM');

  // Populate COA dropdown (Aset accounts)
  const allAccounts = (typeof getAccountOptions === 'function') ? getAccountOptions() : [];
  const kasAccts    = allAccounts.filter(a => a.type === 'Aset');
  const coaEl       = document.getElementById('pmModalCoaCode');
  if (coaEl) coaEl.innerHTML = kasAccts.map(a => `<option value="${escHtml(a.value)}">${escHtml(a.label)}</option>`).join('');

  if (methodId) {
    const m = PosState.paymentMethods.find(x => x.id === methodId);
    if (!m) return;
    titleEl.textContent = 'Edit Metode Pembayaran';
    document.getElementById('pmModalId').value       = m.id;
    document.getElementById('pmModalName').value     = m.name;
    document.getElementById('pmModalIcon').value     = m.icon;
    document.getElementById('pmModalType').value     = m.requiresCash ? 'cash' : 'non-cash';
    document.getElementById('pmModalActive').checked = m.active;
    if (coaEl) coaEl.value = m.coaCode || '1-1100';
    deleteBtn.style.display = 'inline-flex';
  } else {
    titleEl.textContent = 'Tambah Metode Pembayaran';
    document.getElementById('pmModalId').value       = '';
    document.getElementById('pmModalName').value     = '';
    document.getElementById('pmModalIcon').value     = 'smartphone';
    document.getElementById('pmModalType').value     = 'non-cash';
    document.getElementById('pmModalActive').checked = true;
    if (coaEl) coaEl.value = '1-1100';
    deleteBtn.style.display = 'none';
  }
  modal.classList.add('active');
  if (typeof feather!=='undefined') feather.replace();
  setTimeout(() => document.getElementById('pmModalName').focus(), 150);
}
function closePaymentMethodModal() {
  document.getElementById('posPaymentMethodModal').classList.remove('active');
}
function togglePmCashOption() { /* placeholder for future use */ }
function savePaymentMethodFromModal() {
  const name = document.getElementById('pmModalName').value.trim();
  if (!name) { if (typeof showToast==='function') showToast('Nama metode wajib diisi','error'); return; }
  const id   = document.getElementById('pmModalId').value;
  const data = {
    name,
    icon:         document.getElementById('pmModalIcon').value,
    requiresCash: document.getElementById('pmModalType').value === 'cash',
    active:       document.getElementById('pmModalActive').checked,
    coaCode:      document.getElementById('pmModalCoaCode')?.value || '1-1100',
  };
  if (id) {
    const idx = PosState.paymentMethods.findIndex(m => m.id === id);
    if (idx >= 0) PosState.paymentMethods[idx] = { ...PosState.paymentMethods[idx], ...data };
  } else {
    PosState.paymentMethods.push({ id:'pm_'+Date.now(), ...data });
  }
  savePosData();
  closePaymentMethodModal();
  renderMasterPaymentPage();
  if (typeof showToast==='function') showToast(id?'Metode diperbarui':'Metode ditambahkan','success');
}
function confirmDeletePaymentMethod() {
  const id = document.getElementById('pmModalId').value;
  if (!id) return;
  const m = PosState.paymentMethods.find(x => x.id === id);
  if (!m || !confirm(`Hapus metode "${m.name}"?`)) return;
  PosState.paymentMethods = PosState.paymentMethods.filter(x => x.id !== id);
  savePosData();
  closePaymentMethodModal();
  renderMasterPaymentPage();
  if (typeof showToast==='function') showToast('Metode dihapus','success');
}
function quickDeletePaymentMethod(id) {
  const m = PosState.paymentMethods.find(x => x.id === id);
  if (!m || !confirm(`Hapus metode "${m.name}"?`)) return;
  PosState.paymentMethods = PosState.paymentMethods.filter(x => x.id !== id);
  savePosData();
  renderMasterPaymentPage();
  if (typeof showToast==='function') showToast('Metode dihapus','success');
}

// ============================================================
//  LAPORAN POS PAGE
// ============================================================
function renderPOSSessionReport() {
  const tbody = document.getElementById('posSessionTableBody');
  if (!tbody) return;

  // Date filter
  const fromEl = document.getElementById('posSessionFrom');
  const toEl   = document.getElementById('posSessionTo');
  const fromDate = fromEl?.value ? new Date(fromEl.value + 'T00:00:00') : new Date('2020-01-01');
  const toDate   = toEl?.value   ? new Date(toEl.value   + 'T23:59:59') : new Date('2099-12-31');

  const sessions = PosState.sessions.filter(s => {
    const d = new Date(s.openedAt);
    return d >= fromDate && d <= toDate;
  });

  if (!sessions.length) {
    tbody.innerHTML = `<tr><td colspan="12" class="empty-row">Belum ada sesi POS</td></tr>`;
    return;
  }
  tbody.innerHTML = sessions.map(s => {
    const openedAt = new Date(s.openedAt).toLocaleString('id-ID');
    const closedAt = s.closedAt ? new Date(s.closedAt).toLocaleString('id-ID') : '-';
    const statusBadge = s.status === 'open'
      ? `<span class="mp-status-badge on">● Buka</span>`
      : `<span class="mp-status-badge off">✓ Tutup</span>`;
    const journalLink = s.journalId
      ? `<button class="btn-link-primary" onclick="event.stopPropagation();navigateTo('journal')" title="Lihat ${escHtml(s.journalId)}">${escHtml(s.journalId)}</button>`
      : `<span style="font-size:11px;color:#94a3b8">-</span>`;
    // Subtotal = Total + Diskon - Service - Tax
    const sub = (s.summary?.totalRevenue||0) + (s.summary?.totalDiscount||0)
              - (s.summary?.totalService||0) - (s.summary?.totalTax||0);
    return `<tr class="pos-session-row" onclick="toggleSessionDetail('${escHtml(s.id)}')" style="cursor:pointer">
      <td style="font-size:12px;font-weight:600;color:var(--primary)">${escHtml(s.id)}</td>
      <td style="font-size:12px">${openedAt}</td>
      <td style="font-size:12px">${closedAt}</td>
      <td style="font-weight:600">${s.summary?.totalOrders || 0}</td>
      <td>${formatRupiahPos(sub)}</td>
      <td style="color:var(--danger)">-${formatRupiahPos(s.summary?.totalDiscount||0)}</td>
      <td>${formatRupiahPos(s.summary?.totalService||0)}</td>
      <td>${formatRupiahPos(s.summary?.totalTax||0)}</td>
      <td style="font-weight:700;color:var(--primary)">${formatRupiahPos(s.summary?.totalRevenue||0)}</td>
      <td style="color:var(--danger)">${formatRupiahPos(s.summary?.totalCogs||0)}</td>
      <td>${statusBadge}</td>
      <td>${journalLink}</td>
    </tr>
    <tr class="session-detail-row" id="sess-detail-${escHtml(s.id)}" style="display:none">
      <td colspan="12" style="padding:0"></td>
    </tr>`;
  }).join('');
  if (typeof feather !== 'undefined') feather.replace();
}

function toggleSessionDetail(sessionId) {
  const detailRow = document.getElementById('sess-detail-' + sessionId);
  if (!detailRow) return;
  const isOpen = detailRow.style.display !== 'none';
  if (isOpen) { detailRow.style.display = 'none'; return; }

  const sess   = PosState.sessions.find(s => s.id === sessionId);
  const orders = PosState.orders.filter(o => sess?.orderIds?.includes(o.id));

  const rowsHtml = orders.length
    ? orders.map(o => `<tr>
        <td style="font-size:11px;color:var(--primary);font-weight:600">${escHtml(o.id)}</td>
        <td style="font-size:11px">${new Date(o.date).toLocaleTimeString('id-ID')}</td>
        <td style="font-size:11px">${escHtml(o.items.map(i => i.name + ' ×' + i.qty).join(', '))}</td>
        <td><span class="pos-report-method-badge">${escHtml(o.paymentMethodName||'-')}</span></td>
        <td>${formatRupiahPos(o.subtotal)}</td>
        <td style="color:var(--danger)">-${formatRupiahPos(o.discount||0)}</td>
        <td>${formatRupiahPos(o.service||0)}</td>
        <td>${formatRupiahPos(o.tax||0)}</td>
        <td style="font-weight:700">${formatRupiahPos(o.total)}</td>
      </tr>`).join('')
    : `<tr><td colspan="9" style="text-align:center;color:#94a3b8;padding:8px">Tidak ada order</td></tr>`;

  detailRow.querySelector('td').innerHTML = `
    <div class="session-detail-box">
      <table class="session-detail-table">
        <thead><tr>
          <th>Order ID</th><th>Waktu</th><th>Produk</th><th>Metode</th>
          <th>Subtotal</th><th>Diskon</th><th>Service</th><th>Pajak</th><th>Total</th>
        </tr></thead>
        <tbody>${rowsHtml}</tbody>
      </table>
    </div>`;
  detailRow.style.display = '';
}

function setPosSessionRange(range) {
  const now   = new Date();
  const today = now.toISOString().slice(0,10);
  let from = '2020-01-01', to = today;
  if (range === 'month') {
    from = `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-01`;
  } else if (range === 'today') {
    from = today;
  }
  const fromEl = document.getElementById('posSessionFrom');
  const toEl   = document.getElementById('posSessionTo');
  if (fromEl) fromEl.value = from;
  if (toEl)   toEl.value   = to;
  renderPOSSessionReport();
}

function switchPosReportTab(tab) {
  document.querySelectorAll('.pos-report-tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
  document.querySelectorAll('.pos-report-tab-panel').forEach(p => p.style.display = p.dataset.panel === tab ? 'block' : 'none');
  if (tab === 'sessions') renderPOSSessionReport();
  if (tab === 'analytics') renderPOSReportPage();
}

function setPosReportRange(range) {
  const now   = new Date();
  const today = now.toISOString().slice(0,10);
  let from = today, to = today;
  if (range === 'week') {
    const d = new Date(now); d.setDate(d.getDate() - 6);
    from = d.toISOString().slice(0,10);
  } else if (range === 'month') {
    from = `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-01`;
  } else if (range === 'all') {
    from = '2020-01-01';
    to   = today;
  }
  const fromEl = document.getElementById('posReportFrom');
  const toEl   = document.getElementById('posReportTo');
  if (fromEl) fromEl.value = from;
  if (toEl)   toEl.value   = to;
  // Reset session filter when date range changes
  const sf = document.getElementById('posReportSessionFilter');
  if (sf) sf.value = 'all';
  renderPOSReportPage();
}

function renderPOSReportPage() {
  // Set default date range if empty
  const fromEl = document.getElementById('posReportFrom');
  const toEl   = document.getElementById('posReportTo');
  if (!fromEl || !toEl) return;
  if (!fromEl.value || !toEl.value) setPosReportRange('month');

  const fromDate = new Date(fromEl.value + 'T00:00:00');
  const toDate   = new Date(toEl.value   + 'T23:59:59');

  // ── Session filter dropdown ──────────────────────
  const sfEl = document.getElementById('posReportSessionFilter');
  if (sfEl) {
    const currentFilter = sfEl.value || 'all';
    sfEl.innerHTML = '<option value="all">Semua Sesi</option>' +
      PosState.sessions.filter(s => s.status === 'closed').map(s =>
        `<option value="${escHtml(s.id)}" ${s.id === currentFilter ? 'selected' : ''}>${escHtml(s.id)} (${new Date(s.closedAt).toLocaleDateString('id-ID')})</option>`
      ).join('');
    sfEl.value = currentFilter;
  }
  const sessionFilter = sfEl?.value || 'all';

  // Filter orders by date + optional session
  const filtered = PosState.orders.filter(o => {
    const d = new Date(o.date);
    const inRange   = d >= fromDate && d <= toDate;
    const inSession = sessionFilter === 'all' || o.sessionId === sessionFilter;
    return inRange && inSession;
  });

  // ── KPI Row 1 ────────────────────────────────────
  const totalRevenue  = filtered.reduce((s, o) => s + o.total, 0);
  const totalOrders   = filtered.length;
  const avgRevenue    = totalOrders ? totalRevenue / totalOrders : 0;

  const prodQty = {};
  filtered.forEach(o => o.items.forEach(i => { prodQty[i.name] = (prodQty[i.name] || 0) + i.qty; }));
  const topProd     = Object.entries(prodQty).sort((a,b) => b[1]-a[1])[0];
  const topProdName = topProd ? topProd[0] : '-';
  const topProdQty  = topProd ? topProd[1] : 0;

  const methodCount = {};
  filtered.forEach(o => { const n = o.paymentMethodName||o.paymentMethodId||'Unknown'; methodCount[n] = (methodCount[n]||0)+1; });
  const topMethod = Object.entries(methodCount).sort((a,b) => b[1]-a[1])[0];

  // ── KPI Row 2 ────────────────────────────────────
  const sessionsInRange = PosState.sessions.filter(s =>
    s.status === 'closed' && s.closedAt &&
    new Date(s.closedAt) >= fromDate && new Date(s.closedAt) <= toDate &&
    (sessionFilter === 'all' || s.id === sessionFilter)
  );
  const totalCogs     = filtered.reduce((s,o) => s + o.items.reduce((si,i) => si + (i.lineCost||0), 0), 0);
  const totalDiscount = filtered.reduce((s,o) => s + (o.discount||0), 0);
  const totalService  = filtered.reduce((s,o) => s + (o.service||0), 0);
  const grossMargin   = totalRevenue - totalCogs - totalDiscount;
  const marginPct     = totalRevenue > 0 ? ((grossMargin / totalRevenue) * 100).toFixed(1) : 0;

  const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
  // Row 1
  set('rKpiRevenue',        formatRupiahPos(totalRevenue));
  set('rKpiOrders',         `${totalOrders} transaksi`);
  set('rKpiAvg',            formatRupiahPos(Math.round(avgRevenue)));
  set('rKpiTopProduct',     topProdName);
  set('rKpiTopQty',         `${topProdQty} terjual`);
  set('rKpiTopMethod',      topMethod ? topMethod[0] : '-');
  set('rKpiTopMethodCount', topMethod ? `${topMethod[1]} transaksi` : '0 transaksi');
  // Row 2
  set('rKpiSessions',    sessionsInRange.length);
  set('rKpiSessionsSub', 'sesi ditutup');
  set('rKpiMargin',      formatRupiahPos(grossMargin));
  set('rKpiMarginPct',   `${marginPct}%`);
  set('rKpiDiscount',    formatRupiahPos(totalDiscount));
  set('rKpiDiscountSub', totalRevenue > 0 ? `${((totalDiscount/totalRevenue)*100).toFixed(1)}% dari revenue` : '-');
  set('rKpiService',     formatRupiahPos(totalService));
  set('rKpiServiceSub',  `${PosState.settings.serviceRate||0}% service rate`);

  // ── CHART 1: Revenue per day (Line) ──────────────
  const dayMap = {};
  filtered.forEach(o => {
    const day = o.date.slice(0,10);
    dayMap[day] = (dayMap[day] || 0) + o.total;
  });
  const sortedDays = Object.keys(dayMap).sort();
  const dayLabels = sortedDays.map(d => new Date(d+'T12:00:00').toLocaleDateString('id-ID',{day:'2-digit',month:'short'}));
  _posChart('posRevenueChart', 'line', {
    labels: dayLabels,
    datasets: [{
      label: 'Pendapatan',
      data: sortedDays.map(d => dayMap[d]),
      borderColor: '#2563eb',
      backgroundColor: 'rgba(37,99,235,0.08)',
      tension: 0.35, fill: true,
      pointRadius: 4, pointBackgroundColor: '#2563eb'
    }]
  }, {
    scales: {
      y: { ticks: { callback: v => 'Rp '+v.toLocaleString('id-ID'), font:{size:11} }, grid:{color:'#f1f5f9'} },
      x: { ticks: { font:{size:11} }, grid:{display:false} }
    },
    plugins: { legend:{display:false}, tooltip:{ callbacks:{ label: ctx => 'Rp '+ctx.parsed.y.toLocaleString('id-ID') } } }
  });

  // ── CHART 2: Revenue by Payment Method (Doughnut) ──
  const methodRevenue = {};
  filtered.forEach(o => { const n = o.paymentMethodName||'Unknown'; methodRevenue[n] = (methodRevenue[n]||0)+o.total; });
  const pmEntries = Object.entries(methodRevenue);
  _posChart('posPaymentChart', 'doughnut', {
    labels: pmEntries.map(e=>e[0]),
    datasets: [{ data: pmEntries.map(e=>e[1]), backgroundColor: ['#2563eb','#22c55e','#f59e0b','#ef4444','#8b5cf6','#06b6d4'], borderWidth:2, borderColor:'#fff' }]
  }, {
    plugins: {
      legend: { position:'bottom', labels:{ font:{size:11}, padding:12 } },
      tooltip: { callbacks:{ label: ctx => ctx.label+': Rp '+ctx.parsed.toLocaleString('id-ID') } }
    },
    cutout: '60%'
  });

  // ── CHART 3: Top 10 Products (Horizontal Bar) ──
  const topProds = Object.entries(prodQty).sort((a,b)=>b[1]-a[1]).slice(0,10);
  _posChart('posTopProductChart', 'bar', {
    labels: topProds.map(e => e[0].length > 18 ? e[0].slice(0,17)+'…' : e[0]),
    datasets: [{ label:'Qty Terjual', data: topProds.map(e=>e[1]), backgroundColor:'rgba(37,99,235,0.75)', borderRadius:6 }]
  }, {
    indexAxis: 'y',
    scales: { x: { ticks:{font:{size:11}}, grid:{color:'#f1f5f9'} }, y: { ticks:{font:{size:11}}, grid:{display:false} } },
    plugins: { legend:{display:false} }
  });

  // ── CHART 4: Revenue by Category (Doughnut) ──
  const catRevenue = {};
  filtered.forEach(o => o.items.forEach(i => {
    const prod = PosState.products.find(p => p.id === i.productId || p.name === i.name);
    const cat  = prod ? getCategoryLabel(prod.category) : 'Lainnya';
    catRevenue[cat] = (catRevenue[cat]||0) + i.lineTotal;
  }));
  const catEntries = Object.entries(catRevenue);
  _posChart('posCategoryChart', 'doughnut', {
    labels: catEntries.map(e=>e[0]),
    datasets: [{ data: catEntries.map(e=>e[1]), backgroundColor: ['#f59e0b','#2563eb','#22c55e','#8b5cf6','#ef4444'], borderWidth:2, borderColor:'#fff' }]
  }, {
    plugins: {
      legend: { position:'bottom', labels:{font:{size:11}, padding:12} },
      tooltip: { callbacks:{ label: ctx => ctx.label+': Rp '+ctx.parsed.toLocaleString('id-ID') } }
    },
    cutout: '60%'
  });

  // ── CHART 5: Diskon & Service Harian (Grouped Bar) ──
  const discMap = {}, svcMap = {};
  filtered.forEach(o => {
    const day = o.date.slice(0,10);
    discMap[day] = (discMap[day]||0) + (o.discount||0);
    svcMap[day]  = (svcMap[day] ||0) + (o.service ||0);
  });
  _posChart('posDiscServiceChart', 'bar', {
    labels: dayLabels,
    datasets: [
      { label:'Diskon',   data: sortedDays.map(d=>discMap[d]||0), backgroundColor:'rgba(239,68,68,0.7)',  borderRadius:4 },
      { label:'Service',  data: sortedDays.map(d=>svcMap[d] ||0), backgroundColor:'rgba(34,197,94,0.7)',  borderRadius:4 }
    ]
  }, {
    scales: { y: { ticks:{ callback: v => 'Rp '+v.toLocaleString('id-ID'), font:{size:11} }, grid:{color:'#f1f5f9'} }, x:{ticks:{font:{size:11}},grid:{display:false}} },
    plugins: { tooltip:{ callbacks:{ label: ctx => ctx.dataset.label+': Rp '+ctx.parsed.y.toLocaleString('id-ID') } } }
  });

  // ── TABLE ──────────────────────────────────────────
  const countEl = document.getElementById('posReportCount');
  if (countEl) countEl.textContent = `${totalOrders} transaksi`;
  const tbody = document.getElementById('posReportTableBody');
  if (!tbody) return;
  if (!filtered.length) {
    tbody.innerHTML = `<tr><td colspan="6"><div class="pos-report-empty">
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
      <p>Tidak ada transaksi dalam rentang ini</p></div></td></tr>`;
    return;
  }
  tbody.innerHTML = filtered.slice(0, 200).map(o => {
    const dateStr  = new Date(o.date).toLocaleString('id-ID');
    const itemsStr = o.items.map(i=>`${i.name} x${i.qty}`).join(', ');
    const method   = o.paymentMethodName || o.paymentMethodId || '-';
    return `<tr>
      <td style="font-weight:600;font-size:12px;color:var(--primary)">${o.id}</td>
      <td style="font-size:12px">${dateStr}</td>
      <td><div class="pos-report-items-cell" title="${escHtml(itemsStr)}">${escHtml(itemsStr)}</div></td>
      <td><span class="pos-report-method-badge">${escHtml(method)}</span></td>
      <td style="font-weight:700;color:var(--primary)">${formatRupiahPos(o.total)}</td>
      <td>
        <button class="btn-icon" onclick="printReceiptFallback(${JSON.stringify(o).replace(/"/g,'&quot;')})" title="Cetak">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 6 2 18 2 18 9"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><rect x="6" y="14" width="12" height="8"/></svg>
        </button>
      </td>
    </tr>`;
  }).join('');
  if (typeof feather!=='undefined') feather.replace();
}

function _posChart(canvasId, type, data, options) {
  const canvas = document.getElementById(canvasId);
  if (!canvas || typeof Chart === 'undefined') return;
  if (PosCharts[canvasId]) { try { PosCharts[canvasId].destroy(); } catch(e){} }
  PosCharts[canvasId] = new Chart(canvas, {
    type,
    data,
    options: {
      responsive: true,
      maintainAspectRatio: true,
      animation: { duration: 400 },
      ...options
    }
  });
}

// ============================================================
//  ORDER HISTORY MODAL
// ============================================================
function showOrderHistory() {
  const body = document.getElementById('posHistoryBody');
  if (!PosState.orders.length) {
    body.innerHTML = '<div class="pos-history-empty">Belum ada transaksi</div>';
  } else {
    body.innerHTML = PosState.orders.map(order => {
      const dateStr   = new Date(order.date).toLocaleString('id-ID');
      const method    = order.paymentMethodName || order.paymentMethodId || '-';
      const itemsHtml = order.items.map(i=>`${i.name} x${i.qty} = ${formatRupiahPos(i.lineTotal)}`).join('<br>');
      return `
        <div class="pos-history-item">
          <div class="pos-history-header">
            <div><div class="pos-history-id">${order.id}</div><div class="pos-history-date">${dateStr}</div></div>
            <div class="pos-history-total">${formatRupiahPos(order.total)}</div>
          </div>
          <div class="pos-history-items-list">${itemsHtml}</div>
          <div class="pos-history-footer">
            <span class="pos-history-method">${escHtml(method)}</span>
            <button class="pos-history-reprint-btn" onclick="printReceiptFallback(${JSON.stringify(order).replace(/"/g,'&quot;')})">
              <svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 6 2 18 2 18 9"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><rect x="6" y="14" width="12" height="8"/></svg>
              Cetak Ulang
            </button>
          </div>
        </div>`;
    }).join('');
  }
  document.getElementById('posHistoryModal').classList.add('active');
  if (typeof feather!=='undefined') feather.replace();
}
function closeHistoryModal() {
  document.getElementById('posHistoryModal').classList.remove('active');
}

// ============================================================
//  BLUETOOTH PRINTING
// ============================================================
async function connectBluetoothPrinter() {
  if (!navigator.bluetooth) {
    if (typeof showToast==='function') showToast('Web Bluetooth tidak didukung. Gunakan Chrome/Edge di localhost atau HTTPS.','error');
    return;
  }
  try {
    if (typeof showToast==='function') showToast('Mencari printer Bluetooth...','info');
    const device = await navigator.bluetooth.requestDevice({
      acceptAllDevices: true,
      optionalServices: ['000018f0-0000-1000-8000-00805f9b34fb','0000ffe0-0000-1000-8000-00805f9b34fb']
    });
    PosState.btDevice = device;
    const btn = document.getElementById('btnBTConnect');
    if (btn) btn.style.background = '#f0fdf4';
    if (typeof showToast==='function') showToast(`Printer "${device.name||'Unknown'}" terhubung!`,'success');
    device.addEventListener('gattserverdisconnected', () => {
      PosState.btDevice = null;
      if (btn) btn.style.background = '';
      if (typeof showToast==='function') showToast('Printer Bluetooth terputus','warning');
    });
  } catch(err) {
    if (err.name !== 'NotFoundError' && typeof showToast==='function') showToast('Gagal connect printer: '+err.message,'error');
  }
}

async function printReceiptBluetooth(order) {
  if (!PosState.btDevice?.gatt) { printReceiptFallback(order); return; }
  try {
    const server  = await PosState.btDevice.gatt.connect();
    const services = await server.getPrimaryServices();
    let char = null;
    for (const svc of services) {
      const chars = await svc.getCharacteristics().catch(()=>[]);
      for (const c of chars) { if (c.properties.write||c.properties.writeWithoutResponse) { char=c; break; } }
      if (char) break;
    }
    if (!char) throw new Error('Karakteristik printer tidak ditemukan');
    const bytes = buildEscPosBytes(order);
    const CHUNK = 20;
    for (let i=0; i<bytes.length; i+=CHUNK) await char.writeValue(bytes.slice(i,i+CHUNK));
    if (typeof showToast==='function') showToast('Struk dicetak via Bluetooth!','success');
  } catch(err) {
    if (typeof showToast==='function') showToast('Print BT gagal: '+err.message+'. Beralih ke browser print...','warning');
    printReceiptFallback(order);
  }
}

function buildEscPosBytes(order) {
  const enc = new TextEncoder();
  const lines = [];
  const addB = (...b) => lines.push(...b);
  const addT = t  => lines.push(...Array.from(enc.encode(t)));
  addB(0x1B,0x40); addB(0x1B,0x61,0x01);
  addB(0x1B,0x45,0x01); addT('==============================\n  PT Global Kreatif Inovasi  \n       POINT OF SALE         \n==============================\n');
  addB(0x1B,0x45,0x00); addB(0x1B,0x61,0x00);
  addT(`No   : ${order.id}\nTgl  : ${new Date(order.date).toLocaleString('id-ID')}\nKasir: ${order.cashier||'-'}\n------------------------------\n`);
  order.items.forEach(i => { addT(`${i.name.substring(0,22).padEnd(22)} x${i.qty}\n  = ${formatRupiahPos(i.lineTotal)}\n`); });
  addT('------------------------------\n');
  addT(`Subtotal  : ${formatRupiahPos(order.subtotal)}\n`);
  if (order.discount>0) addT(`Diskon    : -${formatRupiahPos(order.discount)}\n`);
  if ((order.service||0)>0) addT(`Service   : ${formatRupiahPos(order.service)}\n`);
  addT(`Pajak ${PosState.settings.taxRate}% : ${formatRupiahPos(order.tax)}\n`);
  addB(0x1B,0x45,0x01); addT(`TOTAL     : ${formatRupiahPos(order.total)}\n`); addB(0x1B,0x45,0x00);
  const m = order.paymentMethodName || order.paymentMethodId || '-';
  addT(`Bayar     : ${m}\n`);
  const pm = PosState.paymentMethods.find(x => x.id===order.paymentMethodId);
  if (pm?.requiresCash) { addT(`Tunai     : ${formatRupiahPos(order.cashAmount)}\nKembali   : ${formatRupiahPos(order.change)}\n`); }
  addB(0x1B,0x61,0x01); addT('==============================\n  Terima kasih atas kunjungan\n          Anda!\n\n\n');
  addB(0x1D,0x56,0x41,0x10);
  return new Uint8Array(lines);
}

function printReceiptFallback(order) {
  const dateStr   = new Date(order.date).toLocaleString('id-ID');
  const method    = order.paymentMethodName || order.paymentMethodId || '-';
  const pm        = PosState.paymentMethods.find(x => x.id===order.paymentMethodId);
  const itemsHtml = order.items.map(i =>
    `<tr><td>${escHtml(i.name)}</td><td style="text-align:right;white-space:nowrap">x${i.qty}</td><td style="text-align:right;white-space:nowrap">${formatRupiahPos(i.lineTotal)}</td></tr>`
  ).join('');
  const html = `<div style="font-family:'Courier New',monospace;font-size:12px;width:300px;margin:0 auto;padding:20px;">
    <div style="text-align:center;font-weight:700;font-size:14px;margin-bottom:4px;">PT Global Kreatif Inovasi</div>
    <div style="text-align:center;margin-bottom:8px;">POINT OF SALE</div>
    <hr style="border:none;border-top:1px dashed #000;margin:6px 0">
    <div>No  : ${order.id}</div><div>Tgl : ${dateStr}</div><div>Kasir: ${escHtml(order.cashier||'-')}</div>
    <hr style="border:none;border-top:1px dashed #000;margin:6px 0">
    <table style="width:100%;border-collapse:collapse;"><tbody>${itemsHtml}</tbody></table>
    <hr style="border:none;border-top:1px dashed #000;margin:6px 0">
    <div style="display:flex;justify-content:space-between"><span>Subtotal</span><span>${formatRupiahPos(order.subtotal)}</span></div>
    ${order.discount>0?`<div style="display:flex;justify-content:space-between"><span>Diskon</span><span>-${formatRupiahPos(order.discount)}</span></div>`:''}
    ${(order.service||0)>0?`<div style="display:flex;justify-content:space-between"><span>Service (${PosState.settings.serviceRate}%)</span><span>${formatRupiahPos(order.service)}</span></div>`:''}
    <div style="display:flex;justify-content:space-between"><span>Pajak (${PosState.settings.taxRate}%)</span><span>${formatRupiahPos(order.tax)}</span></div>
    <div style="display:flex;justify-content:space-between;font-weight:700;font-size:14px;margin-top:4px;padding-top:4px;border-top:1px dashed #000">
      <span>TOTAL</span><span>${formatRupiahPos(order.total)}</span>
    </div>
    <hr style="border:none;border-top:1px dashed #000;margin:6px 0">
    <div>Metode : ${escHtml(method)}</div>
    ${pm?.requiresCash?`<div>Tunai  : ${formatRupiahPos(order.cashAmount)}</div><div>Kembali: ${formatRupiahPos(order.change)}</div>`:''}
    <hr style="border:none;border-top:1px dashed #000;margin:6px 0">
    <div style="text-align:center;margin-top:8px;">Terima kasih!</div>
  </div>`;
  const win = window.open('','_blank','width=380,height=600,scrollbars=yes');
  if (!win) { if (typeof showToast==='function') showToast('Popup terblokir. Izinkan popup untuk cetak struk.','warning'); return; }
  win.document.write(`<!DOCTYPE html><html><head><title>Struk ${order.id}</title><style>@media print{body{margin:0}}</style></head><body onload="window.print();window.close()">${html}</body></html>`);
  win.document.close();
}

// ============================================================
//  SESSION MANAGEMENT
// ============================================================
function showOpenSessionModal() {
  const activeMethods = PosState.paymentMethods.filter(m => m.active);
  const container = document.getElementById('openSessionBalances');
  if (!container) return;
  container.innerHTML = activeMethods.map(m => `
    <div class="pos-form-group">
      <label>${escHtml(m.name)} — Saldo Awal (Rp)</label>
      <input type="number" id="openBal_${m.id}" class="pos-form-input" value="0" min="0" placeholder="0" />
    </div>`).join('');
  document.getElementById('posOpenSessionModal').classList.add('active');
  if (typeof feather !== 'undefined') feather.replace();
  if (activeMethods.length) setTimeout(() => document.getElementById('openBal_' + activeMethods[0].id)?.focus(), 150);
}
function closeOpenSessionModal() {
  document.getElementById('posOpenSessionModal').classList.remove('active');
}
function confirmOpenSession() {
  const activeMethods = PosState.paymentMethods.filter(m => m.active);
  const openingBalances = activeMethods.map(m => ({
    paymentMethodId:   m.id,
    paymentMethodName: m.name,
    amount: parseFloat(document.getElementById('openBal_' + m.id)?.value) || 0
  }));
  const user = (typeof getCurrentUser === 'function' && getCurrentUser()) ? getCurrentUser().username : 'Kasir';
  const session = {
    id:               'SES-' + Date.now(),
    openedAt:         new Date().toISOString(),
    closedAt:         null,
    openedBy:         user,
    closedBy:         null,
    status:           'open',
    openingBalances,
    closingBalances:  [],
    orderIds:         [],
    journalId:        null,
    summary:          { totalOrders:0, totalRevenue:0, totalDiscount:0, totalService:0, totalTax:0, totalCogs:0 }
  };
  PosState.sessions.unshift(session);
  PosState.currentSession = session.id;
  savePosData();
  closeOpenSessionModal();
  updateSessionChip();
  renderProductGrid();
  if (typeof showToast === 'function') showToast('Sesi POS dibuka!', 'success');
}

function showCloseSessionModal() {
  if (!PosState.currentSession) { if (typeof showToast === 'function') showToast('Tidak ada sesi aktif', 'error'); return; }
  const sess = PosState.sessions.find(s => s.id === PosState.currentSession);
  if (!sess) return;

  // Compute session summary
  const sessionOrders = PosState.orders.filter(o => sess.orderIds.includes(o.id));
  const totalRevenue  = sessionOrders.reduce((s, o) => s + o.total, 0);
  const totalDiscount = sessionOrders.reduce((s, o) => s + (o.discount || 0), 0);
  const totalService  = sessionOrders.reduce((s, o) => s + (o.service || 0), 0);
  const totalTax      = sessionOrders.reduce((s, o) => s + (o.tax || 0), 0);
  const totalCogs     = sessionOrders.reduce((s, o) => s + o.items.reduce((si, i) => si + (i.lineCost || 0), 0), 0);

  // Expected closing per method
  const methodTotals = {};
  sessionOrders.forEach(o => {
    methodTotals[o.paymentMethodId] = (methodTotals[o.paymentMethodId] || 0) + o.total;
  });

  // Build summary HTML
  const summaryEl = document.getElementById('closeSessionSummary');
  if (summaryEl) {
    const openedAt = new Date(sess.openedAt).toLocaleString('id-ID');
    summaryEl.innerHTML = `
      <div class="pos-sess-summary-row"><span>Dibuka Oleh</span><strong>${escHtml(sess.openedBy)}</strong></div>
      <div class="pos-sess-summary-row"><span>Waktu Buka</span><strong>${openedAt}</strong></div>
      <div class="pos-sess-summary-row"><span>Total Order</span><strong>${sessionOrders.length} transaksi</strong></div>
      <div class="pos-sess-summary-row"><span>Subtotal Penjualan</span><strong>${formatRupiahPos(totalRevenue - totalTax - totalService + totalDiscount)}</strong></div>
      <div class="pos-sess-summary-row"><span>Total Diskon</span><strong class="text-danger">-${formatRupiahPos(totalDiscount)}</strong></div>
      <div class="pos-sess-summary-row"><span>Total Service</span><strong>${formatRupiahPos(totalService)}</strong></div>
      <div class="pos-sess-summary-row"><span>Total Pajak</span><strong>${formatRupiahPos(totalTax)}</strong></div>
      <div class="pos-sess-summary-row pos-sess-total"><span>Total Pendapatan</span><strong>${formatRupiahPos(totalRevenue)}</strong></div>
      <div class="pos-sess-summary-row"><span>Total HPP</span><strong class="text-danger">${formatRupiahPos(totalCogs)}</strong></div>`;
  }

  // Build closing balance inputs
  const container = document.getElementById('closeSessionBalances');
  if (container) {
    container.innerHTML = PosState.paymentMethods.filter(m => m.active).map(m => {
      const opening  = (sess.openingBalances.find(b => b.paymentMethodId === m.id)?.amount || 0);
      const expected = opening + (methodTotals[m.id] || 0);
      return `<div class="pos-form-group">
        <label>${escHtml(m.name)} — Saldo Aktual (Rp)<small style="color:#64748b;display:block">Diharapkan: ${formatRupiahPos(expected)}</small></label>
        <input type="number" id="closeBal_${m.id}" class="pos-form-input" value="${expected}" min="0" />
      </div>`;
    }).join('');
  }

  document.getElementById('posCloseSessionModal').classList.add('active');
  if (typeof feather !== 'undefined') feather.replace();
}
function closeCloseSessionModal() {
  document.getElementById('posCloseSessionModal').classList.remove('active');
}
function confirmCloseSession() {
  if (!PosState.currentSession) return;
  const sess = PosState.sessions.find(s => s.id === PosState.currentSession);
  if (!sess) return;

  const activeMethods = PosState.paymentMethods.filter(m => m.active);
  const closingBalances = activeMethods.map(m => ({
    paymentMethodId:   m.id,
    paymentMethodName: m.name,
    amount: parseFloat(document.getElementById('closeBal_' + m.id)?.value) || 0
  }));

  const sessionOrders = PosState.orders.filter(o => sess.orderIds.includes(o.id));
  const totalRevenue  = sessionOrders.reduce((s, o) => s + o.total, 0);
  const totalDiscount = sessionOrders.reduce((s, o) => s + (o.discount || 0), 0);
  const totalService  = sessionOrders.reduce((s, o) => s + (o.service || 0), 0);
  const totalTax      = sessionOrders.reduce((s, o) => s + (o.tax || 0), 0);
  const totalCogs     = sessionOrders.reduce((s, o) => s + o.items.reduce((si, i) => si + (i.lineCost || 0), 0), 0);
  const user = (typeof getCurrentUser === 'function' && getCurrentUser()) ? getCurrentUser().username : 'Kasir';

  sess.closedAt       = new Date().toISOString();
  sess.closedBy       = user;
  sess.status         = 'closed';
  sess.closingBalances = closingBalances;
  sess.summary        = { totalOrders: sessionOrders.length, totalRevenue, totalDiscount, totalService, totalTax, totalCogs };

  // Generate journal
  const journalId = generateSessionJournal(sess, sessionOrders);
  sess.journalId = journalId;

  PosState.currentSession = null;
  savePosData();
  closeCloseSessionModal();
  updateSessionChip();
  renderProductGrid();
  if (typeof showToast === 'function') showToast(`Sesi ditutup. ${journalId ? 'Jurnal ' + journalId + ' dibuat.' : ''}`, 'success');
}

// ============================================================
//  JOURNAL GENERATION FROM SESSION
// ============================================================
function generateSessionJournal(sess, sessionOrders) {
  if (!sessionOrders.length) return null;
  if (typeof AppState === 'undefined' || !Array.isArray(AppState.journals)) return null;

  const s = PosState.settings;
  const entries = [];

  // 1. Payment entries per method: Dr Payment COA = amount collected
  const methodTotals = {};
  sessionOrders.forEach(o => {
    const key = o.paymentCoaCode || '1-1100';
    methodTotals[key] = (methodTotals[key] || { amount: 0, name: o.paymentMethodName });
    methodTotals[key].amount += o.total;
  });
  Object.entries(methodTotals).forEach(([coaCode, info]) => {
    const acct = (typeof COA !== 'undefined' && COA[coaCode]) ? COA[coaCode] : null;
    entries.push({ accountCode: coaCode, accountName: acct ? acct.name : info.name, debit: info.amount, kredit: 0, note: `Penerimaan ${info.name}` });
  });

  // 2. Discount entries: Dr Discount COA per fee + Dr adHocDiscount COA for manual discounts
  //    Build feeMap from appliedFees (new orders) + fallback for legacy orders
  const feeMap = {}; // key: `${category}|${coaCode}` → { category, coaCode, name, total }
  sessionOrders.forEach(o => {
    if (o.appliedFees && o.appliedFees.length > 0) {
      o.appliedFees.forEach(f => {
        const key = `${f.category}|${f.coaCode}`;
        if (!feeMap[key]) feeMap[key] = { category: f.category, coaCode: f.coaCode, name: f.name, total: 0 };
        feeMap[key].total += (f.computed || 0);
      });
    } else {
      // Legacy: orders without appliedFees — use settings COA
      if ((o.service || 0) > 0) {
        const k = `service|${s.serviceCoaCode}`;
        if (!feeMap[k]) feeMap[k] = { category:'service', coaCode:s.serviceCoaCode, name:'Service Charge', total:0 };
        feeMap[k].total += o.service;
      }
      if ((o.tax || 0) > 0) {
        const k = `tax|${s.taxCoaCode}`;
        if (!feeMap[k]) feeMap[k] = { category:'tax', coaCode:s.taxCoaCode, name:'Pajak', total:0 };
        feeMap[k].total += o.tax;
      }
    }
    // Ad-hoc discount (manual Rp input) always goes to settings.discountCoaCode
    const adHoc = o.adHocDiscount || (o.appliedFees ? 0 : (o.discount || 0));
    if (adHoc > 0) {
      const k = `discount|${s.discountCoaCode}`;
      if (!feeMap[k]) feeMap[k] = { category:'discount', coaCode:s.discountCoaCode, name:'Diskon Manual', total:0 };
      feeMap[k].total += adHoc;
    }
  });

  // Write discount (Dr) and service/tax (Cr) entries from feeMap
  Object.values(feeMap).forEach(fee => {
    if (fee.total <= 0) return;
    const acct = (typeof COA !== 'undefined' && COA[fee.coaCode]) ? COA[fee.coaCode] : null;
    if (fee.category === 'discount') {
      entries.push({ accountCode: fee.coaCode, accountName: acct?.name || fee.name, debit: fee.total, kredit: 0, note: `Diskon - ${fee.name}` });
    } else if (fee.category === 'service') {
      entries.push({ accountCode: fee.coaCode, accountName: acct?.name || fee.name, debit: 0, kredit: fee.total, note: `Service - ${fee.name}` });
    } else if (fee.category === 'tax') {
      entries.push({ accountCode: fee.coaCode, accountName: acct?.name || fee.name, debit: 0, kredit: fee.total, note: `Pajak - ${fee.name}` });
    }
  });

  // 3. Revenue entries: Cr income per product incomeAccount (gross subtotal)
  const incomeMap = {};
  sessionOrders.forEach(o => o.items.forEach(i => {
    const coaCode = i.incomeAccount || '4-5000';
    incomeMap[coaCode] = (incomeMap[coaCode] || 0) + i.lineTotal;
  }));
  Object.entries(incomeMap).forEach(([coaCode, amt]) => {
    const acct = (typeof COA !== 'undefined' && COA[coaCode]) ? COA[coaCode] : null;
    entries.push({ accountCode: coaCode, accountName: acct ? acct.name : 'Pendapatan Penjualan', debit: 0, kredit: amt, note: 'Pendapatan penjualan POS' });
  });

  // 4. COGS: Dr COGS COA / Cr Inventory — dikelompokkan per akun dari kategori
  const totalCogs = sess.summary.totalCogs;
  if (totalCogs > 0) {
    const cogsMap = {};     // cogsAccount → totalCost
    const inventoryMap = {}; // inventoryAccount → totalCost
    sessionOrders.forEach(o => o.items.forEach(i => {
      if ((i.lineCost || 0) > 0) {
        const cogsCode = i.cogsAccount      || s.cogsCoaCode;
        const invCode  = i.inventoryAccount || s.inventoryCoaCode;
        cogsMap[cogsCode]      = (cogsMap[cogsCode]     || 0) + (i.lineCost || 0);
        inventoryMap[invCode]  = (inventoryMap[invCode] || 0) + (i.lineCost || 0);
      }
    }));
    Object.entries(cogsMap).forEach(([coaCode, amt]) => {
      const acct = (typeof COA !== 'undefined' && COA[coaCode]) ? COA[coaCode] : null;
      entries.push({ accountCode: coaCode, accountName: acct ? acct.name : 'HPP', debit: amt, kredit: 0, note: 'Harga Pokok Penjualan POS' });
    });
    Object.entries(inventoryMap).forEach(([coaCode, amt]) => {
      const acct = (typeof COA !== 'undefined' && COA[coaCode]) ? COA[coaCode] : null;
      entries.push({ accountCode: coaCode, accountName: acct ? acct.name : 'Persediaan', debit: 0, kredit: amt, note: 'Pengurangan persediaan POS' });
    });
  }

  const jeNum = 'JE-POS-' + String(AppState.journals.length + 1).padStart(4, '0');
  const journal = {
    id:          jeNum,
    txId:        sess.id,
    date:        sess.closedAt.slice(0, 10),
    no:          jeNum,
    description: `Jurnal POS Sesi ${sess.id} — ${sessionOrders.length} transaksi`,
    entries
  };
  // Simpan journal entry ke session agar bisa di-restore saat page reload
  sess.journalEntry = journal;

  AppState.journals.push(journal);
  // Rebuild ledger & laporan keuangan agar POS data langsung terefleksi
  if (typeof buildLedger === 'function') {
    AppState.ledger = buildLedger(AppState.journals);
    _posRebuildReports();
  }
  // Rebuild flat rows using the standard flatten function if available
  if (typeof flattenJournalForTable === 'function') {
    AppState.journalRows = flattenJournalForTable(AppState.journals);
  }
  if (typeof saveToStorage === 'function') saveToStorage();
  return jeNum;
}

// ============================================================
//  POS SETTINGS
// ============================================================
function showPOSSettingsModal() {
  const s = PosState.settings;
  const el = id => document.getElementById(id);

  // Populate COA dropdowns (COGS & Inventory only)
  const allAccounts = (typeof getAccountOptions === 'function') ? getAccountOptions() : [];
  const makeOpts = (codes, selected) => codes.map(a => `<option value="${a.value}"${a.value===selected?' selected':''}>${escHtml(a.label)}</option>`).join('');
  const expAccts = allAccounts.filter(a => a.type === 'Beban');
  const astAccts = allAccounts.filter(a => a.type === 'Aset');

  if (el('posSetCogsCoa'))      el('posSetCogsCoa').innerHTML      = makeOpts(expAccts, s.cogsCoaCode);
  if (el('posSetInventoryCoa')) el('posSetInventoryCoa').innerHTML = makeOpts(astAccts, s.inventoryCoaCode);

  document.getElementById('posPOSSettingsModal').classList.add('active');
  if (typeof feather !== 'undefined') feather.replace();
}
function closePOSSettingsModal() {
  document.getElementById('posPOSSettingsModal').classList.remove('active');
}
function savePOSSettings() {
  const el = id => document.getElementById(id);
  PosState.settings.cogsCoaCode      = el('posSetCogsCoa')?.value      || PosState.settings.cogsCoaCode;
  PosState.settings.inventoryCoaCode = el('posSetInventoryCoa')?.value || PosState.settings.inventoryCoaCode;
  savePosData();
  closePOSSettingsModal();
  if (typeof showToast === 'function') showToast('Pengaturan POS disimpan', 'success');
}

// ============================================================
//  MASTER KATEGORI MANAGEMENT
// ============================================================
let _catEditId = null;

function renderMasterCategoryPage() {
  const tbody = document.getElementById('mcTableBody');
  if (!tbody) return;
  const cats = PosState.categories.slice().sort((a,b) => (a.sortOrder||0) - (b.sortOrder||0));
  if (!cats.length) {
    tbody.innerHTML = `<tr><td colspan="6" class="empty-row">Belum ada kategori</td></tr>`;
    return;
  }
  const getCoaLabel = code => {
    if (!code) return '<span style="color:#94a3b8">-</span>';
    const acct = (typeof COA !== 'undefined' && COA[code]) ? COA[code] : null;
    return acct ? `<span style="font-size:11px">${escHtml(code)} – ${escHtml(acct.name)}</span>` : `<span style="font-size:11px;color:#94a3b8">${escHtml(code)}</span>`;
  };
  tbody.innerHTML = cats.map(c => {
    const prodCount = PosState.products.filter(p => p.categoryId === c.id).length;
    return `<tr>
      <td><span class="mp-cat-badge ${getCategoryColor(c.id)}">${escHtml(c.name)}</span></td>
      <td>${getCoaLabel(c.incomeAccount)}</td>
      <td>${getCoaLabel(c.cogsAccount)}</td>
      <td>${getCoaLabel(c.inventoryAccount)}</td>
      <td style="text-align:center"><span class="mp-status-badge ${prodCount>0?'on':'off'}">${prodCount} produk</span></td>
      <td>
        <div class="action-cell">
          <button class="btn-icon" onclick="showCategoryModal('${c.id}')" title="Edit">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
          </button>
          <button class="btn-icon btn-icon-danger" onclick="deleteCategoryItem('${c.id}')" title="Hapus">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M9 6V4h6v2"/></svg>
          </button>
        </div>
      </td>
    </tr>`;
  }).join('');
  if (typeof feather !== 'undefined') feather.replace();
}

function showCategoryModal(categoryId = null) {
  _catEditId = categoryId;
  const modal    = document.getElementById('posCategoryModal');
  const titleEl  = document.getElementById('catModalTitle');
  const delBtn   = document.getElementById('btnDeleteCategory');
  if (!modal) return;

  // Populate COA dropdowns
  const allAccounts = (typeof getAccountOptions === 'function') ? getAccountOptions() : [];
  const mkOpts = (types, sel) => allAccounts
    .filter(a => types.includes(a.type))
    .map(a => `<option value="${escHtml(a.value)}"${a.value===sel?' selected':''}>${escHtml(a.label)}</option>`)
    .join('');

  const c = categoryId ? PosState.categories.find(x => x.id === categoryId) : null;
  titleEl.textContent = c ? 'Edit Kategori' : 'Tambah Kategori';

  document.getElementById('catFormName').value      = c ? c.name      : '';
  document.getElementById('catFormSortOrder').value = c ? (c.sortOrder||0) : PosState.categories.length;

  const incEl  = document.getElementById('catFormIncomeAccount');
  const cgsEl  = document.getElementById('catFormCogsAccount');
  const invEl  = document.getElementById('catFormInventoryAccount');
  if (incEl) incEl.innerHTML  = mkOpts(['Pendapatan'], c?.incomeAccount    || '4-5000');
  if (cgsEl) cgsEl.innerHTML  = mkOpts(['Beban'],      c?.cogsAccount      || '5-5100');
  if (invEl) invEl.innerHTML  = mkOpts(['Aset'],       c?.inventoryAccount || '1-1400');

  delBtn.style.display = c ? 'inline-flex' : 'none';
  modal.classList.add('active');
  if (typeof feather !== 'undefined') feather.replace();
  setTimeout(() => document.getElementById('catFormName').focus(), 150);
}

function closeCategoryModal() {
  const modal = document.getElementById('posCategoryModal');
  if (modal) modal.classList.remove('active');
  _catEditId = null;
}

function saveCategoryFromModal() {
  const name  = document.getElementById('catFormName').value.trim();
  const incAc = document.getElementById('catFormIncomeAccount')?.value;
  const cgsAc = document.getElementById('catFormCogsAccount')?.value;
  const invAc = document.getElementById('catFormInventoryAccount')?.value;
  if (!name) { if (typeof showToast==='function') showToast('Nama kategori wajib diisi','error'); return; }
  if (!incAc||!cgsAc||!invAc) { if (typeof showToast==='function') showToast('Semua akun COA wajib dipilih','error'); return; }

  const sortOrder = parseInt(document.getElementById('catFormSortOrder')?.value) || 0;
  const data = { name, incomeAccount: incAc, cogsAccount: cgsAc, inventoryAccount: invAc, sortOrder };

  if (_catEditId) {
    const idx = PosState.categories.findIndex(c => c.id === _catEditId);
    if (idx >= 0) PosState.categories[idx] = { ...PosState.categories[idx], ...data };
  } else {
    PosState.categories.push({ id: 'cat_' + Date.now(), ...data });
  }
  savePosData();
  closeCategoryModal();
  renderMasterCategoryPage();
  renderCategoryTabs();
  if (typeof showToast==='function') showToast(_catEditId ? 'Kategori diperbarui' : 'Kategori ditambahkan', 'success');
}

function deleteCategoryItem(id) {
  const count = PosState.products.filter(p => p.categoryId === id).length;
  if (count > 0) {
    if (typeof showToast==='function') showToast(`Tidak bisa hapus — ${count} produk masih menggunakan kategori ini`, 'error');
    return;
  }
  const cat = PosState.categories.find(c => c.id === id);
  if (!cat || !confirm(`Hapus kategori "${cat.name}"?`)) return;
  PosState.categories = PosState.categories.filter(c => c.id !== id);
  savePosData();
  renderMasterCategoryPage();
  renderCategoryTabs();
  if (typeof showToast==='function') showToast('Kategori dihapus', 'success');
}

function confirmDeleteCategory() {
  if (_catEditId) deleteCategoryItem(_catEditId);
  closeCategoryModal();
}

// ============================================================
//  UPDATED PRODUCT MODAL (with COA fields)
// ============================================================
function _buildCoaOptions(filterType, selectedCode) {
  const allAccounts = (typeof getAccountOptions === 'function') ? getAccountOptions() : [];
  const accts = filterType ? allAccounts.filter(a => a.type === filterType) : allAccounts;
  return accts.map(a => `<option value="${escHtml(a.value)}"${a.value===selectedCode?' selected':''}>${escHtml(a.label)}</option>`).join('');
}

// Obsolete — akun COA kini di Master Kategori; stub untuk backward compat
function populateProductCoaDropdowns(prod) { /* akun dipindah ke kategori */ }

// ============================================================
//  FEE MASTER MANAGEMENT (Pajak, Service, Diskon)
// ============================================================
let _feeEditId = null;

function showFeeMasterModal() {
  renderFeeMasterList();
  document.getElementById('posFeeMasterModal').classList.add('active');
  if (typeof feather !== 'undefined') feather.replace();
}
function closeFeeMasterModal() {
  document.getElementById('posFeeMasterModal').classList.remove('active');
}

function renderFeeMasterList() {
  const container = document.getElementById('feeMasterListBody');
  if (!container) return;
  const fees = PosState.feeMasters || [];
  if (!fees.length) {
    container.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#9ca3af;padding:20px">Belum ada biaya terdaftar</td></tr>';
    return;
  }
  const catLabel = { tax: 'Pajak', service: 'Service', discount: 'Diskon' };
  const catClass = { tax: 'tax', service: 'service', discount: 'discount' };
  container.innerHTML = fees.map(f => {
    const amtStr = f.amountType === 'percentage' ? `${f.amount}%` : `Rp ${f.amount.toLocaleString('id-ID')}`;
    const coaName = (typeof COA !== 'undefined' && COA[f.coaCode]) ? `${f.coaCode} – ${COA[f.coaCode].name}` : f.coaCode;
    return `<tr>
      <td>${escHtml(f.name)}</td>
      <td><span class="fee-category-badge ${catClass[f.category]||''}">${catLabel[f.category]||f.category}</span></td>
      <td>${amtStr}</td>
      <td style="font-size:12px;color:#6b7280">${escHtml(coaName)}</td>
      <td><label class="pos-toggle"><input type="checkbox" ${f.active?'checked':''} onchange="toggleFeeActive('${f.id}',this.checked)"><span class="pos-toggle-slider"></span></label></td>
      <td style="display:flex;gap:6px">
        <button class="btn-split-acct" onclick="openFeeFormModal('${f.id}')">${fIconSvg('edit-2',13)}</button>
        <button class="btn-split-acct btn-danger-sm" onclick="deleteFeeItem('${f.id}')">${fIconSvg('trash-2',13)}</button>
      </td>
    </tr>`;
  }).join('');
}

function openFeeFormModal(id = null) {
  _feeEditId = id;
  const titleEl = document.getElementById('feeFormTitle');
  if (titleEl) titleEl.textContent = id ? 'Edit Biaya' : 'Tambah Biaya';

  const f = id ? (PosState.feeMasters || []).find(x => x.id === id) : null;

  const nameEl = document.getElementById('feeFormName');
  const catEl  = document.getElementById('feeFormCategory');
  const typeEl = document.getElementById('feeFormAmountType');
  const amtEl  = document.getElementById('feeFormAmount');
  const actEl  = document.getElementById('feeFormActive');

  if (nameEl) nameEl.value = f ? f.name : '';
  if (catEl)  catEl.value  = f ? f.category : 'tax';
  if (typeEl) typeEl.value = f ? f.amountType : 'percentage';
  if (amtEl)  amtEl.value  = f ? f.amount : '';
  if (actEl)  actEl.checked = f ? f.active : true;

  _updateFeeFormCoaDropdown(f ? f.category : 'tax', f ? f.coaCode : '');
  document.getElementById('posFeeFormModal').classList.add('active');
  if (typeof feather !== 'undefined') feather.replace();
}
function closeFeeFormModal() {
  document.getElementById('posFeeFormModal').classList.remove('active');
  _feeEditId = null;
}

function _updateFeeFormCoaDropdown(category, selected) {
  const coaEl = document.getElementById('feeFormCoa');
  if (!coaEl) return;
  const allAccounts = (typeof getAccountOptions === 'function') ? getAccountOptions() : [];
  let filtered = allAccounts;
  if (category === 'tax')      filtered = allAccounts.filter(a => a.type === 'Liabilitas');
  else if (category === 'service')  filtered = allAccounts.filter(a => a.type === 'Pendapatan');
  else if (category === 'discount') filtered = allAccounts.filter(a => a.type === 'Pendapatan');
  coaEl.innerHTML = filtered.map(a =>
    `<option value="${escHtml(a.value)}"${a.value===selected?' selected':''}>${escHtml(a.label)}</option>`
  ).join('');
}

function onFeeFormCategoryChange() {
  const cat = document.getElementById('feeFormCategory')?.value;
  const cur = document.getElementById('feeFormCoa')?.value;
  _updateFeeFormCoaDropdown(cat, cur);
}

function saveFeeItem() {
  const name    = document.getElementById('feeFormName')?.value.trim();
  const cat     = document.getElementById('feeFormCategory')?.value;
  const type    = document.getElementById('feeFormAmountType')?.value;
  const amount  = parseFloat(document.getElementById('feeFormAmount')?.value);
  const coaCode = document.getElementById('feeFormCoa')?.value;
  const active  = document.getElementById('feeFormActive')?.checked ?? true;

  if (!name)   { if (typeof showToast === 'function') showToast('Nama biaya wajib diisi', 'warning'); return; }
  if (isNaN(amount) || amount <= 0) { if (typeof showToast === 'function') showToast('Jumlah harus > 0', 'warning'); return; }
  if (!coaCode) { if (typeof showToast === 'function') showToast('COA wajib dipilih', 'warning'); return; }

  if (_feeEditId) {
    const idx = (PosState.feeMasters || []).findIndex(f => f.id === _feeEditId);
    if (idx >= 0) PosState.feeMasters[idx] = { ...PosState.feeMasters[idx], name, category: cat, amountType: type, amount, coaCode, active };
  } else {
    const newId = 'fee_' + Date.now();
    PosState.feeMasters.push({ id: newId, name, category: cat, amountType: type, amount, coaCode, active });
  }

  savePosData();
  renderFeeMasterList();
  renderCartSummary();
  closeFeeFormModal();
  if (typeof showToast === 'function') showToast(_feeEditId ? 'Biaya diperbarui' : 'Biaya ditambahkan', 'success');
}

function deleteFeeItem(id) {
  if (!confirm('Hapus item biaya ini?')) return;
  PosState.feeMasters = (PosState.feeMasters || []).filter(f => f.id !== id);
  savePosData();
  renderFeeMasterList();
  renderCartSummary();
  if (typeof showToast === 'function') showToast('Biaya dihapus', 'success');
}

function toggleFeeActive(id, checked) {
  const f = (PosState.feeMasters || []).find(x => x.id === id);
  if (f) { f.active = checked; savePosData(); renderCartSummary(); }
}

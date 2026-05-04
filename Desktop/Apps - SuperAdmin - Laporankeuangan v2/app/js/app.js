/**
 * APP.JS - Main Application Controller
 * Mengelola state, navigasi, dan semua interaksi UI
 */

// ===== ICON HELPER =====
function fIcon(name, size = 16) {
  if (typeof feather !== 'undefined' && feather.icons[name]) {
    return feather.icons[name].toSvg({ width: size, height: size });
  }
  return '';
}

// ===== APPLICATION STATE =====
const AppState = {
  statements: [],         // Array parsed statements
  merged: null,           // Merged statement data
  transactions: [],       // Semua transaksi
  journals: [],           // Jurnal entries
  journalRows: [],        // Flat journal rows untuk tabel
  ledger: {},             // Buku besar
  incomeData: null,       // Laporan L/R
  balanceData: null,      // Neraca
  cfData: null,           // Arus Kas
  summary: null,          // Ringkasan
  header: null,           // Info akun

  // UI state
  currentPage: 'dashboard',
  txPage: 1,
  txPerPage: 50,
  txFilter: { search: '', type: '', categories: [], dateFrom: '', dateTo: '' },
  reportFilter: { income: { from: '', to: '' }, balance: { from: '', to: '' }, cashflow: { from: '', to: '' } },

  // Lock state
  isLocked: false,

  // Charts
  charts: {}
};

// ===== STORAGE (full-online mode) =====
// Backend FastAPI is the source of truth. Bank-statement PDF parsing stays
// in-memory only — users re-upload statements per session if needed.
const STORAGE_KEY = 'finreport_gki_v1';

function saveToStorage() {
  return;  // No-op in full-online mode
}

function clearStorage() {
  // No-op
}

function loadFromStorage() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return false;
    const data = JSON.parse(raw);
    if (!data.statements?.length) return false;

    // Restore statements, pastikan coaMapping ada
    const statements = data.statements.map(s => ({
      ...s,
      transactions: s.transactions.map(tx => ({
        ...tx,
        raw: '',
        coaMapping: tx.coaMapping || autoMapTransaction(tx)
      }))
    }));

    const merged = mergeStatements(statements);
    AppState.statements = statements;
    AppState.merged = merged;
    AppState.transactions = merged.transactions;
    AppState.summary = merged.summary;
    AppState.header = merged.accountInfo;
    AppState.isLocked = data.isLocked || false;

    AppState.journals = generateJournalEntries(AppState.transactions);
    // Merge jurnal POS (loadPosData sudah run, PosState.sessions tersedia)
    if (typeof _mergePosJournalsInto    === 'function') _mergePosJournalsInto(AppState.journals);
    if (typeof _mergeManualJournalsInto === 'function') _mergeManualJournalsInto(AppState.journals);
    AppState.journalRows = flattenJournalForTable(AppState.journals);
    AppState.ledger = buildLedger(AppState.journals);

    const periods = merged.periods.filter(Boolean);
    const periodLabel = periods.length > 1
      ? `Periode: ${periods[0]} s/d ${periods[periods.length - 1]}`
      : `Periode: ${periods[0] || 'N/A'}`;
    const company = 'PT Global Kreatif Inovasi';

    AppState.incomeData = generateIncomeStatement(AppState.ledger, periodLabel, company);
    AppState.balanceData = generateBalanceSheet(AppState.ledger, merged.summary, periodLabel, company);
    AppState.cfData = generateCashflowReport(AppState.transactions, merged.summary, periodLabel, company);

    updateAllViews(merged, periodLabel);
    applyLockState(AppState.isLocked);

    document.getElementById('btnExportSheet').disabled = false;
    document.getElementById('btnExportXlsx').disabled = false;
    document.getElementById('btnLock').disabled = false;
    document.getElementById('btnHardReset').disabled = false;
    updateResetDataSection();

    const sidebarComp = document.getElementById('sidebarCompany');
    sidebarComp.innerHTML = `<div class="company-dot"></div><span>${periods.join(', ')}</span>`;

    const txCount = AppState.transactions.filter(t => t.type !== 'SALDO_AWAL').length;
    showToast(`Data dipulihkan: ${txCount} transaksi`, 'success');
    return true;
  } catch(e) {
    console.warn('[Storage] Load failed:', e);
    return false;
  }
}

// ===== SIDEBAR FLYOUT =====
const FLYOUT_GROUPS = {
  accounting: {
    label: 'Accounting',
    items: [
      { page: 'dashboard',    icon: 'home',         label: 'Dashboard' },
      { page: 'upload',       icon: 'upload-cloud', label: 'Upload Statement' },
      { page: 'transactions', icon: 'list',         label: 'Transaksi' },
      { page: 'journal',      icon: 'book-open',    label: 'Jurnal Entri' },
      { page: 'coa',          icon: 'grid',         label: 'Chart of Accounts' },
      { page: 'income',       icon: 'trending-up',  label: 'Laba Rugi' },
      { page: 'balance',      icon: 'bar-chart-2',  label: 'Neraca' },
      { page: 'cashflow',     icon: 'activity',     label: 'Arus Kas' },
      { page: 'users',        icon: 'users',        label: 'Manajemen User' },
    ]
  },
  sales: {
    label: 'Sales',
    items: [
      { page: 'pos',                 icon: 'monitor',      label: 'Point of Sale' },
      { page: 'pos-products',        icon: 'package',      label: 'Master Produk' },
      { page: 'pos-categories',      icon: 'tag',          label: 'Master Kategori' },
      { page: 'pos-payment-methods', icon: 'credit-card',  label: 'Metode Pembayaran' },
      { page: 'pos-report',          icon: 'bar-chart-2',  label: 'Laporan POS' },
      { action: 'showFeeMasterModal',   icon: 'percent',  label: '% Biaya' },
      { action: 'showPOSSettingsModal', icon: 'settings', label: 'Setting' },
      { page: 'customer-master',        icon: 'user-check',   label: 'Master Customer' },
      { page: 'customer-invoices',      icon: 'file-text',    label: 'Customer Invoice' },
      { page: 'customer-payments',      icon: 'dollar-sign',  label: 'Penerimaan' },
      { page: 'customer-report',        icon: 'bar-chart-2',  label: 'Laporan Invoice' },
    ]
  },
  purchase: {
    label: 'Purchase',
    items: [
      { page: 'purchase-vendors',  icon: 'users',       label: 'Master Vendor' },
      { page: 'purchase-bills',    icon: 'file-text',   label: 'Vendor Bill' },
      { page: 'purchase-report',   icon: 'bar-chart-2', label: 'Laporan Vendor Bill' },
      { page: 'purchase-payments', icon: 'send',        label: 'Payment' },
    ]
  },
  inventory: {
    label: 'Inventory',
    items: [
      { page: 'inventory',            icon: 'package',         label: 'Items & Gudang' },
      { page: 'inventory-movements',  icon: 'refresh-cw',      label: 'Pergerakan Stok' },
      { page: 'inventory-transfers',  icon: 'repeat',          label: 'Transfer Stok' },
      { page: 'inv-onhand',           icon: 'archive',         label: 'Stock On-Hand' },
      { page: 'inv-valuation',        icon: 'dollar-sign',     label: 'Stock Valuation' },
      { page: 'inv-stockcard',        icon: 'file-text',       label: 'Kartu Stok' },
      { page: 'inv-reorder',          icon: 'alert-circle',    label: 'Reorder Report' },
      { page: 'inv-slowmoving',       icon: 'clock',           label: 'Slow-Moving' },
      { page: 'inv-costing',          icon: 'layers',          label: 'Costing Method' },
    ]
  },
  payments: {
    label: 'Payments',
    items: [
      { page: 'payments',        icon: 'dollar-sign',  label: 'Semua Pembayaran' },
      { page: 'payments-in',     icon: 'arrow-down-circle', label: 'Penerimaan' },
      { page: 'payments-out',    icon: 'arrow-up-circle',   label: 'Pengeluaran' },
    ]
  }
};

let _currentFlyoutGroup = null;

function openFlyout(group) {
  const cfg = FLYOUT_GROUPS[group];
  if (!cfg) return;
  _currentFlyoutGroup = group;

  document.getElementById('flyoutTitle').textContent = cfg.label;

  const container = document.getElementById('flyoutItems');
  container.innerHTML = cfg.items.map(item => `
    <a href="#" class="nav-item${item.page && AppState.currentPage === item.page ? ' active' : ''}"
       ${item.page ? `data-page="${item.page}"` : `data-action="${item.action}"`}>
      <span class="nav-icon">${fIcon(item.icon, 16)}</span>
      <span class="nav-label">${item.label}</span>
    </a>
  `).join('');

  // Attach click handlers to flyout nav items (page navigation OR modal action)
  container.querySelectorAll('.nav-item').forEach(el => {
    el.addEventListener('click', (e) => {
      e.preventDefault();
      if (el.dataset.action) {
        closeFlyout();
        const fn = window[el.dataset.action];
        if (typeof fn === 'function') fn();
      } else if (el.dataset.page) {
        navigateTo(el.dataset.page);
        closeFlyout();
      }
    });
  });

  document.getElementById('sidebarFlyout').classList.add('open');
  document.getElementById('flyoutOverlay').classList.add('active');

  // Update group button active state
  document.querySelectorAll('.nav-group-btn').forEach(b => b.classList.remove('active-group'));
  const groupBtn = document.querySelector(`.nav-group-btn[data-group="${group}"]`);
  if (groupBtn) groupBtn.classList.add('active-group');
}

function closeFlyout() {
  document.getElementById('sidebarFlyout').classList.remove('open');
  document.getElementById('flyoutOverlay').classList.remove('active');
  _currentFlyoutGroup = null;
}

function updateGroupActiveState(page) {
  const salesPages     = ['pos', 'pos-products', 'pos-categories', 'pos-payment-methods', 'pos-report',
                          'customer-master', 'customer-invoices', 'customer-payments', 'customer-report'];
  const purchasePages  = ['purchase-vendors', 'purchase-bills', 'purchase-payments', 'purchase-report'];
  const group = salesPages.includes(page) ? 'sales'
    : purchasePages.includes(page) ? 'purchase'
    : 'accounting';
  document.querySelectorAll('.nav-group-btn').forEach(b => b.classList.remove('active-group'));
  const btn = document.querySelector(`.nav-group-btn[data-group="${group}"]`);
  if (btn) btn.classList.add('active-group');
  // Also update active item inside flyout if open
  document.querySelectorAll('#flyoutItems .nav-item').forEach(n => {
    n.classList.toggle('active', n.dataset.page === page);
  });
}

function initSidebarFlyout() {
  document.querySelectorAll('.nav-group-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const group = btn.dataset.group;
      if (_currentFlyoutGroup === group) {
        closeFlyout();
      } else {
        openFlyout(group);
      }
    });
  });

  document.getElementById('flyoutCloseBtn').addEventListener('click', closeFlyout);
  document.getElementById('flyoutOverlay').addEventListener('click', closeFlyout);
}

// ===== NAVIGATION =====
function navigateTo(page) {
  // Guard: halaman yang butuh permission
  if (page === 'upload' && !hasPermission('upload')) {
    showToast('Anda tidak memiliki akses untuk upload data', 'error');
    return;
  }
  if (page === 'users' && !hasPermission('manageUsers')) {
    showToast('Anda tidak memiliki akses ke halaman ini', 'error');
    return;
  }

  // Hide all pages
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));

  // Show target page
  const pageEl = document.getElementById(`page-${page}`);
  if (pageEl) pageEl.classList.add('active');

  // Update title
  const titles = {
    dashboard: 'Dashboard', upload: 'Upload Statement',
    transactions: 'Daftar Transaksi', journal: 'Jurnal Entri',
    coa: 'Chart of Accounts', income: 'Laporan Laba Rugi',
    balance: 'Neraca', cashflow: 'Laporan Arus Kas',
    users: 'Manajemen Pengguna', pos: 'Point of Sale',
    'pos-products': 'Master Produk',
    'pos-categories': 'Master Kategori',
    'pos-payment-methods': 'Master Metode Pembayaran',
    'pos-report': 'Laporan POS',
    'purchase-vendors':  'Master Vendor',
    'purchase-bills':    'Vendor Bill',
    'purchase-payments': 'Payment',
    'purchase-report':   'Laporan Vendor Bill',
    'customer-master':       'Master Customer',
    'customer-invoices':     'Customer Invoice',
    'customer-payments':     'Penerimaan Customer',
    'customer-report':       'Laporan Customer Invoice',
    'inventory':             'Inventory',
    'inventory-movements':   'Pergerakan Stok',
    'inventory-transfers':   'Transfer Stok',
    'inv-onhand':            'Stock On-Hand',
    'inv-valuation':         'Stock Valuation',
    'inv-stockcard':         'Kartu Stok',
    'inv-reorder':           'Reorder Report',
    'inv-slowmoving':        'Slow-Moving Items',
    'inv-costing':           'Costing Method',
    'payments':              'Pembayaran',
    'payments-in':           'Penerimaan',
    'payments-out':          'Pengeluaran',
  };
  document.getElementById('pageTitle').textContent = titles[page] || page;
  AppState.currentPage = page;

  // Update sidebar group active state
  updateGroupActiveState(page);

  // Render page-specific content
  if (page === 'users') renderUsersPage();
  if (page === 'journal')              renderJournalTable();
  if (page === 'pos')                  renderPOSPage();
  if (page === 'pos-products')         { if (typeof renderMasterProductPage  === 'function') renderMasterProductPage(); }
  if (page === 'pos-categories')       { if (typeof renderMasterCategoryPage === 'function') renderMasterCategoryPage(); }
  if (page === 'pos-payment-methods')  { if (typeof renderMasterPaymentPage  === 'function') renderMasterPaymentPage(); }
  if (page === 'pos-report')           { if (typeof renderPOSReportPage      === 'function') renderPOSReportPage(); }
  if (page === 'purchase-vendors')  { if (typeof renderMasterVendorPage   === 'function') renderMasterVendorPage(); }
  if (page === 'purchase-bills')    { if (typeof renderVendorBillPage      === 'function') renderVendorBillPage(); }
  if (page === 'purchase-payments') { if (typeof renderPaymentPage         === 'function') renderPaymentPage(); }
  if (page === 'inventory' || page === 'inventory-movements') {
    if (page === 'inventory-movements') InventoryState.activeTab = 'movements';
    else InventoryState.activeTab = 'items';
    if (typeof renderInventoryPage === 'function') renderInventoryPage();
  }
  if (page === 'inventory-transfers') { if (typeof renderTransfersPage     === 'function') renderTransfersPage(); }
  if (page === 'inv-onhand')         { if (typeof renderStockOnHandPage   === 'function') renderStockOnHandPage(); }
  if (page === 'inv-valuation')      { if (typeof renderStockValuationPage=== 'function') renderStockValuationPage(); }
  if (page === 'inv-stockcard')      { if (typeof renderStockCardPage     === 'function') renderStockCardPage(); }
  if (page === 'inv-reorder')        { if (typeof renderReorderPage       === 'function') renderReorderPage(); }
  if (page === 'inv-slowmoving')     { if (typeof renderSlowMovingPage    === 'function') renderSlowMovingPage(); }
  if (page === 'inv-costing')        { if (typeof renderCostingMethodPage === 'function') renderCostingMethodPage(); }
  if (page === 'payments' || page === 'payments-in' || page === 'payments-out') {
    if (typeof renderPaymentsPage === 'function') renderPaymentsPage();
  }
  if (page === 'purchase-report')   { if (typeof renderPurchaseReportPage  === 'function') renderPurchaseReportPage(); }
  if (page === 'customer-master')   { if (typeof renderMasterCustomerPage  === 'function') renderMasterCustomerPage(); }
  if (page === 'customer-invoices') { if (typeof renderCustomerInvoicePage === 'function') renderCustomerInvoicePage(); }
  if (page === 'customer-payments') { if (typeof renderCustomerPaymentPage === 'function') renderCustomerPaymentPage(); }
  if (page === 'customer-report')   { if (typeof renderCustomerReportPage  === 'function') renderCustomerReportPage(); }

  // Auto-render laporan keuangan saat navigasi ke halaman income/balance/cashflow
  if (page === 'income' && AppState.incomeData) {
    const el = document.getElementById('incomeReport');
    const sub = document.getElementById('incomeSubtitle');
    if (el) el.innerHTML = renderIncomeStatement(AppState.incomeData);
    if (sub) sub.textContent = AppState.incomeData.periodLabel || '';
  }
  if (page === 'balance' && AppState.balanceData) {
    const el = document.getElementById('balanceReport');
    const sub = document.getElementById('balanceSubtitle');
    if (el) el.innerHTML = renderBalanceSheet(AppState.balanceData);
    if (sub) sub.textContent = AppState.balanceData.periodLabel || '';
  }
  if (page === 'cashflow' && AppState.cfData) {
    const el = document.getElementById('cashflowReport');
    const sub = document.getElementById('cashflowSubtitle');
    if (el) el.innerHTML = renderCashflowReport(AppState.cfData);
    if (sub) sub.textContent = AppState.cfData.periodLabel || '';
  }
}

// ===== UPLOAD HANDLING =====
let pendingFiles = [];

function initUpload() {
  const zone = document.getElementById('uploadZone');
  const fileInput = document.getElementById('fileInput');
  const btnPick = document.getElementById('btnPickFile');
  const btnProcess = document.getElementById('btnProcess');
  const btnClear = document.getElementById('btnClearFiles');

  // Click to pick
  btnPick.addEventListener('click', () => fileInput.click());
  zone.addEventListener('click', (e) => {
    if (e.target === zone || e.target.tagName === 'H3' || e.target.tagName === 'P') {
      fileInput.click();
    }
  });

  // File selected
  fileInput.addEventListener('change', (e) => {
    addFiles(Array.from(e.target.files));
    fileInput.value = '';
  });

  // Drag & drop
  zone.addEventListener('dragover', (e) => {
    e.preventDefault();
    zone.classList.add('dragover');
  });
  zone.addEventListener('dragleave', () => zone.classList.remove('dragover'));
  zone.addEventListener('drop', (e) => {
    e.preventDefault();
    zone.classList.remove('dragover');
    const files = Array.from(e.dataTransfer.files).filter(f => f.type === 'application/pdf');
    if (files.length === 0) {
      showToast('Hanya file PDF yang didukung', 'error');
      return;
    }
    addFiles(files);
  });

  // Process — konfirmasi jika data lama sudah ada
  btnProcess.addEventListener('click', () => {
    if (AppState.transactions.length > 0) {
      showConfirmModal(
        'Tambah Data Baru?',
        `Data yang sudah ada (${AppState.transactions.length} transaksi) akan <strong>ditambahkan</strong> dengan data dari file baru. File duplikat akan dilewati otomatis. Lanjutkan?`,
        'Ya, Tambahkan',
        processFiles
      );
    } else {
      processFiles();
    }
  });

  // Clear antrian (hanya file belum diproses)
  btnClear.addEventListener('click', () => {
    pendingFiles = [];
    renderFilesList();
    showToast('Antrian file dihapus', 'info');
  });

  // Reset semua data
  document.getElementById('btnResetData').addEventListener('click', () => {
    showConfirmModal(
      'Reset Semua Data?',
      `Semua data transaksi, jurnal, dan laporan akan dihapus permanen dari sesi ini. File PDF tidak ikut terhapus. Lanjutkan?`,
      'Ya, Reset Semua',
      resetAllData,
      true // danger mode
    );
  });
}

function addFiles(files) {
  files.forEach(file => {
    if (!pendingFiles.find(f => f.name === file.name)) {
      pendingFiles.push(file);
    }
  });
  renderFilesList();
}

function renderFilesList() {
  const container = document.getElementById('filesList');
  const wrapper = document.getElementById('uploadedFiles');

  if (pendingFiles.length === 0) {
    wrapper.style.display = 'none';
    return;
  }

  wrapper.style.display = 'block';
  container.innerHTML = pendingFiles.map((file, i) => `
    <div class="file-item" id="file-${i}">
      <span class="file-icon">${fIcon('file', 20)}</span>
      <div class="file-info">
        <div class="file-name">${file.name}</div>
        <div class="file-meta">${(file.size / 1024).toFixed(1)} KB</div>
      </div>
      <span class="file-status" id="status-${i}">Siap</span>
      <button class="file-remove" onclick="removeFile(${i})">${fIcon('x', 16)}</button>
    </div>
  `).join('');
}

function removeFile(idx) {
  pendingFiles.splice(idx, 1);
  renderFilesList();
}

async function processFiles() {
  if (pendingFiles.length === 0) {
    showToast('Pilih file PDF terlebih dahulu', 'warning');
    return;
  }

  const statusDiv = document.getElementById('processingStatus');
  const progressBar = document.getElementById('progressBar');
  const msgEl = document.getElementById('processingMsg');
  statusDiv.style.display = 'block';

  // Deteksi file duplikat (sudah pernah diproses)
  const alreadyLoaded = new Set(AppState.statements.map(s => s.fileName));
  const skippedFiles = pendingFiles.filter(f => alreadyLoaded.has(f.name));
  const filesToProcess = pendingFiles.filter(f => !alreadyLoaded.has(f.name));

  // Tandai file duplikat di UI
  skippedFiles.forEach(file => {
    const pendingIdx = pendingFiles.findIndex(f => f.name === file.name);
    const statusEl = document.getElementById(`status-${pendingIdx}`);
    if (statusEl) { statusEl.textContent = 'Sudah ada'; statusEl.className = 'file-status skip'; }
  });

  if (filesToProcess.length === 0) {
    showToast(`Semua file sudah pernah diproses (${skippedFiles.length} file duplikat dilewati)`, 'warning');
    statusDiv.style.display = 'none';
    return;
  }

  const newStatements = [];
  for (let i = 0; i < filesToProcess.length; i++) {
    const file = filesToProcess[i];
    const pct = Math.round((i / filesToProcess.length) * 80);
    progressBar.style.width = `${pct}%`;
    msgEl.textContent = `Memproses: ${file.name}`;

    // Update status di file list (cari index asli di pendingFiles)
    const pendingIdx = pendingFiles.findIndex(f => f.name === file.name);
    const statusEl = document.getElementById(`status-${pendingIdx}`);
    if (statusEl) { statusEl.textContent = 'Memproses...'; statusEl.className = 'file-status'; }

    try {
      const result = await parseBankStatement(file);
      newStatements.push(result);
      if (statusEl) { statusEl.textContent = 'Selesai'; statusEl.className = 'file-status ok'; }
    } catch (err) {
      console.error('Parse error:', err);
      if (statusEl) { statusEl.textContent = 'Error'; statusEl.className = 'file-status err'; }
      showToast(`Gagal proses ${file.name}: ${err.message}`, 'error');
    }
  }

  progressBar.style.width = '90%';
  msgEl.textContent = 'Membuat jurnal dan laporan...';

  if (newStatements.length === 0) {
    showToast('Tidak ada file yang berhasil diproses', 'error');
    statusDiv.style.display = 'none';
    return;
  }

  // APPEND: gabung statements lama + baru, lalu merge sekaligus
  const allStatements = [...AppState.statements, ...newStatements];
  const merged = mergeStatements(allStatements);  // sort by fileName internal → urutan kronologis benar
  AppState.statements = allStatements;
  AppState.merged = merged;
  AppState.transactions = merged.transactions;
  AppState.summary = merged.summary;
  AppState.header = merged.accountInfo;

  // Generate journals
  AppState.journals = generateJournalEntries(AppState.transactions);
  // Merge jurnal POS + Manual ke dalam pipeline laporan keuangan
  if (typeof _mergePosJournalsInto    === 'function') _mergePosJournalsInto(AppState.journals);
  if (typeof _mergeManualJournalsInto === 'function') _mergeManualJournalsInto(AppState.journals);
  AppState.journalRows = flattenJournalForTable(AppState.journals);

  // Build ledger
  AppState.ledger = buildLedger(AppState.journals);

  // Period label
  const periods = merged.periods.filter(Boolean);
  const periodLabel = periods.length > 1
    ? `Periode: ${periods[0]} s/d ${periods[periods.length - 1]}`
    : `Periode: ${periods[0] || 'N/A'}`;
  const company = 'PT Global Kreatif Inovasi';

  // Generate reports
  AppState.incomeData = generateIncomeStatement(AppState.ledger, periodLabel, company);
  AppState.balanceData = generateBalanceSheet(AppState.ledger, merged.summary, periodLabel, company);
  AppState.cfData = generateCashflowReport(AppState.transactions, merged.summary, periodLabel, company);

  progressBar.style.width = '100%';
  msgEl.textContent = 'Selesai!';

  // Update UI
  updateAllViews(merged, periodLabel);

  // Enable export, lock, dan hard reset buttons
  document.getElementById('btnExportSheet').disabled = false;
  document.getElementById('btnExportXlsx').disabled = false;
  document.getElementById('btnLock').disabled = false;
  document.getElementById('btnHardReset').disabled = false;

  // Simpan ke localStorage
  saveToStorage();

  // Update sidebar
  const sidebarComp = document.getElementById('sidebarCompany');
  sidebarComp.innerHTML = `<div class="company-dot"></div><span>${periods.join(', ')}</span>`;

  const skippedMsg = skippedFiles.length > 0 ? ` · ${skippedFiles.length} duplikat dilewati` : '';
  showToast(`Berhasil menambahkan ${newStatements.length} file baru · Total: ${AppState.transactions.length} transaksi${skippedMsg}`, 'success');
  updateResetDataSection();

  setTimeout(() => {
    statusDiv.style.display = 'none';
    navigateTo('dashboard');
  }, 1500);
}

// ===== CONFIRM MODAL =====
function showConfirmModal(title, bodyHtml, confirmText, onConfirm, isDanger = false) {
  document.getElementById('modalTitle').textContent = title;
  document.getElementById('modalBody').innerHTML = `<p style="font-size:14px;line-height:1.6">${bodyHtml}</p>`;
  const btnSave = document.getElementById('modalSave');
  btnSave.textContent = confirmText;
  btnSave.className = isDanger ? 'btn btn-danger' : 'btn btn-primary';
  btnSave.onclick = () => {
    closeModal();
    if (onConfirm) onConfirm();
  };
  const btnCancel = document.getElementById('modalCancel');
  btnCancel.textContent = 'Batal';
  btnCancel.style.display = '';  // reset visibility
  document.getElementById('modalOverlay').style.display = 'flex';
}

// ===== RESET ALL DATA =====
function resetAllData() {
  if (!hasPermission('resetData')) {
    showToast('Anda tidak memiliki akses untuk reset data', 'error');
    return;
  }
  // Reset AppState data
  AppState.statements = [];
  AppState.merged = null;
  AppState.transactions = [];
  AppState.journals = [];
  AppState.journalRows = [];
  AppState.ledger = {};
  AppState.incomeData = null;
  AppState.balanceData = null;
  AppState.cfData = null;
  AppState.summary = null;
  AppState.header = null;
  AppState.txPage = 1;
  AppState.txFilter = { search: '', type: '', category: '', dateFrom: '', dateTo: '' };
  AppState.reportFilter = { income: { from: '', to: '' }, balance: { from: '', to: '' }, cashflow: { from: '', to: '' } };

  // Destroy charts
  Object.keys(AppState.charts).forEach(k => {
    if (AppState.charts[k]) AppState.charts[k].destroy();
  });
  AppState.charts = {};

  // Reset pending files
  pendingFiles = [];
  renderFilesList();

  // Reset export buttons
  document.getElementById('btnExportSheet').disabled = true;
  document.getElementById('btnExportXlsx').disabled = true;

  // Reset sidebar
  document.getElementById('sidebarCompany').innerHTML = `<div class="company-dot"></div><span>Belum ada data</span>`;

  // Reset report cards
  document.getElementById('incomeReport').innerHTML = '<div class="empty-state">Upload bank statement untuk melihat laporan</div>';
  document.getElementById('balanceReport').innerHTML = '<div class="empty-state">Upload bank statement untuk melihat laporan</div>';
  document.getElementById('cashflowReport').innerHTML = '<div class="empty-state">Upload bank statement untuk melihat laporan</div>';
  document.getElementById('txTableBody').innerHTML = '<tr><td colspan="8" class="empty-row">Belum ada transaksi - upload bank statement terlebih dahulu</td></tr>';
  document.getElementById('journalTableBody').innerHTML = '<tr><td colspan="8" class="empty-row">Belum ada jurnal entri</td></tr>';
  document.getElementById('txCount').textContent = '0 transaksi';
  document.getElementById('txPagination').innerHTML = '';
  document.getElementById('journalSummary').style.display = 'none';

  // Reset filter inputs
  ['income', 'balance', 'cashflow'].forEach(type => {
    document.getElementById(`${type}DateFrom`).value = '';
    document.getElementById(`${type}DateTo`).value = '';
    document.getElementById(`${type}CompareToggle`).checked = false;
    document.getElementById(`${type}CompareOptions`).style.display = 'none';
    document.getElementById(`${type}CompareDateFrom`).value = '';
    document.getElementById(`${type}CompareDateTo`).value = '';
    document.getElementById(`${type}FilterInfo`).textContent = '';
  });

  // Show empty dashboard
  document.getElementById('emptyDashboard').classList.add('show');

  // Hide reset section
  updateResetDataSection();

  // Clear localStorage & disable lock/reset buttons
  clearStorage();
  applyLockState(false);
  document.getElementById('btnLock').disabled = true;
  document.getElementById('btnHardReset').disabled = true;

  showToast('Semua data berhasil direset', 'success');
  navigateTo('upload');
}

// ===== LOCK STATE =====
function applyLockState(locked) {
  if (locked && !hasPermission('lock')) {
    showToast('Anda tidak memiliki akses untuk mengunci data', 'error');
    return;
  }
  AppState.isLocked = locked;
  const btn = document.getElementById('btnLock');
  if (!btn) return;
  if (locked) {
    btn.innerHTML = `${fIcon('lock', 14)} Unlock`;
    btn.classList.add('btn-lock-active');
  } else {
    btn.innerHTML = `${fIcon('unlock', 14)} Lock`;
    btn.classList.remove('btn-lock-active');
  }
  // Re-render tabel agar select disabled/enabled sesuai state
  renderTransactionsTable();
  renderJournalTable();
}

function updateResetDataSection() {
  const section = document.getElementById('resetDataSection');
  const label = document.getElementById('resetDataLabel');
  if (AppState.transactions.length > 0) {
    section.style.display = 'flex';
    const periods = AppState.merged?.periods?.filter(Boolean) || [];
    label.textContent = `Data aktif: ${AppState.transactions.length} transaksi${periods.length ? ' · ' + periods.join(', ') : ''}`;
  } else {
    section.style.display = 'none';
  }
}

// ===== UPDATE ALL VIEWS =====
function updateAllViews(merged, periodLabel) {
  updateDashboard(merged, periodLabel);
  renderTransactionsTable();
  renderJournalTable();
  renderCOATable();
  renderReports(periodLabel);
}

// ===== DASHBOARD =====
function updateDashboard(merged, periodLabel) {
  const { summary } = merged;

  // Hide empty state
  document.getElementById('emptyDashboard').classList.remove('show');

  // Update period
  document.getElementById('dashPeriod').textContent = periodLabel;

  // KPI
  document.getElementById('kpiSaldoAwal').textContent = formatRupiahShort(summary.saldoAwal);
  document.getElementById('kpiTotalCR').textContent = formatRupiahShort(summary.mutasiCR);
  document.getElementById('kpiTotalDB').textContent = formatRupiahShort(summary.mutasiDB);
  document.getElementById('kpiSaldoAkhir').textContent = formatRupiahShort(summary.saldoAkhir);
  document.getElementById('kpiCRCount').textContent = `${summary.txCRCount || 0} transaksi`;
  document.getElementById('kpiDBCount').textContent = `${summary.txDBCount || 0} transaksi`;

  // Charts
  renderCharts(merged);

  // Top recipients
  renderTopRecipients();
}

function renderCharts(merged) {
  const txs = AppState.transactions.filter(t => t.type !== 'SALDO_AWAL');

  // --- Chart 1: Daily Cashflow ---
  destroyChart('cashflowChart');
  const dailyData = buildDailyCashflow(txs);
  const ctx1 = document.getElementById('cashflowChart').getContext('2d');
  AppState.charts.cashflow = new Chart(ctx1, {
    type: 'bar',
    data: {
      labels: dailyData.labels,
      datasets: [
        {
          label: 'Pemasukan (CR)',
          data: dailyData.cr,
          backgroundColor: 'rgba(22, 163, 74, 0.7)',
          borderColor: 'rgba(22, 163, 74, 1)',
          borderWidth: 1
        },
        {
          label: 'Pengeluaran (DB)',
          data: dailyData.db,
          backgroundColor: 'rgba(220, 38, 38, 0.7)',
          borderColor: 'rgba(220, 38, 38, 1)',
          borderWidth: 1
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { position: 'top' } },
      scales: {
        y: {
          beginAtZero: true,
          ticks: {
            callback: v => formatRupiahShort(v)
          }
        }
      }
    }
  });

  // --- Chart 2: Komposisi CR vs DB (Donut) ---
  destroyChart('compositionChart');
  const ctx2 = document.getElementById('compositionChart').getContext('2d');
  AppState.charts.composition = new Chart(ctx2, {
    type: 'doughnut',
    data: {
      labels: ['Pemasukan (CR)', 'Pengeluaran (DB)'],
      datasets: [{
        data: [merged.summary.mutasiCR, merged.summary.mutasiDB],
        backgroundColor: ['rgba(22, 163, 74, 0.8)', 'rgba(220, 38, 38, 0.8)'],
        borderWidth: 2
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: 'bottom' },
        tooltip: {
          callbacks: {
            label: ctx => `${ctx.label}: ${formatRupiah(ctx.parsed)}`
          }
        }
      }
    }
  });

  // --- Chart 3: Pengeluaran per Kategori ---
  destroyChart('categoryChart');
  const catData = buildCategoryData(txs);
  const ctx3 = document.getElementById('categoryChart').getContext('2d');
  AppState.charts.category = new Chart(ctx3, {
    type: 'bar',
    data: {
      labels: catData.labels,
      datasets: [{
        label: 'Jumlah Pengeluaran',
        data: catData.values,
        backgroundColor: [
          'rgba(37,99,235,0.7)', 'rgba(124,58,237,0.7)',
          'rgba(220,38,38,0.7)', 'rgba(245,158,11,0.7)',
          'rgba(16,185,129,0.7)', 'rgba(239,68,68,0.7)',
          'rgba(99,102,241,0.7)', 'rgba(14,165,233,0.7)'
        ],
        borderWidth: 1
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      indexAxis: 'y',
      plugins: { legend: { display: false } },
      scales: {
        x: {
          beginAtZero: true,
          ticks: { callback: v => formatRupiahShort(v) }
        }
      }
    }
  });
}

function buildDailyCashflow(txs) {
  const byDate = {};
  txs.forEach(tx => {
    if (!tx.date) return;
    const d = tx.dateRaw || tx.date;
    if (!byDate[d]) byDate[d] = { cr: 0, db: 0 };
    if (tx.type === 'CR') byDate[d].cr += tx.amount || 0;
    else if (tx.type === 'DB') byDate[d].db += tx.amount || 0;
  });
  const sorted = Object.keys(byDate).sort();
  return {
    labels: sorted,
    cr: sorted.map(d => byDate[d].cr),
    db: sorted.map(d => byDate[d].db)
  };
}

function buildCategoryData(txs) {
  const cats = {};
  txs.filter(t => t.type === 'DB').forEach(tx => {
    const mapping = tx.coaMapping || {};
    const code = mapping.debitAccount || '5-3800';
    const acct = COA[code];
    const label = acct ? acct.name.substring(0, 30) : 'Lain-lain';
    if (!cats[label]) cats[label] = 0;
    cats[label] += tx.amount || 0;
  });
  // Sort by value, take top 8
  const sorted = Object.entries(cats).sort((a, b) => b[1] - a[1]).slice(0, 8);
  return { labels: sorted.map(x => x[0]), values: sorted.map(x => x[1]) };
}

function renderTopRecipients() {
  const txs = AppState.transactions.filter(t => t.type === 'DB');
  const byParty = {};
  txs.forEach(tx => {
    const party = tx.party || 'Unknown';
    if (!byParty[party]) byParty[party] = 0;
    byParty[party] += tx.amount || 0;
  });
  const sorted = Object.entries(byParty).sort((a, b) => b[1] - a[1]).slice(0, 6);

  const container = document.getElementById('topRecipients');
  if (sorted.length === 0) {
    container.innerHTML = '<div class="empty-state">Tidak ada data</div>';
    return;
  }
  container.innerHTML = sorted.map(([name, amount], i) => `
    <div class="recipient-item">
      <div class="recipient-rank">${i + 1}</div>
      <div class="recipient-name">${name.substring(0, 25) || 'N/A'}</div>
      <div class="recipient-amount">${formatRupiahShort(amount)}</div>
    </div>
  `).join('');
}

function destroyChart(id) {
  const key = id.replace('Chart', '').toLowerCase();
  if (AppState.charts[key]) {
    AppState.charts[key].destroy();
    delete AppState.charts[key];
  }
}

// ===== TRANSACTIONS TABLE =====
function renderTransactionsTable() {
  const { transactions, txFilter, txPage, txPerPage } = AppState;

  // Filter
  let filtered = transactions.filter(tx => {
    if (tx.type === 'SALDO_AWAL') return false;

    if (txFilter.type && tx.type !== txFilter.type) return false;

    if (txFilter.search) {
      const search = txFilter.search.toLowerCase();
      const match = (tx.description + tx.party + tx.ref + tx.fullDescription).toLowerCase().includes(search);
      if (!match) return false;
    }

    if (txFilter.categories && txFilter.categories.length > 0) {
      const mapping = tx.coaMapping || {};
      const code = tx.type === 'CR' ? mapping.kreditAccount : mapping.debitAccount;
      if (!txFilter.categories.includes(code)) return false;
    }

    if (txFilter.dateFrom && tx.date && tx.date < txFilter.dateFrom) return false;
    if (txFilter.dateTo && tx.date && tx.date > txFilter.dateTo) return false;

    return true;
  });

  // Pagination
  const total = filtered.length;
  const totalPages = Math.ceil(total / txPerPage);
  const start = (txPage - 1) * txPerPage;
  const paginated = filtered.slice(start, start + txPerPage);

  const tbody = document.getElementById('txTableBody');
  if (paginated.length === 0) {
    tbody.innerHTML = '<tr><td colspan="8" class="empty-row">Tidak ada transaksi yang sesuai filter</td></tr>';
  } else {
    tbody.innerHTML = paginated.map(tx => {
      const mapping = tx.coaMapping || {};
      const isCR = tx.type === 'CR';
      const catCode = isCR ? mapping.kreditAccount : mapping.debitAccount;
      const catName = COA[catCode]?.name || '-';

      return `<tr>
        <td>${tx.date || tx.dateRaw || ''}</td>
        <td>${tx.description || ''}</td>
        <td style="font-size:11px;color:#6b7280">${tx.ref || ''}</td>
        <td>${tx.party || ''}</td>
        <td>
          <select class="category-select" ${AppState.isLocked ? 'disabled' : ''} onchange="updateTxCategory('${tx.id}', this.value, '${tx.type}')">
            ${getCOAOptionsHTML(catCode, tx.type)}
          </select>
        </td>
        <td class="text-right ${!isCR ? 'amount-db' : ''}">${!isCR ? formatRupiah(tx.amount) : ''}</td>
        <td class="text-right ${isCR ? 'amount-cr' : ''}">${isCR ? formatRupiah(tx.amount) : ''}</td>
        <td class="text-right">${tx.saldo ? formatRupiah(tx.saldo) : ''}</td>
      </tr>`;
    }).join('');
  }

  document.getElementById('txCount').textContent = `${total} transaksi`;

  // Pagination
  renderPagination(totalPages, txPage, 'txPagination', (p) => {
    AppState.txPage = p;
    renderTransactionsTable();
  });

  // Update category filter options
  updateCategoryFilter();
}

function getCOAOptionsHTML(selectedCode, txType) {
  const accounts = getAccountOptions();
  return accounts.map(acct => {
    const sel = acct.value === selectedCode ? 'selected' : '';
    return `<option value="${acct.value}" ${sel}>${acct.label}</option>`;
  }).join('');
}

function updateTxCategory(txId, newCode, txType) {
  const tx = AppState.transactions.find(t => t.id === txId);
  if (!tx) return;

  if (!tx.coaMapping) tx.coaMapping = {};
  if (txType === 'CR') {
    tx.coaMapping.kreditAccount = newCode;
  } else {
    tx.coaMapping.debitAccount = newCode;
  }

  // Regenerate journals
  AppState.journals = generateJournalEntries(AppState.transactions);
  if (typeof _mergePosJournalsInto    === 'function') _mergePosJournalsInto(AppState.journals);
  if (typeof _mergeManualJournalsInto === 'function') _mergeManualJournalsInto(AppState.journals);
  AppState.journalRows = flattenJournalForTable(AppState.journals);
  AppState.ledger = buildLedger(AppState.journals);

  // Re-render journal (but not transactions to avoid losing focus)
  renderJournalTable();
  showToast('Kategori diperbarui', 'success');
  saveToStorage();
}

function updateCategoryFilter() {
  const container = document.getElementById('categoryMultiOptions');
  if (!container) return;
  const accounts = getAccountOptions();
  const selected = AppState.txFilter.categories;
  const searchVal = (document.getElementById('categoryMultiSearch')?.value || '').toLowerCase();
  container.innerHTML = accounts.map(a => `
    <label class="multiselect-option${searchVal && !a.label.toLowerCase().includes(searchVal) ? ' ms-hidden' : ''}">
      <input type="checkbox" value="${a.value}" ${selected.includes(a.value) ? 'checked' : ''}
             onchange="onCategoryCheckChange()" />
      ${a.label}
    </label>
  `).join('');
  _updateCategoryBtnLabel();
  _updateSelectAllState();
}

function _updateCategoryBtnLabel() {
  const selected = AppState.txFilter.categories;
  const btn = document.getElementById('categoryMultiBtn');
  const label = document.getElementById('categoryMultiLabel');
  if (!btn || !label) return;
  if (selected.length === 0) {
    label.textContent = 'Semua Kategori';
    btn.classList.remove('active');
    const badge = btn.querySelector('.multiselect-badge');
    if (badge) badge.remove();
  } else {
    label.textContent = 'Kategori dipilih';
    btn.classList.add('active');
    let badge = btn.querySelector('.multiselect-badge');
    if (!badge) {
      badge = document.createElement('span');
      badge.className = 'multiselect-badge';
      label.after(badge);
    }
    badge.textContent = selected.length;
  }
}

function _updateSelectAllState() {
  const accounts = getAccountOptions();
  const selected = AppState.txFilter.categories;
  const chk = document.getElementById('categorySelectAllChk');
  if (!chk) return;
  if (selected.length === 0) {
    chk.checked = false;
    chk.indeterminate = false;
  } else if (selected.length === accounts.length) {
    chk.checked = true;
    chk.indeterminate = false;
  } else {
    chk.checked = false;
    chk.indeterminate = true;
  }
}

function onCategoryCheckChange() {
  const checked = [];
  document.querySelectorAll('#categoryMultiOptions input[type="checkbox"]:checked').forEach(cb => {
    checked.push(cb.value);
  });
  AppState.txFilter.categories = checked;
  AppState.txPage = 1;
  _updateCategoryBtnLabel();
  _updateSelectAllState();
  renderTransactionsTable();
}

function _handleSelectAll(selectAll) {
  AppState.txFilter.categories = selectAll ? getAccountOptions().map(a => a.value) : [];
  AppState.txPage = 1;
  updateCategoryFilter();
  renderTransactionsTable();
}

function renderPagination(totalPages, currentPage, containerId, callback) {
  const container = document.getElementById(containerId);
  if (!container || totalPages <= 1) {
    if (container) container.innerHTML = '';
    return;
  }

  let html = '';
  const range = 2;
  for (let p = 1; p <= totalPages; p++) {
    if (p === 1 || p === totalPages || (p >= currentPage - range && p <= currentPage + range)) {
      html += `<button class="page-btn ${p === currentPage ? 'active' : ''}" onclick="(${callback.toString()})(${p})">${p}</button>`;
    } else if (p === currentPage - range - 1 || p === currentPage + range + 1) {
      html += `<button class="page-btn" disabled>...</button>`;
    }
  }
  container.innerHTML = html;
}

// ===== JOURNAL TABLE =====
let _journalViewMode = 'flat'; // 'flat' | 'group'

function setJournalView(mode) {
  _journalViewMode = mode;
  const btnFlat  = document.getElementById('jViewFlat');
  const btnGroup = document.getElementById('jViewGroup');
  if (btnFlat)  btnFlat.classList.toggle('active', mode === 'flat');
  if (btnGroup) btnGroup.classList.toggle('active', mode === 'group');
  renderJournalTable();
}

function clearJournalFilters() {
  const s = document.getElementById('jSearch');
  const df = document.getElementById('jDateFrom');
  const dt = document.getElementById('jDateTo');
  const at = document.getElementById('jAcctType');
  if (s)  s.value  = '';
  if (df) df.value = '';
  if (dt) dt.value = '';
  if (at) at.value = 'all';
  renderJournalTable();
}

function toggleJournalGroup(jeId) {
  const container = document.getElementById('jg-' + jeId);
  const icon      = document.getElementById('jg-icon-' + jeId);
  if (!container) return;
  const hidden = container.style.display === 'none';
  container.style.display = hidden ? 'table-row' : 'none';
  if (icon) icon.textContent = hidden ? '▼' : '▶';
}

function _updateJournalSummary(journals) {
  const totals = calculateJournalTotals(journals);
  const summaryDiv = document.getElementById('journalSummary');
  if (!summaryDiv) return;
  summaryDiv.style.display = 'grid';
  document.getElementById('jTotalDebit').textContent  = formatRupiah(totals.totalDebit);
  document.getElementById('jTotalKredit').textContent = formatRupiah(totals.totalKredit);
  document.getElementById('jSelisih').textContent     = formatRupiah(totals.selisih);
  const statusEl = document.getElementById('jStatus');
  statusEl.textContent = totals.isBalanced ? 'Balance' : 'Tidak Balance';
  statusEl.className   = `badge ${totals.isBalanced ? 'badge-cr' : 'badge-db'}`;
}

function renderJournalTable() {
  const tbody = document.getElementById('journalTableBody');

  // Read filter values
  const search   = (document.getElementById('jSearch')?.value   || '').toLowerCase().trim();
  const dateFrom = document.getElementById('jDateFrom')?.value  || '';
  const dateTo   = document.getElementById('jDateTo')?.value    || '';
  const acctType = document.getElementById('jAcctType')?.value  || 'all';

  // Filter journals
  let filtered = AppState.journals;
  if (dateFrom) filtered = filtered.filter(j => j.date >= dateFrom);
  if (dateTo)   filtered = filtered.filter(j => j.date <= dateTo);
  if (acctType !== 'all') {
    filtered = filtered.filter(j =>
      j.entries?.some(e => { const a = COA[e.accountCode]; return a?.type === acctType; })
    );
  }
  if (search) {
    filtered = filtered.filter(j =>
      (j.description || '').toLowerCase().includes(search) ||
      (j.no || '').toLowerCase().includes(search) ||
      j.entries?.some(e =>
        (e.accountCode  || '').toLowerCase().includes(search) ||
        (e.accountName  || '').toLowerCase().includes(search)
      )
    );
  }

  if (filtered.length === 0) {
    tbody.innerHTML = `<tr><td colspan="9" class="empty-row">${AppState.journals.length === 0 ? 'Belum ada jurnal entri' : 'Tidak ada jurnal yang sesuai filter'}</td></tr>`;
    _updateJournalSummary(filtered);
    return;
  }

  if (_journalViewMode === 'group') {
    // Group mode: one collapsible header row per journal entry
    tbody.innerHTML = filtered.map((j, idx) => {
      const totalDebit  = j.entries.reduce((s, e) => s + (e.debit  || 0), 0);
      const totalKredit = j.entries.reduce((s, e) => s + (e.kredit || 0), 0);
      const detailHtml  = j.entries.map(e => `
        <tr class="journal-detail-row">
          <td></td><td></td><td></td>
          <td class="journal-detail-note">${e.note || ''}</td>
          <td style="font-weight:600;color:#2563eb">${e.accountCode || ''}</td>
          <td>${e.accountName || ''}</td>
          <td class="text-right ${(e.debit  || 0) > 0 ? 'amount-db' : ''}">${(e.debit  || 0) > 0 ? formatRupiah(e.debit)  : ''}</td>
          <td class="text-right ${(e.kredit || 0) > 0 ? 'amount-cr' : ''}">${(e.kredit || 0) > 0 ? formatRupiah(e.kredit) : ''}</td>
          <td></td>
        </tr>`).join('');
      const isManualJ = j.id?.startsWith('JE-MAN');
      const groupRowBg = isManualJ ? 'background:#f0fdf4' : '';
      const noHtml = isManualJ
        ? `<span style="font-size:11px;color:#16a34a;white-space:nowrap">${j.no || ''} <span class="badge-manual">manual</span></span>`
        : `<span style="font-size:11px;color:#6b7280;white-space:nowrap">${j.no || ''}</span>`;
      const groupAksi = isManualJ
        ? `<td style="display:flex;gap:4px;align-items:center;justify-content:center">
             <button class="btn-split-acct" onclick="event.stopPropagation();openCreateJournalModal('${j.id}')" title="Edit">${fIcon('edit-2',12)}</button>
             <button class="btn-split-acct btn-danger-sm" onclick="event.stopPropagation();deleteManualJournal('${j.id}')" title="Hapus">${fIcon('trash-2',12)}</button>
           </td>`
        : `<td style="text-align:center"><span id="jg-icon-${j.id}" style="color:#6b7280;font-size:10px">▶</span></td>`;
      return `
        <tr class="journal-group-header" style="${groupRowBg}" onclick="toggleJournalGroup('${j.id}')">
          <td>${idx + 1}</td>
          <td>${j.date || ''}</td>
          <td>${noHtml}</td>
          <td style="font-weight:500">${j.description || ''}</td>
          <td style="color:#9ca3af;font-size:12px">${j.entries.length} baris</td>
          <td></td>
          <td class="text-right amount-db">${formatRupiah(totalDebit)}</td>
          <td class="text-right amount-cr">${formatRupiah(totalKredit)}</td>
          ${groupAksi}
        </tr>
        <tr id="jg-${j.id}" style="display:none">
          <td colspan="9" style="padding:0;border-top:none">
            <table style="width:100%;border-collapse:collapse">${detailHtml}</table>
          </td>
        </tr>`;
    }).join('');
  } else {
    // Flat mode
    const rows = flattenJournalForTable(filtered);
    tbody.innerHTML = rows.map(row => {
      const debitVal  = row.debit  > 0 ? formatRupiah(row.debit)  : '';
      const kreditVal = row.kredit > 0 ? formatRupiah(row.kredit) : '';
      const isManual  = row.journalId?.startsWith('JE-MAN');
      const rowClass  = isManual ? 'style="background:#f0fdf4"' : (row.type === 'CR' ? '' : 'style="background:#fef9f9"');
      let aksiCell;
      if (row.isFirst && row.txId) {
        // Bank statement journal → Edit Pecah Akun
        aksiCell = `<td><button class="btn-split-acct" ${AppState.isLocked ? 'disabled style="opacity:0.4;cursor:not-allowed"' : ''} onclick="${AppState.isLocked ? '' : `openSplitModal('${row.txId}')`}">${fIcon('edit-2', 12)} Edit</button></td>`;
      } else if (row.isFirst && isManual) {
        // Manual journal → Edit + Hapus
        aksiCell = `<td style="display:flex;gap:4px;align-items:center">
          <button class="btn-split-acct" onclick="openCreateJournalModal('${row.journalId}')" title="Edit jurnal">${fIcon('edit-2', 12)}</button>
          <button class="btn-split-acct btn-danger-sm" onclick="deleteManualJournal('${row.journalId}')" title="Hapus jurnal">${fIcon('trash-2', 12)}</button>
        </td>`;
      } else {
        aksiCell = '<td></td>';
      }
      const journalIdHtml = row.journalId
        ? (isManual ? `<span style="font-size:11px;color:#16a34a;white-space:nowrap">${row.journalId} <span class="badge-manual">manual</span></span>` : `<span style="font-size:11px;color:#6b7280;white-space:nowrap">${row.journalId}</span>`)
        : '';
      return `<tr ${rowClass}>
        <td>${row.rowNum      || ''}</td>
        <td>${row.date        || ''}</td>
        <td>${journalIdHtml}</td>
        <td>${row.description || ''}</td>
        <td style="font-weight:600;color:#2563eb">${row.accountCode || ''}</td>
        <td>${row.accountName || ''}</td>
        <td class="text-right ${row.debit  > 0 ? 'amount-db' : ''}">${debitVal}</td>
        <td class="text-right ${row.kredit > 0 ? 'amount-cr' : ''}">${kreditVal}</td>
        ${aksiCell}
      </tr>`;
    }).join('');
  }

  _updateJournalSummary(filtered);
}

// ===== COA TABLE =====
let _coaCurrentFilter = 'all';

function renderCOATable(filter = 'all') {
  _coaCurrentFilter = filter;
  const accounts = getAllAccounts().filter(a => a.category !== 'Header');
  const tbody = document.getElementById('coaTableBody');

  const filtered = filter === 'all' ? accounts : accounts.filter(a => a.code.startsWith(filter + '-'));
  filtered.sort((a, b) => a.code.localeCompare(b.code));

  const typeColors = {
    'Aset': 'background:#eff6ff;color:#1d4ed8',
    'Liabilitas': 'background:#fef3c7;color:#92400e',
    'Ekuitas': 'background:#f0fdf4;color:#166534',
    'Pendapatan': 'background:#ecfdf5;color:#065f46',
    'Beban': 'background:#fef2f2;color:#991b1b'
  };

  tbody.innerHTML = filtered.map(acct => `
    <tr>
      <td style="font-weight:700;color:#1d4ed8">${acct.code}</td>
      <td style="font-weight:500">${acct.name}</td>
      <td><span style="padding:2px 8px;border-radius:12px;font-size:11px;${typeColors[acct.type] || ''}">${acct.type}</span></td>
      <td style="font-size:12px;color:#6b7280">${acct.category}</td>
      <td style="font-size:12px">${acct.normal}</td>
      <td style="font-size:12px;color:#6b7280">${acct.desc || ''}</td>
      <td><button class="btn-edit-coa" onclick="openCOAModal('${acct.code}')">Edit</button></td>
    </tr>
  `).join('');
}

// ===== COA MODAL =====
let _coaEditCode = null; // null = add mode, string = edit mode

function openCOAModal(editCode = null) {
  _coaEditCode = editCode;
  const modal = document.getElementById('coaModal');
  const title = document.getElementById('coaModalTitle');
  const err = document.getElementById('coaError');
  err.style.display = 'none';

  if (editCode && COA[editCode]) {
    const acct = COA[editCode];
    title.textContent = 'Edit Akun';
    document.getElementById('coaCode').value = acct.code;
    document.getElementById('coaCode').disabled = true; // kode tidak boleh diubah saat edit
    document.getElementById('coaName').value = acct.name;
    document.getElementById('coaType').value = acct.type;
    document.getElementById('coaCategory').value = acct.category;
    document.getElementById('coaNormal').value = acct.normal;
    document.getElementById('coaDesc').value = acct.desc || '';
  } else {
    title.textContent = 'Tambah Akun';
    document.getElementById('coaCode').value = '';
    document.getElementById('coaCode').disabled = false;
    document.getElementById('coaName').value = '';
    document.getElementById('coaType').value = 'Aset';
    document.getElementById('coaCategory').value = '';
    document.getElementById('coaNormal').value = 'Debit';
    document.getElementById('coaDesc').value = '';
    onCOATypeChange(); // set default normal balance
  }

  modal.style.display = 'flex';
}

function closeCOAModal() {
  document.getElementById('coaModal').style.display = 'none';
  _coaEditCode = null;
}

function onCOATypeChange() {
  const type = document.getElementById('coaType').value;
  const normalMap = { 'Aset': 'Debit', 'Beban': 'Debit', 'Liabilitas': 'Kredit', 'Ekuitas': 'Kredit', 'Pendapatan': 'Kredit' };
  document.getElementById('coaNormal').value = normalMap[type] || 'Debit';
}

function saveCOAAccount() {
  const errEl = document.getElementById('coaError');
  errEl.style.display = 'none';

  const code = document.getElementById('coaCode').value.trim();
  const name = document.getElementById('coaName').value.trim();
  const type = document.getElementById('coaType').value;
  const category = document.getElementById('coaCategory').value.trim() || type;
  const normal = document.getElementById('coaNormal').value;
  const desc = document.getElementById('coaDesc').value.trim();

  // Validasi
  if (!name) {
    errEl.textContent = 'Nama akun tidak boleh kosong.';
    errEl.style.display = 'block';
    return;
  }
  if (!_coaEditCode) {
    // Add mode: validasi kode
    if (!code) {
      errEl.textContent = 'Kode akun tidak boleh kosong.';
      errEl.style.display = 'block';
      return;
    }
    if (!/^\d-\d{4}$/.test(code)) {
      errEl.textContent = 'Format kode akun harus X-XXXX (contoh: 5-1200).';
      errEl.style.display = 'block';
      return;
    }
    if (COA[code]) {
      errEl.textContent = `Kode akun ${code} sudah ada.`;
      errEl.style.display = 'block';
      return;
    }
  }

  const finalCode = _coaEditCode || code;
  const isEdit = !!_coaEditCode;
  COA[finalCode] = { code: finalCode, name, type, category, normal, desc };

  closeCOAModal();
  renderCOATable(_coaCurrentFilter);
  showToast(isEdit ? `Akun ${finalCode} berhasil diupdate` : `Akun ${finalCode} berhasil ditambahkan`, 'success');
}

// Close modal when clicking overlay background
document.addEventListener('click', function(e) {
  const modal = document.getElementById('coaModal');
  if (e.target === modal) closeCOAModal();
});

// ===== REPORTS =====
function renderReports(periodLabel) {
  // Income Statement
  if (AppState.incomeData) {
    document.getElementById('incomeReport').innerHTML = renderIncomeStatement(AppState.incomeData);
    document.getElementById('incomeSubtitle').textContent = periodLabel;
  }

  // Balance Sheet
  if (AppState.balanceData) {
    document.getElementById('balanceReport').innerHTML = renderBalanceSheet(AppState.balanceData);
    document.getElementById('balanceSubtitle').textContent = periodLabel;
  }

  // Cashflow
  if (AppState.cfData) {
    document.getElementById('cashflowReport').innerHTML = renderCashflowReport(AppState.cfData);
    document.getElementById('cashflowSubtitle').textContent = periodLabel;
  }
}

// ===== REPORT DATE FILTER =====
/**
 * Filter transactions by date range, then rebuild ledger & regenerate specific report.
 * reportType: 'income' | 'balance' | 'cashflow'
 */
function applyReportFilter(reportType) {
  if (!AppState.transactions.length) return;

  const filter = AppState.reportFilter[reportType];
  const { from, to } = filter;

  // Filter transactions
  let filtered = AppState.transactions.filter(tx => {
    if (tx.type === 'SALDO_AWAL') return false;
    if (from && tx.date && tx.date < from) return false;
    if (to && tx.date && tx.date > to) return false;
    return true;
  });

  // Period label for filtered range
  const merged = AppState.merged;
  let periodLabel;
  if (from || to) {
    const f = from ? formatDateLabel(from) : '...';
    const t = to ? formatDateLabel(to) : '...';
    periodLabel = `Periode: ${f} s/d ${t}`;
  } else {
    const periods = merged ? merged.periods.filter(Boolean) : [];
    periodLabel = periods.length > 1
      ? `Periode: ${periods[0]} s/d ${periods[periods.length - 1]}`
      : `Periode: ${periods[0] || 'N/A'}`;
  }

  const company = 'PT Global Kreatif Inovasi';

  // Update info badge
  const infoEl = document.getElementById(`${reportType}FilterInfo`);
  if (infoEl) {
    infoEl.textContent = (from || to) ? `Menampilkan ${filtered.length} transaksi` : '';
  }

  if (reportType === 'income') {
    // Rebuild journals & ledger from filtered transactions (include SALDO_AWAL for context)
    const txWithSaldo = AppState.transactions.filter(tx => tx.type === 'SALDO_AWAL').concat(filtered);
    const journals = generateJournalEntries(txWithSaldo);
    // Merge POS + Manual journals yang tanggalnya dalam range filter
    if (typeof _mergePosJournalsInto    === 'function') _mergePosJournalsInto(journals, from, to);
    if (typeof _mergeManualJournalsInto === 'function') _mergeManualJournalsInto(journals, from, to);
    const ledger = buildLedger(journals);
    AppState.incomeData = generateIncomeStatement(ledger, periodLabel, company);
    document.getElementById('incomeReport').innerHTML = renderIncomeStatement(AppState.incomeData);
    document.getElementById('incomeSubtitle').textContent = periodLabel;

  } else if (reportType === 'balance') {
    const txWithSaldo = AppState.transactions.filter(tx => tx.type === 'SALDO_AWAL').concat(filtered);
    const journals = generateJournalEntries(txWithSaldo);
    // Merge POS + Manual journals yang tanggalnya dalam range filter
    if (typeof _mergePosJournalsInto    === 'function') _mergePosJournalsInto(journals, from, to);
    if (typeof _mergeManualJournalsInto === 'function') _mergeManualJournalsInto(journals, from, to);
    const ledger = buildLedger(journals);
    // Compute filtered summary for saldo akhir
    const filteredSummary = computeFilteredSummary(filtered, AppState.summary);
    AppState.balanceData = generateBalanceSheet(ledger, filteredSummary, periodLabel, company);
    document.getElementById('balanceReport').innerHTML = renderBalanceSheet(AppState.balanceData);
    document.getElementById('balanceSubtitle').textContent = periodLabel;

  } else if (reportType === 'cashflow') {
    AppState.cfData = generateCashflowReport(filtered, AppState.summary, periodLabel, company);
    document.getElementById('cashflowReport').innerHTML = renderCashflowReport(AppState.cfData);
    document.getElementById('cashflowSubtitle').textContent = periodLabel;
  }
}

function computeFilteredSummary(filteredTxs, originalSummary) {
  const mutasiCR = filteredTxs.filter(t => t.type === 'CR').reduce((s, t) => s + (t.amount || 0), 0);
  const mutasiDB = filteredTxs.filter(t => t.type === 'DB').reduce((s, t) => s + (t.amount || 0), 0);
  return {
    saldoAwal: originalSummary.saldoAwal,
    mutasiCR,
    mutasiDB,
    saldoAkhir: originalSummary.saldoAwal + mutasiCR - mutasiDB
  };
}

function formatDateLabel(isoDate) {
  if (!isoDate) return '';
  const [y, m, d] = isoDate.split('-');
  const months = ['Jan','Feb','Mar','Apr','Mei','Jun','Jul','Agu','Sep','Okt','Nov','Des'];
  return `${parseInt(d)} ${months[parseInt(m) - 1]} ${y}`;
}

function initReportFilters() {
  const reports = ['income', 'balance', 'cashflow'];

  reports.forEach(type => {
    const cap = type.charAt(0).toUpperCase() + type.slice(1);
    const fromId = `${type}DateFrom`;
    const toId = `${type}DateTo`;
    const resetId = `btnReset${cap}Filter`;
    const toggleId = `${type}CompareToggle`;
    const optionsId = `${type}CompareOptions`;
    const compareBtn = `btn${cap}Compare`;

    document.getElementById(fromId).addEventListener('change', (e) => {
      AppState.reportFilter[type].from = e.target.value;
      applyReportFilter(type);
    });

    document.getElementById(toId).addEventListener('change', (e) => {
      AppState.reportFilter[type].to = e.target.value;
      applyReportFilter(type);
    });

    document.getElementById(resetId).addEventListener('click', () => {
      AppState.reportFilter[type] = { from: '', to: '' };
      document.getElementById(fromId).value = '';
      document.getElementById(toId).value = '';
      // Reset compare
      document.getElementById(toggleId).checked = false;
      document.getElementById(optionsId).style.display = 'none';
      document.getElementById(`${type}CompareDateFrom`).value = '';
      document.getElementById(`${type}CompareDateTo`).value = '';
      applyReportFilter(type);
    });

    // Compare toggle
    document.getElementById(toggleId).addEventListener('change', (e) => {
      document.getElementById(optionsId).style.display = e.target.checked ? 'flex' : 'none';
      if (!e.target.checked) {
        // Re-render without comparison
        applyReportFilter(type);
      }
    });

    // Granularity change: auto-fill compare dates based on current period + granularity
    document.getElementById(`${type}CompareGranularity`).addEventListener('change', () => {
      autoFillCompareDates(type);
    });

    // Compare button
    document.getElementById(compareBtn).addEventListener('click', () => {
      applyComparisonReport(type);
    });

    // Auto-fill compare dates when primary dates change and compare is active
    document.getElementById(fromId).addEventListener('change', () => {
      if (document.getElementById(toggleId).checked) autoFillCompareDates(type);
    });
    document.getElementById(toId).addEventListener('change', () => {
      if (document.getElementById(toggleId).checked) autoFillCompareDates(type);
    });
  });
}

/**
 * Auto-fill the comparison period dates based on main period + granularity
 */
function autoFillCompareDates(type) {
  const from = document.getElementById(`${type}DateFrom`).value;
  const to = document.getElementById(`${type}DateTo`).value;
  if (!from && !to) return;

  const granularity = document.getElementById(`${type}CompareGranularity`).value;

  // Determine the span: use from..to or just one endpoint
  const baseFrom = from ? new Date(from) : null;
  const baseTo = to ? new Date(to) : null;

  let shiftMs = 0;
  const msDay = 86400000;

  if (granularity === 'day') {
    shiftMs = msDay;
  } else if (granularity === 'week') {
    shiftMs = 7 * msDay;
  } else if (granularity === 'month') {
    // Shift by 1 month using date arithmetic
    shiftMs = null; // handled separately
  } else if (granularity === 'quarter') {
    shiftMs = null; // 3 months
  } else if (granularity === 'year') {
    shiftMs = null; // 12 months
  }

  function shiftDate(d, gran, direction = -1) {
    if (!d) return '';
    const nd = new Date(d);
    if (gran === 'day') nd.setDate(nd.getDate() + direction);
    else if (gran === 'week') nd.setDate(nd.getDate() + direction * 7);
    else if (gran === 'month') nd.setMonth(nd.getMonth() + direction);
    else if (gran === 'quarter') nd.setMonth(nd.getMonth() + direction * 3);
    else if (gran === 'year') nd.setFullYear(nd.getFullYear() + direction);
    return nd.toISOString().slice(0, 10);
  }

  const cFrom = shiftDate(baseFrom, granularity, -1);
  const cTo = shiftDate(baseTo, granularity, -1);

  if (cFrom) document.getElementById(`${type}CompareDateFrom`).value = cFrom;
  if (cTo) document.getElementById(`${type}CompareDateTo`).value = cTo;
}

/**
 * Build report data for a given date range
 */
function buildReportData(type, from, to, periodLabel) {
  const company = 'PT Global Kreatif Inovasi';

  const filtered = AppState.transactions.filter(tx => {
    if (tx.type === 'SALDO_AWAL') return false;
    if (from && tx.date && tx.date < from) return false;
    if (to && tx.date && tx.date > to) return false;
    return true;
  });

  if (type === 'income') {
    const txWithSaldo = AppState.transactions.filter(tx => tx.type === 'SALDO_AWAL').concat(filtered);
    const journals = generateJournalEntries(txWithSaldo);
    const ledger = buildLedger(journals);
    return generateIncomeStatement(ledger, periodLabel, company);
  } else if (type === 'balance') {
    const txWithSaldo = AppState.transactions.filter(tx => tx.type === 'SALDO_AWAL').concat(filtered);
    const journals = generateJournalEntries(txWithSaldo);
    const ledger = buildLedger(journals);
    const filteredSummary = computeFilteredSummary(filtered, AppState.summary);
    return generateBalanceSheet(ledger, filteredSummary, periodLabel, company);
  } else if (type === 'cashflow') {
    return generateCashflowReport(filtered, AppState.summary, periodLabel, company);
  }
}

/**
 * Apply comparison: render two periods side-by-side with diff table
 */
function applyComparisonReport(type) {
  if (!AppState.transactions.length) {
    showToast('Upload bank statement terlebih dahulu', 'warning');
    return;
  }

  const mainFrom = document.getElementById(`${type}DateFrom`).value;
  const mainTo = document.getElementById(`${type}DateTo`).value;
  const cmpFrom = document.getElementById(`${type}CompareDateFrom`).value;
  const cmpTo = document.getElementById(`${type}CompareDateTo`).value;
  const gran = document.getElementById(`${type}CompareGranularity`).value;

  const granLabels = { day: 'Hari', week: 'Minggu', month: 'Bulan', quarter: 'Kuartal', year: 'Tahun' };

  const fMain = mainFrom ? formatDateLabel(mainFrom) : '...';
  const tMain = mainTo ? formatDateLabel(mainTo) : '...';
  const fCmp = cmpFrom ? formatDateLabel(cmpFrom) : '...';
  const tCmp = cmpTo ? formatDateLabel(cmpTo) : '...';

  const labelMain = `Periode Saat Ini: ${fMain} – ${tMain}`;
  const labelCmp = `Periode Pembanding: ${fCmp} – ${tCmp}`;

  const dataMain = buildReportData(type, mainFrom, mainTo, labelMain);
  const dataCmp = buildReportData(type, cmpFrom, cmpTo, labelCmp);

  if (!dataMain || !dataCmp) return;

  const container = document.getElementById(`${type}Report`);

  if (type === 'income') {
    container.innerHTML = renderIncomeComparison(dataMain, dataCmp, granLabels[gran]);
    document.getElementById(`${type}Subtitle`).textContent = `Komparasi per ${granLabels[gran]}: ${fMain}–${tMain} vs ${fCmp}–${tCmp}`;
  } else if (type === 'balance') {
    container.innerHTML = renderBalanceComparison(dataMain, dataCmp, granLabels[gran]);
    document.getElementById(`${type}Subtitle`).textContent = `Komparasi per ${granLabels[gran]}: ${fMain}–${tMain} vs ${fCmp}–${tCmp}`;
  } else if (type === 'cashflow') {
    container.innerHTML = renderCashflowComparison(dataMain, dataCmp, granLabels[gran]);
    document.getElementById(`${type}Subtitle`).textContent = `Komparasi per ${granLabels[gran]}: ${fMain}–${tMain} vs ${fCmp}–${tCmp}`;
  }

  const infoEl = document.getElementById(`${type}FilterInfo`);
  if (infoEl) infoEl.textContent = `Mode komparasi (${granLabels[gran]})`;
}

// ===== REPORT-SPECIFIC EXPORT =====

/**
 * Ambil data laporan yang sudah difilter oleh date range aktif, tanpa re-render UI.
 */
function getFilteredReportData(reportType) {
  const filter = AppState.reportFilter[reportType] || {};
  const { from, to } = filter;

  const filtered = AppState.transactions.filter(tx => {
    if (tx.type === 'SALDO_AWAL') return false;
    if (from && tx.date && tx.date < from) return false;
    if (to && tx.date && tx.date > to) return false;
    return true;
  });

  let periodLabel;
  if (from || to) {
    const f = from ? formatDateLabel(from) : '...';
    const t = to   ? formatDateLabel(to)   : '...';
    periodLabel = `Periode: ${f} s/d ${t}`;
  } else {
    const periods = AppState.merged ? AppState.merged.periods.filter(Boolean) : [];
    periodLabel = periods.length > 1
      ? `Periode: ${periods[0]} s/d ${periods[periods.length - 1]}`
      : `Periode: ${periods[0] || 'N/A'}`;
  }

  const company = 'PT Global Kreatif Inovasi';
  const txWithSaldo = AppState.transactions.filter(tx => tx.type === 'SALDO_AWAL').concat(filtered);
  const journals = generateJournalEntries(txWithSaldo);
  const ledger   = buildLedger(journals);

  if (reportType === 'income') {
    return { data: generateIncomeStatement(ledger, periodLabel, company), periodLabel };
  } else if (reportType === 'balance') {
    const filteredSummary = computeFilteredSummary(filtered, AppState.summary);
    return { data: generateBalanceSheet(ledger, filteredSummary, periodLabel, company), periodLabel };
  } else {
    return { data: generateCashflowReport(filtered, AppState.summary, periodLabel, company), periodLabel };
  }
}

function exportReportGSheets(reportType) {
  if (!AppState.transactions.length) { showToast('Upload bank statement terlebih dahulu', 'warning'); return; }
  try {
    const { data } = getFilteredReportData(reportType);
    const result = exportSingleReportGSheets(reportType, data, AppState.header);
    showToast('File Excel didownload. Buka Google Sheets untuk import.', 'success');
    showGSheetsModal(result);
  } catch(err) { console.error(err); showToast('Gagal export: ' + err.message, 'error'); }
}

function exportReportExcel(reportType) {
  if (!AppState.transactions.length) { showToast('Upload bank statement terlebih dahulu', 'warning'); return; }
  try {
    const { data } = getFilteredReportData(reportType);
    const filename = exportSingleReportXlsx(reportType, data, AppState.header);
    showToast(`File "${filename}" berhasil didownload`, 'success');
  } catch(err) { console.error(err); showToast('Gagal export: ' + err.message, 'error'); }
}

function exportReportPdf(reportType) {
  if (!AppState.transactions.length) { showToast('Upload bank statement terlebih dahulu', 'warning'); return; }
  try {
    const { data } = getFilteredReportData(reportType);
    exportReportAsPdf(reportType, data);
    showToast('PDF berhasil dibuat', 'success');
  } catch(err) { console.error(err); showToast('Gagal export PDF: ' + err.message, 'error'); }
}

// ===== EXPORT =====
function handleExportXlsx() {
  if (!AppState.transactions.length) {
    showToast('Upload bank statement terlebih dahulu', 'warning');
    return;
  }

  try {
    const filename = exportToExcel({
      transactions: AppState.transactions,
      journals: AppState.journals,
      journalRows: AppState.journalRows,
      summary: AppState.summary,
      header: AppState.header,
      incomeData: AppState.incomeData,
      balanceData: AppState.balanceData,
      cfData: AppState.cfData,
      periods: AppState.merged?.periods || []
    });
    showToast(`File "${filename}" berhasil didownload`, 'success');
  } catch (err) {
    console.error(err);
    showToast('Gagal export: ' + err.message, 'error');
  }
}

function handleExportGoogleSheets() {
  if (!AppState.transactions.length) {
    showToast('Upload bank statement terlebih dahulu', 'warning');
    return;
  }

  try {
    const result = exportToGoogleSheets({
      transactions: AppState.transactions,
      journals: AppState.journals,
      journalRows: AppState.journalRows,
      summary: AppState.summary,
      header: AppState.header,
      incomeData: AppState.incomeData,
      balanceData: AppState.balanceData,
      cfData: AppState.cfData,
      periods: AppState.merged?.periods || []
    });

    showToast(`File Excel didownload. Buka Google Sheets untuk import.`, 'success');

    // Show instructions modal
    showGSheetsModal(result);
  } catch (err) {
    console.error(err);
    showToast('Gagal export: ' + err.message, 'error');
  }
}

function showGSheetsModal(result) {
  document.getElementById('modalTitle').textContent = 'Export ke Google Sheets';
  document.getElementById('modalBody').innerHTML = `
    <div style="margin-bottom:16px">
      <div style="background:#f0fdf4;border:1px solid #86efac;border-radius:8px;padding:12px;margin-bottom:12px">
        ${fIcon('check-circle', 14)} File <strong>${result.filename}</strong> berhasil didownload
      </div>
      <p style="font-size:13px;font-weight:600;margin-bottom:8px">Langkah Import ke Google Sheets:</p>
      <ol style="padding-left:20px;font-size:13px;line-height:1.8">
        ${result.instructions.map(s => `<li>${s}</li>`).join('')}
      </ol>
    </div>
    <div style="background:#eff6ff;border-radius:8px;padding:12px">
      <p style="font-size:12px;color:#1d4ed8">
        <strong>Tips:</strong> File Excel yang sudah didownload berisi 6 sheet:<br>
        Transaksi • Jurnal Entri • Chart of Accounts • Laba Rugi • Neraca • Arus Kas
      </p>
    </div>
  `;

  document.getElementById('modalSave').textContent = 'Buka Google Sheets';
  document.getElementById('modalSave').onclick = () => {
    window.open('https://sheets.new', '_blank');
    closeModal();
  };
  document.getElementById('modalCancel').textContent = 'Tutup';
  document.getElementById('modalOverlay').style.display = 'flex';
}

function closeModal() {
  document.getElementById('modalOverlay').style.display = 'none';
}

// ===== SPLIT JOURNAL MODAL =====
let _splitTxId = null;

// Helper: build one split-line row HTML for a given side
function _splitLineHTML(side, i, line, accounts, allowRemove) {
  const selectedOpts = accounts.map(a =>
    `<option value="${a.value}" ${a.value === (line.accountCode || '') ? 'selected' : ''}>${a.label}</option>`
  ).join('');
  const removeBtn = allowRemove
    ? `<button class="btn-remove-split" onclick="removeSplitLine('${side}', ${i})">${fIcon('x', 14)}</button>`
    : `<span style="width:24px;flex-shrink:0"></span>`;
  return `
    <div class="split-line" id="split-${side}-${i}">
      <span class="split-line-num">${i + 1}.</span>
      <select class="split-acct-select select-input" onchange="onSplitLineChange()">
        <option value="">-- Pilih Akun --</option>
        ${selectedOpts}
      </select>
      <input type="number" class="split-amount-input" value="${line.amount || 0}"
             min="0" step="1000" oninput="onSplitLineChange()" onchange="onSplitLineChange()" />
      <input type="text" class="split-note-input"
             value="${(line.note || '').replace(/"/g, '&quot;')}"
             placeholder="Catatan (opsional)" />
      ${removeBtn}
    </div>
  `;
}

function openSplitModal(txId) {
  const tx = AppState.transactions.find(t => t.id === txId);
  if (!tx) return;
  _splitTxId = txId;

  document.getElementById('splitModalInfo').innerHTML = `
    <strong>${tx.date || ''}</strong> &nbsp;·&nbsp; ${tx.description || ''} &nbsp;·&nbsp;
    <span style="color:${tx.type === 'CR' ? '#16a34a' : '#dc2626'};font-weight:600">
      ${tx.type} ${formatRupiah(tx.amount)}
    </span>
  `;

  let debitLines, kreditLines;
  const se = tx.splitEntries;

  if (se && !Array.isArray(se) && se.debit && se.kredit) {
    // New structure: object with .debit and .kredit arrays
    debitLines  = se.debit.length  > 0 ? se.debit  : [{ accountCode: '', amount: 0, note: '' }];
    kreditLines = se.kredit.length > 0 ? se.kredit : [{ accountCode: '', amount: 0, note: '' }];
  } else if (Array.isArray(se) && se.length > 0) {
    // Backward compatibility: legacy flat array
    const mapping = tx.coaMapping || {};
    if (tx.type === 'DB') {
      debitLines  = se;
      kreditLines = [{ accountCode: mapping.kreditAccount || '', amount: tx.amount, note: '' }];
    } else {
      debitLines  = [{ accountCode: mapping.debitAccount || '', amount: tx.amount, note: '' }];
      kreditLines = se;
    }
  } else {
    // No existing split – seed with auto-mapped accounts
    const mapping = tx.coaMapping || {};
    debitLines  = [{ accountCode: mapping.debitAccount  || '', amount: tx.amount, note: '' }];
    kreditLines = [{ accountCode: mapping.kreditAccount || '', amount: tx.amount, note: '' }];
  }

  renderSplitDebitLines(debitLines);
  renderSplitKreditLines(kreditLines);
  document.getElementById('splitModal').style.display = 'flex';
}

function closeSplitModal() {
  document.getElementById('splitModal').style.display = 'none';
  _splitTxId = null;
}

function renderSplitDebitLines(lines) {
  const accounts = getAccountOptions();
  document.getElementById('splitDebitLines').innerHTML = lines.map((line, i) =>
    _splitLineHTML('debit', i, line, accounts, lines.length > 1)
  ).join('');
  onSplitLineChange();
}

function renderSplitKreditLines(lines) {
  const accounts = getAccountOptions();
  document.getElementById('splitKreditLines').innerHTML = lines.map((line, i) =>
    _splitLineHTML('kredit', i, line, accounts, lines.length > 1)
  ).join('');
  onSplitLineChange();
}

function addSplitDebitLine() {
  const container = document.getElementById('splitDebitLines');
  const count = container.querySelectorAll('.split-line').length;
  const accounts = getAccountOptions();
  const div = document.createElement('div');
  div.innerHTML = _splitLineHTML('debit', count, { accountCode: '', amount: 0, note: '' }, accounts, true);
  container.appendChild(div.firstElementChild);
  _refreshRemoveButtons('debit');
  onSplitLineChange();
}

function addSplitKreditLine() {
  const container = document.getElementById('splitKreditLines');
  const count = container.querySelectorAll('.split-line').length;
  const accounts = getAccountOptions();
  const div = document.createElement('div');
  div.innerHTML = _splitLineHTML('kredit', count, { accountCode: '', amount: 0, note: '' }, accounts, true);
  container.appendChild(div.firstElementChild);
  _refreshRemoveButtons('kredit');
  onSplitLineChange();
}

function removeSplitLine(side, idx) {
  const containerId = side === 'debit' ? 'splitDebitLines' : 'splitKreditLines';
  const container = document.getElementById(containerId);
  const allLines = container.querySelectorAll('.split-line');
  if (allLines.length <= 1) {
    showToast('Minimal 1 baris diperlukan per sisi', 'warning');
    return;
  }
  document.getElementById(`split-${side}-${idx}`).remove();
  // Re-number remaining lines
  container.querySelectorAll('.split-line').forEach((el, i) => {
    el.id = `split-${side}-${i}`;
    el.querySelector('.split-line-num').textContent = `${i + 1}.`;
    const removeBtn = el.querySelector('.btn-remove-split');
    if (removeBtn) removeBtn.setAttribute('onclick', `removeSplitLine('${side}', ${i})`);
  });
  _refreshRemoveButtons(side);
  onSplitLineChange();
}

function _refreshRemoveButtons(side) {
  const containerId = side === 'debit' ? 'splitDebitLines' : 'splitKreditLines';
  const container = document.getElementById(containerId);
  const allLines = container.querySelectorAll('.split-line');
  const isSingle = allLines.length === 1;
  allLines.forEach((el, i) => {
    const existingBtn = el.querySelector('.btn-remove-split');
    const existingSpacer = el.querySelector('span[style*="width:24px"]');
    if (isSingle) {
      if (existingBtn) {
        const spacer = document.createElement('span');
        spacer.style.cssText = 'width:24px;flex-shrink:0';
        existingBtn.replaceWith(spacer);
      }
    } else {
      if (existingSpacer) {
        const btn = document.createElement('button');
        btn.className = 'btn-remove-split';
        btn.setAttribute('onclick', `removeSplitLine('${side}', ${i})`);
        btn.innerHTML = fIcon('x', 14);
        existingSpacer.replaceWith(btn);
      } else if (existingBtn) {
        existingBtn.setAttribute('onclick', `removeSplitLine('${side}', ${i})`);
      }
    }
  });
}

function onSplitLineChange() {
  const tx = AppState.transactions.find(t => t.id === _splitTxId);
  const txAmount = tx ? tx.amount : 0;

  let debitTotal = 0;
  document.getElementById('splitDebitLines').querySelectorAll('.split-amount-input').forEach(inp => {
    debitTotal += parseFloat(inp.value) || 0;
  });

  let kreditTotal = 0;
  document.getElementById('splitKreditLines').querySelectorAll('.split-amount-input').forEach(inp => {
    kreditTotal += parseFloat(inp.value) || 0;
  });

  document.getElementById('splitDebitTotal').textContent  = formatRupiah(debitTotal);
  document.getElementById('splitKreditTotal').textContent = formatRupiah(kreditTotal);
  document.getElementById('splitBalDebit').textContent    = formatRupiah(debitTotal);
  document.getElementById('splitBalKredit').textContent   = formatRupiah(kreditTotal);

  // Per-column match indicator vs tx.amount
  const debitMatchEl  = document.getElementById('splitDebitMatch');
  const kreditMatchEl = document.getElementById('splitKreditMatch');
  if (Math.abs(debitTotal - txAmount) < 0.01) {
    debitMatchEl.textContent = '= Transaksi';
    debitMatchEl.className   = 'split-col-match match-ok';
  } else {
    const d = debitTotal - txAmount;
    debitMatchEl.textContent = d > 0 ? `+${formatRupiah(d)} vs transaksi` : `${formatRupiah(d)} vs transaksi`;
    debitMatchEl.className   = 'split-col-match match-warn';
  }
  if (Math.abs(kreditTotal - txAmount) < 0.01) {
    kreditMatchEl.textContent = '= Transaksi';
    kreditMatchEl.className   = 'split-col-match match-ok';
  } else {
    const d = kreditTotal - txAmount;
    kreditMatchEl.textContent = d > 0 ? `+${formatRupiah(d)} vs transaksi` : `${formatRupiah(d)} vs transaksi`;
    kreditMatchEl.className   = 'split-col-match match-warn';
  }

  // Balance status (debit vs kredit)
  const statusEl  = document.getElementById('splitStatus');
  const saveBtn   = document.getElementById('btnSaveSplit');
  const warningEl = document.getElementById('splitTxWarning');
  const diff = debitTotal - kreditTotal;

  let blockSave = false;
  const warnings = [];

  // Rule 1: debet harus = kredit (hard block)
  if (Math.abs(diff) < 0.01) {
    statusEl.textContent = '= Balance';
    statusEl.className   = 'split-status ok';
  } else {
    blockSave = true;
    if (diff > 0) {
      statusEl.textContent = `Debet kelebihan ${formatRupiah(diff)}`;
      statusEl.className   = 'split-status err';
    } else {
      statusEl.textContent = `Kredit kelebihan ${formatRupiah(Math.abs(diff))}`;
      statusEl.className   = 'split-status err';
    }
  }

  // Rule 2: total harus = tx.amount (warning, tidak hard block tapi ditampilkan)
  if (Math.abs(debitTotal - txAmount) >= 0.01 || Math.abs(kreditTotal - txAmount) >= 0.01) {
    warnings.push(
      `Perhatian: Total jurnal (${formatRupiah(debitTotal)}) berbeda dengan jumlah transaksi (${formatRupiah(txAmount)}). ` +
      `Pastikan ini disengaja sebelum menyimpan.`
    );
  }

  if (warnings.length > 0) {
    warningEl.innerHTML = warnings.map(w => `<div>${w}</div>`).join('');
    warningEl.style.display = 'block';
  } else {
    warningEl.style.display = 'none';
  }

  saveBtn.disabled = blockSave;
}

function saveSplitEntries() {
  const tx = AppState.transactions.find(t => t.id === _splitTxId);
  if (!tx) return;

  const debitEntries = [];
  let debitValid = true;
  document.getElementById('splitDebitLines').querySelectorAll('.split-line').forEach(line => {
    const code   = line.querySelector('.split-acct-select').value;
    const amount = parseFloat(line.querySelector('.split-amount-input').value) || 0;
    const note   = line.querySelector('.split-note-input').value.trim();
    if (!code || amount <= 0) { debitValid = false; return; }
    const acct = COA[code];
    debitEntries.push({ accountCode: code, accountName: acct ? acct.name : code, amount, note });
  });

  const kreditEntries = [];
  let kreditValid = true;
  document.getElementById('splitKreditLines').querySelectorAll('.split-line').forEach(line => {
    const code   = line.querySelector('.split-acct-select').value;
    const amount = parseFloat(line.querySelector('.split-amount-input').value) || 0;
    const note   = line.querySelector('.split-note-input').value.trim();
    if (!code || amount <= 0) { kreditValid = false; return; }
    const acct = COA[code];
    kreditEntries.push({ accountCode: code, accountName: acct ? acct.name : code, amount, note });
  });

  if (!debitValid || !kreditValid) {
    showToast('Pastikan semua baris memiliki akun dan jumlah yang valid', 'warning');
    return;
  }

  const debitTotal  = debitEntries.reduce((s, e)  => s + e.amount, 0);
  const kreditTotal = kreditEntries.reduce((s, e) => s + e.amount, 0);

  // Hard block: debet harus = kredit
  if (Math.abs(debitTotal - kreditTotal) >= 0.01) {
    showToast('Tidak bisa disimpan: Total Debet harus sama dengan total Kredit', 'error');
    return;
  }

  tx.splitEntries = { debit: debitEntries, kredit: kreditEntries };
  AppState.journals    = generateJournalEntries(AppState.transactions);
  if (typeof _mergePosJournalsInto    === 'function') _mergePosJournalsInto(AppState.journals);
  if (typeof _mergeManualJournalsInto === 'function') _mergeManualJournalsInto(AppState.journals);
  AppState.journalRows = flattenJournalForTable(AppState.journals);
  AppState.ledger      = buildLedger(AppState.journals);
  saveToStorage();
  renderJournalTable();
  closeSplitModal();

  // Informasi apakah total sesuai dengan tx.amount
  const txAmountMatch = Math.abs(debitTotal - tx.amount) < 0.01;
  if (txAmountMatch) {
    showToast(`Jurnal dipecah: ${debitEntries.length} baris debet, ${kreditEntries.length} baris kredit`, 'success');
  } else {
    showToast(
      `Jurnal disimpan. Catatan: total (${formatRupiah(debitTotal)}) berbeda dari jumlah transaksi (${formatRupiah(tx.amount)})`,
      'warning'
    );
  }
}

function clearSplitEntries() {
  const tx = AppState.transactions.find(t => t.id === _splitTxId);
  if (!tx) return;
  delete tx.splitEntries;
  AppState.journals    = generateJournalEntries(AppState.transactions);
  if (typeof _mergePosJournalsInto    === 'function') _mergePosJournalsInto(AppState.journals);
  if (typeof _mergeManualJournalsInto === 'function') _mergeManualJournalsInto(AppState.journals);
  AppState.journalRows = flattenJournalForTable(AppState.journals);
  AppState.ledger      = buildLedger(AppState.journals);
  renderJournalTable();
  closeSplitModal();
  showToast('Pecahan akun dihapus, jurnal kembali ke 2 baris', 'info');
}

// ============================================================
//  MANUAL JOURNAL ENTRY — Create / Edit / Delete
// ============================================================

const MANUAL_JOURNAL_KEY = 'manual_journals_v1';
let _cjEditId = null; // null = create mode, string = edit mode

function _saveManualJournals() {
  return;  // No-op — journals go to backend via BackendSync.syncJournal
}

function _loadManualJournals() {
  // No-op — BackendLoader.loadJournals populates AppState.manualJournals on login
  if (!Array.isArray(AppState.manualJournals)) AppState.manualJournals = [];
}

function _nextManualJournalId() {
  // Generate a per-session counter (in-memory only)
  if (!window.__manualJournalCounter) window.__manualJournalCounter = 0;
  const n = ++window.__manualJournalCounter;
  return 'JE-MAN-' + String(n).padStart(4, '0');
}

/** Merge manual journals ke array journals (tanpa duplikat, optional date filter) */
function _mergeManualJournalsInto(journalsArray, fromStr, toStr) {
  const from = fromStr ? new Date(fromStr + 'T00:00:00') : null;
  const to   = toStr   ? new Date(toStr   + 'T23:59:59') : null;
  (AppState.manualJournals || []).forEach(j => {
    if (from && to) {
      const d = new Date(j.date + 'T00:00:00');
      if (d < from || d > to) return;
    }
    if (!journalsArray.find(e => e.id === j.id)) journalsArray.push(j);
  });
}

/** Load dari localStorage + merge ke AppState + rebuild ledger & laporan */
function _restoreManualJournals() {
  _loadManualJournals();
  AppState.journals = (AppState.journals || []).filter(j => !j.id?.startsWith('JE-MAN'));
  _mergeManualJournalsInto(AppState.journals);
  if (typeof flattenJournalForTable === 'function') {
    AppState.journalRows = flattenJournalForTable(AppState.journals);
  }
  AppState.ledger = buildLedger(AppState.journals);
  if (typeof _posRebuildReports === 'function') _posRebuildReports();
}

// ----- Modal open/close -----

function openCreateJournalModal(editId = null) {
  _cjEditId = editId || null;
  const titleEl = document.getElementById('createJournalModalTitle');

  if (_cjEditId) {
    titleEl.textContent = 'Edit Jurnal Manual';
    const j = (AppState.manualJournals || []).find(j => j.id === _cjEditId);
    if (!j) return;
    document.getElementById('cjDate').value = j.date || '';
    document.getElementById('cjDescription').value = j.description || '';
    const debitEntries  = j.entries.filter(e => (e.debit  || 0) > 0)
                                   .map(e => ({ accountCode: e.accountCode, amount: e.debit,  note: e.note || '' }));
    const kreditEntries = j.entries.filter(e => (e.kredit || 0) > 0)
                                   .map(e => ({ accountCode: e.accountCode, amount: e.kredit, note: e.note || '' }));
    _renderCjLines('debit',  debitEntries.length  ? debitEntries  : [{ accountCode: '', amount: 0, note: '' }]);
    _renderCjLines('kredit', kreditEntries.length ? kreditEntries : [{ accountCode: '', amount: 0, note: '' }]);
  } else {
    titleEl.textContent = 'Buat Jurnal Manual';
    document.getElementById('cjDate').value = new Date().toISOString().slice(0, 10);
    document.getElementById('cjDescription').value = '';
    _renderCjLines('debit',  [{ accountCode: '', amount: 0, note: '' }]);
    _renderCjLines('kredit', [{ accountCode: '', amount: 0, note: '' }]);
  }

  document.getElementById('createJournalModal').style.display = 'flex';
  if (typeof feather !== 'undefined') feather.replace();
}

function closeCreateJournalModal() {
  document.getElementById('createJournalModal').style.display = 'none';
  _cjEditId = null;
}

// ----- Line rendering (reuse split-line HTML pattern) -----

function _cjLineHTML(side, i, line, accounts, allowRemove) {
  const selectedOpts = accounts.map(a =>
    `<option value="${a.value}" ${a.value === (line.accountCode || '') ? 'selected' : ''}>${a.label}</option>`
  ).join('');
  const removeBtn = allowRemove
    ? `<button class="btn-remove-split" onclick="removeCjLine('${side}', ${i})">${fIcon('x', 14)}</button>`
    : `<span style="width:24px;flex-shrink:0"></span>`;
  return `
    <div class="split-line" id="cj-${side}-${i}">
      <span class="split-line-num">${i + 1}.</span>
      <select class="split-acct-select select-input" onchange="onCjLineChange()">
        <option value="">-- Pilih Akun --</option>${selectedOpts}
      </select>
      <input type="number" class="split-amount-input" value="${line.amount || 0}"
             min="0" step="1000" oninput="onCjLineChange()" onchange="onCjLineChange()" />
      <input type="text" class="split-note-input"
             value="${(line.note || '').replace(/"/g, '&quot;')}"
             placeholder="Catatan (opsional)" />
      ${removeBtn}
    </div>`;
}

function _renderCjLines(side, lines) {
  const accounts = getAccountOptions();
  const containerId = side === 'debit' ? 'cjDebitLines' : 'cjKreditLines';
  document.getElementById(containerId).innerHTML =
    lines.map((line, i) => _cjLineHTML(side, i, line, accounts, lines.length > 1)).join('');
  onCjLineChange();
}

function addCjLine(side) {
  const containerId = side === 'debit' ? 'cjDebitLines' : 'cjKreditLines';
  const container = document.getElementById(containerId);
  const count = container.querySelectorAll('.split-line').length;
  const accounts = getAccountOptions();
  const div = document.createElement('div');
  div.innerHTML = _cjLineHTML(side, count, { accountCode: '', amount: 0, note: '' }, accounts, true);
  container.appendChild(div.firstElementChild);
  _refreshCjRemoveButtons(side);
  onCjLineChange();
}

function removeCjLine(side, idx) {
  const containerId = side === 'debit' ? 'cjDebitLines' : 'cjKreditLines';
  const container = document.getElementById(containerId);
  const allLines = container.querySelectorAll('.split-line');
  if (allLines.length <= 1) {
    showToast('Minimal 1 baris per sisi', 'warning');
    return;
  }
  document.getElementById(`cj-${side}-${idx}`).remove();
  container.querySelectorAll('.split-line').forEach((el, i) => {
    el.id = `cj-${side}-${i}`;
    el.querySelector('.split-line-num').textContent = `${i + 1}.`;
    const btn = el.querySelector('.btn-remove-split');
    if (btn) btn.setAttribute('onclick', `removeCjLine('${side}', ${i})`);
  });
  _refreshCjRemoveButtons(side);
  onCjLineChange();
}

function _refreshCjRemoveButtons(side) {
  const containerId = side === 'debit' ? 'cjDebitLines' : 'cjKreditLines';
  const container = document.getElementById(containerId);
  const allLines = container.querySelectorAll('.split-line');
  const isSingle = allLines.length === 1;
  allLines.forEach((el, i) => {
    const existingBtn     = el.querySelector('.btn-remove-split');
    const existingSpacer  = el.querySelector('span[style*="width:24px"]');
    if (isSingle) {
      if (existingBtn) {
        const spacer = document.createElement('span');
        spacer.style.cssText = 'width:24px;flex-shrink:0';
        existingBtn.replaceWith(spacer);
      }
    } else {
      if (existingSpacer) {
        const btn = document.createElement('button');
        btn.className = 'btn-remove-split';
        btn.setAttribute('onclick', `removeCjLine('${side}', ${i})`);
        btn.innerHTML = fIcon('x', 14);
        existingSpacer.replaceWith(btn);
      } else if (existingBtn) {
        existingBtn.setAttribute('onclick', `removeCjLine('${side}', ${i})`);
      }
    }
  });
}

// ----- Live balance recalculation -----

function onCjLineChange() {
  let dt = 0, kt = 0;
  document.getElementById('cjDebitLines')?.querySelectorAll('.split-amount-input')
    .forEach(inp => { dt += parseFloat(inp.value) || 0; });
  document.getElementById('cjKreditLines')?.querySelectorAll('.split-amount-input')
    .forEach(inp => { kt += parseFloat(inp.value) || 0; });

  const fmtDt = formatRupiah(dt), fmtKt = formatRupiah(kt);
  document.getElementById('cjDebitTotal').textContent  = fmtDt;
  document.getElementById('cjKreditTotal').textContent = fmtKt;
  document.getElementById('cjBalDebit').textContent    = fmtDt;
  document.getElementById('cjBalKredit').textContent   = fmtKt;

  const statusEl = document.getElementById('cjStatus');
  const saveBtn  = document.getElementById('btnSaveCj');
  const diff = dt - kt;
  if (Math.abs(diff) < 0.01 && dt > 0) {
    statusEl.textContent = '= Balance';
    statusEl.className   = 'split-status ok';
    saveBtn.disabled     = false;
  } else if (Math.abs(diff) < 0.01 && dt === 0) {
    statusEl.textContent = 'Isi jumlah';
    statusEl.className   = 'split-status err';
    saveBtn.disabled     = true;
  } else {
    statusEl.textContent = diff > 0
      ? `Debet kelebihan ${formatRupiah(diff)}`
      : `Kredit kelebihan ${formatRupiah(Math.abs(diff))}`;
    statusEl.className   = 'split-status err';
    saveBtn.disabled     = true;
  }
}

// ----- Save (create or update) -----

function saveManualJournal() {
  const date        = document.getElementById('cjDate').value;
  const description = document.getElementById('cjDescription').value.trim();

  if (!date)        { showToast('Tanggal wajib diisi', 'warning');     return; }
  if (!description) { showToast('Keterangan wajib diisi', 'warning');  return; }

  const entries = [];
  let valid = true;

  document.getElementById('cjDebitLines').querySelectorAll('.split-line').forEach(line => {
    const code   = line.querySelector('.split-acct-select').value;
    const amount = parseFloat(line.querySelector('.split-amount-input').value) || 0;
    const note   = line.querySelector('.split-note-input').value.trim();
    if (!code || amount <= 0) { valid = false; return; }
    const acct = COA[code];
    entries.push({ accountCode: code, accountName: acct ? acct.name : code, debit: amount, kredit: 0, note });
  });

  document.getElementById('cjKreditLines').querySelectorAll('.split-line').forEach(line => {
    const code   = line.querySelector('.split-acct-select').value;
    const amount = parseFloat(line.querySelector('.split-amount-input').value) || 0;
    const note   = line.querySelector('.split-note-input').value.trim();
    if (!code || amount <= 0) { valid = false; return; }
    const acct = COA[code];
    entries.push({ accountCode: code, accountName: acct ? acct.name : code, debit: 0, kredit: amount, note });
  });

  if (!valid) {
    showToast('Semua baris harus memiliki akun dan jumlah yang valid', 'warning');
    return;
  }

  const dt = entries.reduce((s, e) => s + (e.debit  || 0), 0);
  const kt = entries.reduce((s, e) => s + (e.kredit || 0), 0);
  if (Math.abs(dt - kt) >= 0.01) {
    showToast('Total Debet harus sama dengan Total Kredit', 'error');
    return;
  }

  let savedJournal;
  if (_cjEditId) {
    // Edit mode — update existing
    const j = (AppState.manualJournals || []).find(j => j.id === _cjEditId);
    if (j) {
      j.date        = date;
      j.description = description;
      j.entries     = entries;
      savedJournal  = j;
    }
  } else {
    // Create mode
    const id = _nextManualJournalId();
    AppState.manualJournals = AppState.manualJournals || [];
    savedJournal = { id, no: id, date, description, isManual: true, entries };
    AppState.manualJournals.push(savedJournal);
  }

  _saveManualJournals();

  // Background sync to backend (no-op if not logged into backend)
  if (typeof BackendSync !== 'undefined' && savedJournal && !_cjEditId) {
    BackendSync.syncJournal({
      id:          savedJournal.id,
      date:        savedJournal.date,
      description: savedJournal.description,
      reference:   savedJournal.id,
      entries:     savedJournal.entries,
    });
  }

  // Rebuild AppState.journals + ledger + laporan
  AppState.journals = (AppState.journals || []).filter(j => !j.id?.startsWith('JE-MAN'));
  _mergeManualJournalsInto(AppState.journals);
  AppState.journalRows = flattenJournalForTable(AppState.journals);
  AppState.ledger      = buildLedger(AppState.journals);
  if (typeof _posRebuildReports === 'function') _posRebuildReports();

  renderJournalTable();
  closeCreateJournalModal();
  showToast(_cjEditId ? 'Jurnal berhasil diupdate' : 'Jurnal manual berhasil disimpan', 'success');
}

// ----- Delete -----

function deleteManualJournal(id) {
  if (!confirm(`Hapus jurnal ${id}? Tindakan ini tidak bisa dibatalkan.`)) return;
  AppState.manualJournals = (AppState.manualJournals || []).filter(j => j.id !== id);
  _saveManualJournals();
  AppState.journals    = (AppState.journals || []).filter(j => j.id !== id);
  AppState.journalRows = flattenJournalForTable(AppState.journals);
  AppState.ledger      = buildLedger(AppState.journals);
  if (typeof _posRebuildReports === 'function') _posRebuildReports();
  renderJournalTable();
  showToast(`Jurnal ${id} berhasil dihapus`, 'success');
}

// ===== TOAST =====
function showToast(message, type = 'info') {
  const container = document.getElementById('toastContainer');
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  const icons = {
    success: fIcon('check-circle', 15),
    error: fIcon('x-circle', 15),
    warning: fIcon('alert-triangle', 15),
    info: fIcon('info', 15)
  };
  toast.innerHTML = `<span style="flex-shrink:0">${icons[type] || fIcon('info', 15)}</span><span>${message}</span>`;
  container.appendChild(toast);
  setTimeout(() => toast.remove(), 4000);
}

// ===== FILTERS =====
function initFilters() {
  document.getElementById('searchTx').addEventListener('input', (e) => {
    AppState.txFilter.search = e.target.value;
    AppState.txPage = 1;
    renderTransactionsTable();
  });

  document.getElementById('filterType').addEventListener('change', (e) => {
    AppState.txFilter.type = e.target.value;
    AppState.txPage = 1;
    renderTransactionsTable();
  });

  document.getElementById('filterDateFrom').addEventListener('change', (e) => {
    AppState.txFilter.dateFrom = e.target.value;
    AppState.txPage = 1;
    renderTransactionsTable();
  });

  document.getElementById('filterDateTo').addEventListener('change', (e) => {
    AppState.txFilter.dateTo = e.target.value;
    AppState.txPage = 1;
    renderTransactionsTable();
  });

  document.getElementById('btnResetFilter').addEventListener('click', () => {
    AppState.txFilter = { search: '', type: '', categories: [], dateFrom: '', dateTo: '' };
    AppState.txPage = 1;
    document.getElementById('searchTx').value = '';
    document.getElementById('filterType').value = '';
    document.getElementById('filterDateFrom').value = '';
    document.getElementById('filterDateTo').value = '';
    // Reset multi-select state
    document.getElementById('categoryMultiSearch').value = '';
    updateCategoryFilter();
    renderTransactionsTable();
  });

  // ===== MULTI-SELECT CATEGORY =====
  // Toggle panel buka/tutup
  document.getElementById('categoryMultiBtn').addEventListener('click', (e) => {
    e.stopPropagation();
    const panel = document.getElementById('categoryMultiPanel');
    const btn = document.getElementById('categoryMultiBtn');
    const isOpen = panel.classList.toggle('open');
    btn.classList.toggle('open', isOpen);
    if (isOpen) {
      updateCategoryFilter();
      document.getElementById('categoryMultiSearch').focus();
    }
  });

  // Tutup panel jika klik di luar
  document.addEventListener('click', (e) => {
    const wrap = document.getElementById('categoryMultiWrap');
    if (wrap && !wrap.contains(e.target)) {
      document.getElementById('categoryMultiPanel').classList.remove('open');
      document.getElementById('categoryMultiBtn').classList.remove('open');
    }
  });

  // Search dalam panel
  document.getElementById('categoryMultiSearch').addEventListener('input', () => {
    updateCategoryFilter();
  });

  // Klik area "Semua Kategori" (bukan checkbox-nya langsung)
  document.getElementById('categorySelectAll').addEventListener('click', (e) => {
    if (e.target === document.getElementById('categorySelectAllChk')) return;
    const chk = document.getElementById('categorySelectAllChk');
    chk.checked = !chk.checked;
    _handleSelectAll(chk.checked);
  });

  // Checkbox "Semua Kategori"
  document.getElementById('categorySelectAllChk').addEventListener('change', (e) => {
    _handleSelectAll(e.target.checked);
  });
}

// ===== INIT APP =====
document.addEventListener('DOMContentLoaded', async () => {

  // Load data dari server files → localStorage (jika server tersedia)
  if (typeof DataStore !== 'undefined') await DataStore.init();

  // Navigation — static .btn[data-page] buttons (e.g. dashboard empty state button)
  document.querySelectorAll('.btn[data-page]').forEach(el => {
    el.addEventListener('click', (e) => {
      e.preventDefault();
      navigateTo(el.dataset.page);
    });
  });

  // Sidebar flyout init
  initSidebarFlyout();

  // Sidebar toggle (mobile)
  const _sidebar = document.getElementById('sidebar');
  const _sidebarOverlay = document.getElementById('sidebarOverlay');
  function closeSidebarMobile() {
    if (_sidebar) _sidebar.classList.remove('open');
    if (_sidebarOverlay) _sidebarOverlay.classList.remove('active');
  }
  const _sidebarToggleBtn = document.getElementById('sidebarToggle');
  if (_sidebarToggleBtn) {
    _sidebarToggleBtn.addEventListener('click', () => {
      const isOpen = _sidebar.classList.toggle('open');
      if (_sidebarOverlay) _sidebarOverlay.classList.toggle('active', isOpen);
    });
  }
  if (_sidebarOverlay) _sidebarOverlay.addEventListener('click', closeSidebarMobile);
  // Close sidebar when navigating on mobile
  document.querySelectorAll('.nav-item[data-page]').forEach(el => {
    el.addEventListener('click', () => { if (window.innerWidth <= 768) closeSidebarMobile(); });
  });

  // Export buttons
  document.getElementById('btnExportXlsx').addEventListener('click', handleExportXlsx);
  document.getElementById('btnExportSheet').addEventListener('click', handleExportGoogleSheets);

  // Lock button
  document.getElementById('btnLock').addEventListener('click', () => {
    if (!requirePermission('lock')) return;
    applyLockState(!AppState.isLocked);
    saveToStorage();
  });

  // Hard Reset button
  document.getElementById('btnHardReset').addEventListener('click', () => {
    if (!requirePermission('resetData')) return;
    showConfirmModal(
      'Hard Reset?',
      'Semua data transaksi, pengaturan kategori, dan jurnal akan dihapus <strong>permanen</strong> termasuk data yang tersimpan di browser. Tindakan ini tidak dapat dibatalkan. Lanjutkan?',
      'Ya, Hapus Semua',
      resetAllData,
      true
    );
  });

  // Modal
  document.getElementById('modalClose').addEventListener('click', closeModal);
  document.getElementById('modalCancel').addEventListener('click', closeModal);
  document.getElementById('modalOverlay').addEventListener('click', (e) => {
    if (e.target === document.getElementById('modalOverlay')) closeModal();
  });

  document.getElementById('splitModal').addEventListener('click', (e) => {
    if (e.target === document.getElementById('splitModal')) closeSplitModal();
  });

  // User modal close on overlay click
  document.getElementById('userModal').addEventListener('click', (e) => {
    if (e.target === document.getElementById('userModal')) closeUserModal();
  });

  // Change password modal close on overlay click
  document.getElementById('changePasswordModal').addEventListener('click', (e) => {
    if (e.target === document.getElementById('changePasswordModal')) closeChangePasswordModal();
  });

  // Role modal close on overlay click
  document.getElementById('roleModal').addEventListener('click', (e) => {
    if (e.target === document.getElementById('roleModal')) closeRoleModal();
  });

  // COA filter tabs
  document.querySelectorAll('[data-coa-filter]').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('[data-coa-filter]').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      renderCOATable(btn.dataset.coaFilter);
    });
  });

  // Init modules
  initUpload();
  initFilters();
  initReportFilters();

  // Render COA (always available)
  renderCOATable();

  // Load data dari localStorage, jika tidak ada tampilkan empty state
  if (!loadFromStorage()) {
    document.getElementById('emptyDashboard').classList.add('show');
  }

  // Init POS module
  try {
    if (typeof initPOS === 'function') initPOS();
  } catch(e) { console.error('[App] initPOS failed:', e); }

  // Init Purchase module
  try {
    if (typeof loadPurchaseData === 'function') loadPurchaseData();
  } catch(e) { console.error('[App] loadPurchaseData failed:', e); }

  // Init Sales/Customer module
  try {
    if (typeof loadCustomerData === 'function') loadCustomerData();
  } catch(e) { console.error('[App] loadCustomerData failed:', e); }

  // Restore jurnal manual (load + merge ke AppState)
  try {
    _restoreManualJournals();
  } catch(e) { console.error('[App] _restoreManualJournals failed:', e); }

  // Init authentication (login screen / session check)
  initAuth();

  // Set initial page (accounting group active by default)
  document.querySelector('.nav-group-btn[data-group="accounting"]')?.classList.add('active-group');
  navigateTo('dashboard');

  // Initialize feather icons
  if (typeof feather !== 'undefined') feather.replace();

});

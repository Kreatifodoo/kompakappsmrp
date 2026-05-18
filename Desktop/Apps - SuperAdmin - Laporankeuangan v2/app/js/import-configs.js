/**
 * IMPORT-CONFIGS.JS — Per-master import wizard configs.
 *
 * Each config:
 *   - title:            shown in modal header + filename
 *   - templateFilename: default name for downloaded CSV
 *   - columns[]:        { key, required?, type?, help? }
 *   - exampleRows[]:    sample rows shown in the downloaded template
 *   - notes:            HTML shown at bottom of step 1
 *   - preload(ctx):     async — fetch reference caches (existing rows, accounts, etc.)
 *   - validate(raw, allRows, ctx) -> {errors, warnings}
 *   - import(raw, ctx)  -> { message }
 *   - onComplete:       function name string (called after import to refresh list)
 */

const IMPORT_CONFIGS = {};

// ════════════════════════════════════════════════════════════════
// Customers
// ════════════════════════════════════════════════════════════════
IMPORT_CONFIGS.customer = {
  title: 'Customer',
  templateFilename: 'customer-import-template.csv',
  columns: [
    { key: 'code',          required: true,  help: 'Kode unik customer (mis. CUST-001)' },
    { key: 'name',          required: true,  help: 'Nama customer / pelanggan' },
    { key: 'email',         required: false, help: 'Email kontak (opsional)' },
    { key: 'phone',         required: false, help: 'Nomor telepon (opsional)' },
    { key: 'address',       required: false, help: 'Alamat lengkap (opsional)' },
    { key: 'receivable_account_code', required: false, help: 'Kode akun piutang. Kalau kosong, pakai mapping AR default. Contoh: 1-1200' },
  ],
  exampleRows: [
    { code: 'CUST-001', name: 'Toko Berkah Abadi',  email: 'toko@berkah.id', phone: '081234567890', address: 'Jl. Sudirman 10, Jakarta', receivable_account_code: '1-1200' },
    { code: 'CUST-002', name: 'Warung Pak Tani',    email: '',               phone: '0812-1111-2222', address: 'Pasar Senen Blok B', receivable_account_code: '' },
  ],
  notes: `<strong>Catatan:</strong>
    <ul style="margin:4px 0 0;padding-left:20px">
      <li>Kalau <code>receivable_account_code</code> kosong, sistem pakai mapping <code>ar</code> default (set via Accounting → Account Mappings).</li>
      <li>Customer dengan <code>code</code> yang sama akan di-skip (dianggap sudah ada).</li>
    </ul>`,
  async preload(ctx) {
    const [customers, accounts, mappings] = await Promise.all([
      Api.customers.list({limit: 1000}).catch(() => []),
      Api.accounts.list().catch(() => []),
      Api.accountMappings.list().catch(() => []),
    ]);
    ctx.existingCustomers = customers;
    ctx.accountsByCode = Object.fromEntries(accounts.map(a => [a.code, a]));
    ctx.arDefaultAccountId = mappings.find(m => m.key === 'ar')?.account_id || null;
  },
  validate(raw, all, ctx) {
    const errors = [], warnings = [];
    // Dup against existing
    if (ctx.existingCustomers?.some(c => c.code === raw.code)) {
      warnings.push(`Customer code "${raw.code}" sudah ada — akan di-skip`);
    }
    // Dup within file
    const dupInFile = all.filter(r => r.raw.code === raw.code).length;
    if (dupInFile > 1) errors.push(`Kode "${raw.code}" muncul ${dupInFile}× di file ini`);
    // Validate receivable account
    if (raw.receivable_account_code) {
      const acct = ctx.accountsByCode?.[raw.receivable_account_code];
      if (!acct) errors.push(`Akun piutang "${raw.receivable_account_code}" tidak ditemukan di COA`);
      else if (acct.type !== 'asset') warnings.push(`Akun "${raw.receivable_account_code}" bukan asset (tipe: ${acct.type})`);
    } else if (!ctx.arDefaultAccountId) {
      warnings.push(`Mapping AR default belum di-set; akan auto-skip kalau backend menolak`);
    }
    return { errors, warnings };
  },
  async import(raw, ctx) {
    // Skip duplicate gracefully
    if (ctx.existingCustomers?.some(c => c.code === raw.code)) {
      return { message: 'Skip (sudah ada)' };
    }
    const acctId = raw.receivable_account_code
      ? ctx.accountsByCode[raw.receivable_account_code]?.id
      : ctx.arDefaultAccountId;
    const body = {
      code: raw.code,
      name: raw.name,
      email: raw.email || null,
      phone: raw.phone || null,
      address: raw.address || null,
    };
    if (acctId) body.receivable_account_id = acctId;
    const res = await Api.customers.create(body);
    ctx.existingCustomers.push(res);
    return { message: `Customer ${res.code} dibuat` };
  },
  onComplete: 'renderMasterCustomerPage',
};


// ════════════════════════════════════════════════════════════════
// Suppliers
// ════════════════════════════════════════════════════════════════
IMPORT_CONFIGS.supplier = {
  title: 'Vendor / Supplier',
  templateFilename: 'supplier-import-template.csv',
  columns: [
    { key: 'code',          required: true,  help: 'Kode unik supplier (mis. SUP-001)' },
    { key: 'name',          required: true,  help: 'Nama vendor / supplier' },
    { key: 'email',         required: false, help: 'Email kontak (opsional)' },
    { key: 'phone',         required: false, help: 'Nomor telepon (opsional)' },
    { key: 'address',       required: false, help: 'Alamat lengkap (opsional)' },
    { key: 'payable_account_code', required: false, help: 'Kode akun hutang. Kosong = pakai mapping AP default. Contoh: 2-1100' },
  ],
  exampleRows: [
    { code: 'SUP-001', name: 'PT Distribusi Sejahtera', email: 'sales@distsejahtera.co.id', phone: '021-555-0100', address: 'Jl. Industri Raya 5, Bekasi', payable_account_code: '2-1100' },
    { code: 'SUP-002', name: 'UD Sumber Rezeki',        email: '',                          phone: '0813-9999-1111', address: 'Pasar Induk Tanah Abang', payable_account_code: '' },
  ],
  notes: `<strong>Catatan:</strong>
    <ul style="margin:4px 0 0;padding-left:20px">
      <li>Kalau <code>payable_account_code</code> kosong, sistem pakai mapping <code>ap</code> default.</li>
      <li>Vendor dengan <code>code</code> yang sama akan di-skip.</li>
    </ul>`,
  async preload(ctx) {
    const [suppliers, accounts, mappings] = await Promise.all([
      Api.suppliers.list({limit: 1000}).catch(() => []),
      Api.accounts.list().catch(() => []),
      Api.accountMappings.list().catch(() => []),
    ]);
    ctx.existingSuppliers = suppliers;
    ctx.accountsByCode = Object.fromEntries(accounts.map(a => [a.code, a]));
    ctx.apDefaultAccountId = mappings.find(m => m.key === 'ap')?.account_id || null;
  },
  validate(raw, all, ctx) {
    const errors = [], warnings = [];
    if (ctx.existingSuppliers?.some(s => s.code === raw.code)) {
      warnings.push(`Supplier code "${raw.code}" sudah ada — akan di-skip`);
    }
    if (all.filter(r => r.raw.code === raw.code).length > 1) {
      errors.push(`Kode "${raw.code}" duplikat di file`);
    }
    if (raw.payable_account_code) {
      const acct = ctx.accountsByCode?.[raw.payable_account_code];
      if (!acct) errors.push(`Akun hutang "${raw.payable_account_code}" tidak ditemukan`);
      else if (acct.type !== 'liability') warnings.push(`Akun "${raw.payable_account_code}" bukan liability (tipe: ${acct.type})`);
    } else if (!ctx.apDefaultAccountId) {
      warnings.push(`Mapping AP default belum di-set; backend mungkin tolak`);
    }
    return { errors, warnings };
  },
  async import(raw, ctx) {
    if (ctx.existingSuppliers?.some(s => s.code === raw.code)) {
      return { message: 'Skip (sudah ada)' };
    }
    const acctId = raw.payable_account_code
      ? ctx.accountsByCode[raw.payable_account_code]?.id
      : ctx.apDefaultAccountId;
    const body = {
      code: raw.code, name: raw.name,
      email: raw.email || null, phone: raw.phone || null, address: raw.address || null,
    };
    if (acctId) body.payable_account_id = acctId;
    const res = await Api.suppliers.create(body);
    ctx.existingSuppliers.push(res);
    return { message: `Supplier ${res.code} dibuat` };
  },
  onComplete: 'renderMasterVendorPage',
};


// ════════════════════════════════════════════════════════════════
// Items
// ════════════════════════════════════════════════════════════════
IMPORT_CONFIGS.item = {
  title: 'Item / Produk',
  templateFilename: 'item-import-template.csv',
  columns: [
    { key: 'sku',                required: true,  help: 'Kode unik item (mis. ITM-001)' },
    { key: 'name',               required: true,  help: 'Nama item / produk' },
    { key: 'type',               required: false, help: 'stock (default) / service / non_inventory' },
    { key: 'unit',               required: false, help: 'Satuan: pcs / kg / m / box (default pcs)' },
    { key: 'default_unit_price', required: false, help: 'Harga jual default (angka tanpa titik/koma)' },
    { key: 'default_unit_cost',  required: false, help: 'Harga beli default' },
    { key: 'min_stock',          required: false, help: 'Stok minimum untuk reorder report (default 0)' },
    { key: 'is_lot_tracked',     required: false, help: 'true / false — aktifkan tracking lot/batch (default false)' },
    { key: 'shelf_life_days',    required: false, help: 'Umur simpan dalam hari (opsional, hanya kalau lot-tracked)' },
  ],
  exampleRows: [
    { sku: 'ITM-001', name: 'Kopi Sachet Cap Luwak',  type: 'stock',   unit: 'pcs', default_unit_price: 3500,  default_unit_cost: 2000,  min_stock: 100, is_lot_tracked: 'false', shelf_life_days: '' },
    { sku: 'ITM-002', name: 'Roti Tawar Spesial',     type: 'stock',   unit: 'pcs', default_unit_price: 12000, default_unit_cost: 6000,  min_stock: 20,  is_lot_tracked: 'true',  shelf_life_days: 7 },
    { sku: 'SVC-001', name: 'Jasa Antar (Delivery)',  type: 'service', unit: 'rit', default_unit_price: 15000, default_unit_cost: '',    min_stock: '',  is_lot_tracked: 'false', shelf_life_days: '' },
  ],
  notes: `<strong>Catatan:</strong>
    <ul style="margin:4px 0 0;padding-left:20px">
      <li>Field angka: pakai titik untuk desimal (mis. <code>3500.50</code>), tanpa pemisah ribuan.</li>
      <li><code>is_lot_tracked=true</code> wajib untuk produk yang ada expiry (makanan, farmasi).</li>
      <li>Item dengan <code>sku</code> sama akan di-skip.</li>
    </ul>`,
  async preload(ctx) {
    const items = await Api.items.list({limit: 1000}).catch(() => []);
    ctx.existingSkus = new Set(items.map(i => i.sku));
  },
  validate(raw, all, ctx) {
    const errors = [], warnings = [];
    if (ctx.existingSkus?.has(raw.sku)) warnings.push(`SKU "${raw.sku}" sudah ada — akan di-skip`);
    if (all.filter(r => r.raw.sku === raw.sku).length > 1) errors.push(`SKU "${raw.sku}" duplikat di file`);
    if (raw.type && !['stock', 'service', 'non_inventory'].includes(raw.type)) {
      errors.push(`type "${raw.type}" tidak valid (harus: stock/service/non_inventory)`);
    }
    for (const fld of ['default_unit_price', 'default_unit_cost', 'min_stock', 'shelf_life_days']) {
      if (raw[fld] && isNaN(parseFloat(raw[fld]))) errors.push(`${fld} bukan angka valid: "${raw[fld]}"`);
    }
    if (raw.is_lot_tracked && !['true', 'false', '1', '0', 'yes', 'no', ''].includes(raw.is_lot_tracked.toLowerCase())) {
      errors.push(`is_lot_tracked harus true/false`);
    }
    return { errors, warnings };
  },
  async import(raw, ctx) {
    if (ctx.existingSkus?.has(raw.sku)) return { message: 'Skip (SKU sudah ada)' };
    const truthy = v => ['true','1','yes'].includes(String(v||'').toLowerCase());
    const body = {
      sku: raw.sku,
      name: raw.name,
      type: raw.type || 'stock',
      unit: raw.unit || 'pcs',
      default_unit_price: parseFloat(raw.default_unit_price) || 0,
      default_unit_cost:  parseFloat(raw.default_unit_cost)  || 0,
      min_stock:          parseFloat(raw.min_stock)          || 0,
      is_lot_tracked:     truthy(raw.is_lot_tracked),
      shelf_life_days:    raw.shelf_life_days ? parseInt(raw.shelf_life_days, 10) : null,
    };
    const res = await Api.items.create(body);
    ctx.existingSkus.add(res.sku);
    return { message: `Item ${res.sku} dibuat` };
  },
  onComplete: 'renderInventoryPage',
};


// ════════════════════════════════════════════════════════════════
// Warehouses
// ════════════════════════════════════════════════════════════════
IMPORT_CONFIGS.warehouse = {
  title: 'Gudang',
  templateFilename: 'warehouse-import-template.csv',
  columns: [
    { key: 'code',       required: true,  help: 'Kode unik gudang (mis. WH-01)' },
    { key: 'name',       required: true,  help: 'Nama gudang' },
    { key: 'is_default', required: false, help: 'true / false — gudang default tenant (default false)' },
  ],
  exampleRows: [
    { code: 'WH-01', name: 'Gudang Utama Jakarta', is_default: 'true' },
    { code: 'WH-02', name: 'Gudang Cabang Bandung', is_default: 'false' },
  ],
  notes: `<strong>Tip:</strong> Setelah import, lokasi internal (rak/bin) bisa ditambahkan via <strong>Master Gudang → Locations</strong>.`,
  async preload(ctx) {
    const whs = await Api.warehouses.list().catch(() => []);
    ctx.existingCodes = new Set(whs.map(w => w.code));
  },
  validate(raw, all, ctx) {
    const errors = [], warnings = [];
    if (ctx.existingCodes?.has(raw.code)) warnings.push(`Kode "${raw.code}" sudah ada — skip`);
    if (all.filter(r => r.raw.code === raw.code).length > 1) errors.push(`Kode "${raw.code}" duplikat di file`);
    return { errors, warnings };
  },
  async import(raw, ctx) {
    if (ctx.existingCodes?.has(raw.code)) return { message: 'Skip (sudah ada)' };
    const truthy = v => ['true','1','yes'].includes(String(v||'').toLowerCase());
    const res = await Api.warehouses.create({
      code: raw.code, name: raw.name, is_default: truthy(raw.is_default),
    });
    ctx.existingCodes.add(res.code);
    return { message: `Gudang ${res.code} dibuat` };
  },
  onComplete: 'renderWarehouseMaster',
};


// ════════════════════════════════════════════════════════════════
// Chart of Accounts (COA)
// ════════════════════════════════════════════════════════════════
IMPORT_CONFIGS.account = {
  title: 'Chart of Accounts',
  templateFilename: 'coa-import-template.csv',
  columns: [
    { key: 'code',        required: true,  help: 'Kode akun (mis. 5-1500). Format X-XXXX' },
    { key: 'name',        required: true,  help: 'Nama akun' },
    { key: 'type',        required: true,  help: 'asset / liability / equity / income / expense' },
    { key: 'normal_side', required: false, help: 'debit / credit (default: ikut tipe akun)' },
    { key: 'description', required: false, help: 'Keterangan singkat' },
    { key: 'is_cash',     required: false, help: 'true kalau akun ini cash/bank (untuk Payment)' },
  ],
  exampleRows: [
    { code: '5-1500', name: 'Beban Listrik & Air', type: 'expense', normal_side: 'debit', description: 'Tagihan PLN + PDAM', is_cash: 'false' },
    { code: '1-1130', name: 'Bank BRI - Giro',     type: 'asset',   normal_side: 'debit', description: 'Rekening operasional', is_cash: 'true' },
  ],
  notes: `<strong>Catatan:</strong> Kode akun harus unique. Akun yang sudah ada di-skip.`,
  async preload(ctx) {
    const accts = await Api.accounts.list().catch(() => []);
    ctx.existingCodes = new Set(accts.map(a => a.code));
  },
  validate(raw, all, ctx) {
    const errors = [], warnings = [];
    const validTypes = ['asset', 'liability', 'equity', 'income', 'expense'];
    if (!validTypes.includes(raw.type)) {
      errors.push(`type harus salah satu: ${validTypes.join(' / ')}`);
    }
    if (raw.normal_side && !['debit', 'credit'].includes(raw.normal_side)) {
      errors.push(`normal_side harus 'debit' atau 'credit'`);
    }
    if (ctx.existingCodes?.has(raw.code)) warnings.push(`Kode "${raw.code}" sudah ada — skip`);
    if (all.filter(r => r.raw.code === raw.code).length > 1) errors.push(`Duplikat kode "${raw.code}"`);
    return { errors, warnings };
  },
  async import(raw, ctx) {
    if (ctx.existingCodes?.has(raw.code)) return { message: 'Skip (sudah ada)' };
    const truthy = v => ['true','1','yes'].includes(String(v||'').toLowerCase());
    // Default normal_side: asset/expense → debit, else credit
    const ns = raw.normal_side || (['asset','expense'].includes(raw.type) ? 'debit' : 'credit');
    const res = await Api.accounts.create({
      code: raw.code, name: raw.name, type: raw.type,
      normal_side: ns,
      description: raw.description || null,
      is_cash: truthy(raw.is_cash),
    });
    ctx.existingCodes.add(res.code);
    return { message: `Akun ${res.code} dibuat` };
  },
  onComplete: 'renderCOATable',
};


// ════════════════════════════════════════════════════════════════
// Work Centers
// ════════════════════════════════════════════════════════════════
IMPORT_CONFIGS.workCenter = {
  title: 'Work Center',
  templateFilename: 'work-center-import-template.csv',
  columns: [
    { key: 'code',                   required: true,  help: 'Kode unik (mis. WC-ASM)' },
    { key: 'name',                   required: true,  help: 'Nama work center' },
    { key: 'cost_per_hour',          required: false, help: 'Biaya per jam (Rp). Default 0' },
    { key: 'capacity_hours_per_day', required: false, help: 'Kapasitas jam/hari (default 8)' },
    { key: 'notes',                  required: false, help: 'Catatan' },
  ],
  exampleRows: [
    { code: 'WC-CUT', name: 'Cutting Station',  cost_per_hour: 50000, capacity_hours_per_day: 8, notes: 'Mesin potong' },
    { code: 'WC-ASM', name: 'Assembly Line A',  cost_per_hour: 60000, capacity_hours_per_day: 10, notes: '' },
    { code: 'WC-QC',  name: 'Quality Control',  cost_per_hour: 40000, capacity_hours_per_day: 8, notes: 'Inspeksi' },
  ],
  async preload(ctx) {
    const wcs = await Api.workCenters.list({}).catch(() => []);
    ctx.existingCodes = new Set(wcs.map(w => w.code));
  },
  validate(raw, all, ctx) {
    const errors = [], warnings = [];
    if (ctx.existingCodes?.has(raw.code)) warnings.push(`Kode "${raw.code}" sudah ada — skip`);
    if (all.filter(r => r.raw.code === raw.code).length > 1) errors.push(`Duplikat kode`);
    if (raw.cost_per_hour && isNaN(parseFloat(raw.cost_per_hour))) errors.push(`cost_per_hour bukan angka`);
    if (raw.capacity_hours_per_day && isNaN(parseFloat(raw.capacity_hours_per_day))) errors.push(`capacity_hours_per_day bukan angka`);
    return { errors, warnings };
  },
  async import(raw, ctx) {
    if (ctx.existingCodes?.has(raw.code)) return { message: 'Skip (sudah ada)' };
    const res = await Api.workCenters.create({
      code: raw.code, name: raw.name,
      cost_per_hour: parseFloat(raw.cost_per_hour) || 0,
      capacity_hours_per_day: parseFloat(raw.capacity_hours_per_day) || 8,
      notes: raw.notes || null,
    });
    ctx.existingCodes.add(res.code);
    return { message: `WC ${res.code} dibuat` };
  },
  onComplete: 'renderWorkCenterPage',
};

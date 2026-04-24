/**
 * CHART OF ACCOUNTS (COA)
 * Standar akuntansi untuk PT Global Kreatif Inovasi
 * Berbasis transaksi yang terlihat pada bank statement BCA
 */

const COA = {
  // ===== 1. ASET =====
  '1-0000': { code: '1-0000', name: 'ASET', type: 'Aset', category: 'Header', normal: 'Debit', desc: 'Kelompok Aset' },

  // Aset Lancar
  '1-1000': { code: '1-1000', name: 'Aset Lancar', type: 'Aset', category: 'Header', normal: 'Debit', desc: '' },
  '1-1100': { code: '1-1100', name: 'Kas', type: 'Aset', category: 'Kas & Bank', normal: 'Debit', desc: 'Uang tunai di tangan' },
  '1-1110': { code: '1-1110', name: 'Bank BCA - Rekening Giro 2913139313', type: 'Aset', category: 'Kas & Bank', normal: 'Debit', desc: 'Rekening Giro BCA atas nama PT Global Kreatif Inovasi' },
  '1-1120': { code: '1-1120', name: 'Bank Lain', type: 'Aset', category: 'Kas & Bank', normal: 'Debit', desc: 'Rekening bank lainnya' },
  '1-1200': { code: '1-1200', name: 'Piutang Usaha', type: 'Aset', category: 'Piutang', normal: 'Debit', desc: 'Tagihan kepada pelanggan atas jasa/produk' },
  '1-1210': { code: '1-1210', name: 'Piutang Lain-lain', type: 'Aset', category: 'Piutang', normal: 'Debit', desc: 'Piutang di luar usaha utama' },
  '1-1300': { code: '1-1300', name: 'Uang Muka / Advance', type: 'Aset', category: 'Uang Muka', normal: 'Debit', desc: 'Pembayaran di muka kepada vendor/supplier' },
  '1-1400': { code: '1-1400', name: 'Persediaan', type: 'Aset', category: 'Persediaan', normal: 'Debit', desc: 'Stok barang dagangan / bahan' },
  '1-1500': { code: '1-1500', name: 'Biaya Dibayar di Muka', type: 'Aset', category: 'Prepaid', normal: 'Debit', desc: 'Biaya yang sudah dibayar namun belum jatuh tempo' },
  '1-1510': { code: '1-1510', name: 'Prepaid Maintenance / Support', type: 'Aset', category: 'Prepaid', normal: 'Debit', desc: 'Biaya maintenance software/sistem yang dibayar di muka' },

  // Aset Tidak Lancar
  '1-2000': { code: '1-2000', name: 'Aset Tidak Lancar', type: 'Aset', category: 'Header', normal: 'Debit', desc: '' },
  '1-2100': { code: '1-2100', name: 'Peralatan & Perlengkapan', type: 'Aset', category: 'Aset Tetap', normal: 'Debit', desc: 'Komputer, server, peralatan kantor' },
  '1-2110': { code: '1-2110', name: 'Server & Infrastruktur IT', type: 'Aset', category: 'Aset Tetap', normal: 'Debit', desc: 'Hardware server dan infrastruktur teknologi' },
  '1-2200': { code: '1-2200', name: 'Akumulasi Penyusutan', type: 'Aset', category: 'Kontra Aset', normal: 'Kredit', desc: 'Akumulasi penyusutan aset tetap' },
  '1-2300': { code: '1-2300', name: 'Aset Tidak Berwujud', type: 'Aset', category: 'Intangible', normal: 'Debit', desc: 'Lisensi software, hak cipta' },
  '1-2310': { code: '1-2310', name: 'Lisensi Software (Odoo)', type: 'Aset', category: 'Intangible', normal: 'Debit', desc: 'Biaya lisensi Odoo ERP' },

  // ===== 2. LIABILITAS =====
  '2-0000': { code: '2-0000', name: 'LIABILITAS', type: 'Liabilitas', category: 'Header', normal: 'Kredit', desc: 'Kelompok Kewajiban' },

  // Liabilitas Jangka Pendek
  '2-1000': { code: '2-1000', name: 'Liabilitas Jangka Pendek', type: 'Liabilitas', category: 'Header', normal: 'Kredit', desc: '' },
  '2-1100': { code: '2-1100', name: 'Utang Usaha', type: 'Liabilitas', category: 'Utang', normal: 'Kredit', desc: 'Kewajiban kepada pemasok/vendor' },
  '2-1200': { code: '2-1200', name: 'Utang Gaji & Tunjangan', type: 'Liabilitas', category: 'Utang', normal: 'Kredit', desc: 'Kewajiban pembayaran gaji karyawan' },
  '2-1300': { code: '2-1300', name: 'Utang Pajak', type: 'Liabilitas', category: 'Pajak', normal: 'Kredit', desc: 'Kewajiban pajak PPh, PPN, dsb' },
  '2-1310': { code: '2-1310', name: 'Utang PPh 21', type: 'Liabilitas', category: 'Pajak', normal: 'Kredit', desc: 'PPh pasal 21 atas penghasilan karyawan' },
  '2-1320': { code: '2-1320', name: 'Utang PPh 23', type: 'Liabilitas', category: 'Pajak', normal: 'Kredit', desc: 'PPh pasal 23 atas jasa' },
  '2-1330': { code: '2-1330', name: 'Utang PPN', type: 'Liabilitas', category: 'Pajak', normal: 'Kredit', desc: 'Pajak Pertambahan Nilai' },
  '2-1400': { code: '2-1400', name: 'Pendapatan Diterima di Muka', type: 'Liabilitas', category: 'Deferred', normal: 'Kredit', desc: 'Pembayaran dari pelanggan sebelum jasa diserahkan' },
  '2-1500': { code: '2-1500', name: 'Biaya Akrual', type: 'Liabilitas', category: 'Akrual', normal: 'Kredit', desc: 'Beban yang sudah terjadi namun belum dibayar' },
  '2-1600': { code: '2-1600', name: 'Utang Bank Jangka Pendek', type: 'Liabilitas', category: 'Utang Bank', normal: 'Kredit', desc: 'Pinjaman bank jatuh tempo < 1 tahun' },

  // Liabilitas Jangka Panjang
  '2-2000': { code: '2-2000', name: 'Liabilitas Jangka Panjang', type: 'Liabilitas', category: 'Header', normal: 'Kredit', desc: '' },
  '2-2100': { code: '2-2100', name: 'Utang Bank Jangka Panjang', type: 'Liabilitas', category: 'Utang Bank', normal: 'Kredit', desc: 'Pinjaman bank jatuh tempo > 1 tahun' },

  // ===== 3. EKUITAS =====
  '3-0000': { code: '3-0000', name: 'EKUITAS', type: 'Ekuitas', category: 'Header', normal: 'Kredit', desc: 'Kelompok Modal' },
  '3-1000': { code: '3-1000', name: 'Modal Disetor', type: 'Ekuitas', category: 'Modal', normal: 'Kredit', desc: 'Modal dasar yang disetor pemegang saham' },
  '3-2000': { code: '3-2000', name: 'Laba Ditahan', type: 'Ekuitas', category: 'Laba', normal: 'Kredit', desc: 'Akumulasi laba/rugi tahun-tahun sebelumnya' },
  '3-3000': { code: '3-3000', name: 'Laba/Rugi Tahun Berjalan', type: 'Ekuitas', category: 'Laba', normal: 'Kredit', desc: 'Laba atau rugi periode berjalan' },
  '3-4000': { code: '3-4000', name: 'Prive / Dividen', type: 'Ekuitas', category: 'Prive', normal: 'Debit', desc: 'Pengambilan pribadi atau dividen pemegang saham' },

  // ===== 4. PENDAPATAN =====
  '4-0000': { code: '4-0000', name: 'PENDAPATAN', type: 'Pendapatan', category: 'Header', normal: 'Kredit', desc: 'Kelompok Pendapatan' },

  // Pendapatan Usaha
  '4-1000': { code: '4-1000', name: 'Pendapatan Usaha', type: 'Pendapatan', category: 'Header', normal: 'Kredit', desc: '' },
  '4-1100': { code: '4-1100', name: 'Pendapatan Implementasi ERP/Odoo', type: 'Pendapatan', category: 'Pendapatan Jasa', normal: 'Kredit', desc: 'Pendapatan dari proyek implementasi sistem ERP Odoo' },
  '4-1200': { code: '4-1200', name: 'Pendapatan Support & Maintenance', type: 'Pendapatan', category: 'Pendapatan Jasa', normal: 'Kredit', desc: 'Pendapatan support dan maintenance sistem' },
  '4-1300': { code: '4-1300', name: 'Pendapatan Training / Pelatihan', type: 'Pendapatan', category: 'Pendapatan Jasa', normal: 'Kredit', desc: 'Pendapatan dari kegiatan training/pelatihan' },
  '4-1400': { code: '4-1400', name: 'Pendapatan Custom Development', type: 'Pendapatan', category: 'Pendapatan Jasa', normal: 'Kredit', desc: 'Pendapatan pengembangan custom modul ERP' },
  '4-1500': { code: '4-1500', name: 'Pendapatan Lisensi Software', type: 'Pendapatan', category: 'Pendapatan Jasa', normal: 'Kredit', desc: 'Pendapatan dari penjualan lisensi software' },
  '4-1600': { code: '4-1600', name: 'Pendapatan Hosting / Server', type: 'Pendapatan', category: 'Pendapatan Jasa', normal: 'Kredit', desc: 'Pendapatan layanan hosting server' },

  // Pendapatan Lain-lain
  '4-2000': { code: '4-2000', name: 'Pendapatan Lain-lain', type: 'Pendapatan', category: 'Pendapatan Lain', normal: 'Kredit', desc: '' },
  '4-2100': { code: '4-2100', name: 'Pendapatan Bunga Bank', type: 'Pendapatan', category: 'Pendapatan Lain', normal: 'Kredit', desc: 'Bunga jasa giro dari bank' },
  '4-2200': { code: '4-2200', name: 'Keuntungan Selisih Kurs', type: 'Pendapatan', category: 'Pendapatan Lain', normal: 'Kredit', desc: 'Laba dari transaksi mata uang asing (USD)' },
  '4-2300': { code: '4-2300', name: 'Pendapatan Lain-lain', type: 'Pendapatan', category: 'Pendapatan Lain', normal: 'Kredit', desc: 'Pendapatan di luar usaha utama' },

  // ===== 5. BEBAN =====
  '5-0000': { code: '5-0000', name: 'BEBAN', type: 'Beban', category: 'Header', normal: 'Debit', desc: 'Kelompok Beban' },

  // Beban Operasional
  '5-1000': { code: '5-1000', name: 'Beban Operasional', type: 'Beban', category: 'Header', normal: 'Debit', desc: '' },
  '5-1100': { code: '5-1100', name: 'Beban Gaji & Tunjangan', type: 'Beban', category: 'Beban SDM', normal: 'Debit', desc: 'Gaji, tunjangan, dan bonus karyawan (payroll)' },
  '5-1110': { code: '5-1110', name: 'Beban Gaji Karyawan (Payroll)', type: 'Beban', category: 'Beban SDM', normal: 'Debit', desc: 'Transfer payroll bulanan ke rekening karyawan' },
  '5-1120': { code: '5-1120', name: 'Beban Honorarium / Freelancer', type: 'Beban', category: 'Beban SDM', normal: 'Debit', desc: 'Pembayaran ke konsultan/freelancer' },
  '5-1130': { code: '5-1130', name: 'Beban THR & Bonus', type: 'Beban', category: 'Beban SDM', normal: 'Debit', desc: 'Tunjangan hari raya dan bonus karyawan' },

  '5-2000': { code: '5-2000', name: 'Beban Teknologi & Infrastruktur', type: 'Beban', category: 'Header', normal: 'Debit', desc: '' },
  '5-2100': { code: '5-2100', name: 'Beban Lisensi Odoo / Software', type: 'Beban', category: 'Beban IT', normal: 'Debit', desc: 'Biaya lisensi Odoo HK Limited dan software lain' },
  '5-2200': { code: '5-2200', name: 'Beban Hosting & Server', type: 'Beban', category: 'Beban IT', normal: 'Debit', desc: 'Biaya sewa server, VPS, cloud hosting' },
  '5-2300': { code: '5-2300', name: 'Beban Maintenance Sistem', type: 'Beban', category: 'Beban IT', normal: 'Debit', desc: 'Biaya pemeliharaan sistem dan aplikasi' },
  '5-2400': { code: '5-2400', name: 'Beban Internet & Komunikasi', type: 'Beban', category: 'Beban IT', normal: 'Debit', desc: 'Biaya internet, telepon, komunikasi' },

  '5-3000': { code: '5-3000', name: 'Beban Umum & Administrasi', type: 'Beban', category: 'Header', normal: 'Debit', desc: '' },
  '5-3100': { code: '5-3100', name: 'Beban Administrasi Bank', type: 'Beban', category: 'Beban Admin', normal: 'Debit', desc: 'Biaya administrasi rekening bank' },
  '5-3200': { code: '5-3200', name: 'Beban Sewa Kantor', type: 'Beban', category: 'Beban Admin', normal: 'Debit', desc: 'Biaya sewa ruang kantor' },
  '5-3300': { code: '5-3300', name: 'Beban Perlengkapan Kantor', type: 'Beban', category: 'Beban Admin', normal: 'Debit', desc: 'Alat tulis kantor dan perlengkapan operasional' },
  '5-3400': { code: '5-3400', name: 'Beban Transportasi & Perjalanan', type: 'Beban', category: 'Beban Admin', normal: 'Debit', desc: 'Biaya perjalanan dinas dan transportasi' },
  '5-3500': { code: '5-3500', name: 'Beban Marketing & Promosi', type: 'Beban', category: 'Beban Admin', normal: 'Debit', desc: 'Iklan, promosi, dan kegiatan pemasaran' },
  '5-3600': { code: '5-3600', name: 'Beban Pajak & Perizinan', type: 'Beban', category: 'Beban Admin', normal: 'Debit', desc: 'Pajak perusahaan dan biaya perizinan' },
  '5-3700': { code: '5-3700', name: 'Beban Profesional (Legal, Audit)', type: 'Beban', category: 'Beban Admin', normal: 'Debit', desc: 'Jasa konsultan hukum, akuntan publik' },
  '5-3800': { code: '5-3800', name: 'Beban Lain-lain', type: 'Beban', category: 'Beban Admin', normal: 'Debit', desc: 'Pengeluaran operasional yang tidak terkategori' },

  '5-4000': { code: '5-4000', name: 'Beban Non-Operasional', type: 'Beban', category: 'Header', normal: 'Debit', desc: '' },
  '5-4100': { code: '5-4100', name: 'Beban Bunga Bank', type: 'Beban', category: 'Beban Keuangan', normal: 'Debit', desc: 'Bunga pinjaman kepada bank' },
  '5-4200': { code: '5-4200', name: 'Kerugian Selisih Kurs', type: 'Beban', category: 'Beban Keuangan', normal: 'Debit', desc: 'Rugi dari transaksi mata uang asing' },
  '5-4300': { code: '5-4300', name: 'Beban Penyusutan', type: 'Beban', category: 'Beban Keuangan', normal: 'Debit', desc: 'Penyusutan aset tetap' },

  // ===== POS (Point of Sale) =====
  '4-5000': { code: '4-5000', name: 'POS - Pendapatan Penjualan', type: 'Pendapatan', category: 'Pendapatan POS', normal: 'Kredit', desc: 'Pendapatan penjualan dari Point of Sale' },
  '4-5100': { code: '4-5100', name: 'POS - Pendapatan Service', type: 'Pendapatan', category: 'Pendapatan POS', normal: 'Kredit', desc: 'Pendapatan service charge dari Point of Sale' },
  '4-5200': { code: '4-5200', name: 'POS - Diskon Penjualan', type: 'Pendapatan', category: 'Pendapatan POS', normal: 'Debit', desc: 'Diskon yang diberikan kepada pelanggan POS (contra revenue)' },
  '5-5000': { code: '5-5000', name: 'Harga Pokok Penjualan', type: 'Beban', category: 'HPP', normal: 'Debit', desc: '' },
  '5-5100': { code: '5-5100', name: 'HPP - Makanan & Minuman', type: 'Beban', category: 'HPP', normal: 'Debit', desc: 'Harga pokok penjualan produk makanan dan minuman POS' },
};

/**
 * Aturan mapping otomatis dari deskripsi transaksi ke COA
 * Berdasarkan pola yang ditemukan di bank statement BCA GKI
 */
const COA_MAPPING_RULES = [
  // ===== PENDAPATAN (CR) =====
  {
    pattern: /ODOO HK|odoo hk/i,
    type: 'CR',
    debit: '1-1110',   // Bank BCA
    kredit: '4-1500',  // Pendapatan Lisensi Software
    desc: 'Penerimaan lisensi Odoo dari Odoo HK Limited'
  },
  {
    pattern: /INDIVARA|supp maint|maintenance/i,
    type: 'CR',
    debit: '1-1110',
    kredit: '4-1200',  // Pendapatan Support & Maintenance
    desc: 'Penerimaan support & maintenance'
  },
  {
    pattern: /WHISPER MEDIA|DOO ERP|ERP.*DP|INVOICE/i,
    type: 'CR',
    debit: '1-1110',
    kredit: '4-1100',  // Pendapatan Implementasi ERP
    desc: 'Penerimaan proyek implementasi ERP'
  },
  {
    pattern: /KLIK SEMANGAT|tunning server|Custom HRD|Pem tunning|Pembyaran odoo/i,
    type: 'CR',
    debit: '1-1110',
    kredit: '4-1400',  // Pendapatan Custom Development
    desc: 'Penerimaan custom development & server'
  },
  {
    pattern: /KALIBATA SARANA|trainer/i,
    type: 'CR',
    debit: '1-1110',
    kredit: '4-1300',  // Pendapatan Training
    desc: 'Penerimaan pendapatan training'
  },
  {
    pattern: /METAMINE INTEGRASI|CERMAIMAKMUR|MULIAPACK|INOVASI PANGAN|ARUNA JAYA|PT DRAGON/i,
    type: 'CR',
    debit: '1-1110',
    kredit: '4-1100',  // Pendapatan Implementasi ERP (default untuk pelanggan baru)
    desc: 'Penerimaan dari pelanggan - implementasi/jasa'
  },
  {
    pattern: /NUNING MARTANTRINI/i,
    type: 'CR',
    debit: '1-1110',
    kredit: '4-2300',  // Pendapatan Lain-lain
    desc: 'Penerimaan lain-lain'
  },
  {
    pattern: /SETORAN TUNAI/i,
    type: 'CR',
    debit: '1-1110',
    kredit: '1-1100',  // Kas (setoran tunai dari kas ke bank)
    desc: 'Setoran tunai ke rekening bank'
  },
  {
    pattern: /KR OTOMATIS.*USD|TX.*AUTOCR/i,
    type: 'CR',
    debit: '1-1110',
    kredit: '4-1500',  // Pendapatan Lisensi (Odoo HK biasanya USD)
    desc: 'Penerimaan otomatis (transaksi USD - Odoo HK)'
  },
  {
    pattern: /SWITCHING CR|KR OTOMATIS/i,
    type: 'CR',
    debit: '1-1110',
    kredit: '4-1100',  // Default CR = pendapatan jasa
    desc: 'Penerimaan transfer masuk'
  },

  // ===== BEBAN (DB) =====
  {
    pattern: /payroll|PAYROLL/i,
    type: 'DB',
    debit: '5-1110',  // Beban Gaji
    kredit: '1-1110',
    desc: 'Pembayaran gaji karyawan (payroll)'
  },
  {
    pattern: /KIKI MOHAMAD RIZKI/i,
    type: 'DB',
    debit: '5-1110',  // Default transfer ke Kiki = gaji/tunjangan
    kredit: '1-1110',
    desc: 'Transfer ke Kiki Mohamad Rizki (Gaji/Operasional)'
  },
  {
    pattern: /BIAYA ADM/i,
    type: 'DB',
    debit: '5-3100',  // Biaya Admin Bank
    kredit: '1-1110',
    desc: 'Biaya administrasi bank'
  },
  {
    pattern: /server|SERVER/i,
    type: 'DB',
    debit: '5-2200',  // Hosting & Server
    kredit: '1-1110',
    desc: 'Pembayaran hosting/server'
  },
];

/**
 * Mendapatkan semua akun sebagai array
 */
function getAllAccounts() {
  return Object.values(COA);
}

/**
 * Mendapatkan akun berdasarkan tipe (Aset/Liabilitas/Ekuitas/Pendapatan/Beban)
 */
function getAccountsByType(type) {
  return Object.values(COA).filter(a => a.type === type && a.category !== 'Header');
}

/**
 * Mendapatkan akun berdasarkan kode pertama (1=Aset, 2=Liabilitas, dst)
 */
function getAccountsByGroup(group) {
  return Object.values(COA).filter(a => a.code.startsWith(group + '-') && a.category !== 'Header');
}

/**
 * Auto-mapping transaksi ke COA berdasarkan deskripsi
 */
function autoMapTransaction(tx) {
  const desc = (tx.description + ' ' + tx.party + ' ' + tx.ref).toLowerCase();
  const txType = tx.type; // 'CR' atau 'DB'

  for (const rule of COA_MAPPING_RULES) {
    if (rule.type === txType && rule.pattern.test(desc)) {
      return {
        debitAccount: rule.debit,
        kreditAccount: rule.kredit,
        mappingDesc: rule.desc,
        confidence: 'auto'
      };
    }
  }

  // Default fallback
  if (txType === 'CR') {
    return {
      debitAccount: '1-1110',    // Bank BCA
      kreditAccount: '4-2300',   // Pendapatan Lain-lain
      mappingDesc: 'Penerimaan tidak terkategori',
      confidence: 'default'
    };
  } else {
    return {
      debitAccount: '5-3800',    // Beban Lain-lain
      kreditAccount: '1-1110',   // Bank BCA
      mappingDesc: 'Pengeluaran tidak terkategori',
      confidence: 'default'
    };
  }
}

/**
 * Format nama akun dengan kode
 */
function formatAccountName(code) {
  const acct = COA[code];
  if (!acct) return code;
  return `${acct.code} - ${acct.name}`;
}

/**
 * Mendapatkan daftar akun untuk dropdown (hanya akun detail, bukan header)
 */
function getAccountOptions() {
  return Object.values(COA)
    .filter(a => a.category !== 'Header')
    .map(a => ({ value: a.code, label: `${a.code} - ${a.name}`, type: a.type }));
}

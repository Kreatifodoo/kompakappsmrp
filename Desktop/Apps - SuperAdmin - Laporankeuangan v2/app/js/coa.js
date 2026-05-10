/**
 * CHART OF ACCOUNTS (COA) — full online mode
 *
 * COA object ini di-populate dari backend (per-tenant) saat user login via
 * BackendLoader.loadCOA() di app/js/backend-loader.js. Hardcoded data lama
 * sudah di-strip — sekarang COA = {} sampai backend hydrate.
 *
 * Helper functions di bawah (getAllAccounts, getAccountsByType, dst.) tetap
 * bekerja karena mereka baca dari window.COA — yang akan terisi otomatis
 * setelah login.
 *
 * COA_MAPPING_RULES (legacy bank statement parser) di bagian bawah file ini
 * tetap dipertahankan — itu local-only logic yang independen dari backend.
 */

const COA = {};


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

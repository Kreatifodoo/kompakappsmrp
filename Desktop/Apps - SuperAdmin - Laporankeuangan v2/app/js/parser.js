/**
 * PDF PARSER - BCA Bank Statement
 * Mendukung format e-Statement BCA Rekening Giro
 *
 * Format NYATA dari PDF.js (diverifikasi via browser console):
 *
 * Setiap transaksi adalah SATU BARIS dengan double-space antar token:
 *   "01/04  SALDO  AWAL  48,128.02"
 *   "03/04  SWITCHING  CR  TRANSFER  DR  008  6,250,000.00  6,298,128.02"
 *   "03/04  TRSF  E-BANKING  DB  0304/FTSCY/WS95051  6,250,000.00  DB  48,128.02"
 *   "METAMINE  INTEGRASI"        <- party (baris lanjutan)
 *   "/PLAZA  MANDI"              <- party lanjutan
 *   "6250000.00"                 <- raw amount (duplikat, skip)
 *   "30/04  BIAYA  ADM  364.52  DB  0.00"
 *
 * Algoritma: scan tiap baris, cek apakah diawali DD/MM (tanggal).
 * Jika ya -> parse inline sebagai 1 transaksi.
 * Jika tidak -> tambahkan ke party baris sebelumnya.
 */

// Set PDF.js worker
if (typeof pdfjsLib !== 'undefined') {
  pdfjsLib.GlobalWorkerOptions.workerSrc =
    'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
}

/**
 * Extract semua teks dari PDF menggunakan PDF.js
 * Mengembalikan array baris teks (flat, urut atas-bawah per halaman)
 */
async function extractPdfLines(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = async (e) => {
      try {
        const typedArray = new Uint8Array(e.target.result);
        const pdf = await pdfjsLib.getDocument({ data: typedArray }).promise;
        const allLines = [];

        for (let pageNum = 1; pageNum <= pdf.numPages; pageNum++) {
          const page = await pdf.getPage(pageNum);
          const content = await page.getTextContent();

          // Grup item berdasarkan Y coordinate (baris yang sama)
          const byY = {};
          content.items.forEach(item => {
            const y = Math.round(item.transform[5] / 2) * 2;
            const x = Math.round(item.transform[4]);
            if (!byY[y]) byY[y] = [];
            byY[y].push({ x, text: item.str.trim() });
          });

          // Sort Y descending (atas ke bawah di PDF), gabungkan per baris
          const sortedYs = Object.keys(byY)
            .map(Number)
            .sort((a, b) => b - a);

          sortedYs.forEach(y => {
            const items = byY[y].sort((a, b) => a.x - b.x);
            const lineText = items.map(i => i.text).join('  ').trim();
            if (lineText) allLines.push(lineText);
          });
        }

        resolve(allLines);
      } catch (err) {
        reject(err);
      }
    };
    reader.onerror = reject;
    reader.readAsArrayBuffer(file);
  });
}

/**
 * Parse header informasi rekening dari baris teks
 */
function parseHeaderFromLines(lines) {
  const info = {
    accountNo: '2913139313',
    accountName: 'PT GLOBAL KREATIF INOVASI',
    period: '',
    currency: 'IDR',
    bank: 'BCA',
    branch: 'KCU PONDOK INDAH',
    accountType: 'Rekening Giro'
  };

  for (const line of lines) {
    // Periode: "PERIODE  :  APRIL 2023"
    const periodeMatch = line.match(/PERIODE\s*:\s*((?:JANUARI|FEBRUARI|MARET|APRIL|MEI|JUNI|JULI|AGUSTUS|SEPTEMBER|OKTOBER|NOVEMBER|DESEMBER)\s+\d{4})/i);
    if (periodeMatch) {
      info.period = periodeMatch[1].trim().toUpperCase();
    }
    if (/GLOBAL\s+KREATIF\s+INOVASI/i.test(line)) {
      info.accountName = 'PT GLOBAL KREATIF INOVASI';
    }
  }

  return info;
}

/**
 * Parse ringkasan saldo dari baris teks
 * Format: "SALDO  AWAL  :  48,128.02"  atau  "MUTASI  CR  :  211,999,236.50  9"
 */
function parseSummaryFromLines(lines) {
  const summary = {
    saldoAwal: 0, mutasiCR: 0, mutasiDB: 0, saldoAkhir: 0,
    txCRCount: 0, txDBCount: 0
  };

  // Join semua baris untuk mencari pola summary (dengan multi-space)
  const fullText = lines.join('\n');

  // Normalisasi multi-space ke single space untuk regex matching
  const normalText = fullText.replace(/\s+/g, ' ');

  const saldoAwal = normalText.match(/SALDO AWAL\s*:\s*([\d.,]+)/i);
  if (saldoAwal) summary.saldoAwal = parseAmount(saldoAwal[1]);

  const mutasiCR = normalText.match(/MUTASI CR\s*:\s*([\d.,]+)\s+(\d+)/i);
  if (mutasiCR) {
    summary.mutasiCR = parseAmount(mutasiCR[1]);
    summary.txCRCount = parseInt(mutasiCR[2]);
  }

  const mutasiDB = normalText.match(/MUTASI DB\s*:\s*([\d.,]+)\s+(\d+)/i);
  if (mutasiDB) {
    summary.mutasiDB = parseAmount(mutasiDB[1]);
    summary.txDBCount = parseInt(mutasiDB[2]);
  }

  const saldoAkhir = normalText.match(/SALDO AKHIR\s*:\s*([\d.,]+)/i);
  if (saldoAkhir) summary.saldoAkhir = parseAmount(saldoAkhir[1]);

  return summary;
}

/**
 * Parse angka format BCA: koma = ribuan, titik = desimal
 * "211,999,236.50" -> 211999236.50
 * "48,128.02"      -> 48128.02
 */
function parseAmount(str) {
  if (!str) return 0;
  const cleaned = str.trim().replace(/,/g, '');
  const val = parseFloat(cleaned);
  return isNaN(val) ? 0 : val;
}

// Alias
function parseBCAAmount(str) { return parseAmount(str); }

/**
 * Dapatkan tahun dan bulan dari string periode
 */
function getPeriodYearMonth(periodStr) {
  const months = {
    'JANUARI': '01', 'FEBRUARI': '02', 'MARET': '03', 'APRIL': '04',
    'MEI': '05', 'JUNI': '06', 'JULI': '07', 'AGUSTUS': '08',
    'SEPTEMBER': '09', 'OKTOBER': '10', 'NOVEMBER': '11', 'DESEMBER': '12'
  };
  const upper = (periodStr || '').toUpperCase();
  let month = '01';
  for (const [key, val] of Object.entries(months)) {
    if (upper.includes(key)) { month = val; break; }
  }
  const yearMatch = upper.match(/(\d{4})/);
  const year = yearMatch ? yearMatch[1] : new Date().getFullYear().toString();
  return { year, month };
}

/**
 * Format tanggal dari DD/MM + year ke YYYY-MM-DD
 */
function formatDate(ddmm, year) {
  if (!ddmm) return '';
  const parts = ddmm.split('/');
  if (parts.length < 2) return ddmm;
  return `${year}-${parts[1].padStart(2, '0')}-${parts[0].padStart(2, '0')}`;
}

/**
 * Cek apakah string adalah angka raw tanpa format (duplikat): "3500000.00"
 * Bukan amount terformat dengan koma ribuan
 */
function isRawAmount(str) {
  return /^\d+\.\d{2}$/.test(str) && !/,/.test(str);
}

/**
 * PARSER UTAMA - Parse transaksi dari baris teks PDF BCA
 *
 * Format nyata (verified dari browser console log):
 * Setiap transaksi = 1 baris diawali DD/MM dengan double-space antar token
 *
 * Contoh baris transaksi:
 *   "01/04  SALDO  AWAL  48,128.02"
 *   "03/04  SWITCHING  CR  TRANSFER  DR  008  6,250,000.00  6,298,128.02"
 *   "03/04  TRSF  E-BANKING  DB  0304/FTSCY/WS95051  6,250,000.00  DB  48,128.02"
 *   "30/04  BIAYA  ADM  364.52  DB  0.00"
 *   "26/04  KR  OTOMATIS  TX880433AUTOCR-IR  19,415,903.50  19,416,031.52"
 *
 * Baris tanpa tanggal di depan = party/keterangan lanjutan dari transaksi sebelumnya
 *   "METAMINE  INTEGRASI"
 *   "6250000.00"   <- raw amount duplikat (dibuang)
 *   "KIKI  MOHAMAD  RIZKI"
 */
function parseTransactionsFromLines(lines, period) {
  const { year } = getPeriodYearMonth(period);
  const transactions = [];
  let txCounter = 0;

  // Baris yang dimulai dengan tanggal DD/MM (diikuti minimal 1 spasi + konten)
  const TX_LINE = /^(\d{1,2})\/(\d{2})\s+(.+)$/;

  // Baris yang HANYA berisi tanggal DD/MM (tidak ada di format ini, tapi sebagai fallback)
  const DATE_ONLY = /^(\d{1,2})\/(\d{2})$/;

  // Baris header/footer yang dibuang
  const SKIP_RE = [
    /^REKENING\s+GIRO$/i,
    /^KCU\s/i,
    /^GLOBAL\s+KREATIF/i,
    /^NO\.\s*REKENING/i,
    /^GROGOL/i,
    /^HALAMAN/i,
    /^TJ\s+DUREN/i,
    /^PERIODE\s*:/i,
    /^SOHO\s+CAPITAL/i,
    /^MATA\s+UANG/i,
    /^JAKARRA/i,
    /^INDONESIA$/i,
    /^CATATAN/i,
    /^[•·]\s+Apabila/i,
    /^dengan\s+akhir/i,
    /^tercantum/i,
    /^Bersambung/i,
    /^TANGGAL\s+KETERANGAN/i,
    /^SALDO\s+AWAL\s*:/i,
    /^MUTASI\s+CR\s*:/i,
    /^MUTASI\s+DB\s*:/i,
    /^SALDO\s+AKHIR\s*:/i,
  ];

  function shouldSkip(line) {
    return SKIP_RE.some(p => p.test(line.trim()));
  }

  // State: tx saat ini yang sedang dibangun (belum selesai = menunggu party lines)
  let current = null;

  function finalizeCurrent() {
    if (!current) return;
    if (current.type !== 'SALDO_AWAL' && current.amount <= 0) {
      current = null;
      return;
    }
    transactions.push(current);
    current = null;
  }

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line) continue;
    if (shouldSkip(line)) continue;

    // Cek apakah baris ini dimulai dengan tanggal
    const txMatch = line.match(TX_LINE) || line.match(DATE_ONLY);

    if (txMatch) {
      // Simpan transaksi sebelumnya
      finalizeCurrent();

      const dd = txMatch[1];
      const mm = txMatch[2];
      const rest = txMatch[3] ? txMatch[3].trim() : ''; // konten setelah tanggal

      // Normalisasi multi-space ke single space untuk parsing
      const normRest = rest.replace(/\s+/g, ' ');

      // Identifikasi tipe transaksi dari awal normRest
      let txType = '';
      let description = '';
      let txRest = normRest;

      if (/^SALDO\s+AWAL/i.test(normRest)) {
        txType = 'SALDO_AWAL'; description = 'SALDO AWAL';
        txRest = normRest.replace(/^SALDO\s+AWAL\s*/i, '');
      } else if (/^TRSF\s+E-BANKING\s+DB/i.test(normRest)) {
        txType = 'DB'; description = 'TRSF E-BANKING DB';
        txRest = normRest.replace(/^TRSF\s+E-BANKING\s+DB\s*/i, '');
      } else if (/^TRSF\s+E-BANKING\s+CR/i.test(normRest)) {
        txType = 'CR'; description = 'TRSF E-BANKING CR';
        txRest = normRest.replace(/^TRSF\s+E-BANKING\s+CR\s*/i, '');
      } else if (/^BIAYA\s+ADM/i.test(normRest)) {
        txType = 'DB'; description = 'BIAYA ADM';
        txRest = normRest.replace(/^BIAYA\s+ADM\s*/i, '');
      } else if (/^DB\s+OTOMATIS/i.test(normRest)) {
        txType = 'DB'; description = 'DB OTOMATIS';
        txRest = normRest.replace(/^DB\s+OTOMATIS\s*/i, '');
      } else if (/^BA\s+JASA/i.test(normRest)) {
        txType = 'DB'; description = 'BA JASA E-BANKING';
        txRest = normRest.replace(/^BA\s+JASA\s+E-BANKING\s*/i, '');
      } else if (/^SETORAN\s+TUNAI/i.test(normRest)) {
        txType = 'CR'; description = 'SETORAN TUNAI';
        txRest = normRest.replace(/^SETORAN\s+TUNAI\s*/i, '');
      } else if (/^KR\s+OTOMATIS/i.test(normRest)) {
        txType = 'CR'; description = 'KR OTOMATIS';
        txRest = normRest.replace(/^KR\s+OTOMATIS\s*/i, '');
      } else if (/^SWITCHING\s+CR/i.test(normRest)) {
        txType = 'CR'; description = 'SWITCHING CR';
        txRest = normRest.replace(/^SWITCHING\s+CR\s*/i, '');
      } else if (/^SWITCHING\s+DB/i.test(normRest)) {
        txType = 'DB'; description = 'SWITCHING DB';
        txRest = normRest.replace(/^SWITCHING\s+DB\s*/i, '');
      } else if (/^AUTO\s+DEBIT/i.test(normRest)) {
        txType = 'DB'; description = 'AUTO DEBIT';
        txRest = normRest.replace(/^AUTO\s+DEBIT\s*/i, '');
      } else if (/^DEBIT/i.test(normRest)) {
        txType = 'DB'; description = 'DEBIT';
        txRest = normRest.replace(/^DEBIT\s*/i, '');
      } else if (/^KREDIT/i.test(normRest)) {
        txType = 'CR'; description = 'KREDIT';
        txRest = normRest.replace(/^KREDIT\s*/i, '');
      } else {
        // Unknown type - akan ditentukan dari DB marker setelah parsing token
        txType = 'UNKNOWN';
        description = normRest.substring(0, 30);
        txRest = normRest;
      }

      // Parse token dari sisa baris (txRest)
      // Format: [ref] [amount_fmt] [DB] [saldo_fmt]
      // Semua token sekarang sudah single-space
      const tokens = txRest.split(' ').filter(t => t);

      // Amount pattern: angka dengan koma ribuan dan titik desimal
      // "6,250,000.00" atau "364.52" atau "48,128.02"
      const AMT = /^\d{1,3}(?:,\d{3})*\.\d{2}$|^\d+\.\d{2}$/;

      const amounts = [];
      const partyTokens = [];
      let ref = '';
      let hasDBMarker = false;

      for (const tok of tokens) {
        if (AMT.test(tok) && tok.includes(',')) {
          // Formatted amount (e.g., "6,250,000.00")
          amounts.push(parseAmount(tok));
        } else if (/^\d+\.\d{2}$/.test(tok) && !tok.includes(',')) {
          // Could be raw unformatted amount OR small formatted amount like "364.52"
          // Check if it looks like a full raw duplicate (large integer part)
          // Treat as amount if <= 2 amounts collected so far
          if (amounts.length < 2) {
            amounts.push(parseAmount(tok));
          }
          // else skip as raw duplicate
        } else if (/^(DB|CR)$/.test(tok)) {
          if (tok === 'DB') hasDBMarker = true;
        } else if (/^[A-Z0-9]+\/[A-Z0-9]+\/[A-Z0-9]+$/.test(tok)) {
          ref = tok; // ref like "0304/FTSCY/WS95051"
        } else if (/^(LLG-[A-Z]+|TX[A-Z0-9]+)$/.test(tok)) {
          ref = tok;
        } else if (/^TRANSFER$/.test(tok)) {
          // "TRANSFER DR 008" — skip TRANSFER keyword
        } else if (/^DR$/.test(tok)) {
          // Skip DR keyword (part of "TRANSFER DR 008")
        } else if (/^\d{3,4}$/.test(tok) && partyTokens.length === 0 && ref === '') {
          // CBG code like "008" or "0938" — skip
        } else if (/^-\d{10}$/.test(tok)) {
          // Account number ref
        } else if (/^TANGGAL\s*:\d/.test(tok) || /^TANGGAL$/.test(tok) || tok === ':') {
          // Skip TANGGAL annotation
        } else if (tok) {
          partyTokens.push(tok);
        }
      }

      // Tentukan tipe transaksi untuk tipe yang tidak dikenal
      // Aturan: ada "DB" setelah nominal → Debit, kosong → Credit
      if (txType === 'UNKNOWN') {
        txType = hasDBMarker ? 'DB' : 'CR';
      }

      // Determine amount and saldo
      let txAmount = 0;
      let txSaldo = 0;

      if (txType === 'SALDO_AWAL') {
        txSaldo = amounts[0] || 0;
        txAmount = 0;
      } else if (amounts.length >= 2) {
        txAmount = amounts[0];
        txSaldo = amounts[amounts.length - 1];
      } else if (amounts.length === 1) {
        txAmount = amounts[0];
      }

      // Correction: for DB with no saldo (e.g. last tx), amount might still be valid
      if (txType === 'DB' && hasDBMarker && txAmount === 0 && amounts.length === 1) {
        txAmount = amounts[0];
      }

      const party = partyTokens.join(' ').trim();
      const fullDescription = [description, party].filter(Boolean).join(' - ');

      current = {
        id: `TX-${++txCounter}`,
        date: formatDate(`${dd}/${mm}`, year),
        dateRaw: `${dd}/${mm}`,
        type: txType,
        description,
        fullDescription,
        ref,
        party,
        amount: txAmount,
        saldo: txSaldo,
        raw: line,
        coaMapping: null
      };

    } else {
      // Baris non-tanggal: bisa berupa party, raw amount, atau keterangan lanjutan
      if (!current) continue;

      // Skip raw amount duplikat (integer besar tanpa koma)
      const normLine = line.replace(/\s+/g, ' ').trim();
      if (/^\d+\.\d{2}$/.test(normLine) || /^USD\d/.test(normLine) || /^\/ROC\//.test(normLine)) {
        continue;
      }
      // Skip "TANGGAL :DD/MM rawamt" annotation lines
      if (/^TANGGAL\s*:\s*\d{2}\/\d{2}/i.test(normLine)) {
        // Extract raw amount if present but skip the whole line
        continue;
      }
      // Clearing reference
      if (/^Clearing\d+$/i.test(normLine)) continue;
      // Account number reference
      if (/^-\d{10}$/.test(normLine)) continue;

      // Tambahkan ke party
      const partyAdd = normLine.replace(/\s+/g, ' ').trim();
      if (partyAdd) {
        current.party = current.party ? current.party + ' ' + partyAdd : partyAdd;
        current.fullDescription = [current.description, current.party].filter(Boolean).join(' - ');
      }
    }
  }

  // Finalisasi tx terakhir
  finalizeCurrent();

  return transactions;
}

/**
 * Main function: parse satu file PDF bank statement BCA
 */
async function parseBankStatement(file) {
  const lines = await extractPdfLines(file);

  const header = parseHeaderFromLines(lines);
  const summary = parseSummaryFromLines(lines);
  const transactions = parseTransactionsFromLines(lines, header.period);

  // Hapus duplikat SALDO_AWAL (hanya simpan yang pertama)
  let saldoAwalCount = 0;
  const filteredTx = transactions.filter(tx => {
    if (tx.type === 'SALDO_AWAL') {
      saldoAwalCount++;
      return saldoAwalCount === 1;
    }
    return true;
  });
  transactions.length = 0;
  filteredTx.forEach(tx => transactions.push(tx));

  // Apply COA mapping
  transactions.forEach(tx => {
    if (tx.type !== 'SALDO_AWAL') {
      tx.coaMapping = autoMapTransaction(tx);
    }
  });

  const crCount = transactions.filter(t => t.type === 'CR').length;
  const dbCount = transactions.filter(t => t.type === 'DB').length;
  return { fileName: file.name, header, summary, transactions, rawLines: lines };
}

/**
 * Merge hasil parse dari beberapa file
 */
function mergeStatements(statements) {
  const merged = {
    periods: [],
    accountInfo: statements[0]?.header || {},
    transactions: [],
    summary: {
      saldoAwal: 0, mutasiCR: 0, mutasiDB: 0, saldoAkhir: 0,
      txCRCount: 0, txDBCount: 0
    }
  };

  // Sort by filename (period order)
  statements.sort((a, b) => (a.fileName || '').localeCompare(b.fileName || ''));

  statements.forEach((stmt, idx) => {
    if (stmt.header.period) merged.periods.push(stmt.header.period);

    if (idx === 0) merged.summary.saldoAwal = stmt.summary.saldoAwal;
    merged.summary.saldoAkhir = stmt.summary.saldoAkhir;
    merged.summary.mutasiCR += stmt.summary.mutasiCR;
    merged.summary.mutasiDB += stmt.summary.mutasiDB;
    merged.summary.txCRCount += stmt.summary.txCRCount;
    merged.summary.txDBCount += stmt.summary.txDBCount;

    stmt.transactions.forEach(tx => {
      if (tx.type === 'SALDO_AWAL' && idx > 0) return;
      merged.transactions.push({
        ...tx,
        period: stmt.header.period,
        sourceFile: stmt.fileName
      });
    });
  });

  return merged;
}

/**
 * Format angka ke Rupiah
 */
function formatRupiah(amount, withPrefix = true) {
  if (amount === null || amount === undefined || isNaN(amount)) return withPrefix ? 'Rp 0' : '0';
  const formatted = Math.abs(amount).toLocaleString('id-ID', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  });
  return withPrefix ? `Rp ${formatted}` : formatted;
}

/**
 * Format angka ringkas (juta/miliar)
 */
function formatRupiahShort(amount) {
  if (!amount && amount !== 0) return 'Rp 0';
  const abs = Math.abs(amount);
  const sign = amount < 0 ? '-' : '';
  if (abs >= 1e9) return `${sign}Rp ${(abs / 1e9).toFixed(1)}M`;
  if (abs >= 1e6) return `${sign}Rp ${(abs / 1e6).toFixed(1)}jt`;
  if (abs >= 1e3) return `${sign}Rp ${(abs / 1e3).toFixed(0)}rb`;
  return `${sign}Rp ${abs.toFixed(0)}`;
}

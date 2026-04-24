/**
 * EXPORT MODULE
 * Export ke format Excel/Google Sheets (.xlsx)
 * Format mengikuti referensi Google Sheet:
 * Sheet 1: Transaksi (Bank Statement)
 * Sheet 2: Jurnal Entri
 * Sheet 3: Chart of Accounts
 * Sheet 4: Laporan Laba Rugi
 * Sheet 5: Neraca
 * Sheet 6: Arus Kas
 */

/**
 * Style warna header (hex tanpa #)
 */
const STYLE = {
  headerBg: '1e3a5f',       // Dark blue
  headerFont: 'FFFFFF',
  subheaderBg: '2563eb',    // Medium blue
  subheaderFont: 'FFFFFF',
  sectionBg: 'dbeafe',      // Light blue
  sectionFont: '1e3a5f',
  totalBg: 'fef3c7',        // Yellow tint
  totalFont: '92400e',
  grandtotalBg: '1e3a5f',
  grandtotalFont: 'FFFFFF',
  crBg: 'f0fdf4',           // Light green
  crFont: '166534',
  dbBg: 'fef2f2',           // Light red
  dbFont: '991b1b',
  altRow: 'f8fafc',
  borderColor: 'e2e8f0',
};

/**
 * Buat style cell untuk XLSX
 */
function makeStyle(bgColor, fontColor, bold = false, align = 'left', fontSize = 10) {
  return {
    fill: { patternType: 'solid', fgColor: { rgb: bgColor } },
    font: { bold, color: { rgb: fontColor }, sz: fontSize, name: 'Calibri' },
    alignment: { horizontal: align, vertical: 'center', wrapText: false },
    border: {
      top: { style: 'thin', color: { rgb: STYLE.borderColor } },
      bottom: { style: 'thin', color: { rgb: STYLE.borderColor } },
      left: { style: 'thin', color: { rgb: STYLE.borderColor } },
      right: { style: 'thin', color: { rgb: STYLE.borderColor } }
    }
  };
}

/**
 * Helper: buat cell dengan style
 */
function C(value, style, type = 's') {
  const cell = { v: value, s: style };
  if (type === 'n') cell.t = 'n';
  else if (type === 's') cell.t = 's';
  else cell.t = type;
  return cell;
}

/**
 * Helper: encode cell address
 */
function addr(row, col) {
  const cols = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
  let colStr = '';
  if (col >= 26) colStr = cols[Math.floor(col / 26) - 1] + cols[col % 26];
  else colStr = cols[col];
  return `${colStr}${row + 1}`;
}

/**
 * Build worksheet dari array of arrays dengan styles
 */
function buildWorksheet(data, colWidths = []) {
  const ws = {};
  let maxRow = 0;
  let maxCol = 0;

  data.forEach((row, r) => {
    if (!row) return;
    row.forEach((cell, c) => {
      if (cell === null || cell === undefined) return;
      const cellAddr = addr(r, c);
      if (typeof cell === 'object' && cell.v !== undefined) {
        ws[cellAddr] = cell;
      } else {
        ws[cellAddr] = { v: cell, t: typeof cell === 'number' ? 'n' : 's' };
      }
      if (r > maxRow) maxRow = r;
      if (c > maxCol) maxCol = c;
    });
  });

  ws['!ref'] = `A1:${addr(maxRow, maxCol)}`;

  if (colWidths.length > 0) {
    ws['!cols'] = colWidths.map(w => ({ wch: w }));
  }

  return ws;
}

/**
 * SHEET 1: Transaksi Bank Statement
 * Format: Tanggal | Keterangan | Referensi | Pihak | Tipe | Debit | Kredit | Saldo | Kategori COA | Kode Debit | Kode Kredit
 */
function buildTransactionSheet(transactions, header) {
  const hStyle = makeStyle(STYLE.headerBg, STYLE.headerFont, true, 'center', 11);
  const titleStyle = makeStyle(STYLE.headerBg, STYLE.headerFont, true, 'left', 13);
  const subStyle = makeStyle(STYLE.subheaderBg, STYLE.subheaderFont, true, 'left', 10);
  const crStyle = makeStyle(STYLE.crBg, STYLE.crFont, false, 'left');
  const dbStyle = makeStyle(STYLE.dbBg, STYLE.dbFont, false, 'left');
  const numCrStyle = makeStyle(STYLE.crBg, STYLE.crFont, false, 'right');
  const numDbStyle = makeStyle(STYLE.dbBg, STYLE.dbFont, false, 'right');
  const normalStyle = makeStyle('FFFFFF', '374151', false, 'left');
  const numStyle = makeStyle('FFFFFF', '374151', false, 'right');
  const totalStyle = makeStyle(STYLE.totalBg, STYLE.totalFont, true, 'right');
  const altStyle = makeStyle(STYLE.altRow, '374151', false, 'left');
  const altNumStyle = makeStyle(STYLE.altRow, '374151', false, 'right');

  const data = [];
  const period = transactions[0]?.period || header?.period || '';
  const company = header?.accountName || 'PT GLOBAL KREATIF INOVASI';

  // Title
  data.push([C(`${company} - LAPORAN MUTASI REKENING BCA`, titleStyle)]);
  data.push([C(`Periode: ${period} | No. Rekening: ${header?.accountNo || '2913139313'} | Mata Uang: IDR`, subStyle)]);
  data.push([null]);

  // Header row
  const headers = ['Tanggal', 'Keterangan', 'Referensi', 'Pihak / Counterparty', 'Tipe', 'Debit (DB)', 'Kredit (CR)', 'Saldo', 'Kategori COA', 'Kode Akun Debit', 'Kode Akun Kredit'];
  data.push(headers.map(h => C(h, hStyle)));

  // Data rows
  transactions.forEach((tx, i) => {
    const isAlt = i % 2 === 1;
    const isCR = tx.type === 'CR';
    const isDB = tx.type === 'DB';
    const rowStyle = isCR ? crStyle : (isDB ? dbStyle : (isAlt ? altStyle : normalStyle));
    const numRowStyle = isCR ? numCrStyle : (isDB ? numDbStyle : (isAlt ? altNumStyle : numStyle));

    const mapping = tx.coaMapping || {};
    const catName = tx.type === 'CR'
      ? (COA[mapping.kreditAccount]?.name || '-')
      : (COA[mapping.debitAccount]?.name || '-');

    if (tx.type === 'SALDO_AWAL') {
      data.push([
        C(tx.date || '', makeStyle('f0f9ff', '0c4a6e', true, 'left')),
        C('SALDO AWAL', makeStyle('f0f9ff', '0c4a6e', true, 'left')),
        C('', makeStyle('f0f9ff', '0c4a6e', false, 'left')),
        C('', makeStyle('f0f9ff', '0c4a6e', false, 'left')),
        C('', makeStyle('f0f9ff', '0c4a6e', false, 'left')),
        C('', makeStyle('f0f9ff', '0c4a6e', false, 'right')),
        C('', makeStyle('f0f9ff', '0c4a6e', false, 'right')),
        C(tx.saldo || 0, { ...makeStyle('f0f9ff', '0c4a6e', true, 'right'), t: 'n' }, 'n'),
        C('', makeStyle('f0f9ff', '0c4a6e', false, 'left')),
        C('', makeStyle('f0f9ff', '0c4a6e', false, 'left')),
        C('', makeStyle('f0f9ff', '0c4a6e', false, 'left')),
      ]);
    } else {
      data.push([
        C(tx.date || '', rowStyle),
        C(tx.description || '', rowStyle),
        C(tx.ref || '', rowStyle),
        C(tx.party || '', rowStyle),
        C(tx.type || '', { ...rowStyle, alignment: { horizontal: 'center' } }),
        C(isDB ? (tx.amount || 0) : 0, numRowStyle, 'n'),
        C(isCR ? (tx.amount || 0) : 0, numRowStyle, 'n'),
        C(tx.saldo || 0, numRowStyle, 'n'),
        C(catName, rowStyle),
        C(mapping.debitAccount || '', rowStyle),
        C(mapping.kreditAccount || '', rowStyle),
      ]);
    }
  });

  // Spacer
  data.push([null]);

  // Summary
  const sumStyle = makeStyle(STYLE.totalBg, STYLE.totalFont, true, 'left');
  const txFiltered = transactions.filter(t => t.type !== 'SALDO_AWAL');
  const totalCR = txFiltered.filter(t => t.type === 'CR').reduce((s, t) => s + (t.amount || 0), 0);
  const totalDB = txFiltered.filter(t => t.type === 'DB').reduce((s, t) => s + (t.amount || 0), 0);
  const saldoAkhir = transactions.filter(t => t.saldo > 0).slice(-1)[0]?.saldo || 0;

  data.push([C('RINGKASAN', makeStyle(STYLE.headerBg, STYLE.headerFont, true, 'left'))]);
  data.push([C('Saldo Awal', sumStyle), null, null, null, null, null, null, C(transactions.find(t=>t.type==='SALDO_AWAL')?.saldo || 0, { ...makeStyle(STYLE.totalBg, STYLE.totalFont, true, 'right') }, 'n')]);
  data.push([C('Total Kredit (Masuk)', sumStyle), null, null, null, null, null, C(totalCR, { ...makeStyle(STYLE.crBg, STYLE.crFont, true, 'right') }, 'n')]);
  data.push([C('Total Debit (Keluar)', sumStyle), null, null, null, null, C(totalDB, { ...makeStyle(STYLE.dbBg, STYLE.dbFont, true, 'right') }, 'n')]);
  data.push([C('Saldo Akhir', makeStyle(STYLE.grandtotalBg, STYLE.grandtotalFont, true, 'left')), null, null, null, null, null, null, C(saldoAkhir, { ...makeStyle(STYLE.grandtotalBg, STYLE.grandtotalFont, true, 'right') }, 'n')]);

  return buildWorksheet(data, [12, 22, 22, 28, 6, 18, 18, 18, 28, 16, 16]);
}

/**
 * SHEET 2: Jurnal Entri
 */
function buildJournalSheet(journalRows) {
  const hStyle = makeStyle(STYLE.headerBg, STYLE.headerFont, true, 'center', 11);
  const titleStyle = makeStyle(STYLE.headerBg, STYLE.headerFont, true, 'left', 13);
  const oddStyle = makeStyle('FFFFFF', '374151', false, 'left');
  const evenStyle = makeStyle(STYLE.altRow, '374151', false, 'left');
  const numOddStyle = makeStyle('FFFFFF', '374151', false, 'right');
  const numEvenStyle = makeStyle(STYLE.altRow, '374151', false, 'right');

  const data = [];
  data.push([C('JURNAL ENTRI - PT GLOBAL KREATIF INOVASI', titleStyle)]);
  data.push([C('Double-Entry Bookkeeping | Berbasis Transaksi Bank Statement BCA', makeStyle(STYLE.subheaderBg, STYLE.subheaderFont, false, 'left', 10))]);
  data.push([null]);

  const headers = ['No.', 'Tanggal', 'No. Jurnal', 'Keterangan', 'Kode Akun', 'Nama Akun', 'Debit', 'Kredit'];
  data.push(headers.map(h => C(h, hStyle)));

  let altToggle = false;
  journalRows.forEach((row, i) => {
    if (row.isFirst) altToggle = !altToggle;
    const rs = altToggle ? oddStyle : evenStyle;
    const rn = altToggle ? numOddStyle : numEvenStyle;

    data.push([
      C(row.rowNum || '', rs),
      C(row.date || '', rs),
      C(row.journalId || '', rs),
      C(row.description || '', rs),
      C(row.accountCode || '', rs),
      C(row.accountName || '', rs),
      C(row.debit || 0, rn, 'n'),
      C(row.kredit || 0, rn, 'n'),
    ]);
  });

  // Totals
  const totalDebit = journalRows.reduce((s, r) => s + (r.debit || 0), 0);
  const totalKredit = journalRows.reduce((s, r) => s + (r.kredit || 0), 0);
  data.push([null]);
  const totStyle = makeStyle(STYLE.totalBg, STYLE.totalFont, true, 'right');
  data.push([
    null, null, null, null, null,
    C('TOTAL', makeStyle(STYLE.totalBg, STYLE.totalFont, true, 'left')),
    C(totalDebit, totStyle, 'n'),
    C(totalKredit, totStyle, 'n'),
  ]);

  const isBalanced = Math.abs(totalDebit - totalKredit) < 0.01;
  data.push([
    null, null, null, null, null,
    C('STATUS', makeStyle(STYLE.totalBg, STYLE.totalFont, true, 'left')),
    C(isBalanced ? '✅ BALANCE' : '❌ TIDAK BALANCE', makeStyle(
      isBalanced ? 'd1fae5' : 'fee2e2',
      isBalanced ? '065f46' : '991b1b', true, 'center'
    )),
  ]);

  return buildWorksheet(data, [5, 12, 12, 40, 12, 32, 18, 18]);
}

/**
 * SHEET 3: Chart of Accounts
 */
function buildCOASheet() {
  const hStyle = makeStyle(STYLE.headerBg, STYLE.headerFont, true, 'center', 11);
  const titleStyle = makeStyle(STYLE.headerBg, STYLE.headerFont, true, 'left', 13);
  const typeStyles = {
    'Aset':       makeStyle('eff6ff', '1d4ed8', false, 'left'),
    'Liabilitas': makeStyle('fef3c7', '92400e', false, 'left'),
    'Ekuitas':    makeStyle('f0fdf4', '166534', false, 'left'),
    'Pendapatan': makeStyle('ecfdf5', '065f46', false, 'left'),
    'Beban':      makeStyle('fef2f2', '991b1b', false, 'left'),
  };

  const data = [];
  data.push([C('CHART OF ACCOUNTS - PT GLOBAL KREATIF INOVASI', titleStyle)]);
  data.push([C('Standar Akun untuk Perusahaan IT / ERP Implementor', makeStyle(STYLE.subheaderBg, STYLE.subheaderFont, false, 'left'))]);
  data.push([null]);

  const headers = ['Kode Akun', 'Nama Akun', 'Tipe', 'Kategori', 'Normal Balance', 'Keterangan'];
  data.push(headers.map(h => C(h, hStyle)));

  const accounts = getAllAccounts().filter(a => a.category !== 'Header');
  accounts.sort((a, b) => a.code.localeCompare(b.code));

  accounts.forEach(acct => {
    const s = typeStyles[acct.type] || makeStyle('FFFFFF', '374151', false, 'left');
    data.push([
      C(acct.code, s),
      C(acct.name, s),
      C(acct.type, s),
      C(acct.category, s),
      C(acct.normal, s),
      C(acct.desc || '', s),
    ]);
  });

  return buildWorksheet(data, [14, 42, 12, 22, 14, 50]);
}

/**
 * SHEET 4: Laporan Laba Rugi
 */
function buildIncomeSheet(incomeData) {
  const { companyName, periodLabel, sections, totals } = incomeData;
  const titleStyle = makeStyle(STYLE.headerBg, STYLE.headerFont, true, 'left', 13);
  const sectionStyle = makeStyle(STYLE.sectionBg, STYLE.sectionFont, true, 'left', 11);
  const itemStyle = makeStyle('FFFFFF', '374151', false, 'left');
  const itemNumStyle = makeStyle('FFFFFF', '374151', false, 'right');
  const subtotalStyle = makeStyle(STYLE.totalBg, STYLE.totalFont, true, 'right');
  const totalStyle = makeStyle(STYLE.grandtotalBg, STYLE.grandtotalFont, true, 'right');
  const altStyle = makeStyle(STYLE.altRow, '374151', false, 'left');
  const altNumStyle = makeStyle(STYLE.altRow, '374151', false, 'right');

  const data = [];
  data.push([C(companyName, titleStyle)]);
  data.push([C('LAPORAN LABA RUGI', makeStyle(STYLE.headerBg, STYLE.headerFont, true, 'left', 12))]);
  data.push([C(periodLabel, makeStyle(STYLE.subheaderBg, STYLE.subheaderFont, false, 'left'))]);
  data.push([C('(Berbasis Transaksi Bank - Cash Basis)', makeStyle('f0f9ff', '1e3a5f', false, 'left', 9))]);
  data.push([null]);

  const headers = ['Kode Akun', 'Keterangan', 'Jumlah (Rp)'];
  data.push(headers.map(h => C(h, makeStyle(STYLE.headerBg, STYLE.headerFont, true, 'center'))));

  const addSection = (title, items, total, totalLabel, bgColor = '1e40af') => {
    data.push([null, C(title, sectionStyle)]);
    items.sort((a,b) => a.accountCode.localeCompare(b.accountCode)).forEach((acct, i) => {
      const s = i % 2 === 1 ? altStyle : itemStyle;
      const ns = i % 2 === 1 ? altNumStyle : itemNumStyle;
      data.push([C(acct.accountCode, s), C(acct.accountName, s), C(acct.balance || 0, ns, 'n')]);
    });
    data.push([null, C(totalLabel, makeStyle(STYLE.totalBg, STYLE.totalFont, true, 'left')), C(total, subtotalStyle, 'n')]);
    data.push([null]);
  };

  addSection('PENDAPATAN USAHA', sections.pendapatanUsaha, totals.totalPendapatanUsaha, 'Total Pendapatan Usaha');
  addSection('BEBAN OPERASIONAL', sections.bebanOperasional, totals.totalBebanOperasional, 'Total Beban Operasional');

  data.push([null, C('LABA / RUGI OPERASIONAL', makeStyle(STYLE.grandtotalBg, STYLE.grandtotalFont, true, 'left')), C(totals.labaKotor, totalStyle, 'n')]);
  data.push([null]);

  if (sections.pendapatanLain.length > 0) {
    addSection('PENDAPATAN LAIN-LAIN', sections.pendapatanLain, totals.totalPendapatanLain, 'Total Pendapatan Lain');
  }
  if (sections.bebanNonOperasional.length > 0) {
    addSection('BEBAN NON-OPERASIONAL', sections.bebanNonOperasional, totals.totalBebanNonOp, 'Total Beban Non-Operasional');
  }

  data.push([null, C(totals.labaBersih >= 0 ? 'LABA BERSIH' : 'RUGI BERSIH', makeStyle(STYLE.grandtotalBg, STYLE.grandtotalFont, true, 'left', 12)), C(Math.abs(totals.labaBersih), totalStyle, 'n')]);

  return buildWorksheet(data, [14, 42, 22]);
}

/**
 * SHEET 5: Neraca
 */
function buildBalanceSheet_xlsx(balanceData) {
  const { companyName, periodLabel, sections, totals } = balanceData;
  const titleStyle = makeStyle(STYLE.headerBg, STYLE.headerFont, true, 'left', 13);
  const sectionStyle = makeStyle(STYLE.sectionBg, STYLE.sectionFont, true, 'left', 11);
  const itemStyle = makeStyle('FFFFFF', '374151', false, 'left');
  const itemNumStyle = makeStyle('FFFFFF', '374151', false, 'right');
  const subtotalStyle = makeStyle(STYLE.totalBg, STYLE.totalFont, true, 'right');
  const totalStyle = makeStyle(STYLE.grandtotalBg, STYLE.grandtotalFont, true, 'right');

  const data = [];
  data.push([C(companyName, titleStyle)]);
  data.push([C('NERACA (BALANCE SHEET)', makeStyle(STYLE.headerBg, STYLE.headerFont, true, 'left', 12))]);
  data.push([C(periodLabel, makeStyle(STYLE.subheaderBg, STYLE.subheaderFont, false, 'left'))]);
  data.push([null]);

  const headers = ['Kode Akun', 'Keterangan', 'Jumlah (Rp)'];
  data.push(headers.map(h => C(h, makeStyle(STYLE.headerBg, STYLE.headerFont, true, 'center'))));

  const addSection = (title, items, total, totalLabel) => {
    data.push([null, C(title, sectionStyle)]);
    items.sort((a,b) => a.accountCode.localeCompare(b.accountCode)).forEach(acct => {
      data.push([C(acct.accountCode, itemStyle), C(acct.accountName, itemStyle), C(acct.balance || 0, itemNumStyle, 'n')]);
    });
    data.push([null, C(totalLabel, makeStyle(STYLE.totalBg, STYLE.totalFont, true, 'left')), C(total, subtotalStyle, 'n')]);
    data.push([null]);
  };

  // ASET
  data.push([null, C('═══ ASET ═══', makeStyle(STYLE.headerBg, STYLE.headerFont, true, 'left', 11))]);
  addSection('Aset Lancar', sections.asetLancar, totals.totalAsetLancar, 'Total Aset Lancar');
  if (sections.asetTetap.length > 0) {
    addSection('Aset Tidak Lancar', sections.asetTetap, totals.totalAsetTetap, 'Total Aset Tidak Lancar');
  }
  data.push([null, C('TOTAL ASET', makeStyle(STYLE.grandtotalBg, STYLE.grandtotalFont, true, 'left')), C(totals.totalAset, totalStyle, 'n')]);
  data.push([null]);

  // LIABILITAS
  data.push([null, C('═══ LIABILITAS ═══', makeStyle(STYLE.headerBg, STYLE.headerFont, true, 'left', 11))]);
  addSection('Liabilitas Jangka Pendek', sections.liabJangkaPendek.length > 0 ? sections.liabJangkaPendek : [{ accountCode: '-', accountName: 'Tidak ada liabilitas', balance: 0 }], totals.totalLiabPendek, 'Total Liabilitas Jangka Pendek');
  data.push([null, C('TOTAL LIABILITAS', makeStyle(STYLE.grandtotalBg, STYLE.grandtotalFont, true, 'left')), C(totals.totalLiabilitas, totalStyle, 'n')]);
  data.push([null]);

  // EKUITAS
  data.push([null, C('═══ EKUITAS ═══', makeStyle(STYLE.headerBg, STYLE.headerFont, true, 'left', 11))]);
  const equityItems = sections.ekuitas.length > 0
    ? sections.ekuitas
    : [{ accountCode: '3-2000', accountName: 'Laba Ditahan', balance: totals.totalAset - totals.totalLiabilitas }];
  addSection('Ekuitas', equityItems, totals.totalEkuitas || (totals.totalAset - totals.totalLiabilitas), 'Total Ekuitas');
  data.push([null, C('TOTAL LIABILITAS & EKUITAS', makeStyle(STYLE.grandtotalBg, STYLE.grandtotalFont, true, 'left')), C(totals.totalLiabilitas + (totals.totalEkuitas || (totals.totalAset - totals.totalLiabilitas)), totalStyle, 'n')]);

  return buildWorksheet(data, [14, 42, 22]);
}

/**
 * SHEET 6: Arus Kas
 */
function buildCashflowSheet(cfData) {
  const { companyName, periodLabel, sections, totals } = cfData;
  const titleStyle = makeStyle(STYLE.headerBg, STYLE.headerFont, true, 'left', 13);
  const sectionStyle = makeStyle(STYLE.sectionBg, STYLE.sectionFont, true, 'left', 11);
  const crStyle = makeStyle(STYLE.crBg, STYLE.crFont, false, 'left');
  const crNumStyle = makeStyle(STYLE.crBg, STYLE.crFont, false, 'right');
  const dbStyle = makeStyle(STYLE.dbBg, STYLE.dbFont, false, 'left');
  const dbNumStyle = makeStyle(STYLE.dbBg, STYLE.dbFont, false, 'right');
  const subtotalStyle = makeStyle(STYLE.totalBg, STYLE.totalFont, true, 'right');
  const totalStyle = makeStyle(STYLE.grandtotalBg, STYLE.grandtotalFont, true, 'right');

  const data = [];
  data.push([C(companyName, titleStyle)]);
  data.push([C('LAPORAN ARUS KAS', makeStyle(STYLE.headerBg, STYLE.headerFont, true, 'left', 12))]);
  data.push([C(periodLabel, makeStyle(STYLE.subheaderBg, STYLE.subheaderFont, false, 'left'))]);
  data.push([C('Metode Langsung - Cash Basis', makeStyle('f0f9ff', '1e3a5f', false, 'left', 9))]);
  data.push([null]);

  const headers = ['Tanggal', 'Keterangan', 'Penerimaan', 'Pengeluaran'];
  data.push(headers.map(h => C(h, makeStyle(STYLE.headerBg, STYLE.headerFont, true, 'center'))));

  // Saldo Awal
  data.push([null, C('Saldo Kas Awal Periode', makeStyle('e0f2fe', '0c4a6e', true, 'left')), C(totals.saldoAwal, makeStyle('e0f2fe', '0c4a6e', true, 'right'), 'n')]);
  data.push([null]);

  const addFlowSection = (title, inflowItems, outflowItems, netAmount) => {
    data.push([null, C(title, sectionStyle)]);

    if (inflowItems.length > 0) {
      data.push([null, C('  Penerimaan:', makeStyle('f0fdf4', '166534', true, 'left'))]);
      inflowItems.forEach(item => {
        data.push([C(item.date || '', crStyle), C(item.desc || '', crStyle), C(item.amount || 0, crNumStyle, 'n'), C(0, crNumStyle, 'n')]);
      });
    }
    if (outflowItems.length > 0) {
      data.push([null, C('  Pembayaran:', makeStyle('fef2f2', '991b1b', true, 'left'))]);
      outflowItems.forEach(item => {
        data.push([C(item.date || '', dbStyle), C(item.desc || '', dbStyle), C(0, dbNumStyle, 'n'), C(item.amount || 0, dbNumStyle, 'n')]);
      });
    }

    const netStyle = netAmount >= 0
      ? makeStyle('d1fae5', '065f46', true, 'right')
      : makeStyle('fee2e2', '991b1b', true, 'right');
    data.push([null, C(`Arus Kas Bersih - ${title.replace(/^[IV]+\.\s*/,'')}`, makeStyle(STYLE.totalBg, STYLE.totalFont, true, 'left')), C(netAmount, netStyle, 'n')]);
    data.push([null]);
  };

  addFlowSection('I. AKTIVITAS OPERASIONAL', sections.opInflow, sections.opOutflow, totals.netOp);
  if (sections.invInflow.length + sections.invOutflow.length > 0) {
    addFlowSection('II. AKTIVITAS INVESTASI', sections.invInflow, sections.invOutflow, totals.netInv);
  }
  if (sections.finInflow.length + sections.finOutflow.length > 0) {
    addFlowSection('III. AKTIVITAS PENDANAAN', sections.finInflow, sections.finOutflow, totals.netFin);
  }

  // Net & Saldo Akhir
  data.push([null, C('KENAIKAN / PENURUNAN KAS BERSIH', makeStyle(STYLE.totalBg, STYLE.totalFont, true, 'left')), C(totals.netCashflow, subtotalStyle, 'n')]);
  data.push([null, C('SALDO KAS AKHIR PERIODE', makeStyle(STYLE.grandtotalBg, STYLE.grandtotalFont, true, 'left', 12)), C(totals.saldoAkhir, totalStyle, 'n')]);

  return buildWorksheet(data, [12, 44, 20, 20]);
}

/**
 * MASTER EXPORT FUNCTION
 * Buat workbook lengkap dan download sebagai .xlsx
 */
function exportToExcel(appData) {
  const { transactions, journals, journalRows, summary, header, incomeData, balanceData, cfData, periods } = appData;

  const wb = XLSX.utils.book_new();
  wb.Props = {
    Title: 'Laporan Keuangan - PT Global Kreatif Inovasi',
    Subject: 'Financial Report',
    Author: 'FinReport App',
    CreatedDate: new Date()
  };

  // Sheet 1: Transaksi
  const ws1 = buildTransactionSheet(transactions, header);
  XLSX.utils.book_append_sheet(wb, ws1, '📋 Transaksi');

  // Sheet 2: Jurnal Entri
  const ws2 = buildJournalSheet(journalRows);
  XLSX.utils.book_append_sheet(wb, ws2, '📝 Jurnal Entri');

  // Sheet 3: COA
  const ws3 = buildCOASheet();
  XLSX.utils.book_append_sheet(wb, ws3, '🗂️ Chart of Accounts');

  // Sheet 4: Laba Rugi
  if (incomeData) {
    const ws4 = buildIncomeSheet(incomeData);
    XLSX.utils.book_append_sheet(wb, ws4, '📈 Laba Rugi');
  }

  // Sheet 5: Neraca
  if (balanceData) {
    const ws5 = buildBalanceSheet_xlsx(balanceData);
    XLSX.utils.book_append_sheet(wb, ws5, '⚖️ Neraca');
  }

  // Sheet 6: Arus Kas
  if (cfData) {
    const ws6 = buildCashflowSheet(cfData);
    XLSX.utils.book_append_sheet(wb, ws6, '💰 Arus Kas');
  }

  // Nama file
  const periodStr = (periods || []).join('-') || 'laporan';
  const filename = `Laporan_Keuangan_GKI_${periodStr}.xlsx`;

  // Download
  XLSX.writeFile(wb, filename, { bookType: 'xlsx', type: 'binary' });
  return filename;
}

/**
 * Export khusus untuk Google Sheets - buka link
 * Karena Google Sheets API memerlukan OAuth, pendekatan terbaik adalah
 * membuka Google Sheets dan user bisa import file Excel
 */
function exportToGoogleSheets(appData) {
  // Step 1: Download file xlsx dulu
  const filename = exportToExcel(appData);

  // Step 2: Buka Google Sheets import page
  const importUrl = 'https://sheets.new';

  return {
    filename,
    importUrl,
    instructions: [
      `File "${filename}" sudah terdownload`,
      'Buka Google Sheets (sheets.new)',
      'Klik File > Import',
      'Upload file xlsx yang baru didownload',
      'Pilih "Replace spreadsheet" atau "Insert new sheet"',
      'Klik Import Data'
    ]
  };
}

// =====================================================
// PER-REPORT EXPORT (filtered by active date range)
// =====================================================

/**
 * Export satu laporan ke Excel (.xlsx) - hanya 1 sheet sesuai tipe laporan
 */
function exportSingleReportXlsx(reportType, data, header) {
  const wb = XLSX.utils.book_new();
  wb.Props = { Title: 'Laporan Keuangan', Author: 'FinReport App', CreatedDate: new Date() };

  let ws, sheetName, filePrefix;
  if (reportType === 'income') {
    ws = buildIncomeSheet(data);
    sheetName = 'Laba Rugi';
    filePrefix = 'LabaRugi';
  } else if (reportType === 'balance') {
    ws = buildBalanceSheet_xlsx(data);
    sheetName = 'Neraca';
    filePrefix = 'Neraca';
  } else {
    ws = buildCashflowSheet(data);
    sheetName = 'Arus Kas';
    filePrefix = 'ArusKas';
  }

  XLSX.utils.book_append_sheet(wb, ws, sheetName);

  const periodSlug = (data.periodLabel || '')
    .replace(/Periode:\s*/i, '')
    .replace(/\s+/g, '_')
    .replace(/[^\w-]/g, '')
    .slice(0, 40);
  const filename = `${filePrefix}_${periodSlug || 'laporan'}.xlsx`;
  XLSX.writeFile(wb, filename, { bookType: 'xlsx', type: 'binary' });
  return filename;
}

/**
 * Export satu laporan ke GSheets (download xlsx dulu, lalu instruksi import)
 */
function exportSingleReportGSheets(reportType, data, header) {
  const filename = exportSingleReportXlsx(reportType, data, header);
  return {
    filename,
    importUrl: 'https://sheets.new',
    instructions: [
      `File "${filename}" sudah terdownload`,
      'Buka Google Sheets (sheets.new)',
      'Klik File > Import',
      'Upload file xlsx yang baru didownload',
      'Pilih "Replace spreadsheet" atau "Insert new sheet"',
      'Klik Import Data'
    ]
  };
}

/**
 * Format angka Rupiah untuk PDF
 */
function _fmtRp(val) {
  if (val === null || val === undefined) return '-';
  const n = Number(val);
  if (isNaN(n)) return '-';
  return new Intl.NumberFormat('id-ID', { style: 'currency', currency: 'IDR', maximumFractionDigits: 0 }).format(n);
}

/**
 * Resolve jsPDF constructor dari berbagai cara expose UMD/global
 */
function _getJsPDF() {
  // jsPDF UMD 2.x: window.jspdf.jsPDF
  if (window.jspdf && window.jspdf.jsPDF) return window.jspdf.jsPDF;
  // Beberapa build expose langsung sebagai window.jsPDF
  if (window.jsPDF) return window.jsPDF;
  // Fallback: coba lewat require (unlikely di browser plain)
  return null;
}

/**
 * Export satu laporan ke PDF menggunakan jsPDF + autoTable
 */
function exportReportAsPdf(reportType, data) {
  const jsPDF = _getJsPDF();
  if (!jsPDF) {
    alert('Library jsPDF belum termuat.\n\nPastikan koneksi internet aktif dan refresh halaman, lalu coba lagi.');
    return;
  }

  const doc = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' });
  const { companyName, periodLabel, sections, totals } = data;

  // Judul header
  const titles = {
    income:   'LAPORAN LABA RUGI',
    balance:  'NERACA (BALANCE SHEET)',
    cashflow: 'LAPORAN ARUS KAS'
  };
  const filePrefixes = { income: 'LabaRugi', balance: 'Neraca', cashflow: 'ArusKas' };

  const pageW = doc.internal.pageSize.getWidth();
  let y = 18;

  // Header teks
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(13);
  doc.text(companyName || 'PT Global Kreatif Inovasi', pageW / 2, y, { align: 'center' });
  y += 7;
  doc.setFontSize(11);
  doc.text(titles[reportType] || '', pageW / 2, y, { align: 'center' });
  y += 6;
  doc.setFont('helvetica', 'normal');
  doc.setFontSize(9);
  doc.text(periodLabel || '', pageW / 2, y, { align: 'center' });
  y += 5;
  doc.setDrawColor(30, 58, 138);
  doc.setLineWidth(0.5);
  doc.line(14, y, pageW - 14, y);
  y += 4;

  // Build tabel body berdasarkan tipe laporan
  const rows = [];
  const BLUE_HEADER = [30, 64, 175];
  const SECTION_BG  = [239, 246, 255];
  const TOTAL_BG    = [219, 234, 254];
  const GRAND_BG    = [30, 64, 175];

  const addSectionHeader = (label) => rows.push([
    { content: label, colSpan: 3, styles: { fillColor: SECTION_BG, textColor: [30,64,175], fontStyle: 'bold', fontSize: 9 } }
  ]);
  const addItem = (code, name, val) => rows.push([
    { content: code || '', styles: { fontSize: 8.5 } },
    { content: name || '', styles: { fontSize: 8.5 } },
    { content: _fmtRp(val), styles: { halign: 'right', fontSize: 8.5 } }
  ]);
  const addSubtotal = (label, val) => rows.push([
    { content: '', styles: { fillColor: TOTAL_BG } },
    { content: label, styles: { fillColor: TOTAL_BG, fontStyle: 'bold', fontSize: 9 } },
    { content: _fmtRp(val), styles: { fillColor: TOTAL_BG, halign: 'right', fontStyle: 'bold', fontSize: 9 } }
  ]);
  const addGrandTotal = (label, val) => rows.push([
    { content: '', styles: { fillColor: GRAND_BG, textColor: [255,255,255] } },
    { content: label, styles: { fillColor: GRAND_BG, textColor: [255,255,255], fontStyle: 'bold', fontSize: 10 } },
    { content: _fmtRp(val), styles: { fillColor: GRAND_BG, textColor: [255,255,255], halign: 'right', fontStyle: 'bold', fontSize: 10 } }
  ]);
  const addBlank = () => rows.push([{ content: '', colSpan: 3, styles: { minCellHeight: 2 } }]);

  if (reportType === 'income') {
    addSectionHeader('PENDAPATAN USAHA');
    (sections.pendapatanUsaha || []).sort((a,b)=>a.accountCode.localeCompare(b.accountCode))
      .forEach(a => addItem(a.accountCode, a.accountName, a.balance));
    addSubtotal('Total Pendapatan Usaha', totals.totalPendapatanUsaha);
    addBlank();

    if ((sections.pendapatanLain || []).length > 0) {
      addSectionHeader('PENDAPATAN LAIN-LAIN');
      sections.pendapatanLain.sort((a,b)=>a.accountCode.localeCompare(b.accountCode))
        .forEach(a => addItem(a.accountCode, a.accountName, a.balance));
      addSubtotal('Total Pendapatan Lain', totals.totalPendapatanLain);
      addBlank();
    }

    addSectionHeader('BEBAN OPERASIONAL');
    (sections.bebanOperasional || []).sort((a,b)=>a.accountCode.localeCompare(b.accountCode))
      .forEach(a => addItem(a.accountCode, a.accountName, a.balance));
    addSubtotal('Total Beban Operasional', totals.totalBebanOperasional);
    addBlank();

    if ((sections.bebanNonOperasional || []).length > 0) {
      addSectionHeader('BEBAN NON-OPERASIONAL');
      sections.bebanNonOperasional.sort((a,b)=>a.accountCode.localeCompare(b.accountCode))
        .forEach(a => addItem(a.accountCode, a.accountName, a.balance));
      addSubtotal('Total Beban Non-Operasional', totals.totalBebanNonOp);
      addBlank();
    }

    addGrandTotal(totals.labaBersih >= 0 ? 'LABA BERSIH' : 'RUGI BERSIH', Math.abs(totals.labaBersih));

    doc.autoTable({
      startY: y, head: [['Kode Akun','Keterangan','Jumlah (Rp)']],
      body: rows,
      headStyles: { fillColor: BLUE_HEADER, textColor: 255, fontStyle: 'bold', fontSize: 9 },
      columnStyles: { 0: { cellWidth: 22 }, 1: { cellWidth: 'auto' }, 2: { cellWidth: 38, halign: 'right' } },
      margin: { left: 14, right: 14 }, theme: 'grid', styles: { fontSize: 8.5, cellPadding: 2 }
    });

  } else if (reportType === 'balance') {
    const addSec = (title, items, totalLabel, totalVal) => {
      addSectionHeader(title);
      (items || []).sort((a,b)=>a.accountCode.localeCompare(b.accountCode))
        .forEach(a => addItem(a.accountCode, a.accountName, a.balance));
      addSubtotal(totalLabel, totalVal);
      addBlank();
    };
    addSec('ASET LANCAR', sections.asetLancar, 'Total Aset Lancar', totals.totalAsetLancar);
    addSec('ASET TETAP', sections.asetTetap, 'Total Aset Tetap', totals.totalAsetTetap);
    addGrandTotal('TOTAL ASET', totals.totalAset);
    addBlank();
    addSec('LIABILITAS JANGKA PENDEK', sections.liabJangkaPendek, 'Total Liab. Jangka Pendek', totals.totalLiabPendek);
    addSec('LIABILITAS JANGKA PANJANG', sections.liabJangkaPanjang, 'Total Liab. Jangka Panjang', totals.totalLiabPanjang);
    addSec('EKUITAS', sections.ekuitas, 'Total Ekuitas', totals.totalEkuitas);
    addGrandTotal('TOTAL LIABILITAS + EKUITAS', totals.totalLiabEkuitas);

    doc.autoTable({
      startY: y, head: [['Kode Akun','Keterangan','Jumlah (Rp)']],
      body: rows,
      headStyles: { fillColor: BLUE_HEADER, textColor: 255, fontStyle: 'bold', fontSize: 9 },
      columnStyles: { 0: { cellWidth: 22 }, 1: { cellWidth: 'auto' }, 2: { cellWidth: 38, halign: 'right' } },
      margin: { left: 14, right: 14 }, theme: 'grid', styles: { fontSize: 8.5, cellPadding: 2 }
    });

  } else {
    // cashflow
    const cfRows = [];
    const addCfSection = (title, inflowItems, outflowItems, netAmt) => {
      cfRows.push([{ content: title, colSpan: 2, styles: { fillColor: SECTION_BG, textColor: [30,64,175], fontStyle: 'bold', fontSize: 9 } }]);
      inflowItems.forEach(it => cfRows.push([
        { content: `  + ${it.desc || ''}`, styles: { fontSize: 8.5 } },
        { content: _fmtRp(it.amount), styles: { halign: 'right', textColor: [22,101,52], fontSize: 8.5 } }
      ]));
      outflowItems.forEach(it => cfRows.push([
        { content: `  - ${it.desc || ''}`, styles: { fontSize: 8.5 } },
        { content: `(${_fmtRp(it.amount)})`, styles: { halign: 'right', textColor: [185,28,28], fontSize: 8.5 } }
      ]));
      cfRows.push([
        { content: `Arus Kas Bersih`, styles: { fillColor: TOTAL_BG, fontStyle: 'bold', fontSize: 9 } },
        { content: _fmtRp(netAmt), styles: { fillColor: TOTAL_BG, halign: 'right', fontStyle: 'bold', fontSize: 9 } }
      ]);
      cfRows.push([{ content: '', colSpan: 2, styles: { minCellHeight: 2 } }]);
    };

    cfRows.push([
      { content: 'Saldo Kas Awal Periode', styles: { fontStyle: 'bold', fontSize: 9 } },
      { content: _fmtRp(totals.saldoAwal), styles: { halign: 'right', fontStyle: 'bold', fontSize: 9 } }
    ]);
    cfRows.push([{ content: '', colSpan: 2, styles: { minCellHeight: 2 } }]);

    addCfSection('I. AKTIVITAS OPERASIONAL', sections.opInflow || [], sections.opOutflow || [], totals.netOp);
    if ((sections.invInflow||[]).length + (sections.invOutflow||[]).length > 0)
      addCfSection('II. AKTIVITAS INVESTASI', sections.invInflow || [], sections.invOutflow || [], totals.netInv);
    if ((sections.finInflow||[]).length + (sections.finOutflow||[]).length > 0)
      addCfSection('III. AKTIVITAS PENDANAAN', sections.finInflow || [], sections.finOutflow || [], totals.netFin);

    cfRows.push([
      { content: 'KENAIKAN / PENURUNAN KAS BERSIH', styles: { fillColor: TOTAL_BG, fontStyle: 'bold', fontSize: 9 } },
      { content: _fmtRp(totals.netCashflow), styles: { fillColor: TOTAL_BG, halign: 'right', fontStyle: 'bold', fontSize: 9 } }
    ]);
    cfRows.push([
      { content: 'SALDO KAS AKHIR PERIODE', styles: { fillColor: GRAND_BG, textColor: [255,255,255], fontStyle: 'bold', fontSize: 10 } },
      { content: _fmtRp(totals.saldoAkhir), styles: { fillColor: GRAND_BG, textColor: [255,255,255], halign: 'right', fontStyle: 'bold', fontSize: 10 } }
    ]);

    doc.autoTable({
      startY: y, head: [['Keterangan','Jumlah (Rp)']],
      body: cfRows,
      headStyles: { fillColor: BLUE_HEADER, textColor: 255, fontStyle: 'bold', fontSize: 9 },
      columnStyles: { 0: { cellWidth: 'auto' }, 1: { cellWidth: 45, halign: 'right' } },
      margin: { left: 14, right: 14 }, theme: 'grid', styles: { fontSize: 8.5, cellPadding: 2 }
    });
  }

  // Footer halaman
  const pageCount = doc.internal.getNumberOfPages();
  for (let i = 1; i <= pageCount; i++) {
    doc.setPage(i);
    doc.setFontSize(7);
    doc.setFont('helvetica', 'normal');
    doc.setTextColor(150);
    doc.text(`Halaman ${i} dari ${pageCount}  •  Dicetak: ${new Date().toLocaleDateString('id-ID')}`, pageW / 2, doc.internal.pageSize.getHeight() - 6, { align: 'center' });
    doc.setTextColor(0);
  }

  const periodSlug = (periodLabel || '')
    .replace(/Periode:\s*/i, '')
    .replace(/\s+/g, '_')
    .replace(/[^\w-]/g, '')
    .slice(0, 40);
  const filename = `${filePrefixes[reportType]}_${periodSlug || 'laporan'}.pdf`;
  doc.save(filename);
}

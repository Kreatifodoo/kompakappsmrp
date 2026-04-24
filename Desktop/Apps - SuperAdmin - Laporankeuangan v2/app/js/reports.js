/**
 * LAPORAN KEUANGAN
 * - Laporan Laba Rugi
 * - Neraca (Balance Sheet)
 * - Laporan Arus Kas
 */

/**
 * Generate Laporan Laba Rugi dari ledger
 */
function generateIncomeStatement(ledger, periodLabel, companyName = 'PT Global Kreatif Inovasi') {
  // Kelompokkan pendapatan
  const pendapatanUsaha = [];
  const pendapatanLain = [];
  const bebanOperasional = [];
  const bebanNonOperasional = [];

  Object.values(ledger).forEach(acct => {
    if (!acct.balance && acct.balance !== 0) return;
    if (acct.balance === 0 && acct.totalDebit === 0 && acct.totalKredit === 0) return;

    const code = acct.accountCode;

    if (code.startsWith('4-1') || (code.startsWith('4-5') && acct.normalBalance !== 'Debit')) {
      // 4-1xxx = Pendapatan Usaha biasa
      // 4-5xxx Kredit-normal = POS Revenue (Pendapatan POS, Pendapatan Service)
      pendapatanUsaha.push({ ...acct });
    } else if (code.startsWith('4-2')) {
      pendapatanLain.push({ ...acct });
    } else if (code.startsWith('5-1') || code.startsWith('5-2') || code.startsWith('5-3') ||
               code.startsWith('5-5') || (code.startsWith('4-5') && acct.normalBalance === 'Debit')) {
      // 5-1~5-3xxx = Beban Operasional biasa
      // 5-5xxx = HPP (Harga Pokok Penjualan POS)
      // 4-5xxx Debit-normal = Diskon Penjualan POS (contra revenue, diperlakukan sebagai beban)
      bebanOperasional.push({ ...acct });
    } else if (code.startsWith('5-4')) {
      bebanNonOperasional.push({ ...acct });
    }
  });

  const totalPendapatanUsaha = pendapatanUsaha.reduce((s, a) => s + a.balance, 0);
  const totalPendapatanLain = pendapatanLain.reduce((s, a) => s + a.balance, 0);
  const totalPendapatan = totalPendapatanUsaha + totalPendapatanLain;

  const totalBebanOperasional = bebanOperasional.reduce((s, a) => s + a.balance, 0);
  const totalBebanNonOp = bebanNonOperasional.reduce((s, a) => s + a.balance, 0);
  const totalBeban = totalBebanOperasional + totalBebanNonOp;

  const labaKotor = totalPendapatanUsaha - totalBebanOperasional;
  const labaBersih = totalPendapatan - totalBeban;

  return {
    companyName,
    periodLabel,
    sections: {
      pendapatanUsaha,
      pendapatanLain,
      bebanOperasional,
      bebanNonOperasional
    },
    totals: {
      totalPendapatanUsaha,
      totalPendapatanLain,
      totalPendapatan,
      totalBebanOperasional,
      totalBebanNonOp,
      totalBeban,
      labaKotor,
      labaBersih
    }
  };
}

/**
 * Render HTML Laporan Laba Rugi
 */
function renderIncomeStatement(data) {
  const { companyName, periodLabel, sections, totals } = data;
  const R = (amount, cls = '') => `<span class="${cls}">${formatRupiah(amount || 0)}</span>`;

  let html = `
  <div class="report-header">
    <h3>${companyName}</h3>
    <p><strong>LAPORAN LABA RUGI</strong></p>
    <p>${periodLabel}</p>
    <p style="font-size:11px;color:#999;margin-top:4px">(Berbasis transaksi bank - Cash Basis)</p>
  </div>`;

  // Pendapatan Usaha
  html += `<div class="report-section">
    <div class="report-section-title">PENDAPATAN USAHA</div>`;
  if (sections.pendapatanUsaha.length === 0) {
    html += `<div class="report-row indent"><span>Tidak ada data</span><span>Rp 0</span></div>`;
  } else {
    sections.pendapatanUsaha.sort((a,b) => a.accountCode.localeCompare(b.accountCode)).forEach(acct => {
      html += `<div class="report-row indent">
        <span>${acct.accountCode} - ${acct.accountName}</span>
        ${R(acct.balance, 'text-green')}
      </div>`;
    });
  }
  html += `<div class="report-row subtotal">
    <span>Total Pendapatan Usaha</span>
    ${R(totals.totalPendapatanUsaha, 'text-green text-bold')}
  </div></div>`;

  // Beban Operasional
  html += `<div class="report-section">
    <div class="report-section-title">BEBAN OPERASIONAL</div>`;
  if (sections.bebanOperasional.length === 0) {
    html += `<div class="report-row indent"><span>Tidak ada data</span><span>Rp 0</span></div>`;
  } else {
    sections.bebanOperasional.sort((a,b) => a.accountCode.localeCompare(b.accountCode)).forEach(acct => {
      html += `<div class="report-row indent">
        <span>${acct.accountCode} - ${acct.accountName}</span>
        ${R(acct.balance, 'text-red')}
      </div>`;
    });
  }
  html += `<div class="report-row subtotal">
    <span>Total Beban Operasional</span>
    ${R(totals.totalBebanOperasional, 'text-red text-bold')}
  </div></div>`;

  // Laba Kotor
  html += `<div class="report-row total">
    <span>LABA / RUGI OPERASIONAL</span>
    ${R(totals.labaKotor, totals.labaKotor >= 0 ? 'text-green text-bold' : 'text-red text-bold')}
  </div>`;

  // Pendapatan Lain
  if (sections.pendapatanLain.length > 0) {
    html += `<div class="report-section">
      <div class="report-section-title">PENDAPATAN LAIN-LAIN</div>`;
    sections.pendapatanLain.forEach(acct => {
      html += `<div class="report-row indent">
        <span>${acct.accountCode} - ${acct.accountName}</span>
        ${R(acct.balance, 'text-green')}
      </div>`;
    });
    html += `<div class="report-row subtotal">
      <span>Total Pendapatan Lain-lain</span>
      ${R(totals.totalPendapatanLain, 'text-green')}
    </div></div>`;
  }

  // Beban Non-Operasional
  if (sections.bebanNonOperasional.length > 0) {
    html += `<div class="report-section">
      <div class="report-section-title">BEBAN NON-OPERASIONAL</div>`;
    sections.bebanNonOperasional.forEach(acct => {
      html += `<div class="report-row indent">
        <span>${acct.accountCode} - ${acct.accountName}</span>
        ${R(acct.balance, 'text-red')}
      </div>`;
    });
    html += `<div class="report-row subtotal">
      <span>Total Beban Non-Operasional</span>
      ${R(totals.totalBebanNonOp, 'text-red')}
    </div></div>`;
  }

  // Laba Bersih
  const lbClass = totals.labaBersih >= 0 ? 'text-green text-bold' : 'text-red text-bold';
  html += `<div class="report-row grandtotal">
    <span>${totals.labaBersih >= 0 ? 'LABA BERSIH' : 'RUGI BERSIH'}</span>
    ${R(Math.abs(totals.labaBersih), lbClass)}
  </div>`;

  return html;
}

/**
 * Generate Neraca dari ledger + summary
 */
function generateBalanceSheet(ledger, summary, periodLabel, companyName = 'PT Global Kreatif Inovasi') {
  const asetLancar = [];
  const asetTetap = [];
  const liabJangkaPendek = [];
  const liabJangkaPanjang = [];
  const ekuitas = [];

  Object.values(ledger).forEach(acct => {
    if (acct.balance === 0 && acct.totalDebit === 0 && acct.totalKredit === 0) return;
    const code = acct.accountCode;

    if (code.startsWith('1-1')) asetLancar.push({ ...acct });
    else if (code.startsWith('1-2')) asetTetap.push({ ...acct });
    else if (code.startsWith('2-1')) liabJangkaPendek.push({ ...acct });
    else if (code.startsWith('2-2')) liabJangkaPanjang.push({ ...acct });
    else if (code.startsWith('3-')) ekuitas.push({ ...acct });
  });

  // Pastikan Bank BCA ada di aset lancar dengan saldo akhir yang benar
  const bankBCA = asetLancar.find(a => a.accountCode === '1-1110');
  if (!bankBCA) {
    asetLancar.push({
      accountCode: '1-1110',
      accountName: COA['1-1110'].name,
      balance: summary.saldoAkhir,
      totalDebit: summary.saldoAwal + summary.mutasiCR,
      totalKredit: summary.mutasiDB
    });
  } else {
    bankBCA.balance = summary.saldoAkhir;
  }

  const totalAsetLancar = asetLancar.reduce((s, a) => s + (a.balance || 0), 0);
  const totalAsetTetap = asetTetap.reduce((s, a) => s + (a.balance || 0), 0);
  const totalAset = totalAsetLancar + totalAsetTetap;

  const totalLiabPendek = liabJangkaPendek.reduce((s, a) => s + (a.balance || 0), 0);
  const totalLiabPanjang = liabJangkaPanjang.reduce((s, a) => s + (a.balance || 0), 0);
  const totalLiabilitas = totalLiabPendek + totalLiabPanjang;

  const totalEkuitas = ekuitas.reduce((s, a) => s + (a.balance || 0), 0);
  const totalLiabEkuitas = totalLiabilitas + totalEkuitas;

  return {
    companyName,
    periodLabel,
    sections: { asetLancar, asetTetap, liabJangkaPendek, liabJangkaPanjang, ekuitas },
    totals: { totalAsetLancar, totalAsetTetap, totalAset, totalLiabPendek, totalLiabPanjang, totalLiabilitas, totalEkuitas, totalLiabEkuitas }
  };
}

/**
 * Render HTML Neraca
 */
function renderBalanceSheet(data) {
  const { companyName, periodLabel, sections, totals } = data;
  const R = (amount, cls = '') => `<span class="${cls}">${formatRupiah(amount || 0)}</span>`;

  const renderItems = (items, boldCodes = []) =>
    items.sort((a,b) => a.accountCode.localeCompare(b.accountCode))
      .map(a => `<div class="report-row indent">
        <span>${a.accountCode} - ${a.accountName}</span>
        ${R(a.balance || 0)}
      </div>`).join('');

  let html = `
  <div class="report-header">
    <h3>${companyName}</h3>
    <p><strong>NERACA (BALANCE SHEET)</strong></p>
    <p>${periodLabel}</p>
    <p style="font-size:11px;color:#999;margin-top:4px">(Berbasis transaksi bank - Cash Basis)</p>
  </div>

  <div style="display:grid;grid-template-columns:1fr 1fr;gap:32px">
  <div>
    <!-- ASET -->
    <div class="report-section">
      <div class="report-section-title">ASET</div>
      <div style="font-weight:600;font-size:12px;padding:6px 12px;color:#374151">Aset Lancar</div>
      ${renderItems(sections.asetLancar)}
      <div class="report-row subtotal"><span>Total Aset Lancar</span>${R(totals.totalAsetLancar, 'text-bold')}</div>`;

  if (sections.asetTetap.length > 0) {
    html += `<div style="font-weight:600;font-size:12px;padding:6px 12px;color:#374151">Aset Tidak Lancar</div>
      ${renderItems(sections.asetTetap)}
      <div class="report-row subtotal"><span>Total Aset Tidak Lancar</span>${R(totals.totalAsetTetap, 'text-bold')}</div>`;
  }

  html += `<div class="report-row total"><span>TOTAL ASET</span>${R(totals.totalAset, 'text-bold')}</div>
    </div>
  </div>

  <div>
    <!-- LIABILITAS & EKUITAS -->
    <div class="report-section">
      <div class="report-section-title">LIABILITAS</div>
      <div style="font-weight:600;font-size:12px;padding:6px 12px;color:#374151">Liabilitas Jangka Pendek</div>`;

  if (sections.liabJangkaPendek.length > 0) {
    html += renderItems(sections.liabJangkaPendek);
  } else {
    html += `<div class="report-row indent"><span>Tidak ada liabilitas tercatat</span>${R(0)}</div>`;
  }

  html += `<div class="report-row subtotal"><span>Total Liabilitas Jangka Pendek</span>${R(totals.totalLiabPendek, 'text-bold')}</div>
      <div class="report-row total"><span>TOTAL LIABILITAS</span>${R(totals.totalLiabilitas, 'text-bold')}</div>
    </div>

    <div class="report-section">
      <div class="report-section-title">EKUITAS</div>`;

  if (sections.ekuitas.length > 0) {
    html += renderItems(sections.ekuitas);
  } else {
    html += `<div class="report-row indent"><span>3-2000 - Laba Ditahan</span>${R(totals.totalAset - totals.totalLiabilitas)}</div>`;
  }

  html += `<div class="report-row subtotal"><span>Total Ekuitas</span>${R(totals.totalEkuitas || (totals.totalAset - totals.totalLiabilitas), 'text-bold')}</div>
      <div class="report-row total"><span>TOTAL LIABILITAS & EKUITAS</span>${R(totals.totalLiabilitas + (totals.totalEkuitas || (totals.totalAset - totals.totalLiabilitas)), 'text-bold')}</div>
    </div>
  </div>
  </div>`;

  return html;
}

/**
 * Generate Laporan Arus Kas
 */
function generateCashflowReport(transactions, summary, periodLabel, companyName = 'PT Global Kreatif Inovasi') {
  const opInflow = [], opOutflow = [];
  const invInflow = [], invOutflow = [];
  const finInflow = [], finOutflow = [];

  transactions.forEach(tx => {
    if (tx.type === 'SALDO_AWAL') return;
    if (!tx.amount || tx.amount <= 0) return;

    const mapping = tx.coaMapping || {};
    const code = tx.type === 'DB' ? mapping.debitAccount : mapping.kreditAccount;

    // Klasifikasi arus kas berdasarkan COA
    let category = 'operasional';
    if (code && (code.startsWith('1-2') || code.startsWith('5-2100') || code.startsWith('5-2200'))) {
      category = 'investasi';
    } else if (code && (code.startsWith('2-2') || code.startsWith('3-4'))) {
      category = 'pendanaan';
    }

    const item = {
      date: tx.date,
      desc: tx.party || tx.description,
      amount: tx.amount,
      ref: tx.ref
    };

    if (category === 'operasional') {
      tx.type === 'CR' ? opInflow.push(item) : opOutflow.push(item);
    } else if (category === 'investasi') {
      tx.type === 'CR' ? invInflow.push(item) : invOutflow.push(item);
    } else {
      tx.type === 'CR' ? finInflow.push(item) : finOutflow.push(item);
    }
  });

  const totalOpInflow = opInflow.reduce((s, i) => s + i.amount, 0);
  const totalOpOutflow = opOutflow.reduce((s, i) => s + i.amount, 0);
  const netOp = totalOpInflow - totalOpOutflow;

  const totalInvInflow = invInflow.reduce((s, i) => s + i.amount, 0);
  const totalInvOutflow = invOutflow.reduce((s, i) => s + i.amount, 0);
  const netInv = totalInvInflow - totalInvOutflow;

  const totalFinInflow = finInflow.reduce((s, i) => s + i.amount, 0);
  const totalFinOutflow = finOutflow.reduce((s, i) => s + i.amount, 0);
  const netFin = totalFinInflow - totalFinOutflow;

  const netCashflow = netOp + netInv + netFin;
  const saldoAkhir = summary.saldoAwal + netCashflow;

  return {
    companyName,
    periodLabel,
    sections: { opInflow, opOutflow, invInflow, invOutflow, finInflow, finOutflow },
    totals: {
      totalOpInflow, totalOpOutflow, netOp,
      totalInvInflow, totalInvOutflow, netInv,
      totalFinInflow, totalFinOutflow, netFin,
      netCashflow, saldoAwal: summary.saldoAwal, saldoAkhir
    }
  };
}

/**
 * Render HTML Laporan Arus Kas
 */
function renderCashflowReport(data) {
  const { companyName, periodLabel, sections, totals } = data;
  const R = (amount, cls = '') => `<span class="${cls}">${formatRupiah(amount || 0)}</span>`;
  const signClass = (val) => val >= 0 ? 'text-green text-bold' : 'text-red text-bold';

  const renderFlowItems = (items, type) =>
    items.map(item => `<div class="report-row indent">
      <span>${item.date || ''} - ${item.desc || 'Transaksi'}</span>
      <span class="${type === 'in' ? 'text-green' : 'text-red'}">${formatRupiah(item.amount)}</span>
    </div>`).join('');

  let html = `
  <div class="report-header">
    <h3>${companyName}</h3>
    <p><strong>LAPORAN ARUS KAS</strong></p>
    <p>${periodLabel}</p>
    <p style="font-size:11px;color:#999;margin-top:4px">(Metode Langsung - Cash Basis)</p>
  </div>

  <!-- Saldo Awal -->
  <div class="report-row">
    <span><strong>Saldo Kas Awal Periode</strong></span>
    ${R(totals.saldoAwal, 'text-bold')}
  </div>

  <!-- Operasional -->
  <div class="report-section">
    <div class="report-section-title">I. ARUS KAS DARI AKTIVITAS OPERASIONAL</div>
    ${sections.opInflow.length > 0 ? `
      <div class="report-row indent" style="font-style:italic;color:#666"><span>Penerimaan:</span></div>
      ${renderFlowItems(sections.opInflow, 'in')}
      <div class="report-row indent"><span>Total Penerimaan Operasional</span>${R(totals.totalOpInflow, 'text-green')}</div>
    ` : ''}
    ${sections.opOutflow.length > 0 ? `
      <div class="report-row indent" style="font-style:italic;color:#666"><span>Pembayaran:</span></div>
      ${renderFlowItems(sections.opOutflow, 'out')}
      <div class="report-row indent"><span>Total Pembayaran Operasional</span>${R(totals.totalOpOutflow, 'text-red')}</div>
    ` : ''}
    <div class="report-row subtotal">
      <span>Arus Kas Bersih - Operasional</span>
      ${R(totals.netOp, signClass(totals.netOp))}
    </div>
  </div>`;

  // Investasi (hanya tampilkan jika ada)
  if (sections.invInflow.length + sections.invOutflow.length > 0) {
    html += `<div class="report-section">
      <div class="report-section-title">II. ARUS KAS DARI AKTIVITAS INVESTASI</div>
      ${renderFlowItems(sections.invInflow, 'in')}
      ${renderFlowItems(sections.invOutflow, 'out')}
      <div class="report-row subtotal">
        <span>Arus Kas Bersih - Investasi</span>
        ${R(totals.netInv, signClass(totals.netInv))}
      </div>
    </div>`;
  }

  // Pendanaan (hanya tampilkan jika ada)
  if (sections.finInflow.length + sections.finOutflow.length > 0) {
    html += `<div class="report-section">
      <div class="report-section-title">III. ARUS KAS DARI AKTIVITAS PENDANAAN</div>
      ${renderFlowItems(sections.finInflow, 'in')}
      ${renderFlowItems(sections.finOutflow, 'out')}
      <div class="report-row subtotal">
        <span>Arus Kas Bersih - Pendanaan</span>
        ${R(totals.netFin, signClass(totals.netFin))}
      </div>
    </div>`;
  }

  // Net Cashflow & Saldo Akhir
  html += `
  <div class="report-row total">
    <span>KENAIKAN / PENURUNAN KAS BERSIH</span>
    ${R(totals.netCashflow, signClass(totals.netCashflow))}
  </div>
  <div class="report-row grandtotal">
    <span>SALDO KAS AKHIR PERIODE</span>
    ${R(totals.saldoAkhir, 'text-bold')}
  </div>`;

  return html;
}

// ============================================================
// COMPARISON RENDERERS
// ============================================================

/**
 * Helper: diff cell HTML (curr - prev, with % change)
 */
function diffCell(curr, prev) {
  const diff = curr - prev;
  const pct = prev !== 0 ? ((diff / Math.abs(prev)) * 100).toFixed(1) : (curr !== 0 ? '∞' : '0.0');
  const cls = diff > 0 ? 'diff-positive' : diff < 0 ? 'diff-negative' : 'diff-neutral';
  const sign = diff > 0 ? '+' : '';
  return `<td class="num compare-diff-cell ${cls}">${sign}${formatRupiah(diff)}<br><small>${sign}${pct}%</small></td>`;
}

/**
 * Render tabel diff ringkasan (dipakai ketiga laporan)
 */
function renderDiffTable(rows) {
  return `
  <table class="compare-diff-table">
    <thead>
      <tr>
        <th>Keterangan</th>
        <th class="num">Periode Ini</th>
        <th class="num">Pembanding</th>
        <th class="num">Selisih / %</th>
      </tr>
    </thead>
    <tbody>
      ${rows.map(r => `<tr class="${r.subtotal ? 'subtotal' : ''}">
        <td>${r.label}</td>
        <td class="num">${formatRupiah(r.curr)}</td>
        <td class="num">${formatRupiah(r.prev)}</td>
        ${diffCell(r.curr, r.prev)}
      </tr>`).join('')}
    </tbody>
  </table>`;
}

/**
 * Laporan Laba Rugi — Komparasi dua periode
 */
function renderIncomeComparison(dataA, dataB, granLabel) {
  const hA = `<div class="compare-panel-header current">Periode Saat Ini</div>`;
  const hB = `<div class="compare-panel-header previous">Periode Pembanding</div>`;

  const panelA = `<div class="compare-panel">${hA}${renderIncomeStatement(dataA)}</div>`;
  const panelB = `<div class="compare-panel">${hB}${renderIncomeStatement(dataB)}</div>`;

  const tA = dataA.totals, tB = dataB.totals;
  const diffRows = [
    { label: 'Total Pendapatan Usaha', curr: tA.totalPendapatanUsaha, prev: tB.totalPendapatanUsaha },
    { label: 'Total Pendapatan Lain-lain', curr: tA.totalPendapatanLain, prev: tB.totalPendapatanLain },
    { label: 'Total Beban Operasional', curr: tA.totalBebanOperasional, prev: tB.totalBebanOperasional },
    { label: 'Total Beban Non-Operasional', curr: tA.totalBebanNonOp, prev: tB.totalBebanNonOp },
    { label: 'Laba / Rugi Operasional', curr: tA.labaKotor, prev: tB.labaKotor, subtotal: true },
    { label: 'Laba / Rugi Bersih', curr: tA.labaBersih, prev: tB.labaBersih, subtotal: true },
  ];

  return `
  <div class="compare-wrap">${panelA}${panelB}</div>
  <h4 style="font-size:13px;font-weight:700;margin:16px 0 8px;color:#374151">Ringkasan Selisih (per ${granLabel})</h4>
  ${renderDiffTable(diffRows)}`;
}

/**
 * Neraca — Komparasi dua periode
 */
function renderBalanceComparison(dataA, dataB, granLabel) {
  const hA = `<div class="compare-panel-header current">Periode Saat Ini</div>`;
  const hB = `<div class="compare-panel-header previous">Periode Pembanding</div>`;

  const panelA = `<div class="compare-panel">${hA}${renderBalanceSheet(dataA)}</div>`;
  const panelB = `<div class="compare-panel">${hB}${renderBalanceSheet(dataB)}</div>`;

  const tA = dataA.totals, tB = dataB.totals;
  const diffRows = [
    { label: 'Total Aset Lancar', curr: tA.totalAsetLancar, prev: tB.totalAsetLancar },
    { label: 'Total Aset Tidak Lancar', curr: tA.totalAsetTetap, prev: tB.totalAsetTetap },
    { label: 'Total Aset', curr: tA.totalAset, prev: tB.totalAset, subtotal: true },
    { label: 'Total Liabilitas', curr: tA.totalLiabilitas, prev: tB.totalLiabilitas },
    { label: 'Total Ekuitas', curr: tA.totalEkuitas || (tA.totalAset - tA.totalLiabilitas), prev: tB.totalEkuitas || (tB.totalAset - tB.totalLiabilitas) },
    { label: 'Total Liabilitas & Ekuitas', curr: tA.totalAset, prev: tB.totalAset, subtotal: true },
  ];

  return `
  <div class="compare-wrap">${panelA}${panelB}</div>
  <h4 style="font-size:13px;font-weight:700;margin:16px 0 8px;color:#374151">Ringkasan Selisih (per ${granLabel})</h4>
  ${renderDiffTable(diffRows)}`;
}

/**
 * Arus Kas — Komparasi dua periode
 */
function renderCashflowComparison(dataA, dataB, granLabel) {
  const hA = `<div class="compare-panel-header current">Periode Saat Ini</div>`;
  const hB = `<div class="compare-panel-header previous">Periode Pembanding</div>`;

  const panelA = `<div class="compare-panel">${hA}${renderCashflowReport(dataA)}</div>`;
  const panelB = `<div class="compare-panel">${hB}${renderCashflowReport(dataB)}</div>`;

  const tA = dataA.totals, tB = dataB.totals;
  const diffRows = [
    { label: 'Total Penerimaan Operasional', curr: tA.totalOpInflow, prev: tB.totalOpInflow },
    { label: 'Total Pembayaran Operasional', curr: tA.totalOpOutflow, prev: tB.totalOpOutflow },
    { label: 'Arus Kas Bersih - Operasional', curr: tA.netOp, prev: tB.netOp, subtotal: true },
    { label: 'Arus Kas Bersih - Investasi', curr: tA.netInv, prev: tB.netInv, subtotal: true },
    { label: 'Arus Kas Bersih - Pendanaan', curr: tA.netFin, prev: tB.netFin, subtotal: true },
    { label: 'Kenaikan / Penurunan Kas Bersih', curr: tA.netCashflow, prev: tB.netCashflow, subtotal: true },
    { label: 'Saldo Kas Akhir Periode', curr: tA.saldoAkhir, prev: tB.saldoAkhir, subtotal: true },
  ];

  return `
  <div class="compare-wrap">${panelA}${panelB}</div>
  <h4 style="font-size:13px;font-weight:700;margin:16px 0 8px;color:#374151">Ringkasan Selisih (per ${granLabel})</h4>
  ${renderDiffTable(diffRows)}`;
}

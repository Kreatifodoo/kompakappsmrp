/**
 * JURNAL ENTRI - Auto Generate dari Bank Statement
 * Double-entry bookkeeping berdasarkan transaksi BCA
 */

/**
 * Generate semua jurnal entri dari daftar transaksi
 * Setiap transaksi menghasilkan minimal 2 baris jurnal (debit & kredit)
 */
function generateJournalEntries(transactions) {
  const journals = [];
  let journalNo = 1;

  transactions.forEach((tx, idx) => {
    if (tx.type === 'SALDO_AWAL') {
      // Jurnal pembuka saldo awal
      if (tx.saldo > 0) {
        journals.push({
          id: `JE-${String(journalNo).padStart(4, '0')}`,
          txId: tx.id,
          date: tx.date,
          no: `JE-${String(journalNo).padStart(4, '0')}`,
          description: `Saldo Awal Bank BCA - ${tx.period || ''}`,
          entries: [
            {
              accountCode: '1-1110',
              accountName: COA['1-1110'].name,
              debit: tx.saldo,
              kredit: 0,
              note: 'Saldo awal rekening BCA'
            },
            {
              accountCode: '3-2000',
              accountName: COA['3-2000'].name,
              debit: 0,
              kredit: tx.saldo,
              note: 'Laba ditahan / saldo pembuka'
            }
          ]
        });
        journalNo++;
      }
      return;
    }

    if (!tx.amount || tx.amount <= 0) return;

    const mapping = tx.coaMapping || autoMapTransaction(tx);
    const debitCode = mapping.debitAccount;
    const kreditCode = mapping.kreditAccount;

    const debitAcct = COA[debitCode] || { name: 'Tidak Diketahui' };
    const kreditAcct = COA[kreditCode] || { name: 'Tidak Diketahui' };

    const desc = buildJournalDesc(tx);

    // If tx.splitEntries exist, use split journal entries
    if (tx.splitEntries) {
      const se = tx.splitEntries;

      // PATH A: New structure { debit: [...], kredit: [...] }
      if (!Array.isArray(se) && se.debit && se.kredit) {
        const seDebitTotal  = se.debit.reduce((s, e)  => s + (e.amount || 0), 0);
        const seKreditTotal = se.kredit.reduce((s, e) => s + (e.amount || 0), 0);
        if (Math.abs(seDebitTotal - seKreditTotal) < 0.01) {
          const splitJournal = {
            id: `JE-${String(journalNo).padStart(4, '0')}`,
            txId: tx.id,
            date: tx.date,
            dateRaw: tx.dateRaw,
            no: `JE-${String(journalNo).padStart(4, '0')}`,
            description: desc,
            party: tx.party,
            ref: tx.ref,
            type: tx.type,
            amount: tx.amount,
            period: tx.period,
            sourceFile: tx.sourceFile,
            entries: []
          };
          se.debit.forEach(item => {
            const acct = COA[item.accountCode] || { name: item.accountName || 'Unknown' };
            splitJournal.entries.push({
              accountCode: item.accountCode,
              accountName: acct.name,
              debit: item.amount,
              kredit: 0,
              note: item.note || desc
            });
          });
          se.kredit.forEach(item => {
            const acct = COA[item.accountCode] || { name: item.accountName || 'Unknown' };
            splitJournal.entries.push({
              accountCode: item.accountCode,
              accountName: acct.name,
              debit: 0,
              kredit: item.amount,
              note: item.note || desc
            });
          });
          journals.push(splitJournal);
          journalNo++;
          return;
        }
      }

      // PATH B: Legacy flat array (backward compatibility)
      if (Array.isArray(se) && se.length > 0) {
        const totalSplit = se.reduce((s, e) => s + (e.amount || 0), 0);
        if (Math.abs(totalSplit - tx.amount) < 0.01) {
          const splitJournal = {
            id: `JE-${String(journalNo).padStart(4, '0')}`,
            txId: tx.id,
            date: tx.date,
            dateRaw: tx.dateRaw,
            no: `JE-${String(journalNo).padStart(4, '0')}`,
            description: desc,
            party: tx.party,
            ref: tx.ref,
            type: tx.type,
            amount: tx.amount,
            period: tx.period,
            sourceFile: tx.sourceFile,
            entries: []
          };
          if (tx.type === 'DB') {
            // Multiple debit lines from split + 1 kredit (Bank BCA)
            se.forEach(item => {
              const acct = COA[item.accountCode] || { name: item.accountName || 'Unknown' };
              splitJournal.entries.push({
                accountCode: item.accountCode,
                accountName: acct.name,
                debit: item.amount,
                kredit: 0,
                note: item.note || desc
              });
            });
            splitJournal.entries.push({
              accountCode: kreditCode,
              accountName: kreditAcct.name,
              debit: 0,
              kredit: tx.amount,
              note: desc
            });
          } else {
            // 1 debit (Bank BCA) + multiple kredit lines from split
            splitJournal.entries.push({
              accountCode: debitCode,
              accountName: debitAcct.name,
              debit: tx.amount,
              kredit: 0,
              note: desc
            });
            se.forEach(item => {
              const acct = COA[item.accountCode] || { name: item.accountName || 'Unknown' };
              splitJournal.entries.push({
                accountCode: item.accountCode,
                accountName: acct.name,
                debit: 0,
                kredit: item.amount,
                note: item.note || desc
              });
            });
          }
          journals.push(splitJournal);
          journalNo++;
          return;
        }
      }
    }

    const journal = {
      id: `JE-${String(journalNo).padStart(4, '0')}`,
      txId: tx.id,
      date: tx.date,
      dateRaw: tx.dateRaw,
      no: `JE-${String(journalNo).padStart(4, '0')}`,
      description: desc,
      party: tx.party,
      ref: tx.ref,
      type: tx.type,
      amount: tx.amount,
      period: tx.period,
      sourceFile: tx.sourceFile,
      entries: [
        {
          accountCode: debitCode,
          accountName: debitAcct.name,
          debit: tx.amount,
          kredit: 0,
          note: desc
        },
        {
          accountCode: kreditCode,
          accountName: kreditAcct.name,
          debit: 0,
          kredit: tx.amount,
          note: desc
        }
      ]
    };

    journals.push(journal);
    journalNo++;
  });

  return journals;
}

/**
 * Bangun deskripsi jurnal yang bermakna
 */
function buildJournalDesc(tx) {
  const parts = [];

  if (tx.type === 'CR') {
    parts.push('Penerimaan');
  } else {
    parts.push('Pembayaran');
  }

  // Tambahkan keterangan spesifik
  if (/payroll/i.test(tx.fullDescription || tx.description)) {
    parts.push('Gaji Karyawan (Payroll)');
  } else if (/BIAYA ADM/i.test(tx.description)) {
    parts.push('Biaya Administrasi Bank');
  } else if (/SETORAN TUNAI/i.test(tx.description)) {
    parts.push('Setoran Tunai');
  } else if (tx.party && tx.party.length > 1) {
    parts.push(tx.party.substring(0, 40));
  } else if (tx.description) {
    parts.push(tx.description.substring(0, 40));
  }

  if (tx.ref) {
    parts.push(`| Ref: ${tx.ref.substring(0, 20)}`);
  }

  return parts.join(' - ');
}

/**
 * Hitung total debit dan kredit dari jurnal
 */
function calculateJournalTotals(journals) {
  let totalDebit = 0;
  let totalKredit = 0;

  journals.forEach(j => {
    j.entries.forEach(e => {
      totalDebit += e.debit || 0;
      totalKredit += e.kredit || 0;
    });
  });

  return {
    totalDebit,
    totalKredit,
    selisih: Math.abs(totalDebit - totalKredit),
    isBalanced: Math.abs(totalDebit - totalKredit) < 0.01
  };
}

/**
 * Flatten jurnal menjadi baris-baris untuk tabel display
 */
function flattenJournalForTable(journals) {
  const rows = [];
  let rowNum = 1;

  journals.forEach(j => {
    j.entries.forEach((entry, entryIdx) => {
      rows.push({
        rowNum: entryIdx === 0 ? rowNum++ : '',
        journalId: entryIdx === 0 ? j.no : '',
        txId: entryIdx === 0 ? j.txId : '',
        isSplit: entryIdx === 0 ? j.entries.length > 2 : false,
        date: entryIdx === 0 ? j.date : '',
        description: entryIdx === 0 ? j.description : '',
        accountCode: entry.accountCode,
        accountName: entry.accountName,
        debit: entry.debit > 0 ? entry.debit : null,
        kredit: entry.kredit > 0 ? entry.kredit : null,
        isFirst: entryIdx === 0,
        type: j.type
      });
    });
  });

  return rows;
}

/**
 * Membuat buku besar sederhana dari jurnal
 * Return: { accountCode: { accountName, entries[], totalDebit, totalKredit, balance } }
 */
function buildLedger(journals) {
  const ledger = {};
  if (!Array.isArray(journals)) return ledger;

  journals.forEach(j => {
    if (!j || !Array.isArray(j.entries)) return;
    j.entries.forEach(entry => {
      const code = entry.accountCode;
      if (!ledger[code]) {
        const acct = COA[code];
        ledger[code] = {
          accountCode: code,
          accountName: acct ? acct.name : 'Unknown',
          accountType: acct ? acct.type : '',
          normalBalance: acct ? acct.normal : 'Debit',
          entries: [],
          totalDebit: 0,
          totalKredit: 0,
          balance: 0
        };
      }
      ledger[code].entries.push({
        date: j.date,
        desc: j.description,
        debit: entry.debit || 0,
        kredit: entry.kredit || 0,
        ref: j.no
      });
      ledger[code].totalDebit += entry.debit || 0;
      ledger[code].totalKredit += entry.kredit || 0;
    });
  });

  // Hitung saldo normal setiap akun
  Object.values(ledger).forEach(acct => {
    if (acct.normalBalance === 'Debit') {
      acct.balance = acct.totalDebit - acct.totalKredit;
    } else {
      acct.balance = acct.totalKredit - acct.totalDebit;
    }
  });

  return ledger;
}

/**
 * Ringkasan per akun (trial balance)
 */
function buildTrialBalance(ledger) {
  return Object.values(ledger)
    .filter(a => a.totalDebit > 0 || a.totalKredit > 0)
    .sort((a, b) => a.accountCode.localeCompare(b.accountCode));
}

/**
 * Ringkasan per kategori untuk laporan arus kas
 */
function categorizeForCashflow(journals) {
  const categories = {
    operasional: { inflow: [], outflow: [] },
    investasi: { inflow: [], outflow: [] },
    pendanaan: { inflow: [], outflow: [] }
  };

  journals.forEach(j => {
    if (j.type === 'SALDO_AWAL') return;

    // Tentukan kategori arus kas
    let cat = 'operasional'; // Default

    // Pengeluaran yang bukan operasional
    if (/5-2100|5-2200|5-2300|1-2100|1-2110/i.test(j.entries.map(e => e.accountCode).join(','))) {
      cat = 'investasi';
    }
    if (/2-1600|2-2100|3-4000/i.test(j.entries.map(e => e.accountCode).join(','))) {
      cat = 'pendanaan';
    }

    if (j.type === 'CR') {
      categories[cat].inflow.push({ desc: j.description, amount: j.amount, date: j.date });
    } else {
      categories[cat].outflow.push({ desc: j.description, amount: j.amount, date: j.date });
    }
  });

  return categories;
}

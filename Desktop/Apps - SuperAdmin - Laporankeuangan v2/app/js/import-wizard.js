/**
 * IMPORT-WIZARD.JS — Generic bulk-import widget for master data.
 *
 * Usage:
 *   openImportWizard(IMPORT_CONFIGS.customer);  // or items / suppliers / ...
 *
 * Each config defines the entity's import columns, an example row,
 * an optional async validator (per row), and an async importer (per
 * row). The wizard handles CSV parsing, template download, preview,
 * validation, batch import, and a final summary.
 *
 * CSV parser handles quoted fields (RFC 4180-ish). UTF-8 only.
 */

// ─── CSV parser (no external deps) ────────────────────────────
function parseCSV(text) {
  // Strip UTF-8 BOM
  if (text.charCodeAt(0) === 0xFEFF) text = text.slice(1);
  const rows = [];
  let field = '', row = [], inQuotes = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inQuotes) {
      if (c === '"' && text[i+1] === '"') { field += '"'; i++; }
      else if (c === '"') { inQuotes = false; }
      else { field += c; }
    } else {
      if (c === '"') { inQuotes = true; }
      else if (c === ',') { row.push(field); field = ''; }
      else if (c === '\n') { row.push(field); rows.push(row); row = []; field = ''; }
      else if (c === '\r') { /* skip */ }
      else { field += c; }
    }
  }
  if (field.length > 0 || row.length > 0) { row.push(field); rows.push(row); }
  // Filter empty rows
  return rows.filter(r => r.length > 0 && r.some(c => c.trim() !== ''));
}

function csvEscape(v) {
  const s = String(v ?? '');
  return s.includes(',') || s.includes('"') || s.includes('\n')
    ? `"${s.replace(/"/g, '""')}"` : s;
}

function rowsToCSV(rows) {
  return rows.map(r => r.map(csvEscape).join(',')).join('\n');
}

function downloadCSV(filename, csv) {
  const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename;
  document.body.appendChild(a); a.click(); a.remove();
  URL.revokeObjectURL(url);
}

// ─── State ────────────────────────────────────────────────────
let _impCfg = null;
let _impRows = [];          // [{ raw: {col: val}, errors: [], warnings: [], status: 'pending'|'ok'|'error'|'imported'|'failed' }]
let _impCtx = {};           // shared context across rows (caches: existing customers, accounts, etc.)

// ─── Wizard entrypoint ────────────────────────────────────────
async function openImportWizard(config) {
  _impCfg = config;
  _impRows = [];
  _impCtx = {};

  const html = `
    <div class="modal-backdrop" id="impWizardBackdrop" onclick="if(event.target===this)closeImportWizard()">
      <div class="modal-content" style="max-width:1080px;max-height:90vh">
        <div class="modal-header">
          <h3>📥 Import ${_escImp(config.title)}</h3>
          <button class="modal-close" onclick="closeImportWizard()">×</button>
        </div>
        <div class="modal-body" id="impBody" style="max-height:75vh;overflow-y:auto">
          <!-- Step content rendered here -->
        </div>
      </div>
    </div>`;
  document.body.insertAdjacentHTML('beforeend', html);

  // Preload any reference data needed by validators
  if (typeof config.preload === 'function') {
    try { await config.preload(_impCtx); } catch (e) { console.warn('[import] preload failed', e); }
  }

  _impStep1Upload();
  if (typeof feather !== 'undefined') feather.replace();
}

function closeImportWizard() {
  document.getElementById('impWizardBackdrop')?.remove();
  _impCfg = null;
  _impRows = [];
  _impCtx = {};
}

function _escImp(s) {
  return String(s ?? '').replace(/[<>&"]/g, c => ({'<':'&lt;','>':'&gt;','&':'&amp;','"':'&quot;'}[c]));
}

// ── Step 1: Upload + Template ────────────────────────────────
function _impStep1Upload() {
  const cfg = _impCfg;
  const body = document.getElementById('impBody');
  const colDocsHTML = cfg.columns.map(c => `
    <tr>
      <td><code style="background:#f3f4f6;padding:2px 6px;border-radius:3px">${_escImp(c.key)}</code></td>
      <td>${c.required ? '<strong style="color:#dc2626">✱ Wajib</strong>' : '<span style="color:#6b7280">opsional</span>'}</td>
      <td>${_escImp(c.help || '')}</td>
    </tr>`).join('');

  body.innerHTML = `
    <h4 style="margin:0 0 12px">Step 1 / 3 — Pilih File CSV</h4>
    <p style="color:#6b7280;font-size:13px;margin-bottom:16px">
      Upload file CSV dengan header sesuai template. Unduh template dulu kalau belum punya.
    </p>

    <div style="background:#fef3c7;border-left:4px solid #f59e0b;padding:12px 16px;border-radius:6px;margin-bottom:16px;font-size:13px">
      <strong>💡 Cara cepat:</strong>
      <ol style="margin:8px 0 0;padding-left:20px;line-height:1.6">
        <li>Klik <strong>"Download Template"</strong> di bawah</li>
        <li>Buka file CSV di Excel atau Google Sheets</li>
        <li>Hapus baris contoh, isi data kalian (jangan ubah header)</li>
        <li>Save as CSV (UTF-8) lalu upload di sini</li>
      </ol>
    </div>

    <div style="display:flex;gap:12px;align-items:flex-start;margin-bottom:24px;flex-wrap:wrap">
      <button class="btn btn-primary" onclick="_impDownloadTemplate()">
        <i data-feather="download"></i> Download Template (.csv)
      </button>
      <label class="btn btn-success" style="cursor:pointer">
        <i data-feather="upload"></i> Pilih File CSV
        <input type="file" accept=".csv,text/csv" style="display:none" onchange="_impHandleFile(this)">
      </label>
    </div>

    <h4 style="margin:24px 0 8px">Kolom yang Didukung</h4>
    <div style="overflow-x:auto;border:1px solid #e5e7eb;border-radius:6px">
      <table class="data-table" style="margin:0">
        <thead><tr><th style="width:30%">Header</th><th style="width:15%">Status</th><th>Petunjuk</th></tr></thead>
        <tbody>${colDocsHTML}</tbody>
      </table>
    </div>

    ${cfg.notes ? `<div style="margin-top:16px;padding:12px;background:#f3f4f6;border-radius:6px;font-size:13px;color:#374151">${cfg.notes}</div>` : ''}
  `;
  if (typeof feather !== 'undefined') feather.replace();
}

function _impDownloadTemplate() {
  const cfg = _impCfg;
  const headers = cfg.columns.map(c => c.key);
  // 2-3 example rows from cfg.exampleRows (or single from cfg.exampleRow)
  const examples = cfg.exampleRows || (cfg.exampleRow ? [cfg.exampleRow] : []);
  const exampleRows = examples.map(ex => headers.map(h => ex[h] ?? ''));
  // Add comment row explaining
  const csv = rowsToCSV([
    headers,
    ...exampleRows,
  ]);
  // Prepend a comment line (some tools strip lines starting with #)
  const note = `# Hapus baris contoh sebelum import. Header WAJIB persis seperti di atas. Kolom kosong = pakai default.\n`;
  downloadCSV(cfg.templateFilename || `${cfg.title.toLowerCase().replace(/\s+/g, '-')}-template.csv`, csv);
}

async function _impHandleFile(input) {
  const file = input.files?.[0];
  if (!file) return;
  try {
    const text = await file.text();
    const rows = parseCSV(text);
    // Strip comment rows starting with #
    const filtered = rows.filter(r => !(r[0] && r[0].trim().startsWith('#')));
    if (filtered.length < 2) {
      showToast('File kosong atau hanya berisi header — minimal 1 baris data dibutuhkan', 'error');
      return;
    }
    const headers = filtered[0].map(h => h.trim());
    const dataRows = filtered.slice(1);

    // Validate headers
    const expectedKeys = _impCfg.columns.map(c => c.key);
    const unknownHeaders = headers.filter(h => !expectedKeys.includes(h) && h !== '');
    if (unknownHeaders.length) {
      showToast(`Header tidak dikenal: ${unknownHeaders.join(', ')}. Lihat template untuk daftar valid.`, 'warning');
    }

    _impRows = dataRows.map((cells, idx) => {
      const raw = {};
      headers.forEach((h, i) => { if (h) raw[h] = (cells[i] || '').trim(); });
      return {
        rowNo: idx + 2, // 1-based + header line
        raw, errors: [], warnings: [], status: 'pending',
      };
    });

    await _impValidateAll();
    _impStep2Preview();
  } catch (e) {
    showToast('Gagal baca CSV: ' + e.message, 'error');
  }
}

// ── Step 2: Preview + Validate ────────────────────────────────
async function _impValidateAll() {
  const cfg = _impCfg;
  for (const r of _impRows) {
    r.errors = []; r.warnings = [];
    // Required-field check
    for (const col of cfg.columns) {
      if (col.required && !r.raw[col.key]) {
        r.errors.push(`${col.key} wajib diisi`);
      }
    }
    // Custom validator
    if (!r.errors.length && typeof cfg.validate === 'function') {
      try {
        const res = await cfg.validate(r.raw, _impRows, _impCtx);
        if (res?.errors?.length)   r.errors.push(...res.errors);
        if (res?.warnings?.length) r.warnings.push(...res.warnings);
      } catch (e) {
        r.errors.push('Validation error: ' + e.message);
      }
    }
    r.status = r.errors.length ? 'error' : 'ok';
  }
}

function _impStep2Preview() {
  const cfg = _impCfg;
  const body = document.getElementById('impBody');
  const okCount = _impRows.filter(r => r.status === 'ok').length;
  const errCount = _impRows.filter(r => r.status === 'error').length;
  const warnCount = _impRows.filter(r => r.warnings.length > 0).length;

  const colKeys = cfg.columns.map(c => c.key);

  const rowsHtml = _impRows.map(r => {
    const statusBadge = r.status === 'ok'
      ? '<span style="color:#10b981">✓ OK</span>'
      : r.status === 'error'
      ? '<span style="color:#ef4444">✗ Error</span>'
      : '<span style="color:#6b7280">…</span>';
    const issues = [
      ...r.errors.map(e => `<div style="color:#ef4444;font-size:11px">❌ ${_escImp(e)}</div>`),
      ...r.warnings.map(w => `<div style="color:#f59e0b;font-size:11px">⚠ ${_escImp(w)}</div>`),
    ].join('');
    return `
      <tr style="background:${r.status === 'error' ? '#fef2f2' : (r.warnings.length ? '#fffbeb' : '')}">
        <td style="text-align:center;font-size:11px;color:#6b7280">${r.rowNo}</td>
        <td>${statusBadge}${issues ? '<div style="margin-top:4px">' + issues + '</div>' : ''}</td>
        ${colKeys.map(k => `<td>${_escImp(r.raw[k] || '')}</td>`).join('')}
      </tr>`;
  }).join('');

  body.innerHTML = `
    <h4 style="margin:0 0 12px">Step 2 / 3 — Preview & Validasi</h4>
    <div style="display:flex;gap:12px;margin-bottom:16px;flex-wrap:wrap">
      <div style="padding:8px 16px;background:#d1fae5;color:#065f46;border-radius:6px;font-size:13px">
        ✓ Valid: <strong>${okCount}</strong>
      </div>
      <div style="padding:8px 16px;background:#fee2e2;color:#991b1b;border-radius:6px;font-size:13px">
        ✗ Error: <strong>${errCount}</strong>
      </div>
      ${warnCount > 0 ? `<div style="padding:8px 16px;background:#fef3c7;color:#92400e;border-radius:6px;font-size:13px">⚠ Warning: <strong>${warnCount}</strong></div>` : ''}
      <div style="padding:8px 16px;background:#e5e7eb;color:#374151;border-radius:6px;font-size:13px">
        Total: <strong>${_impRows.length}</strong>
      </div>
    </div>

    <div style="overflow-x:auto;border:1px solid #e5e7eb;border-radius:6px;max-height:400px;overflow-y:auto">
      <table class="data-table" style="margin:0;font-size:12px">
        <thead style="position:sticky;top:0;background:#fff;z-index:1">
          <tr>
            <th style="width:50px">#</th>
            <th style="width:220px">Status</th>
            ${cfg.columns.map(c => `<th>${_escImp(c.key)}</th>`).join('')}
          </tr>
        </thead>
        <tbody>${rowsHtml}</tbody>
      </table>
    </div>

    <div style="margin-top:16px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px">
      <div style="font-size:12px;color:#6b7280">
        ${errCount > 0 ? 'Baris error akan di-skip otomatis kalau klik Import Valid Rows.' : 'Semua siap di-import.'}
      </div>
      <div style="display:flex;gap:8px">
        <button class="btn btn-outline" onclick="_impStep1Upload()">← Ganti File</button>
        ${okCount > 0 ? `<button class="btn btn-success" onclick="_impStep3Execute()">📤 Import ${okCount} Baris Valid</button>` : ''}
      </div>
    </div>
  `;
}

// ── Step 3: Execute import ────────────────────────────────────
async function _impStep3Execute() {
  const cfg = _impCfg;
  const body = document.getElementById('impBody');
  const toImport = _impRows.filter(r => r.status === 'ok');
  let done = 0;
  let failed = 0;

  body.innerHTML = `
    <h4 style="margin:0 0 16px">Step 3 / 3 — Import Sedang Berjalan…</h4>
    <div style="background:#f3f4f6;border-radius:8px;padding:16px;margin-bottom:16px">
      <div style="font-size:13px;color:#374151;margin-bottom:8px">
        <span id="impProgressText">0 / ${toImport.length} selesai</span>
      </div>
      <div style="height:8px;background:#e5e7eb;border-radius:4px;overflow:hidden">
        <div id="impProgressBar" style="height:100%;width:0%;background:#10b981;transition:width 0.2s"></div>
      </div>
    </div>
    <div id="impLog" style="max-height:300px;overflow-y:auto;font-family:monospace;font-size:11px;background:#1f2937;color:#d1fae5;padding:12px;border-radius:6px"></div>
  `;
  const log = document.getElementById('impLog');
  const append = (msg, color='#d1fae5') => {
    log.innerHTML += `<div style="color:${color}">${_escImp(msg)}</div>`;
    log.scrollTop = log.scrollHeight;
  };

  for (const r of toImport) {
    try {
      const result = await cfg.import(r.raw, _impCtx);
      r.status = 'imported';
      done++;
      append(`✓ Baris ${r.rowNo}: ${result?.message || 'OK'}`, '#86efac');
    } catch (e) {
      r.status = 'failed';
      r.errors.push(e.message);
      failed++;
      append(`✗ Baris ${r.rowNo}: ${e.message}`, '#fca5a5');
    }
    document.getElementById('impProgressText').textContent = `${done + failed} / ${toImport.length} selesai`;
    document.getElementById('impProgressBar').style.width = `${((done + failed) / toImport.length) * 100}%`;
  }

  // Summary
  const errLines = _impRows.filter(r => r.status === 'failed').map(r => `
    <li style="margin-bottom:6px">
      <strong>Baris ${r.rowNo}</strong> (${_escImp(Object.values(r.raw)[0] || '')}): ${_escImp(r.errors.join('; '))}
    </li>`).join('');

  setTimeout(() => {
    body.innerHTML = `
      <h4 style="margin:0 0 16px">✅ Selesai!</h4>
      <div style="display:flex;gap:12px;margin-bottom:16px;flex-wrap:wrap">
        <div style="padding:12px 24px;background:#d1fae5;color:#065f46;border-radius:8px">
          ✓ Berhasil: <strong style="font-size:24px">${done}</strong>
        </div>
        ${failed > 0 ? `<div style="padding:12px 24px;background:#fee2e2;color:#991b1b;border-radius:8px">
          ✗ Gagal: <strong style="font-size:24px">${failed}</strong>
        </div>` : ''}
        <div style="padding:12px 24px;background:#e5e7eb;color:#374151;border-radius:8px">
          Total: <strong style="font-size:24px">${toImport.length}</strong>
        </div>
      </div>

      ${failed > 0 ? `
        <h4 style="margin:16px 0 8px;color:#991b1b">Detail Error</h4>
        <ul style="background:#fef2f2;padding:12px 24px;border-radius:6px;font-size:13px;color:#7f1d1d">
          ${errLines}
        </ul>
      ` : ''}

      <div style="margin-top:24px;text-align:right">
        <button class="btn btn-primary" onclick="closeImportWizard(); ${_impCfg.onComplete ? _impCfg.onComplete.toString().replace(/^\(\)\s*=>\s*/, '') : ''}">
          Tutup & Refresh
        </button>
      </div>
    `;
  }, 300);
}

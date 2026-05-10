/**
 * IDENTITY-EXTRAS.JS — Audit Logs viewer + Roles & Permissions management
 *
 * Pages:
 *   renderAuditLogPage()  → page-audit-log
 *   renderRolesPage()     → page-roles
 *   renderChangePasswordModal()  — utility modal
 */

function _escId(s) {
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}
function _fmtDateTime(d) {
  if (!d) return '-';
  try { return new Date(d).toLocaleString('id-ID'); } catch { return String(d).slice(0,19); }
}

// ═══════════════════════════════════════════════════════════════════
// AUDIT LOG VIEWER (#page-audit-log)
// ═══════════════════════════════════════════════════════════════════
async function renderAuditLogPage() {
  const wrap = document.getElementById('page-audit-log');
  if (!wrap) return;
  const today = new Date().toISOString().slice(0,10);
  const aWeekAgo = new Date(Date.now() - 7*86400000).toISOString().slice(0,10);
  wrap.innerHTML = `
    <div class="page-header">
      <h2>Audit Log</h2>
      <p class="page-subtitle">Riwayat perubahan data: siapa ubah apa kapan. Auto-tracked dari semua mutasi backend (create/update/delete/post/void).</p>
    </div>

    <div class="report-filter-bar" style="margin-bottom:12px;display:flex;gap:8px;align-items:end;flex-wrap:wrap">
      <div class="form-group" style="margin:0"><label>Tabel</label>
        <select id="auTable" class="form-control" style="min-width:140px">
          <option value="">— Semua —</option>
          <option value="accounts">Accounts</option>
          <option value="customers">Customers</option>
          <option value="suppliers">Suppliers</option>
          <option value="sales_invoices">Sales Invoices</option>
          <option value="purchase_invoices">Purchase Invoices</option>
          <option value="payments">Payments</option>
          <option value="journal_entries">Journal Entries</option>
          <option value="items">Items</option>
          <option value="warehouses">Warehouses</option>
          <option value="stock_movements">Stock Movements</option>
          <option value="stock_transfers">Stock Transfers</option>
          <option value="users">Users</option>
          <option value="roles">Roles</option>
        </select></div>
      <div class="form-group" style="margin:0"><label>Action</label>
        <select id="auAction" class="form-control">
          <option value="">— Semua —</option>
          <option value="create">create</option>
          <option value="update">update</option>
          <option value="delete">delete</option>
          <option value="post">post</option>
          <option value="void">void</option>
        </select></div>
      <div class="form-group" style="margin:0"><label>Dari</label>
        <input type="date" id="auFrom" class="form-control" value="${aWeekAgo}"></div>
      <div class="form-group" style="margin:0"><label>Sampai</label>
        <input type="date" id="auTo" class="form-control" value="${today}"></div>
      <div class="form-group" style="margin:0"><label>Limit</label>
        <input type="number" id="auLimit" class="form-control" value="100" min="10" max="500" style="width:100px"></div>
      <button class="btn btn-primary" onclick="loadAuditLog()">🔍 Tampilkan</button>
      <button class="btn btn-outline" onclick="clearAuditFilters()">Reset</button>
    </div>

    <div id="auResult"><div class="empty-state">Klik Tampilkan untuk memuat.</div></div>
  `;
  await loadAuditLog();
}

function clearAuditFilters() {
  document.getElementById('auTable').value = '';
  document.getElementById('auAction').value = '';
  loadAuditLog();
}

async function loadAuditLog() {
  const out = document.getElementById('auResult'); if (!out) return;
  const params = {
    table_name: document.getElementById('auTable').value || undefined,
    action: document.getElementById('auAction').value || undefined,
    date_from: document.getElementById('auFrom').value || undefined,
    date_to: document.getElementById('auTo').value || undefined,
    limit: parseInt(document.getElementById('auLimit').value) || 100,
  };
  // Strip undefined keys
  Object.keys(params).forEach(k => params[k] === undefined && delete params[k]);

  out.innerHTML = '<div class="empty-state">Memuat…</div>';
  try {
    const logs = await Api.audit.list(params);
    if (!logs.length) { out.innerHTML = '<div class="empty-state">Tidak ada audit log dalam filter ini.</div>'; return; }

    const actionBadges = {
      create: '<span style="background:#dcfce7;color:#15803d;padding:1px 6px;border-radius:3px;font-size:10px;font-weight:600">CREATE</span>',
      update: '<span style="background:#dbeafe;color:#1e40af;padding:1px 6px;border-radius:3px;font-size:10px;font-weight:600">UPDATE</span>',
      delete: '<span style="background:#fee2e2;color:#991b1b;padding:1px 6px;border-radius:3px;font-size:10px;font-weight:600">DELETE</span>',
      post:   '<span style="background:#fef3c7;color:#92400e;padding:1px 6px;border-radius:3px;font-size:10px;font-weight:600">POST</span>',
      void:   '<span style="background:#fee2e2;color:#991b1b;padding:1px 6px;border-radius:3px;font-size:10px;font-weight:600">VOID</span>',
    };

    out.innerHTML = `
      <p style="font-size:12px;color:#6b7280;margin-bottom:8px">${logs.length} entries</p>
      <table class="data-table">
        <thead><tr>
          <th>Waktu</th><th>Action</th><th>Tabel</th><th>Row ID</th>
          <th>User</th><th>Request ID</th><th>Changes</th><th>Aksi</th>
        </tr></thead>
        <tbody>${logs.map(l => `<tr>
          <td>${_fmtDateTime(l.occurred_at)}</td>
          <td>${actionBadges[l.action] || _escId(l.action)}</td>
          <td><strong>${_escId(l.table_name)}</strong></td>
          <td><code style="font-size:11px">${_escId((l.row_id||'').slice(0,8))}…</code></td>
          <td>${l.user_id ? `<code style="font-size:11px">${_escId((l.user_id||'').slice(0,8))}</code>` : '<em style="color:#9ca3af">system</em>'}</td>
          <td>${l.request_id ? `<code style="font-size:11px">${_escId(l.request_id.slice(0,8))}</code>` : '-'}</td>
          <td><small style="font-family:monospace;color:#6b7280">${_escId(JSON.stringify(l.changes||{}).slice(0,80))}${JSON.stringify(l.changes||{}).length > 80 ? '…' : ''}</small></td>
          <td>
            <button class="btn btn-sm btn-outline" onclick="showAuditDetail('${l.id}')">Detail</button>
            <button class="btn btn-sm btn-outline" onclick="showRowHistory('${l.row_id}','${_escId(l.table_name)}')">History</button>
          </td>
        </tr>`).join('')}</tbody>
      </table>`;
  } catch (e) { out.innerHTML = `<div class="empty-state error">Gagal: ${_escId(e.message)}</div>`; }
}

async function showAuditDetail(logId) {
  // The list endpoint already returns the full row. Find it from current state.
  const logs = await Api.audit.list({limit: 500}).catch(() => []);
  const log = logs.find(l => l.id === logId);
  if (!log) { showToast('Entry tidak ditemukan', 'error'); return; }
  const html = `
    <div class="modal-backdrop" id="auDetailModal" onclick="if(event.target===this)document.getElementById('auDetailModal').remove()">
      <div class="modal-dialog" style="max-width:680px">
        <div class="modal-header">
          <h3>Audit Log Detail</h3>
          <button class="modal-close" onclick="document.getElementById('auDetailModal').remove()">×</button>
        </div>
        <div class="modal-body">
          <table class="data-table" style="margin:0">
            <tr><td><strong>Waktu</strong></td><td>${_fmtDateTime(log.occurred_at)}</td></tr>
            <tr><td><strong>Action</strong></td><td>${_escId(log.action)}</td></tr>
            <tr><td><strong>Tabel</strong></td><td>${_escId(log.table_name)}</td></tr>
            <tr><td><strong>Row ID</strong></td><td><code>${_escId(log.row_id)}</code></td></tr>
            <tr><td><strong>User ID</strong></td><td><code>${_escId(log.user_id || 'system')}</code></td></tr>
            <tr><td><strong>Request ID</strong></td><td><code>${_escId(log.request_id || '-')}</code></td></tr>
          </table>
          <h4 style="margin:16px 0 8px">Changes (JSON)</h4>
          <pre style="background:#f9fafb;padding:12px;border-radius:6px;font-size:12px;overflow:auto;max-height:400px">${_escId(JSON.stringify(log.changes||{}, null, 2))}</pre>
        </div>
      </div>
    </div>`;
  document.body.insertAdjacentHTML('beforeend', html);
}

async function showRowHistory(rowId, tableName) {
  try {
    const history = await Api.audit.history(rowId);
    if (!history.length) { showToast('Tidak ada history', 'info'); return; }
    const html = `
      <div class="modal-backdrop" id="auHistModal" onclick="if(event.target===this)document.getElementById('auHistModal').remove()">
        <div class="modal-dialog" style="max-width:880px">
          <div class="modal-header">
            <h3>Row History — ${_escId(tableName)} <code>${_escId(rowId.slice(0,8))}</code></h3>
            <button class="modal-close" onclick="document.getElementById('auHistModal').remove()">×</button>
          </div>
          <div class="modal-body">
            <p style="color:#6b7280;font-size:12px">${history.length} mutasi (kronologis)</p>
            <table class="data-table">
              <thead><tr><th>Waktu</th><th>Action</th><th>User</th><th>Changes</th></tr></thead>
              <tbody>${history.map(h => `<tr>
                <td>${_fmtDateTime(h.occurred_at)}</td>
                <td>${_escId(h.action)}</td>
                <td><code style="font-size:11px">${_escId((h.user_id||'system').slice(0,8))}</code></td>
                <td><pre style="font-size:11px;margin:0;max-height:120px;overflow:auto">${_escId(JSON.stringify(h.changes||{}, null, 2))}</pre></td>
              </tr>`).join('')}</tbody>
            </table>
          </div>
        </div>
      </div>`;
    document.body.insertAdjacentHTML('beforeend', html);
  } catch (e) { showToast('Gagal: ' + e.message, 'error'); }
}

// ═══════════════════════════════════════════════════════════════════
// ROLES & PERMISSIONS (#page-roles)
// ═══════════════════════════════════════════════════════════════════
async function renderRolesPage() {
  const wrap = document.getElementById('page-roles');
  if (!wrap) return;

  let roles = [], permissions = [];
  try {
    [roles, permissions] = await Promise.all([
      Api.roles.list().catch(() => []),
      Api.permissions.list().catch(() => []),
    ]);
  } catch (e) {}
  window.__rolesCache = { roles, permissions };

  const sysRoles = roles.filter(r => r.is_system);
  const tenantRoles = roles.filter(r => !r.is_system);

  const renderRoleRow = (r) => `<tr>
    <td><strong>${_escId(r.name)}</strong>
        ${r.is_system ? '<span style="background:#fef3c7;color:#92400e;padding:1px 6px;border-radius:3px;font-size:10px;font-weight:600">SYSTEM</span>' : ''}</td>
    <td>${_escId(r.description || '')}</td>
    <td><span style="font-size:11px;color:#6b7280">${(r.permissions||[]).length} perms</span></td>
    <td>
      <button class="btn btn-sm btn-outline" onclick="showRoleModal('${r.id}')">${r.is_system ? 'Lihat' : 'Edit'}</button>
      ${r.is_system ? '' : `<button class="btn btn-sm btn-danger" onclick="deleteRole('${r.id}','${_escId(r.name)}')">×</button>`}
    </td>
  </tr>`;

  wrap.innerHTML = `
    <div class="page-header">
      <div>
        <h2>Roles & Permissions</h2>
        <p class="page-subtitle">Kelola role tenant + assign permissions. Backend permissions: <code>${permissions.length}</code> codes available.</p>
      </div>
      <button class="btn btn-primary" onclick="showRoleModal(null)">+ Tambah Role</button>
    </div>

    <h3 style="font-size:14px;color:#374151;margin:16px 0 8px">System Roles (${sysRoles.length})</h3>
    <div style="background:#fff;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);overflow:hidden;margin-bottom:24px">
      <table class="data-table" style="margin:0">
        <thead><tr><th>Name</th><th>Description</th><th>Permissions</th><th>Aksi</th></tr></thead>
        <tbody>${sysRoles.length === 0 ? '<tr><td colspan="4" style="text-align:center;color:#6b7280;padding:24px">Belum ada system roles.</td></tr>' : sysRoles.map(renderRoleRow).join('')}</tbody>
      </table>
    </div>

    <h3 style="font-size:14px;color:#374151;margin:16px 0 8px">Tenant Roles (${tenantRoles.length})</h3>
    <div style="background:#fff;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);overflow:hidden">
      <table class="data-table" style="margin:0">
        <thead><tr><th>Name</th><th>Description</th><th>Permissions</th><th>Aksi</th></tr></thead>
        <tbody>${tenantRoles.length === 0 ? '<tr><td colspan="4" style="text-align:center;color:#6b7280;padding:24px">Belum ada custom role. Klik <strong>+ Tambah Role</strong> untuk membuat.</td></tr>' : tenantRoles.map(renderRoleRow).join('')}</tbody>
      </table>
    </div>
  `;
}

async function showRoleModal(roleId) {
  const cache = window.__rolesCache || {};
  const allPerms = cache.permissions || [];
  let role = null;
  if (roleId) {
    role = (cache.roles || []).find(r => r.id === roleId);
    if (!role) { showToast('Role tidak ditemukan', 'error'); return; }
  }
  const isSystem = role?.is_system;
  const checkedPerms = new Set(role?.permissions || []);

  // Group permissions by prefix (e.g., 'sales.', 'purchase.', etc.)
  const grouped = {};
  for (const p of allPerms) {
    const prefix = (p.code || '').split('.')[0] || 'other';
    if (!grouped[prefix]) grouped[prefix] = [];
    grouped[prefix].push(p);
  }
  const groupHtml = Object.entries(grouped).sort(([a],[b]) => a.localeCompare(b)).map(([prefix, perms]) => `
    <div style="margin-bottom:12px;border:1px solid #e5e7eb;border-radius:6px;overflow:hidden">
      <div style="background:#f9fafb;padding:6px 12px;font-size:12px;font-weight:600;text-transform:uppercase;color:#374151">${_escId(prefix)} (${perms.length})</div>
      <div style="padding:8px 12px;display:grid;grid-template-columns:repeat(2,1fr);gap:4px">
        ${perms.sort((a,b)=>a.code.localeCompare(b.code)).map(p => `<label style="display:flex;align-items:center;gap:6px;font-size:13px;cursor:pointer">
          <input type="checkbox" name="rolePerms" value="${_escId(p.code)}" ${checkedPerms.has(p.code)?'checked':''} ${isSystem?'disabled':''}>
          <code style="font-size:11px">${_escId(p.code)}</code>
          ${p.description ? `<span style="color:#6b7280;font-size:11px">— ${_escId(p.description)}</span>` : ''}
        </label>`).join('')}
      </div>
    </div>`).join('');

  const html = `
    <div class="modal-backdrop" id="roleModal" onclick="if(event.target===this)closeRoleModal()">
      <div class="modal-dialog" style="max-width:760px;max-height:90vh;display:flex;flex-direction:column">
        <div class="modal-header">
          <h3>${role ? (isSystem ? 'Lihat' : 'Edit') + ' Role' : 'Tambah Role'}${isSystem ? ' (System — Read Only)' : ''}</h3>
          <button class="modal-close" onclick="closeRoleModal()">×</button>
        </div>
        <div class="modal-body" style="overflow-y:auto">
          <div class="form-row">
            <div class="form-group" style="flex:1"><label>Name *</label>
              <input class="form-control" id="roleName" value="${_escId(role?.name||'')}" ${isSystem?'disabled':''} placeholder="e.g. accountant"></div>
          </div>
          <div class="form-group"><label>Description</label>
            <input class="form-control" id="roleDesc" value="${_escId(role?.description||'')}" ${isSystem?'disabled':''} placeholder="Role description"></div>
          <div class="form-group">
            <label>Permissions (${(role?.permissions||[]).length} / ${allPerms.length} selected)</label>
            <div style="font-size:11px;color:#6b7280;margin-bottom:8px">Centang permission yang akan dimiliki role ini.</div>
            <div style="max-height:380px;overflow-y:auto;border:1px solid #e5e7eb;border-radius:6px;padding:8px">${groupHtml || '<div class="empty-state">No permissions defined</div>'}</div>
          </div>
          <div id="roleErr" class="form-error" style="display:none"></div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-outline" onclick="closeRoleModal()">${isSystem ? 'Tutup' : 'Batal'}</button>
          ${isSystem ? '' : `<button class="btn btn-primary" onclick="saveRole('${roleId||''}')">Simpan</button>`}
        </div>
      </div>
    </div>`;
  document.body.insertAdjacentHTML('beforeend', html);
}

function closeRoleModal() { document.getElementById('roleModal')?.remove(); }

async function saveRole(roleId) {
  const errEl = document.getElementById('roleErr');
  errEl.style.display = 'none';
  const name = document.getElementById('roleName').value.trim();
  const desc = document.getElementById('roleDesc').value.trim();
  const perms = Array.from(document.querySelectorAll('input[name="rolePerms"]:checked')).map(c => c.value);

  if (!name) { errEl.textContent = 'Name wajib'; errEl.style.display='block'; return; }

  try {
    if (roleId) {
      await Api.roles.update(roleId, {name, description: desc || null, permissions: perms});
      showToast('Role diupdate', 'success');
    } else {
      await Api.roles.create({name, description: desc || null, permissions: perms});
      showToast('Role dibuat', 'success');
    }
    closeRoleModal();
    await renderRolesPage();
  } catch (e) {
    errEl.textContent = e.message; errEl.style.display = 'block';
  }
}

async function deleteRole(roleId, roleName) {
  if (!confirm(`Hapus role "${roleName}"? Tindakan ini permanent. User dengan role ini akan kehilangan akses.`)) return;
  try {
    await Api.roles.delete(roleId);
    showToast('Role dihapus', 'success');
    await renderRolesPage();
  } catch (e) { showToast('Gagal: ' + e.message, 'error'); }
}

// ═══════════════════════════════════════════════════════════════════
// CHANGE PASSWORD (modal yg bisa dipanggil dari header user)
// ═══════════════════════════════════════════════════════════════════
function showChangePasswordModal() {
  const html = `
    <div class="modal-backdrop" id="cpwModal" onclick="if(event.target===this)closeCpwModal()">
      <div class="modal-dialog" style="max-width:440px">
        <div class="modal-header">
          <h3>Ubah Password</h3>
          <button class="modal-close" onclick="closeCpwModal()">×</button>
        </div>
        <div class="modal-body">
          <div class="form-group"><label>Password Lama *</label>
            <input class="form-control" type="password" id="cpwOld"></div>
          <div class="form-group"><label>Password Baru *</label>
            <input class="form-control" type="password" id="cpwNew">
            <small style="color:#6b7280">Min 8 karakter</small></div>
          <div class="form-group"><label>Konfirmasi Password Baru *</label>
            <input class="form-control" type="password" id="cpwConfirm"></div>
          <div id="cpwErr" class="form-error" style="display:none"></div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-outline" onclick="closeCpwModal()">Batal</button>
          <button class="btn btn-primary" onclick="submitChangePassword()">Simpan</button>
        </div>
      </div>
    </div>`;
  document.body.insertAdjacentHTML('beforeend', html);
}

function closeCpwModal() { document.getElementById('cpwModal')?.remove(); }

async function submitChangePassword() {
  const errEl = document.getElementById('cpwErr');
  errEl.style.display = 'none';
  const oldPw = document.getElementById('cpwOld').value;
  const newPw = document.getElementById('cpwNew').value;
  const confirmPw = document.getElementById('cpwConfirm').value;
  if (!oldPw || !newPw || !confirmPw) { errEl.textContent = 'Semua field wajib'; errEl.style.display='block'; return; }
  if (newPw.length < 8) { errEl.textContent = 'Password baru min 8 karakter'; errEl.style.display='block'; return; }
  if (newPw !== confirmPw) { errEl.textContent = 'Konfirmasi tidak cocok'; errEl.style.display='block'; return; }
  try {
    await Api.authPassword.change(oldPw, newPw);
    showToast('Password berhasil diubah', 'success');
    closeCpwModal();
  } catch (e) {
    errEl.textContent = e.message; errEl.style.display = 'block';
  }
}

// ═══════════════════════════════════════════════════════════════════
// FORGOT PASSWORD — di login screen
// ═══════════════════════════════════════════════════════════════════
function showForgotPasswordModal() {
  const html = `
    <div class="modal-backdrop" id="fpwModal" onclick="if(event.target===this)closeFpwModal()">
      <div class="modal-dialog" style="max-width:440px">
        <div class="modal-header">
          <h3>Lupa Password</h3>
          <button class="modal-close" onclick="closeFpwModal()">×</button>
        </div>
        <div class="modal-body">
          <p style="font-size:13px;color:#374151">Masukkan email akun yang terdaftar. Link reset password akan dikirim ke email tersebut.</p>
          <div class="form-group"><label>Email *</label>
            <input class="form-control" type="email" id="fpwEmail" placeholder="email@example.com"></div>
          <div id="fpwErr" class="form-error" style="display:none"></div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-outline" onclick="closeFpwModal()">Batal</button>
          <button class="btn btn-primary" onclick="submitForgotPassword()">Kirim</button>
        </div>
      </div>
    </div>`;
  document.body.insertAdjacentHTML('beforeend', html);
}

function closeFpwModal() { document.getElementById('fpwModal')?.remove(); }

async function submitForgotPassword() {
  const errEl = document.getElementById('fpwErr');
  errEl.style.display = 'none';
  const email = document.getElementById('fpwEmail').value.trim();
  if (!email || !email.includes('@')) { errEl.textContent = 'Email valid wajib'; errEl.style.display='block'; return; }
  try {
    await Api.authPassword.forgot(email);
    showToast('✓ Link reset dikirim ke email (cek inbox)', 'success');
    closeFpwModal();
  } catch (e) {
    // Always show generic message for security (don't leak which emails exist)
    showToast('✓ Jika email terdaftar, link reset sudah dikirim', 'info');
    closeFpwModal();
  }
}


// ═══════════════════════════════════════════════════════════════════
// TENANT USERS CRUD (re-uses existing #page-users HTML table)
// Replaces legacy localStorage-based renderUsersPage when backend logged in.
// ═══════════════════════════════════════════════════════════════════
async function renderBackendUsersPage() {
  // Hide the legacy localStorage settings section + use existing roles table render
  const appSettings = document.getElementById('appSettingsSection');
  if (appSettings) appSettings.style.display = 'none';

  // Render roles section using backend (re-use existing rolesTableBody)
  await _renderBackendRolesTable();

  // Render users section using backend (re-use existing usersTableBody)
  await _renderBackendUsersTable();
}

async function _renderBackendRolesTable() {
  const tbody = document.getElementById('rolesTableBody');
  if (!tbody) return;
  try {
    const roles = await Api.roles.list();
    const perms = await Api.permissions.list().catch(() => []);
    window.__rolesCache = { roles, permissions: perms };
    if (!roles.length) { tbody.innerHTML = '<tr><td colspan="4" class="empty-row">Belum ada role</td></tr>'; return; }
    tbody.innerHTML = roles.map(r => `
      <tr>
        <td><strong>${_escId(r.name)}</strong>
            ${r.is_system ? '<span style="background:#fef3c7;color:#92400e;padding:1px 6px;border-radius:3px;font-size:10px;font-weight:600;margin-left:4px">SYSTEM</span>' : ''}</td>
        <td>${_escId(r.description || '')}</td>
        <td>${(r.permissions||[]).length} permissions</td>
        <td>
          <button class="btn-icon" onclick="showRoleModal('${r.id}')" title="${r.is_system?'Lihat':'Edit'}">${r.is_system?'👁':'✏️'}</button>
          ${r.is_system ? '' : `<button class="btn-icon btn-icon-danger" onclick="deleteRole('${r.id}','${_escId(r.name)}')" title="Hapus">🗑</button>`}
        </td>
      </tr>`).join('');
  } catch (e) { tbody.innerHTML = `<tr><td colspan="4" class="empty-row" style="color:#b91c1c">Gagal: ${_escId(e.message)}</td></tr>`; }
}

async function _renderBackendUsersTable() {
  const tbody = document.getElementById('usersTableBody');
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="5" class="empty-row">Memuat dari backend...</td></tr>';
  try {
    const users = await Api.users.list();
    if (!users.length) { tbody.innerHTML = '<tr><td colspan="5" class="empty-row">Belum ada pengguna di tenant ini</td></tr>'; return; }
    const me = (typeof getCurrentUser === 'function') ? getCurrentUser() : null;
    tbody.innerHTML = users.map(u => {
      const initial = (u.full_name || u.email).charAt(0).toUpperCase();
      const isMe = u.user_id === me?.userId;
      const lastLogin = u.last_login_at ? new Date(u.last_login_at).toLocaleString('id-ID') : 'Belum pernah';
      const ownerBadge = u.is_owner ? '<span class="badge-superadmin" style="font-size:10px;padding:1px 6px;margin-left:4px">Owner</span>' : '';
      const inactiveBadge = !u.is_active ? '<span class="badge" style="font-size:10px;padding:1px 6px;margin-left:4px;background:#fee2e2;color:#991b1b">Nonaktif</span>' : '';
      const meBadge = isMe ? '<span class="badge badge-neutral" style="font-size:10px;padding:2px 6px;margin-left:2px">Anda</span>' : '';
      const canDeactivate = !isMe && !u.is_owner && u.is_active;
      const canReactivate = !u.is_active;
      return `
        <tr ${!u.is_active?'style="opacity:0.6"':''}>
          <td>
            <div class="user-cell">
              <div class="user-avatar-sm">${_escId(initial)}</div>
              <div>
                <div><strong>${_escId(u.full_name || u.email)}</strong> ${ownerBadge}${inactiveBadge}${meBadge}</div>
                <small style="color:#6b7280">${_escId(u.email)}</small>
              </div>
            </div>
          </td>
          <td><span class="role-badge role-${_escId(u.role_name.toLowerCase())}">${_escId(u.role_name)}</span></td>
          <td>${u.invited_at ? new Date(u.invited_at).toLocaleDateString('id-ID') : '-'}</td>
          <td>${lastLogin}</td>
          <td class="action-cell">
            <button class="btn-icon" onclick="showEditUserModal('${u.user_id}')" title="Edit user">✏️</button>
            ${canDeactivate ? `<button class="btn-icon btn-icon-danger" onclick="deactivateUser('${u.user_id}','${_escId(u.full_name || u.email)}')" title="Nonaktifkan">🚫</button>` : ''}
            ${canReactivate ? `<button class="btn-icon" onclick="reactivateUser('${u.user_id}','${_escId(u.full_name || u.email)}')" title="Aktifkan kembali">✓</button>` : ''}
          </td>
        </tr>`;
    }).join('');
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="5" class="empty-row" style="color:#b91c1c">Gagal: ${_escId(e.message)}</td></tr>`;
  }
}

// ─── Invite (Tambah Pengguna) ─────────────────────────────────
async function showInviteUserModal() {
  const roles = (window.__rolesCache?.roles) || (await Api.roles.list().catch(() => []));
  const roleOpts = roles.map(r => `<option value="${r.id}">${_escId(r.name)}${r.is_system?' (system)':''}</option>`).join('');
  const html = `
    <div class="modal-backdrop" id="inviteUserModal" onclick="if(event.target===this)closeInviteUserModal()">
      <div class="modal-dialog" style="max-width:480px">
        <div class="modal-header">
          <h3>Tambah Pengguna Baru</h3>
          <button class="modal-close" onclick="closeInviteUserModal()">×</button>
        </div>
        <div class="modal-body">
          <div class="form-group"><label>Nama Lengkap *</label>
            <input class="form-control" id="iuName" placeholder="Misal: Andi Setiawan"></div>
          <div class="form-group"><label>Email *</label>
            <input class="form-control" id="iuEmail" type="email" placeholder="email@example.com"></div>
          <div class="form-group"><label>Role *</label>
            <select class="form-control" id="iuRole"><option value="">— Pilih role —</option>${roleOpts}</select></div>
          <div class="form-group">
            <label><input type="checkbox" id="iuAutoPwd" checked> Auto-generate password (akan ditampilkan setelah simpan)</label>
          </div>
          <div class="form-group" id="iuPwdWrap" style="display:none"><label>Password Awal *</label>
            <input class="form-control" type="text" id="iuPwd" placeholder="min 8 karakter">
            <small style="color:#6b7280">Bisa di-share via WhatsApp/SMS. User wajib ganti pada login pertama.</small></div>
          <div id="iuErr" class="form-error" style="display:none"></div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-outline" onclick="closeInviteUserModal()">Batal</button>
          <button class="btn btn-primary" onclick="submitInviteUser()">Simpan & Buat</button>
        </div>
      </div>
    </div>`;
  document.body.insertAdjacentHTML('beforeend', html);
  document.getElementById('iuAutoPwd').addEventListener('change', (e) => {
    document.getElementById('iuPwdWrap').style.display = e.target.checked ? 'none' : '';
  });
}

function closeInviteUserModal() { document.getElementById('inviteUserModal')?.remove(); }

async function submitInviteUser() {
  const errEl = document.getElementById('iuErr');
  errEl.style.display = 'none';
  const name = document.getElementById('iuName').value.trim();
  const email = document.getElementById('iuEmail').value.trim();
  const roleId = document.getElementById('iuRole').value;
  const autoPwd = document.getElementById('iuAutoPwd').checked;
  const pwd = document.getElementById('iuPwd').value;

  if (!name || !email || !roleId) { errEl.textContent = 'Nama, email, role wajib'; errEl.style.display='block'; return; }
  if (!autoPwd && (!pwd || pwd.length < 8)) { errEl.textContent = 'Password min 8 karakter'; errEl.style.display='block'; return; }

  const body = { full_name: name, email, role_id: roleId };
  if (!autoPwd) body.temp_password = pwd;

  try {
    const result = await Api.users.invite(body);
    closeInviteUserModal();
    if (result.temp_password) {
      // Show modal with temp password (one-time display)
      const html = `
        <div class="modal-backdrop" id="iuPwdShow" onclick="if(event.target===this)document.getElementById('iuPwdShow').remove()">
          <div class="modal-dialog" style="max-width:440px">
            <div class="modal-header">
              <h3>✓ User Dibuat</h3>
              <button class="modal-close" onclick="document.getElementById('iuPwdShow').remove()">×</button>
            </div>
            <div class="modal-body">
              <p><strong>${_escId(result.full_name)}</strong> (${_escId(result.email)}) sudah dibuat dengan role <strong>${_escId(result.role_name)}</strong>.</p>
              <div style="background:#fef3c7;border-left:4px solid #eab308;padding:12px 16px;margin:12px 0;border-radius:4px">
                <strong>⚠ Password Awal (sekali tampil):</strong>
                <div style="font-family:monospace;font-size:18px;font-weight:600;background:#fff;padding:8px;border-radius:4px;margin-top:8px;text-align:center;letter-spacing:1px">${_escId(result.temp_password)}</div>
                <small style="display:block;margin-top:8px;color:#92400e">Salin sekarang & share ke user (WhatsApp/SMS). User wajib ganti password pada login pertama. Setelah modal ini ditutup, password tidak bisa ditampilkan lagi.</small>
                <button class="btn btn-sm btn-outline" onclick="navigator.clipboard.writeText('${_escId(result.temp_password)}').then(()=>showToast('Password disalin','success'))" style="margin-top:8px">📋 Salin Password</button>
              </div>
            </div>
            <div class="modal-footer">
              <button class="btn btn-primary" onclick="document.getElementById('iuPwdShow').remove()">OK</button>
            </div>
          </div>
        </div>`;
      document.body.insertAdjacentHTML('beforeend', html);
    } else {
      showToast(`User ${result.email} berhasil ditambahkan`, 'success');
    }
    await _renderBackendUsersTable();
  } catch (e) {
    errEl.textContent = e.message; errEl.style.display = 'block';
  }
}

// ─── Edit User (full_name + role + active) ─────────────────────
async function showEditUserModal(userId) {
  const users = await Api.users.list().catch(() => []);
  const u = users.find(x => x.user_id === userId);
  if (!u) { showToast('User tidak ditemukan', 'error'); return; }
  const roles = (window.__rolesCache?.roles) || (await Api.roles.list().catch(() => []));
  const roleOpts = roles.map(r => `<option value="${r.id}" ${r.id===u.role_id?'selected':''}>${_escId(r.name)}${r.is_system?' (system)':''}</option>`).join('');

  const html = `
    <div class="modal-backdrop" id="editUserModal" onclick="if(event.target===this)closeEditUserModal()">
      <div class="modal-dialog" style="max-width:480px">
        <div class="modal-header">
          <h3>Edit Pengguna</h3>
          <button class="modal-close" onclick="closeEditUserModal()">×</button>
        </div>
        <div class="modal-body">
          <div class="form-group"><label>Email</label>
            <input class="form-control" value="${_escId(u.email)}" disabled></div>
          <div class="form-group"><label>Nama Lengkap *</label>
            <input class="form-control" id="euName" value="${_escId(u.full_name)}"></div>
          <div class="form-group"><label>Role *</label>
            <select class="form-control" id="euRole" ${u.is_owner?'disabled':''}>${roleOpts}</select>
            ${u.is_owner ? '<small style="color:#92400e">⚠ Tenant owner — role tidak bisa diubah.</small>' : ''}</div>
          <div class="form-group">
            <label><input type="checkbox" id="euActive" ${u.is_active?'checked':''}> User aktif (login enabled)</label>
          </div>
          <div id="euErr" class="form-error" style="display:none"></div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-outline" onclick="closeEditUserModal()">Batal</button>
          <button class="btn btn-primary" onclick="submitEditUser('${userId}')">Simpan</button>
        </div>
      </div>
    </div>`;
  document.body.insertAdjacentHTML('beforeend', html);
}

function closeEditUserModal() { document.getElementById('editUserModal')?.remove(); }

async function submitEditUser(userId) {
  const errEl = document.getElementById('euErr');
  errEl.style.display = 'none';
  const body = {
    full_name: document.getElementById('euName').value.trim(),
    is_active: document.getElementById('euActive').checked,
  };
  const roleSel = document.getElementById('euRole');
  if (!roleSel.disabled) body.role_id = roleSel.value;
  try {
    await Api.users.update(userId, body);
    showToast('User diupdate', 'success');
    closeEditUserModal();
    await _renderBackendUsersTable();
  } catch (e) {
    errEl.textContent = e.message; errEl.style.display = 'block';
  }
}

async function deactivateUser(userId, name) {
  if (!confirm(`Nonaktifkan user "${name}"? User tidak bisa login lagi (refresh tokens di-revoke). Membership tetap untuk audit trail.`)) return;
  try {
    await Api.users.deactivate(userId);
    showToast('User dinonaktifkan', 'success');
    await _renderBackendUsersTable();
  } catch (e) { showToast('Gagal: ' + e.message, 'error'); }
}

async function reactivateUser(userId, name) {
  if (!confirm(`Aktifkan kembali user "${name}"?`)) return;
  try {
    await Api.users.update(userId, {is_active: true});
    showToast('User diaktifkan', 'success');
    await _renderBackendUsersTable();
  } catch (e) { showToast('Gagal: ' + e.message, 'error'); }
}

// Wrappers untuk button HTML existing — route ke backend versions
window.openUserModal = function() { showInviteUserModal(); };
window.openChangePasswordModal = function() { showChangePasswordModal(); };

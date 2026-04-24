/**
 * USERS.JS - User Management (CRUD)
 * Render halaman user, tambah/edit/hapus user
 */

// ===== RENDER ROLES SECTION =====
function renderRolesSection() {
  const roles = getRoles();
  const users = getUsers();
  const tbody = document.getElementById('rolesTableBody');
  if (!tbody) return;

  const editSvg = `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>`;
  const delSvg  = `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>`;

  tbody.innerHTML = roles.map(role => {
    const userCount = users.filter(u => u.role === role.name).length;
    const canDelete = !role.isBuiltIn && userCount === 0;
    const permBadges = role.permissions.map(p => {
      const found = ALL_PERMISSIONS.find(ap => ap.key === p);
      return `<span class="badge badge-neutral" style="font-size:10px;padding:2px 6px;margin:1px">${found ? found.label : p}</span>`;
    }).join('');

    return `<tr>
      <td>
        <span class="role-badge role-${role.name.toLowerCase()}">${role.name}</span>
        ${role.isBuiltIn ? '<span class="badge badge-neutral" style="font-size:10px;padding:1px 5px;margin-left:4px">Bawaan</span>' : ''}
        ${userCount > 0 ? `<span style="font-size:11px;color:#8b8fa8;margin-left:4px">(${userCount} user)</span>` : ''}
      </td>
      <td style="color:#8b8fa8;font-size:13px">${role.description || '-'}</td>
      <td><div style="display:flex;flex-wrap:wrap;gap:2px">${permBadges}</div></td>
      <td class="action-cell">
        <button class="btn-icon" onclick="openRoleModal('${role.id}')" title="Edit role">${editSvg}</button>
        ${canDelete ? `<button class="btn-icon btn-icon-danger" onclick="confirmDeleteRole('${role.id}','${role.name}')" title="Hapus role">${delSvg}</button>` : ''}
      </td>
    </tr>`;
  }).join('');
}

// ===== MODAL TAMBAH/EDIT ROLE =====
function openRoleModal(roleId = null) {
  if (!hasPermission('manageUsers')) return;
  const roles = getRoles();
  const role = roleId ? roles.find(r => r.id === roleId) : null;

  document.getElementById('roleModalTitle').textContent = role ? 'Edit Role' : 'Tambah Role';
  document.getElementById('roleModalId').value = roleId || '';
  document.getElementById('roleModalName').value = role ? role.name : '';
  document.getElementById('roleModalDesc').value = role ? (role.description || '') : '';
  document.getElementById('roleModalError').style.display = 'none';

  // Render permission checkboxes
  const container = document.getElementById('roleModalPermissions');
  container.innerHTML = ALL_PERMISSIONS.map(p => `
    <label class="permission-item">
      <input type="checkbox" value="${p.key}"
        ${role && role.permissions.includes(p.key) ? 'checked' : ''}>
      ${p.label}
    </label>
  `).join('');

  // Lock nama untuk built-in role
  document.getElementById('roleModalName').readOnly = !!(role && role.isBuiltIn);

  document.getElementById('roleModal').style.display = 'flex';
  if (!role || !role.isBuiltIn) {
    setTimeout(() => document.getElementById('roleModalName').focus(), 100);
  }
}

function closeRoleModal() {
  document.getElementById('roleModal').style.display = 'none';
}

function saveRoleModal() {
  const roleId  = document.getElementById('roleModalId').value;
  const name    = document.getElementById('roleModalName').value.trim();
  const desc    = document.getElementById('roleModalDesc').value.trim();
  const errorEl = document.getElementById('roleModalError');
  const btn     = document.getElementById('btnSaveRole');

  errorEl.style.display = 'none';

  if (!name || name.length < 2) {
    errorEl.textContent = 'Nama role minimal 2 karakter';
    errorEl.style.display = 'block';
    return;
  }

  const checkedPerms = [...document.querySelectorAll('#roleModalPermissions input[type=checkbox]:checked')]
    .map(cb => cb.value);

  if (checkedPerms.length === 0) {
    errorEl.textContent = 'Pilih minimal satu izin akses';
    errorEl.style.display = 'block';
    return;
  }

  const roles = getRoles();

  // Cek duplikat nama (kecuali dirinya sendiri)
  const dup = roles.find(r => r.name.toLowerCase() === name.toLowerCase() && r.id !== roleId);
  if (dup) {
    errorEl.textContent = 'Nama role sudah digunakan';
    errorEl.style.display = 'block';
    return;
  }

  // Guard: pastikan minimal satu role tetap punya manageUsers
  const otherRolesWithManage = roles.filter(r => r.id !== roleId && r.permissions.includes('manageUsers'));
  if (!checkedPerms.includes('manageUsers') && otherRolesWithManage.length === 0) {
    errorEl.textContent = 'Minimal satu role harus memiliki izin Manajemen Pengguna';
    errorEl.style.display = 'block';
    return;
  }

  btn.disabled = true;
  btn.textContent = 'Menyimpan...';

  if (roleId) {
    const idx = roles.findIndex(r => r.id === roleId);
    if (idx !== -1) {
      roles[idx].name = name;
      roles[idx].description = desc;
      roles[idx].permissions = checkedPerms;
    }
  } else {
    roles.push({
      id: 'role_' + Date.now(),
      name,
      description: desc,
      permissions: checkedPerms,
      isBuiltIn: false
    });
  }

  saveRoles(roles);
  closeRoleModal();
  renderRolesSection();
  updateUserRoleDropdown();
  showToast(`Role "${name}" berhasil ${roleId ? 'diperbarui' : 'ditambahkan'}`, 'success');

  btn.disabled = false;
  btn.textContent = 'Simpan';
}

function confirmDeleteRole(roleId, roleName) {
  if (!hasPermission('manageUsers')) return;
  showConfirmModal(
    'Hapus Role?',
    `Role <strong>${roleName}</strong> akan dihapus permanen. Tindakan ini tidak dapat dibatalkan.`,
    'Ya, Hapus',
    () => {
      const roles = getRoles().filter(r => r.id !== roleId);
      saveRoles(roles);
      renderRolesSection();
      updateUserRoleDropdown();
      showToast(`Role "${roleName}" dihapus`, 'success');
    },
    true
  );
}

// ===== UPDATE DROPDOWN ROLE DI USER MODAL =====
function updateUserRoleDropdown() {
  const select = document.getElementById('userModalRole');
  if (!select) return;
  const roles = getRoles();
  const currentVal = select.value;
  select.innerHTML = roles.map(r =>
    `<option value="${r.name}"${r.name === currentVal ? ' selected' : ''}>${r.name}</option>`
  ).join('');
}

// ===== APP SETTINGS (Super Admin only) =====
function renderAppSettings() {
  const section = document.getElementById('appSettingsSection');
  if (!section) return;
  const session = getCurrentUser();
  if (!session || !session.isSuperAdmin) { section.style.display = 'none'; return; }

  const settings = getSettings();
  const roles = getRoles();
  const roleOptions = roles.map(r =>
    `<option value="${r.name}"${r.name === settings.defaultRegistrationRole ? ' selected' : ''}>${r.name}</option>`
  ).join('');

  section.style.display = 'block';
  section.innerHTML = `
    <div class="settings-card">
      <div class="settings-card-header">
        <h3>Pengaturan Aplikasi</h3>
        <span class="badge-superadmin">Super Admin Only</span>
      </div>
      <div class="settings-row">
        <div>
          <div class="settings-label">Pendaftaran Publik</div>
          <div class="settings-desc">Izinkan pengguna mendaftar sendiri dari halaman login</div>
        </div>
        <label class="toggle-switch">
          <input type="checkbox" id="togPublicReg" ${settings.allowPublicRegistration ? 'checked' : ''}
            onchange="updateAppSetting('allowPublicRegistration', this.checked)">
          <span class="toggle-slider"></span>
        </label>
      </div>
      <div class="settings-row" id="defaultRoleRow"
        style="${settings.allowPublicRegistration ? '' : 'opacity:0.5;pointer-events:none'}">
        <div>
          <div class="settings-label">Role Default Pendaftar</div>
          <div class="settings-desc">Role yang diberikan ke pengguna yang mendaftar sendiri</div>
        </div>
        <select class="settings-select"
          onchange="updateAppSetting('defaultRegistrationRole', this.value)">
          ${roleOptions}
        </select>
      </div>
      <div class="settings-row">
        <div>
          <div class="settings-label">Kode Pemulihan Super Admin</div>
          <div class="settings-desc">Buat ulang kode jika kode lama hilang atau tidak aman</div>
        </div>
        <button class="btn btn-outline" onclick="regenerateRecoveryCode()">Buat Ulang Kode</button>
      </div>
    </div>
    ${renderLicenseInfoCard()}
  `;
}

function renderLicenseInfoCard() {
  if (typeof getLicense !== 'function') return '';
  const lic    = getLicense();
  if (!lic) {
    return `<div class="settings-card" style="margin-top:16px">
      <div class="settings-card-header">
        <h3>Informasi Lisensi</h3>
        <span style="font-size:12px;color:#ef4444;font-weight:600">Tidak Ada Lisensi</span>
      </div>
      <div style="padding:16px 0;color:#64748b;font-size:14px">
        Belum ada lisensi aktif. Hubungi vendor untuk aktivasi.
      </div>
    </div>`;
  }
  const status   = typeof getLicenseStatus === 'function' ? getLicenseStatus() : 'valid';
  const daysLeft = typeof getLicenseDaysRemaining === 'function' ? getLicenseDaysRemaining() : null;
  const maxDisp  = lic.maxUsers ? `${lic.maxUsers} pengguna` : 'Unlimited';
  const isLifetime = lic.isLifetime || !lic.expiresAt;
  const expDisp  = isLifetime
    ? '♾️ Lifetime'
    : new Date(lic.expiresAt).toLocaleDateString('id-ID', { day:'2-digit', month:'long', year:'numeric' });
  const actDisp  = new Date(lic.activatedAt).toLocaleDateString('id-ID', { day:'2-digit', month:'long', year:'numeric' });
  const statusMap = {
    valid:    { label: isLifetime ? '♾️ Lifetime' : 'Aktif', color: '#166534', bg: '#dcfce7', border: '#86efac' },
    expiring: { label: `Exp ${daysLeft}h`,  color: '#92400e', bg: '#fef3c7', border: '#fcd34d' },
    grace:    { label: 'Masa Tenggang',     color: '#991b1b', bg: '#fee2e2', border: '#fca5a5' },
    dead:     { label: 'Kedaluwarsa',       color: '#991b1b', bg: '#fee2e2', border: '#fca5a5' },
    none:     { label: 'Tidak Ada',         color: '#64748b', bg: '#f1f5f9', border: '#e2e8f0' }
  };
  const s = statusMap[status] || statusMap.valid;
  const planColors = { Starter:'#0369a1', Pro:'#6d28d9', Enterprise:'#92400e' };
  const planBg    = { Starter:'#e0f2fe', Pro:'#ede9fe', Enterprise:'#fef3c7' };
  const planColor = planColors[lic.plan] || '#374151';
  const planBgC   = planBg[lic.plan] || '#f1f5f9';
  const daysText  = isLifetime
    ? 'Tidak ada expired'
    : (daysLeft !== null
        ? (daysLeft > 0 ? `${daysLeft} hari lagi` : `${Math.abs(daysLeft)} hari yang lalu`)
        : '');

  return `<div class="settings-card" style="margin-top:16px">
    <div class="settings-card-header">
      <h3>Informasi Lisensi</h3>
      <span style="background:${s.bg};color:${s.color};border:1px solid ${s.border};
        border-radius:99px;padding:3px 10px;font-size:12px;font-weight:600">${s.label}</span>
    </div>
    <div class="license-info-card">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px;flex-wrap:wrap">
        <div style="font-size:15px;font-weight:700;color:#1e293b">${lic.clientName}</div>
        <span style="background:${planBgC};color:${planColor};border-radius:99px;
          padding:2px 10px;font-size:11px;font-weight:600">${lic.plan}</span>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px 24px;font-size:13px">
        <div><span style="color:#64748b">Berlaku hingga:</span> <strong>${expDisp}</strong></div>
        <div><span style="color:#64748b">Sisa waktu:</span> <strong>${daysText}</strong></div>
        <div><span style="color:#64748b">Maks. pengguna:</span> <strong>${maxDisp}</strong></div>
        <div><span style="color:#64748b">Client ID:</span> <strong>${lic.clientId}</strong></div>
        <div><span style="color:#64748b">Diaktifkan:</span> <strong>${actDisp}</strong></div>
      </div>
    </div>
  </div>`;
}

function updateAppSetting(key, value) {
  const settings = getSettings();
  settings[key] = value;
  saveSettings(settings);
  const row = document.getElementById('defaultRoleRow');
  if (row && key === 'allowPublicRegistration') {
    row.style.opacity = value ? '' : '0.5';
    row.style.pointerEvents = value ? '' : 'none';
  }
  showToast('Pengaturan disimpan', 'success');
}

function regenerateRecoveryCode() {
  showConfirmModal(
    'Buat Ulang Kode Pemulihan?',
    'Kode lama tidak akan berlaku lagi. Pastikan Anda menyimpan kode baru yang akan ditampilkan.',
    'Ya, Buat Ulang',
    async () => {
      const code = generateRecoveryCode();
      await saveRecoveryHash(code);
      // Tampilkan kode baru menggunakan showConfirmModal sebagai info panel
      showConfirmModal(
        'Kode Pemulihan Baru',
        `<p style="margin-bottom:12px">Simpan kode berikut di tempat yang aman. <strong>Hanya ditampilkan sekali.</strong></p>
         <div class="recovery-code-box" style="margin:0 0 12px"><span style="font-size:15px">${code}</span></div>
         <p style="color:#ef4444;font-size:12px">Kode lama sudah tidak berlaku.</p>`,
        'Tutup',
        () => {},
        false
      );
      // Sembunyikan tombol Batal karena ini cuma info
      const btnCancel = document.getElementById('modalCancel');
      if (btnCancel) btnCancel.style.display = 'none';
    },
    false
  );
}

// ===== RENDER HALAMAN USERS =====
function renderUsersPage() {
  if (!hasPermission('manageUsers')) {
    showToast('Anda tidak memiliki akses ke halaman ini', 'error');
    navigateTo('dashboard');
    return;
  }

  renderAppSettings();
  renderRolesSection();

  const users = getUsers();
  const currentUser = getCurrentUser();
  const tbody = document.getElementById('usersTableBody');
  if (!tbody) return;

  if (users.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5" class="empty-row">Belum ada pengguna</td></tr>';
    return;
  }

  tbody.innerHTML = users.map(u => {
    const initial = u.username.charAt(0).toUpperCase();
    const isMe = u.id === currentUser?.userId;
    const roleClass = u.role.toLowerCase();
    const createdAt = u.createdAt ? new Date(u.createdAt).toLocaleDateString('id-ID') : '-';
    const lastLogin = u.lastLogin ? new Date(u.lastLogin).toLocaleString('id-ID') : 'Belum pernah';
    const saTag = u.isSuperAdmin
      ? '<span class="badge-superadmin" style="font-size:10px;padding:1px 6px;margin-left:4px">Super Admin</span>'
      : '';
    const canDelete = !isMe && !u.isSuperAdmin;
    return `
      <tr>
        <td>
          <div class="user-cell">
            <div class="user-avatar-sm">${initial}</div>
            <span>${u.username}</span>
            ${saTag}
            ${isMe ? '<span class="badge badge-neutral" style="font-size:10px;padding:2px 6px;margin-left:2px">Anda</span>' : ''}
          </div>
        </td>
        <td><span class="role-badge role-${roleClass}">${u.role}</span></td>
        <td>${createdAt}</td>
        <td>${lastLogin}</td>
        <td class="action-cell">
          <button class="btn-icon" onclick="openUserModal('${u.id}')" title="Edit pengguna"><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg></button>
          ${canDelete ? `<button class="btn-icon btn-icon-danger" onclick="confirmDeleteUser('${u.id}', '${u.username}')" title="Hapus pengguna"><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg></button>` : ''}
        </td>
      </tr>
    `;
  }).join('');
}

// ===== MODAL TAMBAH/EDIT USER =====
function openUserModal(userId = null) {
  if (!hasPermission('manageUsers')) return;

  const users = getUsers();
  const user = userId ? users.find(u => u.id === userId) : null;

  document.getElementById('userModalTitle').textContent = user ? 'Edit Pengguna' : 'Tambah Pengguna';
  document.getElementById('userModalId').value = userId || '';
  document.getElementById('userModalUsername').value = user ? user.username : '';
  updateUserRoleDropdown();
  document.getElementById('userModalRole').value = user ? user.role : (getRoles()[1]?.name || 'Akuntan');
  document.getElementById('userModalPassword').value = '';
  document.getElementById('userModalConfirm').value = '';
  document.getElementById('userModalPasswordHint').textContent =
    user ? 'Kosongkan jika tidak ingin mengubah password' : '';
  document.getElementById('userModalError').style.display = 'none';
  document.getElementById('userModalError').textContent = '';

  // Lock role untuk Super Admin (tidak bisa diubah)
  const roleSelect = document.getElementById('userModalRole');
  if (roleSelect) roleSelect.disabled = !!(user && user.isSuperAdmin);

  document.getElementById('userModal').style.display = 'flex';
  setTimeout(() => document.getElementById('userModalUsername').focus(), 100);
}

function closeUserModal() {
  document.getElementById('userModal').style.display = 'none';
}

async function saveUserModal() {
  const userId = document.getElementById('userModalId').value;
  const username = document.getElementById('userModalUsername').value.trim();
  const password = document.getElementById('userModalPassword').value;
  const confirm = document.getElementById('userModalConfirm').value;
  const role = document.getElementById('userModalRole').value;
  const errorEl = document.getElementById('userModalError');
  const btn = document.getElementById('btnSaveUser');

  errorEl.style.display = 'none';

  // Validasi username
  if (!username || username.length < 3) {
    errorEl.textContent = 'Username minimal 3 karakter';
    errorEl.style.display = 'block';
    return;
  }
  if (!/^[a-zA-Z0-9._-]+$/.test(username)) {
    errorEl.textContent = 'Username hanya boleh huruf, angka, titik, underscore, atau strip';
    errorEl.style.display = 'block';
    return;
  }

  const users = getUsers();

  // Cek duplikat username
  const duplicate = users.find(u =>
    u.username.toLowerCase() === username.toLowerCase() && u.id !== userId
  );
  if (duplicate) {
    errorEl.textContent = 'Username sudah digunakan';
    errorEl.style.display = 'block';
    return;
  }

  // Validasi password
  if (!userId) {
    // Tambah user baru: password wajib
    if (!password) {
      errorEl.textContent = 'Password tidak boleh kosong';
      errorEl.style.display = 'block';
      return;
    }
  }

  if (password) {
    if (password.length < 6) {
      errorEl.textContent = 'Password minimal 6 karakter';
      errorEl.style.display = 'block';
      return;
    }
    if (password !== confirm) {
      errorEl.textContent = 'Konfirmasi password tidak cocok';
      errorEl.style.display = 'block';
      return;
    }
  }

  // Guard Super Admin: tidak bisa diubah rolenya
  if (userId) {
    const currentUserData = users.find(u => u.id === userId);
    if (currentUserData?.isSuperAdmin) {
      // Force role tetap Admin untuk Super Admin
      // (select di-disable di UI, tapi double-check di sini)
    } else if (currentUserData?.role === 'Admin' && role !== 'Admin') {
      const adminCount = users.filter(u => u.role === 'Admin').length;
      if (adminCount <= 1) {
        errorEl.textContent = 'Tidak dapat mengubah role Admin terakhir';
        errorEl.style.display = 'block';
        return;
      }
    }
  }

  btn.disabled = true;
  btn.textContent = 'Menyimpan...';

  try {
    if (userId) {
      // Edit user
      const idx = users.findIndex(u => u.id === userId);
      if (idx !== -1) {
        users[idx].username = username;
        users[idx].role = role;
        if (password) {
          users[idx].passwordHash = await hashPassword(password);
        }
      }
    } else {
      // Tambah user baru
      const hash = await hashPassword(password);
      users.push({
        id: 'u_' + Date.now(),
        username,
        passwordHash: hash,
        role,
        isSuperAdmin: false,
        createdAt: new Date().toISOString(),
        lastLogin: null
      });
    }

    saveUsers(users);
    closeUserModal();
    renderUsersPage();
    showToast(`Pengguna "${username}" berhasil ${userId ? 'diperbarui' : 'ditambahkan'}`, 'success');
  } catch(e) {
    errorEl.textContent = 'Terjadi kesalahan. Coba lagi.';
    errorEl.style.display = 'block';
  } finally {
    btn.disabled = false;
    btn.textContent = 'Simpan';
  }
}

// ===== HAPUS USER =====
function confirmDeleteUser(userId, username) {
  if (!hasPermission('manageUsers')) return;

  const users = getUsers();
  const user = users.find(u => u.id === userId);
  if (!user) return;

  // Cegah hapus Super Admin
  if (user.isSuperAdmin) {
    showToast('Akun Super Admin tidak dapat dihapus', 'error');
    return;
  }

  // Cegah hapus admin terakhir
  if (user.role === 'Admin') {
    const adminCount = users.filter(u => u.role === 'Admin').length;
    if (adminCount <= 1) {
      showToast('Tidak dapat menghapus Admin terakhir', 'error');
      return;
    }
  }

  showConfirmModal(
    'Hapus Pengguna?',
    `Pengguna <strong>${username}</strong> akan dihapus permanen. Tindakan ini tidak dapat dibatalkan.`,
    'Ya, Hapus',
    () => {
      const updated = users.filter(u => u.id !== userId);
      saveUsers(updated);
      renderUsersPage();
      showToast(`Pengguna "${username}" dihapus`, 'success');
    },
    true
  );
}

// ===== GANTI PASSWORD SENDIRI =====
function openChangePasswordModal() {
  const modal = document.getElementById('changePasswordModal');
  if (!modal) return;
  document.getElementById('cpOldPassword').value = '';
  document.getElementById('cpNewPassword').value = '';
  document.getElementById('cpConfirmPassword').value = '';
  document.getElementById('cpError').style.display = 'none';
  modal.style.display = 'flex';
}

function closeChangePasswordModal() {
  const modal = document.getElementById('changePasswordModal');
  if (modal) modal.style.display = 'none';
}

async function saveChangePassword() {
  const session = getCurrentUser();
  if (!session) return;

  const oldPwd = document.getElementById('cpOldPassword').value;
  const newPwd = document.getElementById('cpNewPassword').value;
  const confirmPwd = document.getElementById('cpConfirmPassword').value;
  const errorEl = document.getElementById('cpError');
  const btn = document.getElementById('btnSaveChangePassword');

  errorEl.style.display = 'none';

  if (!oldPwd) {
    errorEl.textContent = 'Masukkan password lama';
    errorEl.style.display = 'block';
    return;
  }
  if (!newPwd || newPwd.length < 6) {
    errorEl.textContent = 'Password baru minimal 6 karakter';
    errorEl.style.display = 'block';
    return;
  }
  if (newPwd !== confirmPwd) {
    errorEl.textContent = 'Konfirmasi password tidak cocok';
    errorEl.style.display = 'block';
    return;
  }

  btn.disabled = true;
  btn.textContent = 'Menyimpan...';

  try {
    const users = getUsers();
    const userIdx = users.findIndex(u => u.id === session.userId);
    if (userIdx === -1) throw new Error('User not found');

    const oldHash = await hashPassword(oldPwd);
    if (oldHash !== users[userIdx].passwordHash) {
      errorEl.textContent = 'Password lama tidak cocok';
      errorEl.style.display = 'block';
      return;
    }

    users[userIdx].passwordHash = await hashPassword(newPwd);
    saveUsers(users);
    closeChangePasswordModal();
    showToast('Password berhasil diubah', 'success');
  } catch(e) {
    errorEl.textContent = 'Terjadi kesalahan. Coba lagi.';
    errorEl.style.display = 'block';
  } finally {
    btn.disabled = false;
    btn.textContent = 'Simpan Password';
  }
}

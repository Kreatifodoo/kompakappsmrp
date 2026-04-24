/**
 * AUTH.JS - Authentication & Session Management
 * Sistem login, session, password hashing, dan permission check
 */

const AUTH_STORAGE_KEY = 'finreport_users_v1';
const SESSION_KEY      = 'finreport_session_v1';
const SESSION_TIMEOUT  = 30 * 60 * 1000; // 30 menit

// ===== PASSWORD HASHING (SHA-256 via Web Crypto API) =====
async function hashPassword(password) {
  const encoder = new TextEncoder();
  const data = encoder.encode(password + '_finreport_gki_salt_2024');
  const hashBuffer = await crypto.subtle.digest('SHA-256', data);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
}

// ===== USER STORAGE =====
function getUsers() {
  try {
    const raw = localStorage.getItem(AUTH_STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch(e) {
    return [];
  }
}

function saveUsers(users) {
  localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(users));
  if (typeof DataStore !== 'undefined') DataStore.push(AUTH_STORAGE_KEY);
}

// ===== SESSION MANAGEMENT =====
function getSession() {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    const session = JSON.parse(raw);
    if (Date.now() > session.expiresAt) {
      sessionStorage.removeItem(SESSION_KEY);
      return null;
    }
    return session;
  } catch(e) {
    return null;
  }
}

function setSession(user) {
  const session = {
    userId: user.id,
    username: user.username,
    role: user.role,
    isSuperAdmin: user.isSuperAdmin || false,
    loginAt: Date.now(),
    expiresAt: Date.now() + SESSION_TIMEOUT
  };
  sessionStorage.setItem(SESSION_KEY, JSON.stringify(session));
  return session;
}

function clearSession() {
  sessionStorage.removeItem(SESSION_KEY);
}

function extendSession() {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    if (!raw) return;
    const session = JSON.parse(raw);
    session.expiresAt = Date.now() + SESSION_TIMEOUT;
    sessionStorage.setItem(SESSION_KEY, JSON.stringify(session));
  } catch(e) {}
}

function getCurrentUser() {
  return getSession();
}

// ===== SETTINGS & SUPER ADMIN STORAGE =====
const SETTINGS_KEY    = 'finreport_settings_v1';
const SA_RECOVERY_KEY = 'finreport_sa_recovery_v1';

function getSettings() {
  try {
    const raw = localStorage.getItem(SETTINGS_KEY);
    return raw ? JSON.parse(raw) : { allowPublicRegistration: false, defaultRegistrationRole: 'Viewer' };
  } catch(e) { return { allowPublicRegistration: false, defaultRegistrationRole: 'Viewer' }; }
}

function saveSettings(s) {
  localStorage.setItem(SETTINGS_KEY, JSON.stringify(s));
  if (typeof DataStore !== 'undefined') DataStore.push(SETTINGS_KEY);
}

function hasSuperAdmin() {
  return getUsers().some(u => u.isSuperAdmin);
}

// ===== RECOVERY CODE =====
function generateRecoveryCode() {
  const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
  const segments = [];
  for (let s = 0; s < 4; s++) {
    let seg = '';
    for (let i = 0; i < 6; i++) seg += chars[Math.floor(Math.random() * chars.length)];
    segments.push(seg);
  }
  return segments.join('-'); // XXXXXX-XXXXXX-XXXXXX-XXXXXX
}

async function saveRecoveryHash(plainCode) {
  const hash = await hashPassword(plainCode.replace(/-/g, '').toUpperCase());
  localStorage.setItem(SA_RECOVERY_KEY, hash);
  if (typeof DataStore !== 'undefined') DataStore.push(SA_RECOVERY_KEY);
}

async function verifyRecoveryCode(input) {
  const stored = localStorage.getItem(SA_RECOVERY_KEY);
  if (!stored) return false;
  const hash = await hashPassword(input.replace(/-/g, '').toUpperCase());
  return hash === stored;
}

function copyRecoveryCode() {
  const code = document.getElementById('recoveryCodeDisplay')?.textContent || '';
  if (!code) return;
  navigator.clipboard.writeText(code).then(() => {
    showToast('Kode berhasil disalin', 'success');
  }).catch(() => {
    showToast('Salin kode secara manual dari kotak di atas', 'warning');
  });
}

// ===== PERMISSION SYSTEM =====
const ROLES_KEY = 'finreport_roles_v1';

const ALL_PERMISSIONS = [
  { key: 'upload',      label: 'Upload Laporan' },
  { key: 'editCOA',     label: 'Edit Chart of Accounts' },
  { key: 'editJournal', label: 'Edit Jurnal Entri' },
  { key: 'viewReport',  label: 'Lihat Laporan' },
  { key: 'export',      label: 'Export Data' },
  { key: 'manageUsers', label: 'Manajemen Pengguna' },
  { key: 'resetData',   label: 'Reset Data' },
  { key: 'lock',        label: 'Kunci Aplikasi' }
];

const DEFAULT_ROLES = [
  { id: 'role_admin',   name: 'Admin',   description: 'Akses penuh ke semua fitur',
    permissions: ['upload','editCOA','editJournal','viewReport','export','manageUsers','resetData','lock'],
    isBuiltIn: true },
  { id: 'role_akuntan', name: 'Akuntan', description: 'Upload, edit, lihat dan export laporan',
    permissions: ['upload','editCOA','editJournal','viewReport','export'],
    isBuiltIn: false },
  { id: 'role_viewer',  name: 'Viewer',  description: 'Hanya lihat dan export laporan',
    permissions: ['viewReport','export'],
    isBuiltIn: false }
];

function getRoles() {
  try {
    const raw = localStorage.getItem(ROLES_KEY);
    return raw ? JSON.parse(raw) : DEFAULT_ROLES;
  } catch(e) { return DEFAULT_ROLES; }
}

function saveRoles(roles) {
  localStorage.setItem(ROLES_KEY, JSON.stringify(roles));
  if (typeof DataStore !== 'undefined') DataStore.push(ROLES_KEY);
}

function seedDefaultRoles() {
  if (!localStorage.getItem(ROLES_KEY)) saveRoles(DEFAULT_ROLES);
}

function hasPermission(action) {
  const session = getCurrentUser();
  if (!session) return false;
  if (session.isSuperAdmin) return true; // Super Admin punya semua akses
  const roles = getRoles();
  const roleObj = roles.find(r => r.name === session.role);
  if (!roleObj) return false;
  return roleObj.permissions.includes(action);
}

function requirePermission(action) {
  if (!hasPermission(action)) {
    showToast('Anda tidak memiliki akses untuk tindakan ini', 'error');
    return false;
  }
  return true;
}

// ===== LOGIN / LOGOUT =====
async function login(username, password) {
  const users = getUsers();
  const user = users.find(u => u.username.toLowerCase() === username.toLowerCase());
  if (!user) return { success: false, error: 'Username tidak ditemukan' };

  const hash = await hashPassword(password);
  if (hash !== user.passwordHash) return { success: false, error: 'Password salah' };

  // Update last login timestamp
  user.lastLogin = new Date().toISOString();
  saveUsers(users);

  setSession(user);
  return { success: true };
}

function logout() {
  clearSession();
  if (idleTimer) clearTimeout(idleTimer);
  showLoginScreen();
}

// ===== FIRST RUN SETUP =====
function isFirstRun() {
  if (getUsers().length === 0) return true;
  // Setiap ZIP punya _DIST_BUILD_ID unik (timestamp+random).
  // Jika marker tidak cocok → distribusi baru, harus fresh install.
  const _bid = window._DIST_BUILD_ID || window._EXPECTED_LICENSE_KEY || '';
  if (typeof _bid === 'string' && _bid) {
    const _marker = localStorage.getItem('finreport_install_marker_v1');
    if (_marker !== _bid) return true;
  }
  return false;
}

async function createDefaultAdmin(username, password) {
  const hash = await hashPassword(password);
  const user = {
    id: 'u_' + Date.now(),
    username: username.trim(),
    passwordHash: hash,
    role: 'Admin',
    isSuperAdmin: true,
    createdAt: new Date().toISOString(),
    lastLogin: null
  };
  saveUsers([user]);
  return user;
}

// ===== FRESH INSTALL DATA PURGE =====
// Hapus semua data aplikasi dari localStorage agar setiap paket ZIP baru
// benar-benar bersih tanpa data transaksi, user, atau konfigurasi lama.
const _ALL_APP_KEYS = [
  'finreport_gki_v1',       // Data transaksi & laporan keuangan
  'finreport_users_v1',     // Akun pengguna
  'finreport_settings_v1',  // Pengaturan aplikasi
  'finreport_sa_recovery_v1', // Kode pemulihan Super Admin
  'finreport_roles_v1',     // Role & permission
  'finreport_license_v1',   // Data lisensi
  'finreport_install_marker_v1', // Marker instalasi
  'pos_data_v1',            // Data Point of Sale
  'purchase_data_v1',       // Data Purchase (vendor, bill, payment)
  'customer_data_v1',       // Data Customer (master, invoice, penerimaan)
  'manual_journals_v1',     // Manual journal entries
  'manual_journals_counter', // Manual journal ID counter
];

function _purgeAllAppData() {
  _ALL_APP_KEYS.forEach(k => localStorage.removeItem(k));
  sessionStorage.removeItem('finreport_session_v1');
  // Sync deletions to server files
  if (typeof DataStore !== 'undefined') DataStore.pushAll();
}

// ===== PANEL SWITCHER (Login Overlay) =====
function showLoginPanel(id) {
  ['licensePanel','setupPanel','recoveryCodePanel','loginPanel','registerPanel','saRecoveryPanel']
    .forEach(p => {
      const el = document.getElementById(p);
      if (el) el.style.display = 'none';
    });
  const target = document.getElementById(id);
  if (target) target.style.display = 'block';
}

// ===== SHOW / HIDE LOGIN SCREEN =====
function showLoginScreen() {
  document.getElementById('loginOverlay').style.display = 'flex';
  document.getElementById('sidebar').style.display = 'none';
  document.querySelector('.main-wrapper').style.display = 'none';

  // Clear form
  const uInput = document.getElementById('loginUsername');
  const pInput = document.getElementById('loginPassword');
  if (uInput) uInput.value = '';
  if (pInput) pInput.value = '';
  document.getElementById('loginError').textContent = '';
  document.getElementById('loginError').style.display = 'none';

  // ===== CEK LISENSI =====
  let licStatus = (typeof getLicenseStatus === 'function') ? getLicenseStatus() : 'valid';

  // Setiap ZIP punya _DIST_BUILD_ID unik. Jika marker tidak cocok,
  // ini distribusi baru → hapus semua data lama agar benar-benar bersih.
  const _bid = window._DIST_BUILD_ID || window._EXPECTED_LICENSE_KEY || '';
  if (typeof _bid === 'string' && _bid) {
    const _marker = localStorage.getItem('finreport_install_marker_v1');
    if (_marker !== _bid) {
      _purgeAllAppData();
      licStatus = 'none';
    }
  }

  if (licStatus === 'none' || licStatus === 'dead') {
    showLoginPanel('licensePanel');
    // Tombol "Sudah Aktivasi? Login" hanya muncul jika pernah ada lisensi (dead),
    // bukan pada instalasi baru (none) — agar user tidak melewati flow aktivasi.
    const btnSkip = document.getElementById('btnSkipToLogin');
    if (btnSkip) btnSkip.style.display = (licStatus === 'dead') ? '' : 'none';
    if (licStatus === 'dead') {
      const errEl = document.getElementById('licError');
      if (errEl) {
        errEl.textContent = 'Lisensi kedaluwarsa dan melewati masa tenggang. Harap masukkan kunci lisensi baru.';
        errEl.style.display = 'block';
      }
    }
    return;
  }
  // ===== END CEK LISENSI =====

  if (isFirstRun()) {
    showLoginPanel('setupPanel');
  } else {
    showLoginPanel('loginPanel');
    // Tampilkan tombol register jika public registration aktif
    const settings = getSettings();
    const btnReg = document.getElementById('btnRegister');
    if (btnReg) btnReg.style.display = settings.allowPublicRegistration ? '' : 'none';
    // Link SA recovery — tampil jika ada Super Admin
    const saLink = document.getElementById('linkSARecovery');
    if (saLink) saLink.style.display = hasSuperAdmin() ? '' : 'none';
  }
}

function hideLoginScreen() {
  document.getElementById('loginOverlay').style.display = 'none';
  document.getElementById('sidebar').style.display = 'flex';
  document.querySelector('.main-wrapper').style.display = 'block';
}

// ===== APPLY USER PERMISSIONS TO UI =====
function applyUserPermissions() {
  const session = getCurrentUser();
  if (!session) return;

  // Upload nav item
  const uploadNav = document.querySelector('[data-page="upload"]');
  if (uploadNav) uploadNav.style.display = hasPermission('upload') ? 'flex' : 'none';

  // Reset & Lock buttons
  const btnReset = document.getElementById('btnHardReset');
  const btnLock = document.getElementById('btnLock');
  if (btnReset) btnReset.style.display = hasPermission('resetData') ? '' : 'none';
  if (btnLock) btnLock.style.display = hasPermission('lock') ? '' : 'none';

  // Users nav (admin only)
  const usersNav = document.querySelector('[data-page="users"]');
  if (usersNav) usersNav.style.display = hasPermission('manageUsers') ? 'flex' : 'none';

  // Update user info di sidebar
  const userInfoEl = document.getElementById('currentUserInfo');
  if (userInfoEl) {
    const initial = session.username.charAt(0).toUpperCase();
    const roleLabel = session.isSuperAdmin
      ? `${session.role} <span class="badge-superadmin" style="font-size:9px;padding:1px 5px;vertical-align:middle">SA</span>`
      : session.role;
    userInfoEl.innerHTML = `
      <div class="sidebar-user-row">
        <div class="user-avatar-sidebar">${initial}</div>
        <div class="user-details-sidebar">
          <span class="user-name-sidebar">${session.username}</span>
          <span class="user-role-sidebar">${roleLabel}</span>
        </div>
        <button class="btn-logout-sidebar" onclick="logout()" title="Logout"><svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg></button>
      </div>
    `;
  }
}

// ===== AUTO LOGOUT ON IDLE =====
let idleTimer = null;

function resetIdleTimer() {
  if (idleTimer) clearTimeout(idleTimer);
  idleTimer = setTimeout(() => {
    const session = getSession();
    if (session) {
      showToast('Sesi Anda berakhir karena tidak aktif. Silakan login kembali.', 'warning');
      logout();
    }
  }, SESSION_TIMEOUT);
}

function initIdleDetection() {
  ['click', 'mousemove', 'keydown', 'scroll', 'touchstart'].forEach(event => {
    document.addEventListener(event, () => {
      extendSession();
      resetIdleTimer();
    }, { passive: true });
  });
  resetIdleTimer();
}

// ===== LOGIN FORM HANDLER =====
async function handleLoginSubmit() {
  const username = document.getElementById('loginUsername').value.trim();
  const password = document.getElementById('loginPassword').value;
  const errorEl = document.getElementById('loginError');
  const btnLogin = document.getElementById('btnLogin');

  errorEl.style.display = 'none';

  // Guard: pastikan lisensi valid dan setup sudah selesai sebelum login
  let _loginLicStatus = (typeof getLicenseStatus === 'function') ? getLicenseStatus() : 'valid';
  const _bidLogin = window._DIST_BUILD_ID || window._EXPECTED_LICENSE_KEY || '';
  if (typeof _bidLogin === 'string' && _bidLogin) {
    const _marker = localStorage.getItem('finreport_install_marker_v1');
    if (_marker !== _bidLogin) {
      _loginLicStatus = 'none'; // Setup paket ini belum selesai
    }
  }
  if (_loginLicStatus === 'none' || _loginLicStatus === 'dead') {
    showLoginScreen();
    return;
  }

  if (!username || !password) {
    errorEl.textContent = 'Masukkan username dan password';
    errorEl.style.display = 'block';
    return;
  }

  btnLogin.disabled = true;
  btnLogin.textContent = 'Masuk...';

  try {
    const result = await login(username, password);
    if (result.success) {
      hideLoginScreen();
      applyUserPermissions();
      initIdleDetection();
      if (typeof showLicenseExpiryBanner === 'function') showLicenseExpiryBanner();
      showToast(`Selamat datang, ${getCurrentUser().username}!`, 'success');
    } else {
      errorEl.textContent = result.error;
      errorEl.style.display = 'block';
      document.getElementById('loginPassword').value = '';
    }
  } catch(e) {
    errorEl.textContent = 'Terjadi kesalahan. Coba lagi.';
    errorEl.style.display = 'block';
  } finally {
    btnLogin.disabled = false;
    btnLogin.textContent = 'Masuk';
  }
}

// ===== FIRST-TIME SETUP HANDLER =====
async function handleSetupSubmit() {
  const username = document.getElementById('setupUsername').value.trim();
  const password = document.getElementById('setupPassword').value;
  const confirm  = document.getElementById('setupConfirm').value;
  const errorEl  = document.getElementById('setupError');
  const btn      = document.getElementById('btnSetup');

  errorEl.style.display = 'none';

  if (!username || username.length < 3) {
    errorEl.textContent = 'Username minimal 3 karakter';
    errorEl.style.display = 'block';
    return;
  }
  if (!password || password.length < 6) {
    errorEl.textContent = 'Password minimal 6 karakter';
    errorEl.style.display = 'block';
    return;
  }
  if (password !== confirm) {
    errorEl.textContent = 'Konfirmasi password tidak cocok';
    errorEl.style.display = 'block';
    return;
  }

  btn.disabled = true;
  btn.textContent = 'Membuat akun...';

  try {
    const adminUser = await createDefaultAdmin(username, password);

    // Generate & simpan recovery code, lalu tampilkan panel
    const code = generateRecoveryCode();
    await saveRecoveryHash(code);

    document.getElementById('recoveryCodeDisplay').textContent = code;
    const ackCheck = document.getElementById('rcAckCheck');
    const btnRC = document.getElementById('btnContinueRC');
    if (ackCheck) ackCheck.checked = false;
    if (btnRC) btnRC.disabled = true;
    // Tandai setup selesai menggunakan _DIST_BUILD_ID (unik per generate).
    // Ini memastikan distribusi baru selalu mulai bersih walaupun license key sama.
    const _bidSetup = window._DIST_BUILD_ID || window._EXPECTED_LICENSE_KEY || '';
    if (typeof _bidSetup === 'string' && _bidSetup) {
      localStorage.setItem('finreport_install_marker_v1', _bidSetup);
      if (typeof DataStore !== 'undefined') DataStore.push('finreport_install_marker_v1');
    }
    showLoginPanel('recoveryCodePanel');
  } catch(e) {
    errorEl.textContent = 'Gagal membuat akun. Coba lagi.';
    errorEl.style.display = 'block';
    btn.disabled = false;
    btn.textContent = 'Buat Akun & Mulai';
  }
}

// ===== RECOVERY CODE PANEL =====
function continueAfterRecoveryCode() {
  // User must login explicitly — do not auto-login after setup
  clearSession();
  // Redirect to login panel (isFirstRun() is now false, users exist)
  showLoginPanel('loginPanel');
  // Show SA recovery link since a super admin now exists
  const saLink = document.getElementById('linkSARecovery');
  if (saLink) saLink.style.display = '';
  // Respect public registration setting for register button
  const settings = getSettings();
  const btnReg = document.getElementById('btnRegister');
  if (btnReg) btnReg.style.display = settings.allowPublicRegistration ? '' : 'none';
  // Pre-fill username from setup form for convenience
  const setupUsername = document.getElementById('setupUsername')?.value?.trim();
  const loginUsernameInput = document.getElementById('loginUsername');
  if (setupUsername && loginUsernameInput) loginUsernameInput.value = setupUsername;
  showToast('Akun Super Admin berhasil dibuat. Silakan login untuk melanjutkan.', 'success');
}

// ===== PUBLIC REGISTRATION =====
async function handlePublicRegister() {
  const username = document.getElementById('regUsername').value.trim();
  const password = document.getElementById('regPassword').value;
  const confirm  = document.getElementById('regConfirm').value;
  const errorEl  = document.getElementById('regError');
  const btn      = document.getElementById('btnRegister2');

  errorEl.style.display = 'none';

  if (!username || username.length < 3) {
    errorEl.textContent = 'Username minimal 3 karakter'; errorEl.style.display = 'block'; return;
  }
  if (!/^[a-zA-Z0-9._-]+$/.test(username)) {
    errorEl.textContent = 'Username hanya boleh huruf, angka, . _ -'; errorEl.style.display = 'block'; return;
  }
  if (!password || password.length < 6) {
    errorEl.textContent = 'Password minimal 6 karakter'; errorEl.style.display = 'block'; return;
  }
  if (password !== confirm) {
    errorEl.textContent = 'Konfirmasi password tidak cocok'; errorEl.style.display = 'block'; return;
  }

  const users = getUsers();
  if (users.find(u => u.username.toLowerCase() === username.toLowerCase())) {
    errorEl.textContent = 'Username sudah digunakan'; errorEl.style.display = 'block'; return;
  }

  btn.disabled = true;
  btn.textContent = 'Mendaftar...';
  try {
    const settings = getSettings();
    const hash = await hashPassword(password);
    users.push({
      id: 'u_' + Date.now(),
      username,
      passwordHash: hash,
      role: settings.defaultRegistrationRole || 'Viewer',
      isSuperAdmin: false,
      createdAt: new Date().toISOString(),
      lastLogin: null
    });
    saveUsers(users);
    // Kembali ke login, isi username
    showLoginPanel('loginPanel');
    const uInput = document.getElementById('loginUsername');
    if (uInput) uInput.value = username;
    // Reset register form
    ['regUsername','regPassword','regConfirm'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.value = '';
    });
    showToast(`Akun "${username}" berhasil dibuat. Silakan login.`, 'success');
  } catch(e) {
    errorEl.textContent = 'Gagal mendaftar. Coba lagi.'; errorEl.style.display = 'block';
  } finally {
    btn.disabled = false;
    btn.textContent = 'Daftar';
  }
}

// ===== SUPER ADMIN PASSWORD RECOVERY =====
let _saRecoveryVerified = false;

async function handleSARecoveryStep1() {
  const code    = document.getElementById('saRecCode').value.trim();
  const errorEl = document.getElementById('saRecError');
  const btn     = document.getElementById('btnVerifyCode');

  errorEl.style.display = 'none';
  if (!code) {
    errorEl.textContent = 'Masukkan kode pemulihan';
    errorEl.style.display = 'block';
    return;
  }

  btn.disabled = true;
  btn.textContent = 'Memverifikasi...';
  const ok = await verifyRecoveryCode(code);
  btn.disabled = false;
  btn.textContent = 'Verifikasi';

  if (!ok) {
    errorEl.textContent = 'Kode pemulihan tidak valid';
    errorEl.style.display = 'block';
    return;
  }

  _saRecoveryVerified = true;
  document.getElementById('saRecStep1').style.display = 'none';
  document.getElementById('saRecStep2').style.display = 'block';
}

async function handleSARecoveryStep2() {
  if (!_saRecoveryVerified) return;
  const newPwd  = document.getElementById('saRecNewPwd').value;
  const confirm = document.getElementById('saRecConfirm').value;
  const errorEl = document.getElementById('saRecError2');
  const btn     = document.getElementById('btnResetSAPwd');

  errorEl.style.display = 'none';
  if (!newPwd || newPwd.length < 6) {
    errorEl.textContent = 'Password minimal 6 karakter'; errorEl.style.display = 'block'; return;
  }
  if (newPwd !== confirm) {
    errorEl.textContent = 'Konfirmasi password tidak cocok'; errorEl.style.display = 'block'; return;
  }

  btn.disabled = true;
  btn.textContent = 'Menyimpan...';
  try {
    const users = getUsers();
    const sa = users.find(u => u.isSuperAdmin);
    if (!sa) throw new Error('Super Admin not found');
    sa.passwordHash = await hashPassword(newPwd);
    saveUsers(users);
    _saRecoveryVerified = false;
    // Reset form
    ['saRecCode','saRecNewPwd','saRecConfirm'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.value = '';
    });
    document.getElementById('saRecStep1').style.display = 'block';
    document.getElementById('saRecStep2').style.display = 'none';
    showLoginPanel('loginPanel');
    showToast('Password Super Admin berhasil direset. Silakan login.', 'success');
  } catch(e) {
    errorEl.textContent = 'Gagal reset password. Coba lagi.'; errorEl.style.display = 'block';
  } finally {
    btn.disabled = false;
    btn.textContent = 'Reset Password';
  }
}

// ===== LEGACY DATA MIGRATION =====
function migrateLegacyData() {
  const users = getUsers();
  if (users.length === 0) return; // Tidak ada user, skip

  const hasSA = users.some(u => u.isSuperAdmin);
  if (hasSA) return; // Sudah ada Super Admin, skip

  // Temukan Admin pertama → jadikan Super Admin
  const firstAdmin = users.find(u => u.role === 'Admin');
  if (!firstAdmin) return;

  firstAdmin.isSuperAdmin = true;
  saveUsers(users);

  // Jika belum ada recovery code, tampilkan peringatan setelah app terbuka
  if (!localStorage.getItem(SA_RECOVERY_KEY)) {
    setTimeout(() => {
      showToast(
        'Akun Anda dijadikan Super Admin. Segera buat Kode Pemulihan di Manajemen Pengguna → Pengaturan Aplikasi.',
        'warning'
      );
    }, 1500);
  }
}

// ===== INIT AUTH =====
function initAuth() {
  seedDefaultRoles();
  migrateLegacyData();

  // Login form submit
  document.getElementById('loginForm')?.addEventListener('submit', (e) => {
    e.preventDefault();
    handleLoginSubmit();
  });

  // Setup form submit
  document.getElementById('setupForm')?.addEventListener('submit', (e) => {
    e.preventDefault();
    handleSetupSubmit();
  });

  // Enter key on password for login
  document.getElementById('loginPassword')?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') handleLoginSubmit();
  });

  // Check existing session
  const session = getCurrentUser();
  if (session) {
    // Already logged in
    hideLoginScreen();
    applyUserPermissions();
    initIdleDetection();
  } else {
    showLoginScreen();
  }
}

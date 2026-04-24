/**
 * LICENSE.JS - Software License Management
 * Verifikasi dan manajemen kunci lisensi aplikasi.
 * Harus di-load SEBELUM auth.js di index.html.
 */

// ===== MASTER SECRET (obfuscated - jangan diubah setelah deploy) =====
// Secret ini identik dengan yang ada di license-generator.html
const _lp1 = 'finrep'; const _lp2 = '2024'; const _lp3 = 'gki';
const _lp4 = 'lic';    const _lp5 = 'k9x2'; const _lp6 = 'mstr';
const _MASTER_SECRET = _lp1 + _lp2 + _lp4 + _lp6 + _lp5 + _lp3;

// ===== CONSTANTS =====
const LICENSE_STORAGE_KEY = 'finreport_license_v1';
const LICENSE_GRACE_DAYS  = 7;   // Hari tenggang setelah expired
const LICENSE_WARN_DAYS   = 30;  // Mulai tampilkan peringatan H-30
const _LIFETIME_SENTINEL  = 0xFFFFFFFF; // Sentinel: kunci tidak pernah expired

const _PLAN_MAP  = { 0: 'Starter', 1: 'Pro', 2: 'Enterprise' };
const _PLAN_RMAP = { 'Starter': 0, 'Pro': 1, 'Enterprise': 2 };
const _B32CHARS  = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'; // 32 char, tanpa I/O/1/0

// ===== BASE32 DECODE =====
function _base32Decode(str) {
  const charMap = {};
  for (let i = 0; i < _B32CHARS.length; i++) charMap[_B32CHARS[i]] = i;
  let bits = 0, value = 0;
  const output = [];
  const clean = str.toUpperCase().replace(/[^A-Z2-9]/g, '');
  for (const c of clean) {
    if (!(c in charMap)) continue;
    value = (value << 5) | charMap[c];
    bits += 5;
    if (bits >= 8) {
      bits -= 8;
      output.push((value >>> bits) & 0xFF);
    }
  }
  return new Uint8Array(output);
}

// ===== BASE32 ENCODE =====
function _base32Encode(bytes) {
  let bits = 0, value = 0, output = '';
  for (let i = 0; i < bytes.length; i++) {
    value = (value << 8) | bytes[i];
    bits += 8;
    while (bits >= 5) {
      bits -= 5;
      output += _B32CHARS[(value >>> bits) & 31];
    }
  }
  if (bits > 0) output += _B32CHARS[(value << (5 - bits)) & 31];
  return output;
}

// ===== CRC16-CCITT =====
function _crc16(str) {
  const bytes = new TextEncoder().encode(str);
  let crc = 0xFFFF;
  for (const b of bytes) {
    crc ^= b << 8;
    for (let i = 0; i < 8; i++) {
      crc = (crc & 0x8000) ? ((crc << 1) ^ 0x1021) : (crc << 1);
      crc &= 0xFFFF;
    }
  }
  return crc;
}

// ===== HMAC-SHA256 (Web Crypto API) =====
async function _hmacSign(secret, dataBytes) {
  const keyBytes  = new TextEncoder().encode(secret);
  const cryptoKey = await crypto.subtle.importKey(
    'raw', keyBytes, { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']
  );
  const sig = await crypto.subtle.sign('HMAC', cryptoKey, dataBytes);
  return new Uint8Array(sig).slice(0, 4); // Ambil 4 byte pertama
}

// ===== VERIFY LICENSE KEY =====
// keyStr: string 'FREP-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX'
// clientNameInput: string nama perusahaan yang dimasukkan user
// Returns: { valid, expired, graceExpired, daysRemaining, data, error }
async function verifyLicenseKey(keyStr, clientNameInput) {
  try {
    // Strip prefix dan dashes → 28 char Base32
    const clean = keyStr.toUpperCase().replace(/[\s\-]/g, '');
    if (!clean.startsWith('FREP')) {
      return { valid: false, error: 'Format kunci tidak valid (harus diawali FREP)' };
    }
    const encoded = clean.slice(4); // 28 char
    if (encoded.length < 26) {
      return { valid: false, error: 'Kunci lisensi terlalu pendek' };
    }

    // Decode Base32 → bytes (ambil 16 byte pertama)
    const decoded  = _base32Decode(encoded);
    if (decoded.length < 16) {
      return { valid: false, error: 'Kunci lisensi tidak lengkap' };
    }
    const payload  = decoded.slice(0, 12); // 12 byte payload
    const sigGiven = decoded.slice(12, 16); // 4 byte signature

    // Verifikasi HMAC signature
    const sigExpected = await _hmacSign(_MASTER_SECRET, payload);
    let mismatch = 0;
    for (let i = 0; i < 4; i++) mismatch |= (sigGiven[i] ^ sigExpected[i]);
    if (mismatch !== 0) {
      return { valid: false, error: 'Kunci lisensi tidak valid (tanda tangan salah)' };
    }

    // Parse payload
    const view      = new DataView(payload.buffer, payload.byteOffset);
    const clientId  = view.getUint32(0, false);
    const daysSinceEpoch = view.getUint32(4, false);
    const planCode  = payload[8];
    const maxUsers  = payload[9];
    const nameCrc   = view.getUint16(10, false);

    // Validasi nama perusahaan (case-insensitive, trimmed)
    const nameNorm = (clientNameInput || '').trim().toUpperCase();
    if (!nameNorm) {
      return { valid: false, error: 'Nama perusahaan tidak boleh kosong' };
    }
    if (_crc16(nameNorm) !== nameCrc) {
      return { valid: false, error: 'Nama perusahaan tidak cocok dengan lisensi ini' };
    }

    const plan = _PLAN_MAP[planCode] || 'Starter';

    // Cek apakah ini kunci Lifetime
    const isLifetime = (daysSinceEpoch === _LIFETIME_SENTINEL);
    let expiresAt, expired, graceExpired, daysRemaining;

    if (isLifetime) {
      expiresAt    = null;
      expired      = false;
      graceExpired = false;
      daysRemaining = null;
    } else {
      expiresAt     = new Date(daysSinceEpoch * 86400000);
      const now     = new Date();
      const msPerDay = 86400000;
      daysRemaining = Math.ceil((expiresAt.getTime() - now.getTime()) / msPerDay);
      expired       = daysRemaining <= 0;
      graceExpired  = daysRemaining <= -LICENSE_GRACE_DAYS;
    }

    return {
      valid:        isLifetime || !graceExpired,
      expired,
      graceExpired,
      daysRemaining,
      isLifetime,
      data: {
        clientId,
        clientName:  clientNameInput.trim(),
        plan,
        maxUsers:    maxUsers === 255 ? null : maxUsers, // null = unlimited
        isLifetime,
        expiresAt:   isLifetime ? null : expiresAt.toISOString(),
        activatedAt: new Date().toISOString(),
        keyStr:      keyStr.toUpperCase().replace(/[^A-Z0-9\-]/g, '')
      },
      error: (!isLifetime && graceExpired)
        ? `Lisensi telah kedaluwarsa dan melewati masa tenggang ${LICENSE_GRACE_DAYS} hari`
        : null
    };
  } catch(e) {
    return { valid: false, error: 'Gagal memproses kunci: ' + e.message };
  }
}

// ===== LOCALSTORAGE =====
function getLicense() {
  try {
    const raw = localStorage.getItem(LICENSE_STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch(e) { return null; }
}

function saveLicense(data) {
  localStorage.setItem(LICENSE_STORAGE_KEY, JSON.stringify(data));
  if (typeof DataStore !== 'undefined') DataStore.push(LICENSE_STORAGE_KEY);
}

// ===== STATUS HELPERS =====
function getLicenseStatus() {
  // Returns: 'none' | 'valid' | 'expiring' | 'expired' | 'grace' | 'dead'
  const lic = getLicense();
  if (!lic) return 'none';
  if (lic.isLifetime) return 'valid'; // Lifetime → selalu valid
  if (!lic.expiresAt) return 'valid'; // Fallback safety
  const now      = Date.now();
  const expiry   = new Date(lic.expiresAt).getTime();
  const msPerDay = 86400000;
  const daysLeft = Math.ceil((expiry - now) / msPerDay);
  if (daysLeft <= -LICENSE_GRACE_DAYS) return 'dead';     // melewati masa tenggang
  if (daysLeft <= 0)                   return 'grace';    // dalam masa tenggang
  if (daysLeft <= LICENSE_WARN_DAYS)   return 'expiring'; // mendekati expired
  return 'valid';
}

function isLicenseValid() {
  const s = getLicenseStatus();
  return s !== 'none' && s !== 'dead';
}

function getLicenseDaysRemaining() {
  const lic = getLicense();
  if (!lic) return null;
  if (lic.isLifetime || !lic.expiresAt) return null; // null = infinite
  const msPerDay = 86400000;
  return Math.ceil((new Date(lic.expiresAt).getTime() - Date.now()) / msPerDay);
}

// ===== EXPIRY BANNER =====
function showLicenseExpiryBanner() {
  const banner = document.getElementById('licenseExpiryBanner');
  if (!banner) return;
  const status = getLicenseStatus();
  const days   = getLicenseDaysRemaining();

  if (status === 'expiring') {
    banner.textContent = '\u26A0\uFE0F Peringatan: Lisensi Anda akan kedaluwarsa dalam ' + days + ' hari. Hubungi vendor untuk perpanjangan.';
    banner.className = 'license-banner license-banner-warning';
    banner.style.display = 'block';
    document.body.classList.add('has-license-banner');
  } else if (status === 'grace') {
    const graceLeft = LICENSE_GRACE_DAYS + (days || 0);
    banner.textContent = '\u26D4 Lisensi kedaluwarsa! Masa tenggang ' + graceLeft + ' hari tersisa. Segera hubungi vendor.';
    banner.className = 'license-banner license-banner-danger';
    banner.style.display = 'block';
    document.body.classList.add('has-license-banner');
  } else {
    banner.style.display = 'none';
    banner.className = 'license-banner';
    document.body.classList.remove('has-license-banner');
  }
}

// ===== LICENSE ACTIVATION PANEL HANDLER =====
async function handleLicenseSubmit() {
  const keyInput  = document.getElementById('licKeyInput');
  const nameInput = document.getElementById('licNameInput');
  const errorEl   = document.getElementById('licError');
  const btn       = document.getElementById('btnActivateLicense');

  if (!errorEl || !btn) return;
  errorEl.style.display = 'none';

  const key  = (keyInput?.value || '').trim();
  const name = (nameInput?.value || '').trim();

  if (!name) {
    errorEl.textContent = 'Masukkan nama perusahaan yang terdaftar';
    errorEl.style.display = 'block';
    nameInput?.focus();
    return;
  }
  if (!key) {
    errorEl.textContent = 'Masukkan kunci lisensi';
    errorEl.style.display = 'block';
    keyInput?.focus();
    return;
  }
  if (!key.startsWith('FREP')) {
    errorEl.textContent = 'Format kunci tidak valid (harus diawali dengan FREP-)';
    errorEl.style.display = 'block';
    return;
  }

  btn.disabled = true;
  btn.textContent = 'Memverifikasi...';

  try {
    const result = await verifyLicenseKey(key, name);

    if (!result.valid) {
      errorEl.textContent = result.error || 'Kunci lisensi tidak valid';
      errorEl.style.display = 'block';
      return;
    }

    saveLicense(result.data);

    const planLabel = result.data.plan;
    const maxLabel  = result.data.maxUsers ? `${result.data.maxUsers} pengguna` : 'Unlimited pengguna';

    showToast(
      `Lisensi ${planLabel} berhasil diaktifkan untuk ${result.data.clientName}! (${maxLabel})`,
      'success'
    );

    // Lanjut ke setup (pertama kali) atau login
    if (typeof isFirstRun === 'function' && isFirstRun()) {
      showLoginPanel('setupPanel');
    } else {
      showLoginPanel('loginPanel');
    }
  } catch(e) {
    errorEl.textContent = 'Terjadi kesalahan. Coba lagi.';
    errorEl.style.display = 'block';
  } finally {
    btn.disabled = false;
    btn.textContent = 'Aktifkan Lisensi';
  }
}

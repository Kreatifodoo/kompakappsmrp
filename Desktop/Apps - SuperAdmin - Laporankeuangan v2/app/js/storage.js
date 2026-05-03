/**
 * storage.js — DataStore: File-Based Persistence Bridge
 * ======================================================
 * Write-through cache pattern:
 *   - localStorage = runtime cache (sync, fast reads)
 *   - serve.py API = persistent file storage (async writes)
 *
 * On startup: load server files → localStorage
 * On save:    write localStorage (sync) + push to server (fire-and-forget)
 *
 * Falls back to localStorage-only mode when server is not available.
 */

// eslint-disable-next-line no-unused-vars
const DataStore = {
  _serverAvailable: false,
  _apiBase: '',

  // All localStorage keys managed by the app
  _allKeys: [
    'finreport_gki_v1',
    'finreport_users_v1',
    'finreport_settings_v1',
    'finreport_sa_recovery_v1',
    'finreport_roles_v1',
    'finreport_license_v1',
    'finreport_install_marker_v1',
    'pos_data_v1',
    'purchase_data_v1',
    'customer_data_v1',
    'manual_journals_v1',
    'manual_journals_counter'
  ],

  /**
   * Initialize DataStore — call FIRST before any module loads data.
   * Pings server API; if available, pulls all data files into localStorage.
   */
  async init() {
    // Full-online mode: file-based DataStore disabled.
    // The FastAPI backend (/api/v1) is now the source of truth.
    // BackendLoader hydrates state on login; saves go directly via Api.* / BackendSync.*
    this._serverAvailable = false;
    console.log('[DataStore] Disabled — using FastAPI backend instead');
  },

  /**
   * Pull all data from server files → localStorage.
   * Clears localStorage first so server files are the source of truth.
   */
  async _pullAll() {
    try {
      const res = await fetch('/api/data', { cache: 'no-store' });
      if (!res.ok) return;
      const serverKeys = await res.json();

      // Clear managed keys from localStorage (server is source of truth)
      this._allKeys.forEach(k => localStorage.removeItem(k));

      // Load each server file into localStorage
      for (const key of serverKeys) {
        try {
          const r = await fetch(`/api/data/${encodeURIComponent(key)}`, { cache: 'no-store' });
          if (r.ok) {
            const text = await r.text();
            localStorage.setItem(key, text);
          }
        } catch (e) {
          console.warn('[DataStore] Pull failed for key:', key);
        }
      }
    } catch (e) {
      console.warn('[DataStore] Pull all failed:', e);
    }
  },

  /**
   * Push a single key from localStorage to server (fire-and-forget).
   * Called after every save operation in app modules.
   */
  push(key) {
    if (!this._serverAvailable) return;
    const value = localStorage.getItem(key);
    if (value === null || value === undefined) {
      // Key was removed — delete from server too
      fetch(`/api/data/${encodeURIComponent(key)}`, { method: 'DELETE' })
        .catch(err => console.warn('[DataStore] Delete failed:', key, err));
    } else {
      fetch(`/api/data/${encodeURIComponent(key)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: value
      }).catch(err => console.warn('[DataStore] Push failed:', key, err));
    }
  },

  /**
   * Push ALL managed keys to server. Used after bulk operations like purge.
   */
  pushAll() {
    if (!this._serverAvailable) return;
    this._allKeys.forEach(k => this.push(k));
  },

  /**
   * Download backup ZIP of data/ + filestore/.
   */
  async backup() {
    if (!this._serverAvailable) {
      if (typeof showToast === 'function') showToast('Backup hanya tersedia saat menggunakan server (start.sh/start.bat)', 'error');
      return;
    }
    try {
      // Push all current data to server first
      this.pushAll();
      // Small delay to let pushes complete
      await new Promise(r => setTimeout(r, 500));
      // Trigger download
      window.location.href = '/api/backup';
      if (typeof showToast === 'function') showToast('Backup sedang didownload...', 'success');
    } catch (e) {
      if (typeof showToast === 'function') showToast('Backup gagal: ' + e.message, 'error');
    }
  },

  /**
   * Restore from a backup ZIP file.
   * @param {File} file — ZIP file from file input
   */
  async restore(file) {
    if (!this._serverAvailable) {
      if (typeof showToast === 'function') showToast('Restore hanya tersedia saat menggunakan server', 'error');
      return;
    }
    if (!file) return;
    if (!confirm('Restore akan mengganti SEMUA data saat ini. Lanjutkan?')) return;

    try {
      const buffer = await file.arrayBuffer();
      const res = await fetch('/api/restore', {
        method: 'POST',
        headers: { 'Content-Type': 'application/zip' },
        body: buffer
      });
      if (res.ok) {
        if (typeof showToast === 'function') showToast('Restore berhasil! Memuat ulang...', 'success');
        // Reload data from server into localStorage
        await this._pullAll();
        // Reload the page to reinitialize everything
        setTimeout(() => window.location.reload(), 1000);
      } else {
        const err = await res.json().catch(() => ({ message: 'Unknown error' }));
        if (typeof showToast === 'function') showToast('Restore gagal: ' + err.message, 'error');
      }
    } catch (e) {
      if (typeof showToast === 'function') showToast('Restore gagal: ' + e.message, 'error');
    }
  },

  /**
   * Check if server-based storage is active.
   */
  isServerMode() {
    return this._serverAvailable;
  }
};

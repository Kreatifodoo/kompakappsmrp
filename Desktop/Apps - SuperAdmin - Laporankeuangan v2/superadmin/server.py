#!/usr/bin/env python3
from __future__ import annotations
"""
SuperAdmin License Manager — Backend Server
============================================
Port : 8090
Data : superadmin/data/licenses.json
Config: superadmin/config.json

API Endpoints:
  POST  /api/login                    Authenticate superadmin
  POST  /api/logout                   Invalidate session
  GET   /api/licenses                 List all licenses
  POST  /api/licenses                 Generate new license + optional send email
  DELETE /api/licenses/{id}           Delete a license record
  POST  /api/licenses/{id}/resend     Resend email for existing license
  GET   /api/stats                    Dashboard statistics
  GET   /api/config/smtp              Get SMTP config (password masked)
  PUT   /api/config/smtp              Save SMTP config
  PUT   /api/config/password          Change admin password
  GET   /api/config/test-smtp         Test SMTP connection
  GET   /health                       Health check

Python stdlib only — no pip install needed.
"""

import hashlib
import hmac as _hmac
import http.server
import io
import json
import os
import re
import secrets
import smtplib
import socketserver
import struct
import time
import uuid
from datetime import date, datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from urllib.parse import unquote, urlparse

# ── Paths ────────────────────────────────────────────────────────────────────
DIR         = os.path.dirname(os.path.abspath(__file__))
DATA_DIR    = os.path.join(DIR, 'data')
LICENSES_DB = os.path.join(DATA_DIR, 'licenses.json')
CONFIG_FILE = os.path.join(DIR, 'config.json')
PORT        = 8090

os.makedirs(DATA_DIR, exist_ok=True)

# ── Default config ────────────────────────────────────────────────────────────
_DEFAULT_CONFIG = {
    "admin_password_hash": None,  # filled in after _sha256_hex is defined
    "smtp": {
        "host": "smtp.gmail.com",
        "port": 587,
        "username": "",
        "password": "",
        "sender_name": "Kompak Accounting",
        "sender_email": "",
        "use_tls": True
    },
    "license_secret": "finrep2024licmstrk9x2gki",  # MUST match license.js _MASTER_SECRET
    "app_name": "Kompak Accounting",
    "support_email": "",
    "support_whatsapp": ""
}

# ── SHA256 helper ─────────────────────────────────────────────────────────────
def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()

# Default admin password = "KompakAdmin2024" (change via UI)
_DEFAULT_ADMIN_HASH = _sha256_hex("KompakAdmin2024")

# ── Config persistence ────────────────────────────────────────────────────────
def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
            # Merge with defaults for missing keys
            for k, v in _DEFAULT_CONFIG.items():
                if k not in cfg:
                    cfg[k] = v
            return cfg
        except Exception:
            pass
    # Create default config
    cfg = dict(_DEFAULT_CONFIG)
    cfg['admin_password_hash'] = _DEFAULT_ADMIN_HASH
    save_config(cfg)
    return cfg

def save_config(cfg: dict):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

# ── License DB ────────────────────────────────────────────────────────────────
def load_licenses() -> list:
    if os.path.exists(LICENSES_DB):
        try:
            with open(LICENSES_DB, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return []

def save_licenses(licenses: list):
    with open(LICENSES_DB, 'w', encoding='utf-8') as f:
        json.dump(licenses, f, indent=2, ensure_ascii=False)

# ── Session store (in-memory) ─────────────────────────────────────────────────
_SESSIONS: dict[str, float] = {}  # token → expiry epoch
SESSION_TTL = 8 * 3600  # 8 hours

def create_session() -> str:
    token = secrets.token_urlsafe(32)
    _SESSIONS[token] = time.time() + SESSION_TTL
    return token

def validate_session(token: str) -> bool:
    expiry = _SESSIONS.get(token)
    if expiry is None:
        return False
    if time.time() > expiry:
        del _SESSIONS[token]
        return False
    return True

def delete_session(token: str):
    _SESSIONS.pop(token, None)

# ── License generation (Python port of license.js) ───────────────────────────
_B32CHARS = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
_PLAN_RMAP = {'Starter': 0, 'Pro': 1, 'Enterprise': 2}
_LIFETIME_SENTINEL = 0xFFFFFFFF

def _base32_encode(data: bytes) -> str:
    bits = 0
    value = 0
    output = ''
    for byte in data:
        value = (value << 8) | byte
        bits += 8
        while bits >= 5:
            bits -= 5
            output += _B32CHARS[(value >> bits) & 31]
    if bits > 0:
        output += _B32CHARS[(value << (5 - bits)) & 31]
    return output

def _crc16(text: str) -> int:
    """CRC16-CCITT (same as in license.js)."""
    data = text.encode('utf-8')
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc

def generate_license_key(
    client_id: int,
    client_name: str,
    plan: str,
    max_users: int,
    expires_at: date | None,
    is_lifetime: bool,
    secret: str
) -> str:
    """Generate FREP-XXXX-XXXX-... license key identical to license.js."""
    # Build 12-byte payload
    payload = bytearray(12)
    struct.pack_into('>I', payload, 0, client_id & 0xFFFFFFFF)
    if is_lifetime:
        struct.pack_into('>I', payload, 4, _LIFETIME_SENTINEL)
    else:
        days_since_epoch = int(expires_at.toordinal()) - date(1970, 1, 1).toordinal()
        # Convert to JS-style days (ms / 86400000)
        # JS epoch is Unix epoch
        import calendar
        ts = calendar.timegm(expires_at.timetuple())
        days = ts // 86400
        struct.pack_into('>I', payload, 4, days & 0xFFFFFFFF)
    payload[8] = _PLAN_RMAP.get(plan, 0)
    payload[9] = min(max(max_users, 1), 255)
    name_norm = client_name.strip().upper()
    crc = _crc16(name_norm)
    struct.pack_into('>H', payload, 10, crc)

    # HMAC-SHA256, take first 4 bytes
    sig = _hmac.new(secret.encode(), bytes(payload), hashlib.sha256).digest()[:4]

    full = bytes(payload) + sig  # 16 bytes
    encoded = _base32_encode(full)
    padded = encoded.ljust(28, _B32CHARS[0])
    groups = [padded[i:i+4] for i in range(0, 28, 4)]
    return 'FREP-' + '-'.join(groups)

# ── Email ─────────────────────────────────────────────────────────────────────
def send_license_email(license_record: dict, smtp_cfg: dict, app_cfg: dict) -> None:
    """Send HTML license email to the recipient address in license_record."""
    recipient = license_record.get('recipient_email', '')
    if not recipient:
        raise ValueError("Alamat email penerima tidak tersedia")
    if not smtp_cfg.get('host') or not smtp_cfg.get('username'):
        raise ValueError("Konfigurasi SMTP belum diisi. Isi terlebih dahulu di menu Pengaturan.")

    app_name     = app_cfg.get('app_name', 'Kompak Accounting')
    sender_name  = smtp_cfg.get('sender_name', app_name)
    sender_email = smtp_cfg.get('sender_email') or smtp_cfg['username']
    support_email = app_cfg.get('support_email', sender_email)
    support_wa    = app_cfg.get('support_whatsapp', '')

    rec = license_record
    expiry_display = 'Lifetime (Tidak Ada Batas Waktu)' if rec.get('is_lifetime') else _fmt_date(rec.get('expires_at'))
    max_display = 'Unlimited' if not rec.get('max_users') else f"{rec['max_users']} pengguna"
    plan_color = {'Starter': '#0369a1', 'Pro': '#6d28d9', 'Enterprise': '#92400e'}.get(rec.get('plan', 'Pro'), '#0369a1')
    plan_bg    = {'Starter': '#e0f2fe', 'Pro': '#ede9fe', 'Enterprise': '#fef3c7'}.get(rec.get('plan', 'Pro'), '#e0f2fe')

    # Build activation steps outside the main f-string to avoid nesting issues
    _steps = [
        f'Buka aplikasi <strong>{app_name}</strong>',
        f'Masukkan <strong>Nama Perusahaan</strong>: <code style="background:#f1f5f9;padding:2px 6px;border-radius:4px;">{rec.get("client_name", "")}</code>',
        'Masukkan <strong>Kunci Lisensi</strong> di kotak yang tersedia',
        'Klik tombol <strong>"Aktifkan Lisensi"</strong>',
        'Buat akun <strong>Super Admin</strong> &amp; simpan <span style="color:#dc2626;font-weight:600;">Kode Pemulihan!</span>',
    ]
    _activation_rows = ''.join(
        f'<tr><td style="width:32px;vertical-align:top;padding:0 12px 12px 0;">'
        f'<div style="width:28px;height:28px;background:#2563eb;border-radius:50%;text-align:center;'
        f'line-height:28px;font-size:13px;font-weight:700;color:#fff;">{i}</div></td>'
        f'<td style="padding-bottom:12px;font-size:14px;color:#475569;line-height:1.5;">{step}</td></tr>'
        for i, step in enumerate(_steps, start=1)
    )
    _support_rows = ''
    if support_email:
        _support_rows += f'<p style="font-size:14px;color:#475569;margin:0 0 4px;">📧 Email: <a href="mailto:{support_email}" style="color:#2563eb;">{support_email}</a></p>'
    if support_wa:
        _wa_num = re.sub(r'[^0-9]', '', support_wa)
        _support_rows += f'<p style="font-size:14px;color:#475569;margin:0;">💬 WhatsApp: <a href="https://wa.me/{_wa_num}" style="color:#2563eb;">{support_wa}</a></p>'

    html = f"""<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Kunci Lisensi {app_name}</title>
</head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:'Segoe UI',Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;padding:32px 16px;">
  <tr><td align="center">
  <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;">

    <!-- Header -->
    <tr><td style="background:#1e293b;border-radius:12px 12px 0 0;padding:32px;text-align:center;">
      <div style="font-size:28px;font-weight:700;color:#fff;letter-spacing:-0.5px;">
        {app_name}
      </div>
      <div style="font-size:14px;color:#94a3b8;margin-top:4px;">Kunci Lisensi Software</div>
    </td></tr>

    <!-- Body -->
    <tr><td style="background:#fff;padding:40px 40px 32px;">

      <p style="font-size:16px;color:#1e293b;margin:0 0 8px;">Kepada Yth. Tim IT,</p>
      <p style="font-size:16px;color:#1e293b;font-weight:700;margin:0 0 24px;">{rec.get('client_name', '')}</p>

      <p style="font-size:14px;color:#475569;line-height:1.6;margin:0 0 28px;">
        Terima kasih telah mempercayakan pengelolaan keuangan bisnis Anda kepada <strong>{app_name}</strong>.
        Berikut adalah detail lisensi software Anda.
      </p>

      <!-- License card -->
      <div style="background:#0f172a;border-radius:12px;padding:28px;margin-bottom:28px;">
        <div style="font-size:11px;color:#94a3b8;letter-spacing:.1em;text-transform:uppercase;margin-bottom:10px;">
          KUNCI LISENSI ANDA
        </div>
        <div style="font-family:'Courier New',monospace;font-size:20px;font-weight:700;color:#4ade80;
                    letter-spacing:3px;word-break:break-all;line-height:1.5;margin-bottom:20px;">
          {rec.get('key_str', '')}
        </div>
        <table cellpadding="0" cellspacing="0" style="width:100%;">
          <tr>
            <td style="width:50%;padding-right:8px;">
              <div style="background:#1e293b;border-radius:8px;padding:12px 16px;">
                <div style="font-size:11px;color:#64748b;margin-bottom:4px;">Nama Perusahaan</div>
                <div style="font-size:14px;color:#e2e8f0;font-weight:600;">{rec.get('client_name', '')}</div>
              </div>
            </td>
            <td style="width:50%;padding-left:8px;">
              <div style="background:#1e293b;border-radius:8px;padding:12px 16px;">
                <div style="font-size:11px;color:#64748b;margin-bottom:4px;">Plan</div>
                <div style="font-size:14px;font-weight:700;color:{plan_color};background:{plan_bg};
                            display:inline-block;padding:2px 10px;border-radius:99px;">{rec.get('plan', 'Pro')}</div>
              </div>
            </td>
          </tr>
          <tr><td colspan="2" style="height:8px;"></td></tr>
          <tr>
            <td style="padding-right:8px;">
              <div style="background:#1e293b;border-radius:8px;padding:12px 16px;">
                <div style="font-size:11px;color:#64748b;margin-bottom:4px;">Maks. Pengguna</div>
                <div style="font-size:14px;color:#e2e8f0;font-weight:600;">{max_display}</div>
              </div>
            </td>
            <td style="padding-left:8px;">
              <div style="background:#1e293b;border-radius:8px;padding:12px 16px;">
                <div style="font-size:11px;color:#64748b;margin-bottom:4px;">Berlaku Hingga</div>
                <div style="font-size:14px;color:#e2e8f0;font-weight:600;">{expiry_display}</div>
              </div>
            </td>
          </tr>
        </table>
      </div>

      <!-- Activation steps -->
      <h3 style="font-size:15px;color:#1e293b;margin:0 0 16px;">📋 Cara Aktivasi</h3>
      <table cellpadding="0" cellspacing="0" style="width:100%;margin-bottom:28px;">
        {_activation_rows}
      </table>

      <!-- Warning box -->
      <div style="background:#fef3c7;border:1px solid #fcd34d;border-radius:8px;padding:16px;margin-bottom:28px;">
        <div style="font-size:13px;color:#92400e;font-weight:600;margin-bottom:4px;">&#9888;&#65039; Penting</div>
        <ul style="margin:0;padding-left:18px;font-size:13px;color:#78350f;line-height:1.7;">
          <li>Nama perusahaan saat aktivasi harus <strong>PERSIS sama</strong> seperti yang tertera di atas</li>
          <li>Kode Pemulihan Super Admin hanya ditampilkan <strong>SEKALI</strong> — simpan di tempat aman</li>
          <li>Lisensi ini terdaftar untuk satu instalasi perusahaan</li>
        </ul>
      </div>

      <!-- Support -->
      <div style="border-top:1px solid #e2e8f0;padding-top:24px;">
        <p style="font-size:14px;color:#475569;margin:0 0 8px;">Butuh bantuan? Tim support kami siap membantu:</p>
        {_support_rows}
      </div>

    </td></tr>

    <!-- Footer -->
    <tr><td style="background:#f8fafc;border-radius:0 0 12px 12px;padding:20px 40px;text-align:center;
                   border-top:1px solid #e2e8f0;">
      <p style="font-size:12px;color:#94a3b8;margin:0;">
        Email ini dikirim secara otomatis oleh sistem {app_name}.<br>
        Harap jangan membalas email ini.
      </p>
    </td></tr>

  </table>
  </td></tr>
</table>
</body>
</html>"""

    # Plain-text fallback
    plain = f"""Kunci Lisensi {app_name}
{"="*50}

Kepada Yth. Tim IT {rec.get('client_name', '')},

Berikut adalah detail lisensi software Anda:

Nama Perusahaan : {rec.get('client_name', '')}
Kunci Lisensi   : {rec.get('key_str', '')}
Plan            : {rec.get('plan', '')}
Maks. Pengguna  : {max_display}
Berlaku Hingga  : {expiry_display}

Cara Aktivasi:
1. Buka aplikasi {app_name}
2. Masukkan Nama Perusahaan: {rec.get('client_name', '')}
3. Masukkan Kunci Lisensi di atas
4. Klik "Aktifkan Lisensi"
5. Buat akun Super Admin — SIMPAN Kode Pemulihan!

{"Kontak Support: " + support_email if support_email else ""}
{"WhatsApp: " + support_wa if support_wa else ""}

{app_name} Team"""

    msg = MIMEMultipart('alternative')
    msg['From']    = f'"{sender_name}" <{sender_email}>'
    msg['To']      = recipient
    msg['Subject'] = f'🔑 Kunci Lisensi {app_name} — {rec.get("client_name", "")}'
    msg.attach(MIMEText(plain, 'plain', 'utf-8'))
    msg.attach(MIMEText(html, 'html', 'utf-8'))

    with smtplib.SMTP(smtp_cfg['host'], int(smtp_cfg['port']), timeout=10) as server:
        if smtp_cfg.get('use_tls', True):
            server.starttls()
        server.login(smtp_cfg['username'], smtp_cfg['password'])
        server.sendmail(sender_email, [recipient], msg.as_string())

def _fmt_date(iso_str: str | None) -> str:
    if not iso_str:
        return '-'
    try:
        d = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
        months = ['Jan','Feb','Mar','Apr','Mei','Jun','Jul','Agu','Sep','Okt','Nov','Des']
        return f"{d.day:02d} {months[d.month-1]} {d.year}"
    except Exception:
        return iso_str

# ── HTTP Handler ──────────────────────────────────────────────────────────────
class LicenseManagerHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIR, **kwargs)

    def log_message(self, format, *args):
        if args and '/api/' in str(args[0]):
            super().log_message(format, *args)

    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    # ── Auth helper ────────────────────────────────────────────────
    def _get_token(self) -> str | None:
        auth = self.headers.get('Authorization', '')
        if auth.startswith('Bearer '):
            return auth[7:].strip()
        return None

    def _require_auth(self) -> bool:
        token = self._get_token()
        if not token or not validate_session(token):
            self._json({'error': 'Unauthorized', 'code': 401}, 401)
            return False
        return True

    # ── Body / response ────────────────────────────────────────────
    def _read_json(self) -> dict:
        length = int(self.headers.get('Content-Length', 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode('utf-8'))
        except Exception:
            return {}

    def _json(self, data: dict | list, status: int = 200):
        body = json.dumps(data, ensure_ascii=False, default=str).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)

    # ── Router ─────────────────────────────────────────────────────
    def do_GET(self):
        p = urlparse(self.path).path
        if p == '/health':
            self._json({'status': 'ok', 'time': datetime.now(timezone.utc).isoformat()})
        elif p == '/api/licenses':
            self._handle_list()
        elif p == '/api/stats':
            self._handle_stats()
        elif p == '/api/config/smtp':
            self._handle_get_smtp()
        elif p == '/api/config/app':
            self._handle_get_app_config()
        else:
            super().do_GET()

    def do_POST(self):
        p = urlparse(self.path).path
        if p == '/api/login':
            self._handle_login()
        elif p == '/api/logout':
            self._handle_logout()
        elif p == '/api/licenses':
            self._handle_generate()
        elif re.match(r'^/api/licenses/[^/]+/resend$', p):
            lid = p.split('/')[3]
            self._handle_resend(lid)
        else:
            self._json({'error': 'Not found'}, 404)

    def do_PUT(self):
        p = urlparse(self.path).path
        if p == '/api/config/smtp':
            self._handle_save_smtp()
        elif p == '/api/config/password':
            self._handle_change_password()
        elif p == '/api/config/app':
            self._handle_save_app_config()
        else:
            self._json({'error': 'Not found'}, 404)

    def do_DELETE(self):
        p = urlparse(self.path).path
        m = re.match(r'^/api/licenses/([^/]+)$', p)
        if m:
            self._handle_delete(m.group(1))
        else:
            self._json({'error': 'Not found'}, 404)

    # ── Handlers ───────────────────────────────────────────────────
    def _handle_login(self):
        body = self._read_json()
        pw   = body.get('password', '')
        cfg  = load_config()
        expected_hash = cfg.get('admin_password_hash', _DEFAULT_ADMIN_HASH)
        if _sha256_hex(pw) != expected_hash:
            self._json({'error': 'Password salah'}, 401)
            return
        token = create_session()
        self._json({'token': token, 'expires_in': SESSION_TTL})

    def _handle_logout(self):
        token = self._get_token()
        if token:
            delete_session(token)
        self._json({'status': 'ok'})

    def _handle_list(self):
        if not self._require_auth():
            return
        licenses = load_licenses()
        self._json(licenses)

    def _handle_stats(self):
        if not self._require_auth():
            return
        licenses = load_licenses()
        now  = datetime.now(timezone.utc)
        total = len(licenses)
        active = expiring = expired = 0
        for r in licenses:
            if r.get('is_lifetime') or not r.get('expires_at'):
                active += 1
                continue
            try:
                exp = datetime.fromisoformat(r['expires_at'].replace('Z', '+00:00'))
                if exp.tzinfo is None:
                    exp = exp.replace(tzinfo=timezone.utc)
                diff = (exp - now).days
                if diff < 0:
                    expired += 1
                elif diff <= 30:
                    expiring += 1
                else:
                    active += 1
            except Exception:
                active += 1
        next_id = max((r.get('client_id', 0) for r in licenses), default=0) + 1
        self._json({
            'total': total, 'active': active,
            'expiring': expiring, 'expired': expired,
            'next_client_id': next_id
        })

    def _handle_generate(self):
        if not self._require_auth():
            return
        body = self._read_json()
        cfg  = load_config()

        client_name  = (body.get('client_name') or '').strip()
        recipient    = (body.get('recipient_email') or '').strip()
        plan         = body.get('plan', 'Pro')
        max_users    = int(body.get('max_users', 10))
        is_lifetime  = bool(body.get('is_lifetime', False))
        expires_str  = (body.get('expires_at') or '').strip()
        send_email   = bool(body.get('send_email', False))

        if not client_name:
            self._json({'error': 'Nama perusahaan tidak boleh kosong'}, 400)
            return
        if plan not in ('Starter', 'Pro', 'Enterprise'):
            self._json({'error': 'Plan tidak valid'}, 400)
            return

        expires_at: date | None = None
        if not is_lifetime:
            if not expires_str:
                self._json({'error': 'Tanggal expired harus diisi'}, 400)
                return
            try:
                expires_at = date.fromisoformat(expires_str[:10])
            except ValueError:
                self._json({'error': 'Format tanggal tidak valid (gunakan YYYY-MM-DD)'}, 400)
                return
            if expires_at <= date.today():
                self._json({'error': 'Tanggal expired harus di masa mendatang'}, 400)
                return

        # Auto-increment client_id
        licenses = load_licenses()
        client_id = int(body.get('client_id') or 0)
        if client_id <= 0:
            client_id = max((r.get('client_id', 0) for r in licenses), default=0) + 1

        secret  = cfg.get('license_secret', _DEFAULT_CONFIG['license_secret'])
        key_str = generate_license_key(
            client_id=client_id,
            client_name=client_name,
            plan=plan,
            max_users=max_users,
            expires_at=expires_at,
            is_lifetime=is_lifetime,
            secret=secret
        )

        record = {
            'id': str(uuid.uuid4()),
            'client_id': client_id,
            'client_name': client_name,
            'recipient_email': recipient,
            'plan': plan,
            'max_users': None if max_users == 255 else max_users,
            'is_lifetime': is_lifetime,
            'expires_at': None if is_lifetime else expires_at.isoformat(),
            'key_str': key_str,
            'email_sent': False,
            'email_sent_at': None,
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'notes': body.get('notes', '')
        }

        # Send email if requested
        email_error = None
        if send_email and recipient:
            try:
                send_license_email(record, cfg.get('smtp', {}), cfg)
                record['email_sent'] = True
                record['email_sent_at'] = datetime.now(timezone.utc).isoformat()
            except Exception as e:
                email_error = str(e)

        licenses.insert(0, record)
        save_licenses(licenses)

        resp = {'license': record}
        if email_error:
            resp['email_error'] = email_error
        self._json(resp, 201)

    def _handle_resend(self, lid: str):
        if not self._require_auth():
            return
        licenses = load_licenses()
        record = next((r for r in licenses if r['id'] == lid), None)
        if not record:
            self._json({'error': 'Lisensi tidak ditemukan'}, 404)
            return
        recipient = record.get('recipient_email', '')
        if not recipient:
            self._json({'error': 'Email penerima tidak tersedia untuk lisensi ini'}, 400)
            return
        cfg = load_config()
        try:
            send_license_email(record, cfg.get('smtp', {}), cfg)
            record['email_sent'] = True
            record['email_sent_at'] = datetime.now(timezone.utc).isoformat()
            save_licenses(licenses)
            self._json({'status': 'ok', 'sent_to': recipient})
        except Exception as e:
            self._json({'error': str(e)}, 500)

    def _handle_delete(self, lid: str):
        if not self._require_auth():
            return
        licenses = load_licenses()
        new_list = [r for r in licenses if r['id'] != lid]
        if len(new_list) == len(licenses):
            self._json({'error': 'Lisensi tidak ditemukan'}, 404)
            return
        save_licenses(new_list)
        self._json({'status': 'ok', 'deleted': lid})

    def _handle_get_smtp(self):
        if not self._require_auth():
            return
        cfg = load_config()
        smtp = dict(cfg.get('smtp', {}))
        smtp['password'] = '••••••••' if smtp.get('password') else ''
        self._json(smtp)

    def _handle_save_smtp(self):
        if not self._require_auth():
            return
        body = self._read_json()
        cfg  = load_config()
        smtp = cfg.get('smtp', {})
        for field in ('host', 'port', 'username', 'sender_name', 'sender_email', 'use_tls'):
            if field in body:
                smtp[field] = body[field]
        # Only update password if it's not the masked placeholder
        if body.get('password') and body['password'] != '••••••••':
            smtp['password'] = body['password']
        cfg['smtp'] = smtp
        save_config(cfg)
        masked = dict(smtp)
        masked['password'] = '••••••••' if masked.get('password') else ''
        self._json({'status': 'ok', 'smtp': masked})

    def _handle_get_app_config(self):
        if not self._require_auth():
            return
        cfg = load_config()
        self._json({
            'app_name':        cfg.get('app_name', ''),
            'support_email':   cfg.get('support_email', ''),
            'support_whatsapp': cfg.get('support_whatsapp', ''),
        })

    def _handle_save_app_config(self):
        if not self._require_auth():
            return
        body = self._read_json()
        cfg  = load_config()
        for field in ('app_name', 'support_email', 'support_whatsapp'):
            if field in body:
                cfg[field] = body[field]
        save_config(cfg)
        self._json({'status': 'ok'})

    def _handle_change_password(self):
        if not self._require_auth():
            return
        body = self._read_json()
        old_pw = body.get('old_password', '')
        new_pw = body.get('new_password', '')
        cfg    = load_config()
        if _sha256_hex(old_pw) != cfg.get('admin_password_hash', _DEFAULT_ADMIN_HASH):
            self._json({'error': 'Password lama tidak cocok'}, 400)
            return
        if len(new_pw) < 8:
            self._json({'error': 'Password baru minimal 8 karakter'}, 400)
            return
        cfg['admin_password_hash'] = _sha256_hex(new_pw)
        save_config(cfg)
        self._json({'status': 'ok', 'message': 'Password berhasil diubah'})


# ── Threaded server ───────────────────────────────────────────────────────────
class ThreadedServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == '__main__':
    print(f'SuperAdmin License Manager berjalan di http://localhost:{PORT}')
    print(f'  Data  : {DATA_DIR}')
    print(f'  Config: {CONFIG_FILE}')
    print(f'  Password default: KompakAdmin2024  (ganti via Settings)')
    print(f'  Tekan Ctrl+C untuk menghentikan.')
    with ThreadedServer(('', PORT), LicenseManagerHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print('\nServer dihentikan.')

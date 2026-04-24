#!/usr/bin/env python3
"""
serve.py — FinReport API + Static File Server
===============================================
Serves the FinReport SPA and provides a REST API for:
- JSON data persistence (data/ folder)
- File uploads (filestore/ folder)
- Backup & restore (ZIP download/upload)

Port: 8080
"""

import http.server, socketserver, os, json, io, zipfile, shutil, re
from urllib.parse import urlparse, unquote

PORT = 8080
DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(DIR, 'data')
FILESTORE_DIR = os.path.join(DIR, 'filestore')

# Ensure directories exist
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(FILESTORE_DIR, exist_ok=True)


def _sanitize_key(key):
    """Remove dangerous path components from key."""
    key = unquote(key)
    key = re.sub(r'[^a-zA-Z0-9_\-]', '_', key)
    return key


class FinReportHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIR, **kwargs)

    # ── Logging (quieter) ──────────────────────────────
    def log_message(self, format, *args):
        if '/api/' in str(args[0]) if args else False:
            super().log_message(format, *args)

    # ── CORS ───────────────────────────────────────────
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, PUT, POST, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    # ── GET ─────────────────────────────────────────────
    def do_GET(self):
        path = urlparse(self.path).path

        if path == '/api/ping':
            self._json_ok({'status': 'ok', 'dataDir': 'data/', 'filestoreDir': 'filestore/'})

        elif path == '/api/data':
            keys = sorted([f[:-5] for f in os.listdir(DATA_DIR) if f.endswith('.json')])
            self._json_ok(keys)

        elif path.startswith('/api/data/'):
            key = _sanitize_key(path[len('/api/data/'):])
            filepath = os.path.join(DATA_DIR, f'{key}.json')
            if os.path.exists(filepath):
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(content.encode('utf-8'))
            else:
                self._json_err('Not found', 404)

        elif path == '/api/backup':
            self._handle_backup()

        elif path.startswith('/api/filestore/'):
            filename = _sanitize_key(path[len('/api/filestore/'):])
            filepath = os.path.join(FILESTORE_DIR, filename)
            if os.path.exists(filepath):
                with open(filepath, 'rb') as f:
                    data = f.read()
                self.send_response(200)
                self.send_header('Content-Type', 'application/octet-stream')
                self.send_header('Content-Length', len(data))
                self.end_headers()
                self.wfile.write(data)
            else:
                self._json_err('File not found', 404)

        else:
            super().do_GET()

    # ── PUT ─────────────────────────────────────────────
    def do_PUT(self):
        path = urlparse(self.path).path

        if path.startswith('/api/data/'):
            key = _sanitize_key(path[len('/api/data/'):])
            body = self._read_body()
            filepath = os.path.join(DATA_DIR, f'{key}.json')
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(body.decode('utf-8'))
            self._json_ok({'status': 'ok', 'key': key})
        else:
            self._json_err('Method not allowed', 405)

    # ── DELETE ──────────────────────────────────────────
    def do_DELETE(self):
        path = urlparse(self.path).path

        if path.startswith('/api/data/'):
            key = _sanitize_key(path[len('/api/data/'):])
            filepath = os.path.join(DATA_DIR, f'{key}.json')
            if os.path.exists(filepath):
                os.remove(filepath)
            self._json_ok({'status': 'ok', 'key': key, 'deleted': True})
        else:
            self._json_err('Method not allowed', 405)

    # ── POST ────────────────────────────────────────────
    def do_POST(self):
        path = urlparse(self.path).path

        if path == '/api/restore':
            self._handle_restore()
        elif path == '/api/filestore':
            self._handle_filestore_upload()
        else:
            self._json_err('Method not allowed', 405)

    # ── Helpers ─────────────────────────────────────────
    def _read_body(self):
        length = int(self.headers.get('Content-Length', 0))
        return self.rfile.read(length) if length > 0 else b''

    def _json_ok(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)

    def _json_err(self, message, status=400):
        self._json_ok({'status': 'error', 'message': message}, status)

    # ── Backup: GET /api/backup ─────────────────────────
    def _handle_backup(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            for folder, prefix in [(DATA_DIR, 'data'), (FILESTORE_DIR, 'filestore')]:
                for root, dirs, files in os.walk(folder):
                    for fname in files:
                        if fname.startswith('.'):
                            continue  # skip .gitkeep etc.
                        fpath = os.path.join(root, fname)
                        arcname = os.path.join(prefix, os.path.relpath(fpath, folder))
                        zf.write(fpath, arcname)
        buf.seek(0)
        data = buf.read()
        self.send_response(200)
        self.send_header('Content-Type', 'application/zip')
        self.send_header('Content-Disposition', 'attachment; filename="finreport-backup.zip"')
        self.send_header('Content-Length', len(data))
        self.end_headers()
        self.wfile.write(data)

    # ── Restore: POST /api/restore ──────────────────────
    def _handle_restore(self):
        body = self._read_body()
        try:
            buf = io.BytesIO(body)
            with zipfile.ZipFile(buf, 'r') as zf:
                # Clear existing data before restore
                for fname in os.listdir(DATA_DIR):
                    if fname.endswith('.json'):
                        os.remove(os.path.join(DATA_DIR, fname))
                # Extract
                for member in zf.namelist():
                    if member.endswith('/'):
                        continue  # skip directory entries
                    if member.startswith('data/') or member.startswith('filestore/'):
                        target = os.path.join(DIR, member)
                        os.makedirs(os.path.dirname(target), exist_ok=True)
                        with zf.open(member) as src, open(target, 'wb') as dst:
                            dst.write(src.read())
            self._json_ok({'status': 'ok', 'message': 'Restore berhasil'})
        except Exception as e:
            self._json_err(f'Restore gagal: {str(e)}', 500)

    # ── Filestore Upload: POST /api/filestore ───────────
    def _handle_filestore_upload(self):
        body = self._read_body()
        # Expect JSON with {filename, data (base64)}
        try:
            payload = json.loads(body.decode('utf-8'))
            filename = _sanitize_key(payload.get('filename', 'upload'))
            import base64
            file_data = base64.b64decode(payload.get('data', ''))
            filepath = os.path.join(FILESTORE_DIR, filename)
            with open(filepath, 'wb') as f:
                f.write(file_data)
            self._json_ok({'status': 'ok', 'filename': filename, 'size': len(file_data)})
        except Exception as e:
            self._json_err(f'Upload gagal: {str(e)}', 500)


# ── Start Server ────────────────────────────────────────
if __name__ == '__main__':
    with socketserver.TCPServer(("", PORT), FinReportHandler) as httpd:
        print(f'FinReport berjalan di http://localhost:{PORT}')
        print(f'  Data folder   : {DATA_DIR}')
        print(f'  Filestore     : {FILESTORE_DIR}')
        print(f'  Tekan Ctrl+C untuk menghentikan server.')
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print('\nServer dihentikan.')

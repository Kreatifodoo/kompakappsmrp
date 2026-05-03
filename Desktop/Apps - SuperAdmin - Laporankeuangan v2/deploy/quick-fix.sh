#!/bin/bash
# deploy/quick-fix.sh
# ──────────────────────────────────────────────────────────────────────────
# Jalankan ini di server kalau website mati dan perlu diperbaiki cepat.
# Tidak perlu setup ulang — cukup restart semua service.
#
#   ssh user@<server-ip>
#   cd "/opt/kompakapp/Desktop/Apps - SuperAdmin - Laporankeuangan v2"
#   bash deploy/quick-fix.sh
# ──────────────────────────────────────────────────────────────────────────
set -euo pipefail

echo "=== Cek status services ==="
echo "--- kompak-spa (frontend lama, port 8080) ---"
systemctl status kompak-spa --no-pager || true

echo ""
echo "--- kompak-api (FastAPI, port 8000) ---"
systemctl status kompak-api --no-pager || true

echo ""
echo "--- nginx ---"
systemctl status nginx --no-pager || true

echo ""
echo "=== Apakah port 8080 dan 8000 sedang listen? ==="
ss -tlnp | grep -E '8080|8000' || echo "(tidak ada yang listen)"

echo ""
echo "=== Restart semua ==="

# Coba pakai systemctl dulu (setup baru)
if systemctl list-units --type=service 2>/dev/null | grep -q kompak-spa; then
    systemctl restart kompak-spa && echo "✅ kompak-spa restarted" || true
    systemctl restart kompak-api && echo "✅ kompak-api restarted" || true
else
    # Fallback: cara lama (pkill + nohup)
    echo "systemd services belum ada — pakai cara lama..."
    APPDIR="$(cd "$(dirname "$0")/.." && pwd)"

    pkill -f "python.*serve.py" || true
    sleep 1
    nohup python3 "$APPDIR/app/serve.py" > /tmp/kompak-spa.log 2>&1 &
    echo "✅ serve.py started (PID $!)"
fi

systemctl reload nginx && echo "✅ nginx reloaded" || true

echo ""
echo "=== Test lokal ==="
sleep 2
curl -fsS http://127.0.0.1:8080/ > /dev/null \
    && echo "✅ Frontend (port 8080) OK" \
    || echo "❌ Frontend (port 8080) TIDAK RESPOND"

curl -fsS http://127.0.0.1:8000/health > /dev/null \
    && echo "✅ FastAPI (port 8000) OK" \
    || echo "⚠️  FastAPI (port 8000) belum jalan (mungkin belum di-setup)"

echo ""
echo "Log frontend : journalctl -u kompak-spa -f"
echo "             : atau cat /tmp/kompak-spa.log"
echo "Log FastAPI  : journalctl -u kompak-api -f"

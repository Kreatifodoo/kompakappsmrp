#!/bin/bash
# deploy/setup-license-subdomain.sh
# ──────────────────────────────────────────────────────────────────────────
# One-shot setup untuk subdomain license.kompakapps.com (SuperAdmin License
# Manager). Jalankan SATU KALI sebagai root setelah DNS A record sudah
# diarahkan ke IP server:
#
#   ssh root@<server-ip>
#   cd "/opt/kompakapp/Desktop/Apps - SuperAdmin - Laporankeuangan v2"
#   git pull origin main
#   bash deploy/setup-license-subdomain.sh
# ──────────────────────────────────────────────────────────────────────────
set -euo pipefail

DOMAIN="license.kompakapps.com"
APPDIR="/opt/kompakapp/Desktop/Apps - SuperAdmin - Laporankeuangan v2"
SUPERADMIN_DIR="$APPDIR/superadmin"
SERVICE_NAME="kompak-superadmin"

echo "=== [1/6] Verifikasi direktori ==="
if [ ! -d "$SUPERADMIN_DIR" ]; then
    echo "❌ Folder $SUPERADMIN_DIR tidak ada. Jalankan 'git pull origin main' dulu."
    exit 1
fi
echo "✅ $SUPERADMIN_DIR ada"

echo ""
echo "=== [2/6] Buat systemd service kompak-superadmin (port 8090) ==="
cat > /etc/systemd/system/${SERVICE_NAME}.service << EOF
[Unit]
Description=Kompak Accounting — SuperAdmin License Manager
After=network.target

[Service]
Type=exec
User=www-data
WorkingDirectory=$SUPERADMIN_DIR
ExecStart=/usr/bin/python3 server.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=kompak-superadmin

[Install]
WantedBy=multi-user.target
EOF

# www-data harus bisa write seluruh superadmin/ — config.json dan data/licenses.json
# di-create on-the-fly oleh server.py saat first-run, jadi parent dir wajib writable.
chown -R www-data:www-data "$SUPERADMIN_DIR"

systemctl daemon-reload
systemctl enable ${SERVICE_NAME}
systemctl restart ${SERVICE_NAME}
sleep 2

if systemctl is-active --quiet ${SERVICE_NAME}; then
    echo "✅ ${SERVICE_NAME} running di port 8090"
else
    echo "❌ ${SERVICE_NAME} gagal start. Cek: journalctl -u ${SERVICE_NAME} -n 30"
    exit 1
fi

echo ""
echo "=== [3/6] Test lokal port 8090 ==="
curl -fsS http://127.0.0.1:8090/health > /dev/null \
    && echo "✅ server.py respond di 127.0.0.1:8090" \
    || { echo "❌ Tidak respond"; exit 1; }

echo ""
echo "=== [4/6] Pasang nginx config (HTTP only dulu untuk certbot) ==="
# Pasang config minimal HTTP untuk certbot HTTP challenge
cat > /etc/nginx/sites-available/kompak-license << EOF
server {
    listen 80;
    server_name $DOMAIN;
    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }
    location / {
        proxy_pass http://127.0.0.1:8090;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }
}
EOF
ln -sf /etc/nginx/sites-available/kompak-license /etc/nginx/sites-enabled/kompak-license
nginx -t && systemctl reload nginx
echo "✅ nginx HTTP config aktif"

echo ""
echo "=== [5/6] Issue SSL certificate (Let's Encrypt) ==="
certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos \
    -m admin@kompakapps.com \
    --redirect || echo "⚠️  Certbot gagal. Coba manual: certbot --nginx -d $DOMAIN"

echo ""
echo "=== [6/6] Pasang nginx config FINAL (dengan SSL + security headers) ==="
cp "$APPDIR/deploy/nginx-license.conf" /etc/nginx/sites-available/kompak-license
nginx -t && systemctl reload nginx
echo "✅ nginx final config aktif"

echo ""
echo "================================================================"
echo "✅ Setup selesai!"
echo ""
echo "   URL          : https://$DOMAIN"
echo "   Password default: KompakAdmin2024 (ganti via menu Pengaturan)"
echo ""
echo "   Cek service  : systemctl status ${SERVICE_NAME}"
echo "   Lihat log    : journalctl -u ${SERVICE_NAME} -f"
echo "   Restart      : systemctl restart ${SERVICE_NAME}"
echo "================================================================"

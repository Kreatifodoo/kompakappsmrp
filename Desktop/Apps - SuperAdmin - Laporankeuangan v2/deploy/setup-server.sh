#!/bin/bash
# deploy/setup-server.sh
# ──────────────────────────────────────────────────────────────────────────
# One-time server setup untuk Linode (Ubuntu 22.04).
# Jalankan SATU KALI sebagai root atau sudo user:
#   bash deploy/setup-server.sh
# ──────────────────────────────────────────────────────────────────────────
set -euo pipefail

DOMAIN="accounting.kompakapps.com"
APPDIR="/opt/kompakapp/Desktop/Apps - SuperAdmin - Laporankeuangan v2"
BACKEND_DIR="$APPDIR/backend"
VENV_DIR="$BACKEND_DIR/.venv"

echo "=== [1/8] Update system packages ==="
apt-get update -y
apt-get install -y nginx certbot python3-certbot-nginx \
    python3.12 python3.12-venv python3.12-dev \
    postgresql-client git curl build-essential libpq-dev

echo "=== [2/8] Create app directory ==="
mkdir -p /opt/kompakapp
# Kalau repo belum ada, clone; kalau sudah ada, skip
if [ ! -d "$APPDIR/.git" ]; then
    cd /opt/kompakapp
    git clone https://github.com/Kreatifodoo/kompakappsmrp.git \
        "Desktop/Apps - SuperAdmin - Laporankeuangan v2"
fi

echo "=== [3/8] Setup Python venv for FastAPI backend ==="
python3.12 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install -e "$BACKEND_DIR"

echo "=== [4/8] Create .env for FastAPI backend ==="
if [ ! -f "$BACKEND_DIR/.env" ]; then
    cp "$BACKEND_DIR/.env.example" "$BACKEND_DIR/.env"
    # Generate JWT secret
    JWT=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))")
    sed -i "s|JWT_SECRET=.*|JWT_SECRET=$JWT|" "$BACKEND_DIR/.env"
    sed -i "s|APP_ENV=.*|APP_ENV=production|" "$BACKEND_DIR/.env"
    sed -i "s|APP_DEBUG=.*|APP_DEBUG=false|" "$BACKEND_DIR/.env"
    echo ""
    echo "⚠️  EDIT $BACKEND_DIR/.env — set DB_PRIMARY_URL, DB_REPLICA_URL, REDIS_URL"
    echo "    lalu jalankan: alembic upgrade head && python -m app.scripts.seed"
fi

echo "=== [5/8] Setup systemd services ==="

# Service: FastAPI backend
cat > /etc/systemd/system/kompak-api.service << EOF
[Unit]
Description=Kompak Accounting — FastAPI Backend
After=network.target postgresql.service

[Service]
Type=exec
User=www-data
WorkingDirectory=$BACKEND_DIR
EnvironmentFile=$BACKEND_DIR/.env
ExecStart=$VENV_DIR/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 2
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=kompak-api

[Install]
WantedBy=multi-user.target
EOF

# Service: legacy SPA server (port 8080)
cat > /etc/systemd/system/kompak-spa.service << EOF
[Unit]
Description=Kompak Accounting — Legacy SPA Server
After=network.target

[Service]
Type=exec
User=www-data
WorkingDirectory=$APPDIR/app
ExecStart=/usr/bin/python3 serve.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=kompak-spa

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable kompak-api kompak-spa
systemctl start kompak-api kompak-spa || true

echo "=== [6/8] Setup nginx ==="
cp "$APPDIR/deploy/nginx.conf" /etc/nginx/sites-available/kompakapp
ln -sf /etc/nginx/sites-available/kompakapp /etc/nginx/sites-enabled/kompakapp
rm -f /etc/nginx/sites-enabled/default

# Test config dulu (tanpa SSL, untuk certbot)
nginx -t && systemctl reload nginx

echo "=== [7/8] SSL certificate (Let's Encrypt) ==="
certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos \
    -m admin@kompakapps.com || echo "⚠️  Certbot gagal — jalankan manual"

echo "=== [8/8] Final nginx reload ==="
nginx -t && systemctl reload nginx

echo ""
echo "✅ Setup selesai!"
echo "   Frontend : https://$DOMAIN"
echo "   API docs : https://$DOMAIN/docs"
echo "   Health   : https://$DOMAIN/health"
echo ""
echo "Cek status:"
echo "  systemctl status kompak-api"
echo "  systemctl status kompak-spa"
echo "  journalctl -u kompak-api -f"

#!/bin/bash
cd "$(dirname "$0")"

echo "============================================"
echo "  FinReport - Laporan Keuangan"
echo "============================================"
echo "  Server: http://localhost:8080"
echo "  Data  : ./data/"
echo "  Files : ./filestore/"
echo "  Tekan Ctrl+C untuk menghentikan"
echo "============================================"
echo ""

# Coba buka browser otomatis (macOS: open, Linux: xdg-open)
if command -v open &>/dev/null; then
    open "http://localhost:8080" &
elif command -v xdg-open &>/dev/null; then
    xdg-open "http://localhost:8080" &
fi

# Jalankan serve.py (API + static server)
if command -v python3 &>/dev/null; then
    python3 serve.py
elif command -v python &>/dev/null; then
    python serve.py
else
    echo "[ERROR] Python tidak ditemukan!"
    echo "Silakan install Python 3:"
    echo "  - Ubuntu/Debian : sudo apt install python3"
    echo "  - CentOS/RHEL   : sudo yum install python3"
    echo "  - macOS          : brew install python3"
    exit 1
fi

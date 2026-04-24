#!/bin/bash
cd "$(dirname "$0")"

echo "============================================"
echo "  FinReport - License Generator (SuperAdmin)"
echo "============================================"
echo "  Buka browser dan akses:"
echo "  http://localhost:8081/license-generator.html"
echo "  Tekan Ctrl+C untuk menghentikan"
echo "============================================"
echo ""

# Coba buka browser otomatis (macOS: open, Linux: xdg-open)
if command -v open &>/dev/null; then
    open "http://localhost:8081/license-generator.html" &
elif command -v xdg-open &>/dev/null; then
    xdg-open "http://localhost:8081/license-generator.html" &
fi

# Cari Python yang tersedia
if command -v python3 &>/dev/null; then
    python3 -m http.server 8081
elif command -v python &>/dev/null; then
    python -m http.server 8081
else
    echo "[ERROR] Python tidak ditemukan!"
    echo ""
    echo "Alternatif: Buka license-generator.html langsung di browser"
    echo "(fitur copy key tetap berfungsi via fallback method)"
    echo ""
    echo "Untuk install Python 3:"
    echo "  - Ubuntu/Debian : sudo apt install python3"
    echo "  - CentOS/RHEL   : sudo yum install python3"
    echo "  - macOS          : brew install python3"
    exit 1
fi

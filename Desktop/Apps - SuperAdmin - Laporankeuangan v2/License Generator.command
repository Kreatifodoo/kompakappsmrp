#!/bin/bash
# ============================================
#   FinReport — License Generator Launcher
#   Double-click file ini untuk membuka
#   License Generator secara offline.
# ============================================

cd "$(dirname "$0")"

echo "========================================"
echo "  FinReport License Generator"
echo "========================================"
echo ""

# Cek Python
if command -v python3 &>/dev/null; then
    PYTHON=python3
elif command -v python &>/dev/null; then
    PYTHON=python
else
    echo "[ERROR] Python tidak ditemukan."
    echo "Install Python 3 dari https://python.org"
    echo ""
    read -p "Tekan Enter untuk keluar..."
    exit 1
fi

# Cek apakah offline HTML perlu di-build / di-update
REBUILD=false

if [ ! -f "license-generator-offline.html" ]; then
    echo "  Pertama kali: membangun versi offline..."
    REBUILD=true
else
    # Rebuild jika source atau file app lebih baru dari output
    if [ "license-generator.html" -nt "license-generator-offline.html" ] || \
       [ "app/js/app.js" -nt "license-generator-offline.html" ]; then
        echo "  Perubahan terdeteksi: memperbarui versi offline..."
        REBUILD=true
    fi
fi

if [ "$REBUILD" = true ]; then
    $PYTHON build.py --no-open
    if [ $? -ne 0 ]; then
        echo ""
        echo "[ERROR] Build gagal."
        read -p "Tekan Enter untuk keluar..."
        exit 1
    fi
else
    echo "  Versi offline sudah terkini."
fi

echo ""
echo "  Membuka License Generator di browser..."
open "license-generator-offline.html"
echo "  Selesai!"

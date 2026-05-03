#!/bin/bash
# SuperAdmin License Manager — Start Script
# Jalankan: bash start.sh
# Kemudian buka: http://localhost:8090

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║   Kompak — SuperAdmin License Manager        ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
echo "  URL    : http://localhost:8090"
echo "  Password default: KompakAdmin2024"
echo ""
echo "  Tekan Ctrl+C untuk menghentikan."
echo ""

# Kill any existing instance
pkill -f "python.*server.py" 2>/dev/null || true
sleep 0.5

python3 server.py

@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo   FinReport - License Generator (SuperAdmin)
echo ============================================
echo   Buka browser dan akses:
echo   file:///  (langsung buka license-generator.html)
echo   ATAU via server: http://localhost:8081
echo ============================================
echo.

:: Generator bisa dibuka langsung sebagai file://, tapi
:: jika ingin via HTTP server (untuk clipboard API), jalankan server ini.
echo Membuka license-generator.html via HTTP server...
echo.

:: Coba buka browser otomatis
start "" "http://localhost:8081/license-generator.html"

:: Coba python3 dulu, fallback ke python
python3 --version >nul 2>&1
if %errorlevel% == 0 (
    python3 -m http.server 8081
) else (
    python --version >nul 2>&1
    if %errorlevel% == 0 (
        python -m http.server 8081
    ) else (
        echo [ERROR] Python tidak ditemukan!
        echo Silakan install Python 3 dari https://python.org
        echo.
        echo Alternatif: Buka license-generator.html langsung di browser
        echo (fitur copy key tetap berfungsi via fallback method)
        pause
        exit /b 1
    )
)

pause

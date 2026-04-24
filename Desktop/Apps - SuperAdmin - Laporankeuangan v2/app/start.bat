@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo   FinReport - Laporan Keuangan
echo ============================================
echo   Server: http://localhost:8080
echo   Data  : .\data\
echo   Files : .\filestore\
echo   Tekan Ctrl+C untuk menghentikan
echo ============================================
echo.

:: Coba buka browser otomatis
start "" "http://localhost:8080"

:: Jalankan serve.py (API + static server)
python3 --version >nul 2>&1
if %errorlevel% == 0 (
    python3 serve.py
) else (
    python --version >nul 2>&1
    if %errorlevel% == 0 (
        python serve.py
    ) else (
        echo [ERROR] Python tidak ditemukan!
        echo Silakan install Python 3 dari https://python.org
        echo Pastikan centang "Add Python to PATH" saat instalasi.
        pause
        exit /b 1
    )
)

pause

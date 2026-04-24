@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo   FinReport License Generator
echo ========================================
echo.

:: Cek Python
python3 --version >nul 2>&1
if %errorlevel% == 0 (
    set PYTHON=python3
) else (
    python --version >nul 2>&1
    if %errorlevel% == 0 (
        set PYTHON=python
    ) else (
        echo [ERROR] Python tidak ditemukan.
        echo Install Python 3 dari https://python.org
        echo Pastikan centang "Add Python to PATH" saat instalasi.
        echo.
        pause
        exit /b 1
    )
)

:: Build jika offline HTML belum ada atau source lebih baru
set REBUILD=0
if not exist "license-generator-offline.html" (
    echo   Pertama kali: membangun versi offline...
    set REBUILD=1
) else (
    :: Cek apakah license-generator.html lebih baru (simple check via xcopy /D)
    xcopy /D /L /Y "license-generator.html" "license-generator-offline.html" >nul 2>&1
    if %errorlevel% == 0 (
        echo   Perubahan terdeteksi: memperbarui versi offline...
        set REBUILD=1
    )
)

if %REBUILD% == 1 (
    %PYTHON% build.py --no-open
    if %errorlevel% neq 0 (
        echo.
        echo [ERROR] Build gagal.
        pause
        exit /b 1
    )
) else (
    echo   Versi offline sudah terkini.
)

echo.
echo   Membuka License Generator di browser...
start "" "license-generator-offline.html"
echo   Selesai!

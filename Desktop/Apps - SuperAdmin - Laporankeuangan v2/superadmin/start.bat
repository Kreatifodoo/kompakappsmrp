@echo off
title SuperAdmin License Manager
cd /d "%~dp0"
echo.
echo =============================================
echo   Kompak -- SuperAdmin License Manager
echo =============================================
echo.
echo   URL    : http://localhost:8090
echo   Password default: KompakAdmin2024
echo.
echo   Tekan Ctrl+C untuk menghentikan.
echo.
python server.py
pause

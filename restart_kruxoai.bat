@echo off
cd /d "%~dp0"
title KruxoAI - Quick Restart
color 0b
echo ======================================================================
echo                  KRUXOAI QUICK RESTART SYSTEM
echo                  Official Platform: https://kruxoai.com
echo ======================================================================
echo.
echo [*] Terminating running KruxoAI sessions...
taskkill /F /FI "WINDOWTITLE eq KRUXOAI*" /T >nul 2>&1
taskkill /F /IM KruxoAI.exe >nul 2>&1
ping 127.0.0.1 -n 2 >nul
echo [*] Audio streams and UI memory cleared.
echo [*] Launching KruxoAI Desktop System...
echo.
start "" "C:\Python314\python.exe" main.py
echo [OK] KruxoAI has been restarted successfully!
ping 127.0.0.1 -n 3 >nul
exit

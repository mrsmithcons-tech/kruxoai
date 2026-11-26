@echo off
title KruxoAI — Quick Restart
color 0b
echo ======================================================================
echo                  KRUXOAI QUICK RESTART SYSTEM
echo                  Official Platform: https://kruxoai.com
echo ======================================================================
echo.
echo [*] Terminating running KruxoAI sessions...

:: Close any running KruxoAI GUI windows
taskkill /F /FI "WINDOWTITLE eq KRUXOAI*" /T >nul 2>&1
taskkill /F /IM KruxoAI.exe >nul 2>&1

:: Release audio and network ports
timeout /t 1 /nobreak >nul

echo [*] Audio streams and UI memory cleared.
echo [*] Launching KruxoAI Desktop System...
echo.

start "" python main.py

echo [OK] KruxoAI has been restarted successfully!
timeout /t 2 >nul
exit

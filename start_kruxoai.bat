@echo off
cd /d "%~dp0"
title KruxoAI - Desktop Launcher
color 0b
echo ======================================================================
echo                     KRUXOAI DESKTOP LAUNCHER
echo                  Official Platform: https://kruxoai.com
echo ======================================================================
echo.
echo [*] Starting KruxoAI Desktop System...
echo.
start "" "C:\Python314\pythonw.exe" main.py
exit

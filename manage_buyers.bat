@echo off
title KruxoAI Commercial Admin & DRM Manager
color 0a

:MENU
cls
echo ======================================================================
echo             KRUXOAI COMMERCIAL ADMIN & BUYER DRM MANAGER
echo             Official Platform: https://kruxoai.com
echo ======================================================================
echo.
echo   [1] List All Registered Buyers & Status (Active / Banned)
echo   [2] Generate & Register New Buyer License Key ($20)
echo   [3] Ban / Revoke a Buyer's License (Illegal Resale, Tampering)
echo   [4] Unban / Restore a Buyer's License
echo   [5] Verify a License Key
echo   [6] Check Code Integrity & Anti-Tamper Alerts
echo   [7] Exit
echo.
echo ======================================================================
set /p OPT="Select an option (1-7): "

if "%OPT%"=="1" goto LIST_BUYERS
if "%OPT%"=="2" goto GEN_KEY
if "%OPT%"=="3" goto BAN_USER
if "%OPT%"=="4" goto UNBAN_USER
if "%OPT%"=="5" goto VERIFY_KEY
if "%OPT%"=="6" goto TAMPER_CHECK
if "%OPT%"=="7" exit /b
goto MENU

:LIST_BUYERS
cls
echo ======================================================================
echo                   KRUXOAI REGISTERED BUYERS LIST
echo ======================================================================
python core/license_manager.py list
echo.
pause
goto MENU

:GEN_KEY
cls
call generate_key.bat
goto MENU

:BAN_USER
cls
echo ======================================================================
echo                   BAN & REVOKE BUYER LICENSE
echo ======================================================================
echo.
set /p TARGET="Enter Buyer Email or License Key to Ban: "
if "%TARGET%"=="" goto MENU
set /p REASON="Enter Reason (e.g. Illegal resale, Code modification): "
if "%REASON%"=="" set REASON=Violation of commercial terms (illegal resale/tampering)
echo.
python core/license_manager.py ban "%TARGET%" "%REASON%"
echo.
pause
goto MENU

:UNBAN_USER
cls
echo ======================================================================
echo                   UNBAN & RESTORE BUYER LICENSE
echo ======================================================================
echo.
set /p TARGET="Enter Buyer Email or License Key to Unban: "
if "%TARGET%"=="" goto MENU
echo.
python core/license_manager.py unban "%TARGET%"
echo.
pause
goto MENU

:VERIFY_KEY
cls
echo ======================================================================
echo                   VERIFY LICENSE AUTHENTICITY
echo ======================================================================
echo.
set /p V_EMAIL="Enter Buyer Email: "
set /p V_KEY="Enter License Key: "
echo.
python core/license_manager.py verify "%V_EMAIL%" "%V_KEY%"
echo.
pause
goto MENU

:TAMPER_CHECK
cls
echo ======================================================================
echo             CHECK CODE INTEGRITY & ANTI-TAMPER ALERTS
echo ======================================================================
echo.
python core/license_manager.py check-tamper
echo.
if exist memory\tamper_alerts.json (
    echo Security Alerts Log:
    type memory\tamper_alerts.json
) else (
    echo Zero security alerts logged. System is intact and secure.
)
echo.
pause
goto MENU

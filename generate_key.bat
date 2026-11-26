@echo off
title KruxoAI Buyer Registration & License Generator
color 0b
echo ======================================================================
echo    KRUXOAI COMMERCIAL BUYER REGISTRATION & LICENSE GENERATOR ($20)
echo    Official Platform: https://kruxoai.com
echo ======================================================================
echo.
set /p EMAIL="Enter Buyer's Email: "
if "%EMAIL%"=="" (
    echo [ERROR] Email cannot be empty.
    pause
    exit /b
)

set /p NAME="Enter Buyer's Full Name (optional): "
set /p NOTES="Enter Payment Note (e.g. Stripe $20, PayPal, Invoice #): "

echo.
echo Registering buyer and generating cryptographic license key...
echo.
python core/license_manager.py generate "%EMAIL%" "%NAME%" "%NOTES%"
echo.
echo Key has been generated and saved to your buyers database!
echo Send this key and download link to the buyer.
echo.
pause

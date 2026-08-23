@echo off
title MAJOR-PAIN-ATE - SOC Dashboard
echo.
echo   MAJOR-PAIN-ATE // open the SOC DASHBOARD
echo   ----------------------------------------
echo.
set /p IP=Laptop 1 IP address (e.g. 192.168.1.42):
if "%IP%"=="" goto :noip
start "" "http://%IP%:5000/dashboard"
timeout /t 2 >nul
exit /b 0

:noip
echo No IP entered. Run again and type laptop 1's IP (from: hostname -I).
pause
exit /b 1

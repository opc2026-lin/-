@echo off
setlocal
chcp 65001 >nul
set "PYTHONUTF8=1"
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"
title Load Forecast Verify v4.3.6

where py >nul 2>nul
if %errorlevel%==0 (
  py -3 "%SCRIPT_DIR%verify_manual_v4_3_6.py"
) else (
  python "%SCRIPT_DIR%verify_manual_v4_3_6.py"
)

echo.
echo Finished.
pause

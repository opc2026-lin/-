@echo off
setlocal
chcp 65001 >nul
set "PYTHONUTF8=1"
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"
title Load Forecast Validate v4.3.9

where py >nul 2>nul
if %errorlevel%==0 (
  py -3 "%SCRIPT_DIR%validate_manual_v4_3_9.py"
) else (
  python "%SCRIPT_DIR%validate_manual_v4_3_9.py"
)

echo.
echo Finished.
pause

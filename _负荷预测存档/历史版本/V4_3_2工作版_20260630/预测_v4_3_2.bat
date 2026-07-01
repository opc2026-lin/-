@echo off
setlocal
chcp 65001 >nul
set "PYTHONUTF8=1"
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"
title ?????? v4.3.2

where py >nul 2>nul
if %errorlevel%==0 (
  py -3 "%SCRIPT_DIR%predict_manual_v4_3_2.py"
) else (
  python "%SCRIPT_DIR%predict_manual_v4_3_2.py"
)

echo.
echo Finished.
pause


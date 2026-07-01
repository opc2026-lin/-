@echo off
setlocal
chcp 65001 >nul
set "PYTHONUTF8=1"
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"
title Load Forecast Train+Predict v5.0

where py >nul 2>nul
if %errorlevel%==0 (
  py -3 "%SCRIPT_DIR%train_predict_manual_v5_0.py"
) else (
  python "%SCRIPT_DIR%train_predict_manual_v5_0.py"
)

echo.
echo Finished.
pause

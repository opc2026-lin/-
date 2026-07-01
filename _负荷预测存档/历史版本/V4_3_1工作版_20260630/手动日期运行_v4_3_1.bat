@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

echo Load Forecast Manual Runner v4.3.1
echo.
echo Select mode:
echo   1. all
echo   2. train
echo   3. predict
echo   4. validate
echo   5. verify
set /p MODE_CHOICE=Enter number: 

if "%MODE_CHOICE%"=="1" set "MODE=all"
if "%MODE_CHOICE%"=="2" set "MODE=train"
if "%MODE_CHOICE%"=="3" set "MODE=predict"
if "%MODE_CHOICE%"=="4" set "MODE=validate"
if "%MODE_CHOICE%"=="5" set "MODE=verify"

if not defined MODE (
  echo Invalid mode.
  pause
  exit /b 1
)

where py >nul 2>nul
if %errorlevel%==0 (
  py -3 "%SCRIPT_DIR%05_auto_run_v4_3_1.py" --mode %MODE%
) else (
  python "%SCRIPT_DIR%05_auto_run_v4_3_1.py" --mode %MODE%
)

echo.
echo Finished.
pause


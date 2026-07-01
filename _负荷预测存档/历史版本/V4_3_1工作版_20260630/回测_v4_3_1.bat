@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

where py >nul 2>nul
if %errorlevel%==0 (
  py -3 "%SCRIPT_DIR%validate_manual_v4_3_1.py"
) else (
  python "%SCRIPT_DIR%validate_manual_v4_3_1.py"
)

echo.
echo Finished.
pause

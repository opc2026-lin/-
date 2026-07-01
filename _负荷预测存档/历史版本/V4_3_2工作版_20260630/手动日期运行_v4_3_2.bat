@echo off
setlocal
chcp 65001 >nul
set "PYTHONUTF8=1"

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

echo 负荷预测手动运行器 v4.3.2
echo.
echo 请选择运行模式:
echo   1. 全流程
echo   2. 只训练
echo   3. 只预测
echo   4. 只回测
echo   5. 只校验
set /p MODE_CHOICE=请输入编号: 

if "%MODE_CHOICE%"=="1" set "MODE=all"
if "%MODE_CHOICE%"=="2" set "MODE=train"
if "%MODE_CHOICE%"=="3" set "MODE=predict"
if "%MODE_CHOICE%"=="4" set "MODE=validate"
if "%MODE_CHOICE%"=="5" set "MODE=verify"

if not defined MODE (
  echo 运行模式无效。
  pause
  exit /b 1
)

where py >nul 2>nul
if %errorlevel%==0 (
  py -3 "%SCRIPT_DIR%05_auto_run_v4_3_2.py" --mode %MODE%
) else (
  python "%SCRIPT_DIR%05_auto_run_v4_3_2.py" --mode %MODE%
)

echo.
echo 运行结束。
pause


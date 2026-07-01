@echo off
setlocal
chcp 65001 >nul
set "PYTHONUTF8=1"

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

echo 负荷预测一键运行器 v4.3.2
echo.
echo 请选择运行模式:
echo   1. 全流程（训练 + 预测 + 回测）
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

set /p START_DATE=请输入目标日期 (YYYY-MM-DD): 
set /p DAYS=请输入连续天数，直接回车默认 1: 

if "%DAYS%"=="" set "DAYS=1"

where py >nul 2>nul
if %errorlevel%==0 (
  py -3 "%SCRIPT_DIR%run_forecast_v4_3_2.py" --mode %MODE% --start-date %START_DATE% --days %DAYS%
) else (
  python "%SCRIPT_DIR%run_forecast_v4_3_2.py" --mode %MODE% --start-date %START_DATE% --days %DAYS%
)

echo.
echo 运行结束。
pause


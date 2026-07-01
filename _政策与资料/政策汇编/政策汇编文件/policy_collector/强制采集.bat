@echo off
chcp 65001 >nul
title 政策采集 - 强制运行

echo ========================================
echo   政策采集 - 强制运行模式
echo ========================================
echo.

cd /d "%~dp0"
set FORCE_RUN=1
python run_daily.py

echo.
echo 按任意键关闭...
pause >nul

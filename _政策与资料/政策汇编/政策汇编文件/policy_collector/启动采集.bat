@echo off
chcp 65001 >nul
title 政策采集自动化

echo ========================================
echo   政策采集自动化系统
echo   亿云能源科技
echo ========================================
echo.
echo 正在启动采集任务...
echo.

cd /d "%~dp0"
python run_daily.py

echo.
echo 按任意键关闭...
pause >nul

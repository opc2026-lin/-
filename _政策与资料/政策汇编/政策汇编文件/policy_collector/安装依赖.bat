@echo off
chcp 65001 >nul
title 安装依赖

echo ========================================
echo   政策采集系统 - 安装依赖
echo ========================================
echo.

cd /d "%~dp0"

echo [1/2] 安装Python依赖...
pip install requests pyyaml beautifulsoup4 openpyxl playwright --quiet

echo.
echo [2/2] 安装Playwright浏览器（用于动态页面）...
python -m playwright install chromium

echo.
echo ========================================
echo   安装完成！
echo ========================================
echo.
echo 现在可以运行:
echo   - 启动采集.bat   （自动判断是否需要采集）
echo   - 强制采集.bat   （立即采集）
echo ========================================
echo.
pause

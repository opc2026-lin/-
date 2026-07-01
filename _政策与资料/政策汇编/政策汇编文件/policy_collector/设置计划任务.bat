@echo off
chcp 65001 >nul
title 设置每周一自动采集

echo ========================================
echo   设置 Windows 计划任务
echo   每周一 10:00 自动采集政策
echo ========================================
echo.

set "BAT_PATH=%~dp0启动采集.bat"

echo 任务名称: 政策采集_每周一
echo 执行文件: %BAT_PATH%
echo 执行时间: 每周一 10:00
echo.

schtasks /create /tn "政策采集_每周一" /tr "\"%BAT_PATH%\"" /sc weekly /d MON /st 10:00 /f

if %errorlevel% equ 0 (
    echo ✅ 计划任务创建成功！
    echo.
    echo 可在"任务计划程序"中查看和管理。
) else (
    echo ❌ 创建失败，请以管理员身份运行此脚本。
)

echo.
pause

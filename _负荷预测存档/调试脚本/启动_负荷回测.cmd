@echo off
setlocal EnableExtensions
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch_latest.ps1" backtest
if errorlevel 1 (
  echo.
  echo Failed to launch backtest.
  pause
)
exit /b %errorlevel%


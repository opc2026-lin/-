@echo off
setlocal EnableExtensions
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch_latest.ps1" train
if errorlevel 1 (
  echo.
  echo Failed to launch training.
  pause
)
exit /b %errorlevel%


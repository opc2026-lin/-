@echo off
setlocal EnableExtensions
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch_latest.ps1" verify
if errorlevel 1 (
  echo.
  echo Failed to launch verify.
  pause
)
exit /b %errorlevel%


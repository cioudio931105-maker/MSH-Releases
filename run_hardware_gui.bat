@echo off
setlocal
cd /d "%~dp0"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch_hardware_gui.ps1" -Diagnostics
if errorlevel 1 (
  echo.
  echo Hardware GUI failed to start.
)
pause

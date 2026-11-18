@echo off
setlocal
for %%I in ("%~dp0..\..") do set "MSH_ROOT=%%~fI\"
cd /d "%MSH_ROOT%"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%MSH_ROOT%launch_hardware_gui.ps1" -Diagnostics
if errorlevel 1 (
  echo.
  echo Hardware GUI failed to start.
)
pause

@echo off
setlocal
for %%I in ("%~dp0..\..") do set "MSH_ROOT=%%~fI\"
cd /d "%MSH_ROOT%"
call "%MSH_ROOT%scripts\diagnostics\run_hardware_gui.bat"

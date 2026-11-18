@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_EXE=python"

if exist "..\.venv312\Scripts\python.exe" (
  "..\.venv312\Scripts\python.exe" -c "import sys" >nul 2>nul
  if not errorlevel 1 set "PYTHON_EXE=..\.venv312\Scripts\python.exe"
)

if "%PYTHON_EXE%"=="python" if exist "..\.venv\Scripts\python.exe" (
  "..\.venv\Scripts\python.exe" -c "import sys" >nul 2>nul
  if not errorlevel 1 set "PYTHON_EXE=..\.venv\Scripts\python.exe"
)

"%PYTHON_EXE%" "offline_analysis_gui.py"
if errorlevel 1 (
  echo.
  echo Offline analysis launcher failed.
  pause
)

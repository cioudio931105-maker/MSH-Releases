@echo off
setlocal
chcp 65001 >nul
set "testPython=%~dp0.venv312\Scripts\python.exe"
set "testPythonw=%~dp0.venv312\Scripts\pythonw.exe"
if not exist "%testPython%" (
    echo 找不到專案的 .venv312 Python 環境。請先建立原始碼執行環境。
    pause
    exit /b 1
)
"%testPython%" -c "import tkinter, serial" >nul 2>&1
if errorlevel 1 (
    echo 專案環境缺少 tkinter 或 pyserial，請先檢查環境。
    pause
    exit /b 1
)
start "" "%testPythonw%" "%~dp0launch_basic_motor_test.pyw"
exit /b 0

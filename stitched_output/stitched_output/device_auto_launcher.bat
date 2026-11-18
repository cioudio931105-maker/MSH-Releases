@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "ROOT=%~dp0"
set "PROJECT_DIR=%ROOT%stitched_output"
set "WINDOW_TITLE=Stepper Drag UI"
set "HAS_ARGS=0"
set "VENV_PY=%PROJECT_DIR%\.venv\Scripts\python.exe"
set "VENV_PYW=%PROJECT_DIR%\.venv\Scripts\pythonw.exe"
set "D_GPU_PY=D:\Cell_Project_gpu_env\python.exe"
set "D_GPU_PYW=D:\Cell_Project_gpu_env\pythonw.exe"
set "WORKSPACE_GPU_PY=%ROOT%..\..\.conda-gpu\python.exe"
set "WORKSPACE_GPU_PYW=%ROOT%..\..\.conda-gpu\pythonw.exe"
set "WORKSPACE_VENV_PY=%ROOT%..\..\.venv\Scripts\python.exe"
set "WORKSPACE_VENV_PYW=%ROOT%..\..\.venv\Scripts\pythonw.exe"
set "WORKSPACE_VENV312_PY=%ROOT%..\..\.venv312\Scripts\python.exe"
set "WORKSPACE_VENV312_PYW=%ROOT%..\..\.venv312\Scripts\pythonw.exe"
if not exist "!PROJECT_DIR!" (
  echo [ERROR] Project directory not found: !PROJECT_DIR!
  exit /b 1
)

if not "%~1"=="" set "HAS_ARGS=1"

if "%HAS_ARGS%"=="1" (
  set "UI_SCRIPT_ABS=%PROJECT_DIR%\hardware\move_and_capture.py"
  if not exist "!UI_SCRIPT_ABS!" set "UI_SCRIPT_ABS=%PROJECT_DIR%\hardware\stepper_drag_gui.py"
) else (
  set "UI_SCRIPT_ABS=%PROJECT_DIR%\hardware\stepper_drag_gui.py"
  if not exist "!UI_SCRIPT_ABS!" set "UI_SCRIPT_ABS=%PROJECT_DIR%\hardware\move_and_capture.py"
)
if not exist "!UI_SCRIPT_ABS!" set "UI_SCRIPT_ABS=%PROJECT_DIR%\scripts\capture_helper.py"

if not exist "!UI_SCRIPT_ABS!" (
  echo [ERROR] UI script not found.
  exit /b 1
)

set "PY_CMD="
set "PY_ARGS="
set "PYW_CMD="
set "PYW_ARGS="

set "PYTHONPATH="

call :try_cuda_python "!WORKSPACE_GPU_PY!"
call :try_cuda_python "!D_GPU_PY!"
call :try_python "!WORKSPACE_VENV312_PY!"
call :try_python "!WORKSPACE_VENV_PY!"
call :try_python "!VENV_PY!"
call :try_command python
call :try_command py

if exist "!WORKSPACE_VENV_PYW!" (
  if /I "!PY_CMD!"=="!WORKSPACE_VENV_PY!" set "PYW_CMD=!WORKSPACE_VENV_PYW!"
)

if exist "!WORKSPACE_GPU_PYW!" (
  if /I "!PY_CMD!"=="!WORKSPACE_GPU_PY!" set "PYW_CMD=!WORKSPACE_GPU_PYW!"
)

if exist "!D_GPU_PYW!" (
  if /I "!PY_CMD!"=="!D_GPU_PY!" set "PYW_CMD=!D_GPU_PYW!"
)

if exist "!WORKSPACE_VENV312_PYW!" (
  if /I "!PY_CMD!"=="!WORKSPACE_VENV312_PY!" set "PYW_CMD=!WORKSPACE_VENV312_PYW!"
)

if exist "!VENV_PYW!" (
  if /I "!PY_CMD!"=="!VENV_PY!" set "PYW_CMD=!VENV_PYW!"
)

if not defined PYW_CMD (
  where pythonw >nul 2>nul
  if not errorlevel 1 set "PYW_CMD=pythonw"
)

if not defined PYW_CMD (
  where pyw >nul 2>nul
  if not errorlevel 1 set "PYW_CMD=pyw"
)

if not defined PY_CMD (
  echo [ERROR] Python not found. Please install Python.
  exit /b 1
)

echo [INFO] Selected interpreter: "!PY_CMD!" !PY_ARGS!

if defined PYW_CMD if "%HAS_ARGS%"=="0" (
  echo [INFO] Launching no-console: "!PYW_CMD!" !PYW_ARGS! "!UI_SCRIPT_ABS!"
  start "!WINDOW_TITLE!" /D "!PROJECT_DIR!" "!PYW_CMD!" !PYW_ARGS! "!UI_SCRIPT_ABS!"
) else (
  echo [INFO] Launching: "!PY_CMD!" !PY_ARGS! "!UI_SCRIPT_ABS!"
  pushd "!PROJECT_DIR!" >nul
  call "!PY_CMD!" !PY_ARGS! "!UI_SCRIPT_ABS!" %*
  set "EXIT_CODE=!ERRORLEVEL!"
  popd >nul
  exit /b !EXIT_CODE!
)

exit /b 0

:try_python
if not defined PY_CMD if exist "%~1" (
  "%~1" -c "import sys" >nul 2>nul
  if not errorlevel 1 set "PY_CMD=%~1"
)
exit /b 0

:try_cuda_python
if not defined PY_CMD if exist "%~1" (
  "%~1" -c "import torch, sys; raise SystemExit(0 if torch.cuda.is_available() else 1)" >nul 2>nul
  if not errorlevel 1 set "PY_CMD=%~1"
)
exit /b 0

:try_command
if not defined PY_CMD (
  where %~1 >nul 2>nul
  if not errorlevel 1 (
    if /I "%~1"=="py" (
      %~1 -3 -c "import sys" >nul 2>nul
      if not errorlevel 1 (
        set "PY_CMD=%~1"
        set "PY_ARGS=-3"
      )
    ) else (
      %~1 -c "import sys" >nul 2>nul
      if not errorlevel 1 set "PY_CMD=%~1"
    )
  )
)
exit /b 0

@echo off
setlocal EnableExtensions EnableDelayedExpansion
for %%I in ("%~dp0..\..") do set "MSH_ROOT=%%~fI\"

set "ROOT=%MSH_ROOT%"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

set "DEFAULT_CAMERA_SERIAL=24536563"
set "DEFAULT_ARGS=--require-cuda --camera-serial %DEFAULT_CAMERA_SERIAL% --serial-port COM7 --serial-port COM8 --serial-mode open"

set "WORKSPACE_GPU_PY=%ROOT%\.conda-gpu\python.exe"
set "E_GPU_PY=E:\Cell_Project_gpu_env\python.exe"
set "D_GPU_PY=D:\Cell_Project_gpu_env\python.exe"
set "WORKSPACE_VENV312_PY=%ROOT%\.venv312\Scripts\python.exe"
set "WORKSPACE_VENV_PY=%ROOT%\.venv\Scripts\python.exe"

set "PY_CMD="
set "PY_ARGS="

call :try_cuda_python "!WORKSPACE_GPU_PY!"
call :try_cuda_python "!E_GPU_PY!"
call :try_cuda_python "!D_GPU_PY!"
call :try_python "!WORKSPACE_VENV312_PY!"
call :try_python "!WORKSPACE_VENV_PY!"
call :try_command python.exe
call :try_command python

if not defined PY_CMD (
  echo [ERROR] Python not found. Install Python or repair the project environment.
  if "%~1"=="" pause
  exit /b 1
)

echo [INFO] Selected interpreter: "!PY_CMD!"

if "%~1"=="" (
  echo [INFO] Running default hardware preflight with camera !DEFAULT_CAMERA_SERIAL! and COM7/COM8.
  call "!PY_CMD!" !PY_ARGS! -m cell_stitching_project.hardware_preflight --workspace-root "!ROOT!" !DEFAULT_ARGS!
) else (
  echo [INFO] Running hardware preflight with custom arguments.
  call "!PY_CMD!" !PY_ARGS! -m cell_stitching_project.hardware_preflight --workspace-root "!ROOT!" %*
)

set "EXIT_CODE=%ERRORLEVEL%"
if "%~1"=="" pause
exit /b %EXIT_CODE%

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
    %~1 -c "import sys" >nul 2>nul
    if not errorlevel 1 set "PY_CMD=%~1"
  )
)
exit /b 0

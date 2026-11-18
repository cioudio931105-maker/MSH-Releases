@echo off
setlocal EnableExtensions EnableDelayedExpansion
for %%I in ("%~dp0..\..") do set "MSH_ROOT=%%~fI\"

set "ROOT=%MSH_ROOT%"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

set "DEFAULT_INPUT_DIR=%ROOT%\stitched_output\stitched_output\stitched_output\captured"
set "DEFAULT_OUTPUT_DIR=%ROOT%\stitched_output\stitched_output\stitched_output\output"
set "DEFAULT_ARGS=--input_dir ""%DEFAULT_INPUT_DIR%"" --output_dir ""%DEFAULT_OUTPUT_DIR%"" --compute_device cuda --input_order coordinates --performance_profile balanced"

set "WORKSPACE_GPU_PY=%ROOT%\.conda-gpu\python.exe"
set "E_GPU_PY=E:\Cell_Project_gpu_env\python.exe"
set "D_GPU_PY=D:\Cell_Project_gpu_env\python.exe"
set "PY_CMD="
set "PY_ARGS="

call :try_cuda_python "!WORKSPACE_GPU_PY!"
call :try_cuda_python "!E_GPU_PY!"
call :try_cuda_python "!D_GPU_PY!"

if not defined PY_CMD (
  echo [ERROR] No CUDA-ready Python environment was found.
  echo [INFO] Checked:
  echo        "!WORKSPACE_GPU_PY!"
  echo        "!E_GPU_PY!"
  echo        "!D_GPU_PY!"
  if "%~1"=="" pause
  exit /b 1
)

echo [INFO] Selected interpreter: "!PY_CMD!"

if "%~1"=="" (
  if not exist "!DEFAULT_INPUT_DIR!" (
    echo [ERROR] Default input directory not found: "!DEFAULT_INPUT_DIR!"
    echo [INFO] Run from a terminal with custom arguments, for example:
    echo        .\gpu_stitch.bat --input_dir "C:\path\to\images" --output_dir "C:\path\to\output" --compute_device cuda
    pause
    exit /b 1
  )
  echo [INFO] Running default GPU stitch.
  echo [INFO] Input : "!DEFAULT_INPUT_DIR!"
  echo [INFO] Output: "!DEFAULT_OUTPUT_DIR!"
  call "!PY_CMD!" !PY_ARGS! -m cell_stitching_project.main !DEFAULT_ARGS!
) else (
  echo [INFO] Running stitch with custom arguments.
  call "!PY_CMD!" !PY_ARGS! -m cell_stitching_project.main %*
)

set "EXIT_CODE=%ERRORLEVEL%"
if "%~1"=="" pause
exit /b %EXIT_CODE%

:try_cuda_python
if not defined PY_CMD if exist "%~1" (
  "%~1" -c "import torch, sys; raise SystemExit(0 if torch.cuda.is_available() else 1)" >nul 2>nul
  if not errorlevel 1 set "PY_CMD=%~1"
)
exit /b 0

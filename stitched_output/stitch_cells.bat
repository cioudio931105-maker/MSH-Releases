@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "ROOT=%~dp0"
set "TARGET=%ROOT%stitch_cells.ps1"

if not exist "!TARGET!" (
  echo [ERROR] Target script not found: !TARGET!
  pause
  exit /b 1
)

echo [INFO] Launching stitch workflow...
echo [INFO] You can drag a folder onto this BAT, or run it directly and paste a path when prompted.
echo.

powershell -ExecutionPolicy Bypass -File "!TARGET!" %*
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if "!EXIT_CODE!"=="0" (
  echo [INFO] Stitching finished.
  echo [INFO] Latest output:
  echo [INFO]   !ROOT!stitched_output\stitched_output\output\stitched_output.png
) else (
  echo [ERROR] Stitching failed with exit code !EXIT_CODE!.
)

pause
exit /b !EXIT_CODE!

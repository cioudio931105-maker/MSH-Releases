@echo off
setlocal

cd /d "%~dp0"

set "PYTHON_EXE=%~dp0.venv312\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=%~dp0.conda-gpu\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

set "MODEL=E:\Cell_Project_training_staging\train\blood_cells_3cls_manual_annotation_continue_20260609\weights\best.pt"
if not exist "%MODEL%" set "MODEL=%~dp0stitched_output\stitched_output\stitched_output\models\blood_cells_3cls_400x_refine_20260517.pt"

set "DATA=%~dp0staging\confidence_boost_3cls\latest\data.yaml"
if not exist "%DATA%" set "DATA=E:\Cell_Project_training_staging\manual_annotation_augmented_3cls_latest\data.yaml"
if not exist "%DATA%" set "DATA=%~dp0staging\manual_annotation_augmented_3cls\latest\data.yaml"

"%PYTHON_EXE%" -m cell_stitching_project.calibrate_confidence_thresholds_3cls ^
  --model "%MODEL%" ^
  --data "%DATA%" ^
  --split val ^
  --output-dir "E:\Cell_Project_training_staging\confidence_calibration\latest" ^
  --imgsz 960 ^
  --overwrite

if errorlevel 1 (
  echo.
  echo Confidence calibration failed.
  exit /b 1
)

echo.
echo Confidence calibration completed.
echo Output: E:\Cell_Project_training_staging\confidence_calibration\latest

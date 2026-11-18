@echo off
setlocal
cd /d "%~dp0"
set "PYTHON_EXE=%~dp0.venv312\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=%~dp0.conda-gpu\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"
"%PYTHON_EXE%" -m cell_stitching_project.train_manual_annotation_3cls --data "%~dp0stitched_output\stitched_output\stitched_output\captured\manual_annotation_dataset\data.yaml" --model "%~dp0stitched_output\stitched_output\stitched_output\models\blood_cells_3cls_400x_refine_20260517.pt" --name "blood_cells_3cls_manual_annotation_refine_latest" --epochs 20 --imgsz 960 --batch 1 --device 0 --workers 0

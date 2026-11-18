@echo off
setlocal
for %%I in ("%~dp0..\..") do set "MSH_ROOT=%%~fI\"
cd /d "%MSH_ROOT%"
set "PYTHON_EXE=%MSH_ROOT%.venv312\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=%MSH_ROOT%.venv312\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=%MSH_ROOT%.venv312-cpu\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=%MSH_ROOT%.conda-gpu\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"
"%PYTHON_EXE%" -m cell_stitching_project.train_manual_annotation_3cls --data "%MSH_ROOT%stitched_output\stitched_output\stitched_output\captured\manual_annotation_dataset\data.yaml" --model "%MSH_ROOT%stitched_output\stitched_output\stitched_output\models\blood_cells_3cls_400x_refine_20260517.pt" --name "blood_cells_3cls_manual_annotation_refine_latest" --epochs 20 --imgsz 960 --batch 1 --device 0 --workers 0

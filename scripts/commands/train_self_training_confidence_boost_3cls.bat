@echo off
setlocal
for %%I in ("%~dp0..\..") do set "MSH_ROOT=%%~fI\"
cd /d "%MSH_ROOT%"

set "PYTHON_EXE=%MSH_ROOT%.venv312\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=%MSH_ROOT%.venv312\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=%MSH_ROOT%.venv312-cpu\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=%MSH_ROOT%.conda-gpu\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

set MODEL=E:\Cell_Project_training_staging\train\blood_cells_3cls_manual_annotation_continue_20260609\weights\best.pt
set PSEUDO=E:\Cell_Project_training_staging\pseudo_label_3cls\latest
set MANUAL_AUG=E:\Cell_Project_training_staging\manual_annotation_augmented_3cls_latest
set DATASET=E:\Cell_Project_training_staging\confidence_boost_3cls_self_training_latest
set TRAIN_OUT=E:\Cell_Project_training_staging\train

"%PYTHON_EXE%" -m cell_stitching_project.collect_pseudo_labels_3cls --model "%MODEL%" --output-root "%PSEUDO%" --overwrite --max-images 300 --imgsz 960
if errorlevel 1 exit /b %errorlevel%

"%PYTHON_EXE%" -m cell_stitching_project.train_confidence_boost_3cls --model "%MODEL%" --manual-augmented-root "%MANUAL_AUG%" --pseudo-root "%PSEUDO%" --dataset-out "%DATASET%" --project "%TRAIN_OUT%" --name blood_cells_3cls_self_training_confidence_latest --max-txl-train 180 --max-txl-val 60 --epochs 8 --imgsz 640 --batch 2 --device 0 --workers 0
exit /b %errorlevel%

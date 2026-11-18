@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_EXE=%~dp0.venv312\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=%~dp0.conda-gpu\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

"%PYTHON_EXE%" -m cell_stitching_project.augment_manual_annotation_dataset --overwrite --copies 8
if errorlevel 1 exit /b %errorlevel%

"%PYTHON_EXE%" -m cell_stitching_project.train_augmented_manual_annotation_3cls --epochs 30 --imgsz 960 --batch 1 --device 0 --workers 0
exit /b %errorlevel%

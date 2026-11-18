@echo off
setlocal
for %%I in ("%~dp0..\..") do set "MSH_ROOT=%%~fI\"
cd /d "%MSH_ROOT%"

set "PYTHON_EXE=%MSH_ROOT%.venv312\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=%MSH_ROOT%.venv312\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=%MSH_ROOT%.venv312-cpu\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=%MSH_ROOT%.conda-gpu\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

"%PYTHON_EXE%" -m cell_stitching_project.augment_manual_annotation_dataset --overwrite --copies 8
if errorlevel 1 exit /b %errorlevel%

"%PYTHON_EXE%" -m cell_stitching_project.train_confidence_boost_3cls --epochs 6 --imgsz 640 --batch 2 --device 0 --workers 0
exit /b %errorlevel%

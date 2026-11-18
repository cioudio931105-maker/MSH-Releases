@echo off
setlocal
cd /d "%~dp0"
set "PYTHON_EXE=%~dp0.venv312\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=%~dp0.conda-gpu\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"
"%PYTHON_EXE%" "%~dp0stitched_output\stitched_output\stitched_output\hardware\live_cell_annotator.py"

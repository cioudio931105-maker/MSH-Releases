@echo off
setlocal
for %%I in ("%~dp0..\..") do set "MSH_ROOT=%%~fI\"
cd /d "%MSH_ROOT%"
set "PYTHON_EXE=%MSH_ROOT%.venv312\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=%MSH_ROOT%.venv312\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=%MSH_ROOT%.venv312-cpu\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=%MSH_ROOT%.conda-gpu\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"
"%PYTHON_EXE%" "%MSH_ROOT%msh_app\hardware\live_cell_annotator.py"

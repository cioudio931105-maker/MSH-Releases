@echo off
setlocal

cd /d "%~dp0"

set "PYTHON_EXE=%~dp0..\.venv312\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=%~dp0..\.conda-gpu\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

echo Continue training the 3-class blood cell YOLO model from latest offline detections.
echo.
echo Default settings:
echo   min confidence: 0.65
echo   epochs: 30
echo   image size: 960
echo   batch: 2
echo   device: cuda:0
echo.
echo Extra arguments can be appended to this .bat, for example:
echo   --device cuda --batch 4
echo.

"%PYTHON_EXE%" train_three_class_from_detections.py --min-conf 0.65 --epochs 30 --batch 2 --imgsz 960 --device 0 %*

echo.
pause

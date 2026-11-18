PYTHON ?= python
APP_DIR := .
REQ_FILE := $(APP_DIR)/requirements.txt
HARDWARE_DIR := $(APP_DIR)/hardware

.PHONY: help install run-gui list-ports run-cli clean

help:
	@echo "Available targets:"
	@echo "  make install                    Install Python dependencies"
	@echo "  make run-gui                    Launch stepper drag GUI"
	@echo "  make list-ports                 List serial ports"
	@echo "  make run-cli PORT=COM3 STEPS=200 [BAUD=115200]"
	@echo "  make clean                      Remove Python cache files"

install:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r $(REQ_FILE)

run-gui:
	$(PYTHON) $(HARDWARE_DIR)/stepper_drag_gui.py

list-ports:
	$(PYTHON) $(HARDWARE_DIR)/stepper_cli.py --list

run-cli:
	@if "$(PORT)"=="" (echo Usage: make run-cli PORT=COM3 STEPS=200 [BAUD=115200] & exit /b 2)
	$(PYTHON) $(HARDWARE_DIR)/stepper_cli.py --port $(PORT) --baud $(if $(BAUD),$(BAUD),115200) --steps $(if $(STEPS),$(STEPS),0)

clean:
	$(PYTHON) -c "from pathlib import Path; import shutil; \
for d in Path('.').rglob('__pycache__'): shutil.rmtree(d, ignore_errors=True); \
print('Removed __pycache__ directories.')"

# -*- mode: python ; coding: utf-8 -*-
"""Reproducible one-directory PyInstaller build for the MSH Windows GUI."""

import os
from pathlib import Path

from msh_release_model import RELEASE_MODEL_RELATIVE_PATH

ROOT = Path(SPECPATH).resolve()
YOLO_BUILD_CONFIG = ROOT / "build" / "ultralytics"
YOLO_BUILD_CONFIG.mkdir(parents=True, exist_ok=True)
os.environ["YOLO_CONFIG_DIR"] = str(YOLO_BUILD_CONFIG)
LEGACY_ROOT = ROOT / "stitched_output" / "stitched_output" / "stitched_output"
HARDWARE_ROOT = LEGACY_ROOT / "hardware"
WBC_RELEASE_MODEL = ROOT / RELEASE_MODEL_RELATIVE_PATH

if not WBC_RELEASE_MODEL.is_file():
    raise FileNotFoundError(
        "Missing approved WBC release model: "
        f"{WBC_RELEASE_MODEL}. Restore the external model before building MSH."
    )

datas = [
    (str(ROOT / "assets" / "msh-cyberpunk-splash-640.png"), "assets"),
    (str(ROOT / "assets" / "msh-cyberpunk-splash.png"), "assets"),
    (str(ROOT / "assets" / "msh-pixel-icon.ico"), "assets"),
    (str(ROOT / "assets" / "msh-pixel-icon.png"), "assets"),
    (str(ROOT / "assets" / "branding" / "v1"), "assets/branding/v1"),
    (str(ROOT / "cell_stitching_project"), "cell_stitching_project"),
    (str(HARDWARE_ROOT), "stitched_output/stitched_output/stitched_output/hardware"),
    (str(LEGACY_ROOT / "cell_identification"), "stitched_output/stitched_output/stitched_output/cell_identification"),
    (str(WBC_RELEASE_MODEL), "stitched_output/stitched_output/stitched_output/models"),
    (str(ROOT / "yolov8n.pt"), "stitched_output/stitched_output/stitched_output/models"),
]
binaries = []
hiddenimports = [
    "arduino_stepper",
    "cell_identification",
    "kornia_rs",
    "pypylon",
    "pypylon.genicam",
    "pypylon.pylon",
    "tkinter.filedialog",
    "tkinter.messagebox",
    "tkinter.ttk",
]

a = Analysis(
    [str(ROOT / "launch_msh.pyw")],
    pathex=[str(ROOT), str(HARDWARE_ROOT), str(LEGACY_ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MSH",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(ROOT / "assets" / "msh-pixel-icon.ico"),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="MSH",
)

# -*- mode: python ; coding: utf-8 -*-
"""Reproducible one-directory PyInstaller build for the MSH Windows GUI."""

import os
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

from msh_distribution import application_files

ROOT = Path(SPECPATH).resolve()
YOLO_BUILD_CONFIG = ROOT / "build" / "ultralytics"
YOLO_BUILD_CONFIG.mkdir(parents=True, exist_ok=True)
os.environ["YOLO_CONFIG_DIR"] = str(YOLO_BUILD_CONFIG)
LEGACY_ROOT = ROOT / "msh_app"
HARDWARE_ROOT = LEGACY_ROOT / "hardware"

datas = [
    (str(ROOT / "LICENSE"), "."),
    (str(ROOT / "THIRD_PARTY_NOTICES.md"), "."),
    (str(ROOT / "assets" / "msh-cyberpunk-splash-640.png"), "assets"),
    (str(ROOT / "assets" / "msh-cyberpunk-splash.png"), "assets"),
    (str(ROOT / "assets" / "msh-pixel-icon.ico"), "assets"),
    (str(ROOT / "assets" / "msh-pixel-icon.png"), "assets"),
]
for subtree in (
    "licenses",
    "assets/branding/v1",
    "cell_stitching_project",
    "microscope_stitcher_project",
    "msh_app/hardware",
    "msh_app/cell_identification",
):
    datas.extend(application_files(ROOT, subtree))
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
sys.path.insert(0, str(ROOT / "microscope_stitcher_project"))
hiddenimports.extend(collect_submodules("microscope_stitcher"))

a = Analysis(
    [str(ROOT / "launch_msh.pyw")],
    pathex=[str(ROOT), str(HARDWARE_ROOT), str(LEGACY_ROOT), str(ROOT / "microscope_stitcher_project")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
# Dependency hooks can collect demo photos, datasets or optional weights.
weight_suffixes = {".pt", ".pth", ".ckpt", ".onnx", ".engine", ".safetensors", ".tflite", ".h5", ".keras", ".pb", ".weights", ".omc", ".caffemodel"}
excluded_resource_prefixes = (
    "ultralytics/assets/",
    "matplotlib/mpl-data/sample_data/",
    "pypylon/pylondataprocessingplugins/",
    "pypylon/dataprocessingpluginsb/",
    "pypylon/docs/",
)
a.datas = [
    entry for entry in a.datas
    if Path(entry[0]).suffix.lower() not in weight_suffixes
    and not entry[0].replace("\\", "/").lower().startswith(excluded_resource_prefixes)
]
a.binaries = [
    entry for entry in a.binaries
    if not entry[0].replace("\\", "/").lower().startswith(excluded_resource_prefixes)
]
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

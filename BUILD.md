# MSH release build

## Supported build baseline

- Windows 10 or 11, 64-bit
- Python 3.12.13 (the tested development baseline)
- PyInstaller 6 and Inno Setup 6

Use a clean, tested Python 3.12 environment. Do not build from Conda base or
rely on a developer PATH. CPU is the default public build because it works on
computers without NVIDIA CUDA. Keep CPU and GPU dependencies in separate
environments.

```powershell
.\.venv312\python.exe -m venv .venv312-cpu
.\.venv312-cpu\Scripts\python.exe -m pip install -r requirements-cpu.txt -r requirements-build.txt
.\scripts\build_release.ps1 -Runtime cpu -PythonPath .\.venv312-cpu\Scripts\python.exe
```

The CPU build creates an onedir application at `dist\cpu\MSH\` and
`dist\release\MSH_Setup_v<version>_CPU.exe` plus its SHA-256 checksum. Onedir
is intentional: PyTorch, OpenCV,
pypylon, and native DLLs are materially more reliable than a self-extracting
onefile executable.

For the optional NVIDIA/CUDA build, prepare a separate environment with
`requirements-gpu.txt`, then run:

```powershell
.\scripts\build_release.ps1 -Runtime gpu -PythonPath .\.venv312\python.exe
```

This creates `dist\gpu\MSH\` and a `_GPU.exe` installer. Both installers use
the same application identity, so installing one variant replaces/upgrades the
other rather than creating two conflicting MSH installations.

## Client review update manifest

MSH checks the public release-only manifest configured in `msh_update.py`. Do
not point client builds at a private repository and never embed a GitHub token
in the application. Start from `release/latest.example.json`, then for every
review release:

1. Build the final installer.
2. Generate its SHA-256 checksum.
3. Upload the installer and checksum to the public release-only repository.
4. Replace every example value, especially `version`, URLs, `sha256`, release
   notes, and date.
5. Publish the completed file as `latest.json` only after the installer asset is
   available at its HTTPS URL.

The updater only opens the download after user confirmation. It does not execute
the unsigned installer or replace running application files.

For a quick packaging smoke test without Inno Setup:

```powershell
.\scripts\build_release.ps1 -Runtime cpu -PythonPath .\.venv312-cpu\Scripts\python.exe -SkipInstaller
```

## Model and hardware prerequisites

`yolov8n.pt` is packaged only as a generic fallback. Do not release WBC claims
until an approved WBC model is supplied through `%LOCALAPPDATA%\MSH\models\`
and independently validated. Basler operation requires the official pylon
Runtime and the correct camera-interface driver on the target computer.

Never run motor, XY-stage, or camera-motion validation merely to test packaging.
Those tests require an authorised B-site hardware session.

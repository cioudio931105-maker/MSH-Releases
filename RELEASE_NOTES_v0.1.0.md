# Microscope Scanner Helper v0.1.0 — Release candidate

## New

- Windows onedir application and Inno Setup installer pipeline.
- General-user CPU installer plus an independently buildable optional GPU
  variant; variant filenames do not overwrite one another.
- Per-user installation, Start Menu shortcut, optional desktop shortcut,
  uninstaller, and SHA-256 checksum generation.
- Per-user logs under `%LOCALAPPDATA%\MSH\` and default capture/stitch output
  under `%USERPROFILE%\Documents\MSH\`.

## Improvements

- The GUI no longer auto-applies a developer-machine Basler PFS profile.
- Model resolution checks `%LOCALAPPDATA%\MSH\models\` before built-in
  fallbacks.
- Unexpected startup errors are logged without showing raw tracebacks to users.

## Requirements

- Windows 10/11 x64.
- Official Basler pylon Runtime and correct camera-interface driver for Basler
  use.
- An approved WBC model installed separately for validated cell detection.

## Known issues / release gates

- The CPU installer has passed a same-machine install, 20-second GUI startup,
  and uninstall smoke test. A clean Windows machine test is still required.
- The installer is not yet digitally code-signed and may trigger Windows
  SmartScreen warnings.
- No physical Basler, COM, Arduino, XY-stage, motor-safety, or end-to-end scan
  test was performed in this packaging session.
- Ultralytics licensing and WBC model redistribution rights require project-owner
  approval before public publication.

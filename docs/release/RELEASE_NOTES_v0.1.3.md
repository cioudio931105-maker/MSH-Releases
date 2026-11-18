# MSH v0.1.3 client review build

## Release correction

This supersedes the incorrectly packaged v0.1.2 CPU installer. Do not use
v0.1.2 as evidence of the current source behaviour: its installer was created
from a stale PyInstaller output directory and did not contain the intended
post-v0.1.1 application changes.

## Included application baseline

- Current GUI and live-preview source from commit `79f55879881d446619aa4d2a5c3b14276cba087c`.
- Current manual motor-control UI and hardware helper source as recorded in
  the accompanying build manifest.
- Verified WBC-only review model `wbc_focus_yolov8n_e_20260611.pt`.

## Packaging evidence

The installer is accompanied by a SHA-256 checksum and
`MSH_Setup_v0.1.3_CPU.exe.build-manifest.json`. Review the manifest's version,
Git commit, executable hash, and critical-source hashes before distribution.

## Review limitations

This remains an unsigned client-review build. CPU inference is included; no
Basler, COM, Arduino, XY-platform, motor, or full-scan hardware test is implied
by this packaging correction.

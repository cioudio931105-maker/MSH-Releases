# Hardware Preflight Checklist

Use this checklist before a real machine run so camera, models, output folders, and motor controllers are ready.

Run the preflight before opening the UI or any serial monitor. If the UI already holds `COM7` / `COM8`, an `open` check will fail by design because the port is already locked.

## What It Checks

`python -m cell_stitching_project.hardware_preflight` verifies:

- Python environment and required modules
- Basler camera detection, with optional serial lock to a specific camera
- Legacy cell-preview/default cell model: `blood_cells_3cls_yolov8n_20260429.pt`
- Live detection preset model: `waste_sorting_v1`
- Output directories for capture, stitch, and live sessions
- Serial / PLC ports by enumeration, open test, or Arduino-style `PING` / `PONG`

## Recommended Command

Run this from the workspace root:

```powershell
python -m cell_stitching_project.hardware_preflight `
  --workspace-root "C:\Cell_Project\Cell_Project" `
  --camera-serial "24536563" `
  --serial-port COM7 `
  --serial-port COM8 `
  --serial-mode open `
  --capture-output-dir "C:\Cell_Project\Cell_Project\stitched_output\stitched_output\stitched_output\captured" `
  --stitch-output-dir "C:\Cell_Project\Cell_Project\stitched_output\stitched_output\stitched_output\output" `
  --live-output-dir "C:\Cell_Project\Cell_Project\session_output"
```

## One-Click Launcher

Double-click [hardware_preflight.bat](/C:/Cell_Project/Cell_Project/hardware_preflight.bat) from the workspace root.

Its default run uses:

- camera serial `24536563`
- `COM7`
- `COM8`
- `serial-mode open`

If you want custom arguments, run it from a terminal:

```powershell
.\hardware_preflight.bat --serial-mode detect --serial-port COM7 --serial-port COM8
```

## Serial Modes

- `detect`: only check whether the COM port exists in Windows
- `open`: open and close the port to confirm it is usable
- `ping`: send `PING` and require an Arduino-style `PONG` reply

Use `ping` only for controllers that implement that handshake. For a generic PLC, keep `open`.

## Typical Pass Criteria

- Basler camera is listed and the selected serial matches the expected camera
- `legacy_cell_preview` passes and loads `blood_cells_3cls_yolov8n_20260429.pt`
- `live_detection_preset` passes and loads `waste_sorting_v1_best.pt`
- Capture, stitch, and live output directories are writable
- Required COM ports open successfully
- Overall status is `PASS`

## If You Need JSON

```powershell
python -m cell_stitching_project.hardware_preflight `
  --workspace-root "C:\Cell_Project\Cell_Project" `
  --json
```

## Common Failure Cases

- `Basler camera ... was not found`
  Check USB, Pylon Viewer, camera serial, and whether another app already holds the camera.

- `model exists but failed to load`
  Usually means the active Python does not have `ultralytics` or a matching `torch` install.

- `Output directory is not writable`
  Check path permissions and whether the folder is on a disconnected drive.

- `Serial port ... could not be opened`
  Another app may already hold the COM port, or the selected baud / controller is wrong.

- `Serial port ... is present but currently locked by another application`
  The controller is visible in Windows, but the UI, Arduino IDE serial monitor, or another tool already opened that COM port.

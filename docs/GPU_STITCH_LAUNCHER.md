# GPU Stitch Launcher

Use [gpu_stitch.bat](/C:/Cell_Project/Cell_Project/gpu_stitch.bat) for one-click stitching from the workspace root.

## Default Double-Click Run

Double-click `gpu_stitch.bat` to run:

- input dir: `C:\Cell_Project\Cell_Project\stitched_output\stitched_output\stitched_output\captured`
- output dir: `C:\Cell_Project\Cell_Project\stitched_output\stitched_output\stitched_output\output`
- device: `cuda`
- input order: `coordinates`
- performance profile: `balanced`

The launcher now only accepts a CUDA-ready Python environment and prefers:

1. `C:\Cell_Project\Cell_Project\.conda-gpu\python.exe`
2. `E:\Cell_Project_gpu_env\python.exe`
3. `D:\Cell_Project_gpu_env\python.exe`

If none of those interpreters has `torch.cuda.is_available() == True`, the launcher stops with an error instead of silently falling back to CPU.

## Custom Run

From PowerShell:

```powershell
.\gpu_stitch.bat --input_dir "C:\path\to\images" --output_dir "C:\path\to\output" --compute_device cuda
```

Example with coordinates and no post-stitch detection:

```powershell
.\gpu_stitch.bat `
  --input_dir "C:\Cell_Project\Cell_Project\staging\gpu_stitch_smoke_input_20260417" `
  --output_dir "C:\Cell_Project\Cell_Project\staging\gpu_stitch_smoke_output_manual" `
  --compute_device cuda `
  --input_order coordinates `
  --disable_post_stitch_detection
```

## Main Outputs

- `stitched_result.png`
- `overlay_preview.png`
- `shifts.json`
- `shifts.csv`
- `stitch_log.txt`

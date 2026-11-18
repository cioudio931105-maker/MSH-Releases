> 歷史快照：這是核心／資料分離前的 README，原相對位置為專案根目錄。日常操作請看目前根目錄 README。

# Microscope-Scanner-Helper_MSH (MSH)

MSH first-party application source is licensed under GNU AGPL version 3
(`AGPL-3.0-only`); see [LICENSE](LICENSE). Third-party code retains its own terms
and attribution in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and [licenses](licenses/README.md).
The selected release direction is public application source with privately managed
user models/data; see [source release preparation](docs/OPEN_SOURCE_RELEASE_zh_TW.md).

## Application-only distribution

MSH supplies functionality only. **Users provide their own models and data.**
New source commits, source handoffs and installers exclude weights, datasets,
research images, annotations and experiment outputs. Local training remains
supported; its inputs and results stay ignored. See [the distribution policy](docs/APPLICATION_ONLY_POLICY.md),
including the limits of existing Git history and older installers.

MSH is a research project for microscope scanning, WBC AI detection, image
stitching, Basler camera integration, and XY-platform/Arduino hardware control.
Models and research datasets are user-supplied local assets.

## Release layout and local artifacts

Application GUI and hardware source now live in `msh_app/`. Command utilities are in
`scripts/commands/`, environment/transfer tools in `scripts/maintenance/`, and release
documents in `docs/release/`. See [the project map](docs/PROJECT_MAP.md) and
[release layout and artifact review](docs/RELEASE_LAYOUT.md).

Daily startup uses the installed `MSH.exe` or a shortcut to `pythonw.exe` and
`launch_msh.pyw`; CMD is used only by explicit command/diagnostic tools. Existing
local models, datasets, recordings and outputs remain at their original paths.
The offline artifact browser inventories them for review and never deletes them.

## Windows user installation

For the complete direct-install and future release workflow, see
[MSH 直接安裝與往後發佈流程](docs/DIRECT_INSTALL_RELEASE_WORKFLOW_zh_TW.md).
The application-only installer is not published yet; existing v0.1.x artifacts
must not be described as model-free builds.

Download `MSH_Setup_v<version>_CPU.exe` and its `.sha256` checksum from the
matching GitHub Release. Verify the SHA-256 value, run the installer, then start **MSH**
from the Start Menu (or the optional desktop shortcut). The installer is per-user
and does not require administrator rights; it does not install Git, Python,
Conda, or a command-line environment.

MSH is designed for offline operation. Images, crops, CSV, JSON, logs, and scan
results remain on the local computer. Default capture and stitch output is under
`Documents\MSH\`; logs and application state are under `%LOCALAPPDATA%\MSH\`.
Uninstalling MSH removes the application only, not those user-data folders.

### Client review updates

Packaged review builds include **說明 > 檢查更新...**. MSH also performs one
silent check shortly after startup. When a newer review build is available, it
shows the version, release notes, and SHA-256 value, then asks before opening
the installer download in the user's browser. MSH never downloads or runs an
installer silently. Install the newer build over the existing MSH installation;
the stable Inno Setup `AppId` keeps it as the same application.

Because the source repository is not anonymously accessible, public update
metadata and installer assets must be published from a separate release-only
location. The application does not contain a GitHub token or other private
credential.

### Hardware and model prerequisites

- Basler features require the official Basler pylon Runtime and the driver for
  the connected camera interface. The app does not bundle arbitrary SDK files.
- Select COM ports in the GUI; no application COM port is hardcoded.
- A Basler PFS profile is never applied automatically. Choose it explicitly for
  the active camera.
- New builds include no WBC or generic fallback model. Select your own existing
  local detection model in the GUI. Missing models are not downloaded by MSH.
- Research presets below describe optional local paths, not included files. Supply
  your own models and optional label lists. See [models/README.md](models/README.md).

### Troubleshooting

- **Camera unavailable:** confirm pylon Runtime, camera driver, cable/power, and
  that Pylon Viewer is not holding the camera.
- **COM port unavailable:** reconnect the controller and select the detected
  port in MSH; the GUI can still open without an Arduino.
- **GPU unavailable:** the general `_CPU.exe` installer intentionally runs
  inference on CPU. A separately tested `_GPU.exe` variant may be supplied for
  supported NVIDIA systems.
- **Model not found:** select your own existing local model with the model chooser.
- **Startup failed:** inspect `%LOCALAPPDATA%\MSH\msh.log`.

Release maintainers should follow [BUILD.md](docs/release/BUILD.md),
[RELEASE_CHECKLIST.md](docs/release/RELEASE_CHECKLIST.md), and
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Current candidate notes are in
[RELEASE_NOTES_v0.1.4.md](docs/release/RELEASE_NOTES_v0.1.4.md); internal candidate evidence is in
[RELEASE_CANDIDATE_v0.1.4.md](docs/RELEASE_CANDIDATE_v0.1.4.md).

## 400x WBC-Only Detection

For single-class 400x white-blood-cell detection, manually select the integrated `wbc_400x` preset, which points to:

- model: `stitched_output\stitched_output\stitched_output\models\wbc_focus_yolov8n_20260611.pt`
- labels: `stitched_output\stitched_output\stitched_output\models\wbc_400x_labels.txt`
- class: `WBC`

The following D-drive locations are examples of B-machine local storage, not
required paths on every machine. Large external datasets and generated 400x
WBC-only training sets may be kept there:

- MLL23 downloads: `D:\Cell_Project_Datasets\MLL23`
- generated YOLO datasets: `D:\Cell_Project_training_staging\wbc400_wbc_only`
- YOLO training runs: `D:\Cell_Project_training_staging\train\wbc_400x`

Live Basler detection:

```powershell
python -m cell_stitching_project.detect_live `
  --preset wbc_400x `
  --output-dir "C:\path\to\session_output" `
  --save-crops
```

Offline image detection:

```powershell
python -m cell_stitching_project.cell_identification `
  --model "stitched_output\stitched_output\stitched_output\models\wbc_focus_yolov8n_20260611.pt" `
  --class-file "stitched_output\stitched_output\stitched_output\models\wbc_400x_labels.txt" `
  --source "C:\path\to\400x_images" `
  --output-dir "C:\path\to\output\wbc_400x"
```

## Five-Class WBC Detection

The recognition pipeline now has a first-class five-WBC label set:

- `neutrophil`
- `lymphocyte`
- `monocyte`
- `eosinophil`
- `basophil`

Use `datasets\wbc_400x\classes.txt` for SSD/ONNX label loading, or `datasets\wbc_400x\data.yaml` for YOLO training. The existing `TXL-PBC` `data.yaml` remains the original three-class blood-cell setup (`WBC`, `RBC`, `Platelets`), so do not reuse those old annotations as five-class labels unless they have been relabeled by subtype.

Example inference after training/exporting a five-class model:

```powershell
python -m cell_stitching_project.cell_identification `
  --model "C:\path\to\wbc_5cls_yolov8n.pt" `
  --source "C:\path\to\images" `
  --class-file "datasets\wbc_400x\classes.txt" `
  --output-dir "C:\path\to\output\cell_identification"
```

For 400x WBC fine-tuning, place relabeled 400x images and YOLO labels under the paths referenced by `datasets\wbc_400x\data.yaml`, then run:

```powershell
python -m cell_stitching_project.train_yolo_wbc400 `
  --data "datasets\wbc_400x\data.yaml" `
  --model "yolov8s.pt" `
  --epochs 260 `
  --imgsz 1280 `
  --batch 4 `
  --device 0
```

After training, copy the run's `weights\best.pt` to `stitched_output\stitched_output\stitched_output\models\wbc_5cls_400x_yolov8s.pt` and use preset `wbc_5cls_400x`.

If confidence is still weak, collect the low-confidence real 400x cases, manually correct labels, and add them back to `datasets\wbc_400x`:

```powershell
python -m cell_stitching_project.collect_wbc400_hard_examples `
  --model "stitched_output\stitched_output\stitched_output\models\wbc_5cls_400x_yolov8s.pt" `
  --source "C:\path\to\400x_captures" `
  --class-file "datasets\wbc_400x\classes.txt" `
  --review-below 0.65
```

## Live Detection Default

`python -m cell_stitching_project.detect_live` 現在預設使用病理主流程的三分類 YOLO 模型 `blood_cells_3cls`（WBC、RBC、Platelets）。

```powershell
python -m cell_stitching_project.detect_live `
  --output-dir "C:\path\to\session_output" `
  --save-crops
```

`waste_sorting_v1` 仍保留為 alternate / experimental preset；需要時請明確指定 `--preset waste_sorting_v1`。

如果要改回舊 SSD 流程：

```powershell
python -m cell_stitching_project.detect_live `
  --preset none `
  --backend ssd `
  --net mb1-ssd `
  --model "C:\path\to\model.pth" `
  --labels "C:\path\to\labels.txt" `
  --output-dir "C:\path\to\session_output" `
  --save-crops
```

`Cell_Project` 目前同時包含兩套系統：

1. 主線 Python 套件 `cell_stitching_project/`
2. GUI 與硬體控制程式 `msh_app/`

如果你現在要做新功能、修主流程、跑拼接或模型流程，優先看 `cell_stitching_project/`。
如果你要處理 Tk GUI、Arduino 步進馬達、舊版掃描流程，再看 legacy 區。

## 主要功能

- 顯微影像拼接
- 細胞辨識與後處理
- Basler 相機擷取
- Basler 即時偵測
- VOC 資料集整理
- SSD 訓練、評估與 ONNX 匯出

## 主要入口

影像拼接：

```powershell
python -m cell_stitching_project.main `
  --input_dir "C:\path\to\images" `
  --output_dir "C:\path\to\output"
```

細胞辨識：

```powershell
python -m cell_stitching_project.cell_identification `
  --model "C:\path\to\best.pt" `
  --source "C:\path\to\images" `
  --output-dir "C:\path\to\output\cell_identification"
```

Basler 擷取：

```powershell
python -m cell_stitching_project.capture_basler `
  --output-dir "C:\path\to\captures" `
  --camera-serial "<optional-serial>"
```

Basler 即時偵測：

```powershell
python -m cell_stitching_project.detect_live `
  --source basler `
  --backend ssd `
  --net mb1-ssd `
  --model "C:\path\to\model.pth" `
  --labels "C:\path\to\labels.txt" `
  --output-dir "C:\path\to\session_output" `
  --save-crops
```

VOC 資料集整理：

```powershell
python -m cell_stitching_project.prepare_voc_dataset `
  --input-dir "C:\path\to\flat_or_voc_dataset" `
  --output-dir "C:\path\to\voc_dataset"
```

SSD 訓練：

```powershell
python -m cell_stitching_project.train_ssd `
  --dataset-type voc `
  --datasets "C:\path\to\voc_dataset" `
  --net mb1-ssd `
  --batch-size 8 `
  --num-epochs 50 `
  --use-cuda true `
  --checkpoint-folder "C:\path\to\models"
```

SSD 評估：

```powershell
python -m cell_stitching_project.eval_ssd `
  --net mb1-ssd `
  --trained-model "C:\path\to\models\mb1-ssd-Epoch-49-Loss-1.234567.pth" `
  --dataset-type voc `
  --dataset "C:\path\to\voc_dataset" `
  --label-file "C:\path\to\models\labels.txt" `
  --eval-dir "C:\path\to\eval_results"
```

SSD 匯出 ONNX：

```powershell
python -m cell_stitching_project.export_ssd_onnx `
  --net mb1-ssd `
  --input "C:\path\to\models\mb1-ssd-Epoch-49-Loss-1.234567.pth" `
  --labels "C:\path\to\models\labels.txt" `
  --output "C:\path\to\models\mb1-ssd.onnx"
```

## 環境安裝

CPU 基本依賴：

```powershell
pip install -r cell_stitching_project\requirements.txt
```

GPU 額外依賴：

```powershell
pip install -r cell_stitching_project\requirements-gpu.txt
```

Basler 相關流程還需要：

- 先在主機安裝 Basler Pylon runtime/SDK
- 再安裝 `pypylon`

SSD ONNX 匯出還需要：

- `onnx`
- `onnxscript`

## 文件索引

- 專案地圖：[docs/PROJECT_MAP.md](docs/PROJECT_MAP.md)
- 套件說明：[cell_stitching_project/README.md](cell_stitching_project/README.md)
- 新機建置：[docs/NEW_MACHINE_SETUP.md](docs/NEW_MACHINE_SETUP.md)

## 新機建置

若要在新的 Windows 機器上重建完整專案，包含 legacy GUI、Basler 支援、GPU 拼接與模型包裝，建議使用：

```powershell
.\scripts\maintenance\setup_gpu_env.ps1 -EnvPath "E:\Cell_Project_gpu_env" -RequireCuda
python -m cell_stitching_project.verify_environment --workspace-root "C:\Cell_Project\Cell_Project" --require-cuda
```

詳細步驟請看 [docs/NEW_MACHINE_SETUP.md](docs/NEW_MACHINE_SETUP.md)。

## Windows GUI 啟動

完成 Python 環境安裝後，可建立類似一般 Windows 應用程式的桌面捷徑：

```powershell
.\install_gui_shortcut.ps1
```

若要同時建立桌面與開始功能表捷徑：

```powershell
.\install_gui_shortcut.ps1 -Location Both
```

日常使用時雙擊 `MSH`，啟動時不會顯示 CMD 視窗。捷徑會指向目前的專案位置；移動 repository 後請重新執行安裝腳本。

MSH 的正式第一版識別（捷徑／視窗圖示與啟動畫面）保存在
[`assets/branding/v1/README.md`](assets/branding/v1/README.md)；後續設計請以新版本資料夾保存。

若 GUI 無法啟動，請執行保留命令視窗的診斷入口：

```powershell
.\scripts\diagnostics\run_hardware_gui.bat
```

來源版的啟動紀錄同時寫入 `%LOCALAPPDATA%\MSH\msh.log` 與 `logs/hardware_gui_startup.log`；`logs/` 為本機執行資料，不應加入 Git。可在不啟動 GUI 或連接硬體的情況下檢查啟動環境：

```powershell
.\launch_hardware_gui.ps1 -CheckOnly
```

## Cross-machine Git workflow

A is primarily the development machine. B is primarily the hardware-verification
machine. Do not claim Basler, COM, XY-platform, motor, Arduino, or complete scan
success unless it has been tested on B with the applicable hardware.

Before transferring work between machines, inspect the worktree and make sure it
is clean before pulling:

```powershell
git status
git pull --ff-only
```

After making and reviewing a focused change, stage only explicitly named files or
directories, then commit and push to the official remote:

```powershell
git status
git add README.md cell_stitching_project/README.md package_for_transfer.ps1
git commit -m "Describe the focused change"
git push origin
```

Never use `git add .` or `git add -A` in this project.

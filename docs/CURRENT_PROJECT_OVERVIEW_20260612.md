# Cell_Project Current Project Overview

更新日期：2026-06-12

本文件是「非破壞式統整」：只整理目前專案內容與風險邊界，不搬移、不刪除、不改名任何既有程式、模型、資料集、輸出檔或環境資料夾。

## 目前狀態摘要

- 工作區外層：`C:\Cell_Project`
- 主要專案根目錄：`C:\Cell_Project\Cell_Project`
- 已建立完整備份：`E:\Cell_Project_backup_20260612_042323`
- 備份日誌：`E:\Cell_Project_backup_20260612_042323.robocopy.log`
- 專案目前約有 `87,697` 個檔案、`7,333` 個資料夾、總量約 `11.427 GB`
- 主要內容是顯微影像拼接、血球辨識、Basler/硬體控制、離線影片分析、訓練資料與 legacy GUI/輸出

## Git 與資料保護注意事項

目前有兩層 Git 狀態需要小心：

- 外層 `C:\Cell_Project\.git` 把 `Cell_Project/` 視為未追蹤內容。
- 內層 `C:\Cell_Project\Cell_Project\.git` 在 `main` 分支，最後 commit 為 `f34d264 Add bundled YOLO model for complete repo functionality`。
- 內層 repo 目前有多個已修改與未追蹤檔案。這些很可能包含使用者近期工作、資料、模型與部署輸出。

在未確認前，請避免執行：

- `git reset --hard`
- `git clean -fdx`
- 刪除或重建 `.venv*`、`stitched_output`、`staging`、`output`、`offline_cell_analysis`
- 移動 `stitched_output\stitched_output\stitched_output`，因為現有文件與 legacy launcher 明確依賴這個路徑

## 主要資料夾地圖

| 路徑 | 約略大小 | 檔案數 | 用途 |
|---|---:|---:|---|
| `stitched_output/` | 4.338 GB | 6,140 | legacy GUI、硬體控制、拼接輸出、模型、偵測輸出與舊版資料 |
| `cell_stitching_project/` | 2.327 GB | 642 | 核心 Python 套件、拼接、辨識、訓練、Basler、SSD/YOLO 流程 |
| `.venv312/` | 1.372 GB | 28,913 | Python 3.12 虛擬環境 |
| `.venv/` | 1.165 GB | 32,568 | 另一套 Python 虛擬環境 |
| `staging/` | 0.792 GB | 3,418 | 訓練/轉換/測試用暫存資料 |
| `offline_cell_analysis/` | 0.542 GB | 1,662 | 離線影片分析工具、GUI、打包 exe、影片與輸出 |
| `.git/` | 0.470 GB | 5,546 | 內層 Git 儲存庫資料 |
| `.conda-verify-20260408/` | 0.149 GB | 5,695 | Conda/部署驗證相關環境殘留 |
| `output/` | 0.134 GB | 67 | 主要輸出結果 |
| `datasets/` | 0.096 GB | 2,856 | 公開/自建訓練資料集與設定 |
| `tests/` | 小 | 53 | pytest 測試 |
| `microscope_stitcher_project/` | 小 | 60 | 獨立顯微拼接流程與手動對齊工具 |
| `docs/` | 小 | 15+ | 安裝、交付、硬體、拼接與訓練文件 |

## 核心功能分區

### 1. 主要 Python 套件：`cell_stitching_project/`

這是目前最重要的程式碼區，包含：

- 影像拼接：`main.py`、`alignment.py`、`blending.py`、`preprocess.py`、`io_utils.py`、`visualization.py`
- 座標/蛇形掃描拼接：`coordinate_overlay_stitch.py`、`serpentine_stitch.py`
- 連續錄影與 WBC serpentine capture：`serpentine_recording.py`、`wbc_serpentine_capture.py`
- 細胞/白血球辨識：`cell_identification.py`、`cell_analysis.py`、`model_presets.py`
- live detection：`detect_live.py`
- Basler 相機：`capture_basler.py`、`camera/basler.py`
- 硬體檢查：`hardware_preflight.py`
- SSD 訓練/推論/匯出：`ssd/`、`train_ssd.py`、`eval_ssd.py`、`export_ssd_onnx.py`
- YOLO/WBC 訓練資料與訓練流程：`prepare_*dataset.py`、`train_*3cls.py`、`train_yolo_wbc400.py`、`train_wbc5_classifier.py`
- 環境檢查：`verify_environment.py`

注意：`cell_identfication.py` 是 typo 版檔名，但很可能是相容性 wrapper。不要直接刪除。

### 2. 顯微拼接獨立工具：`microscope_stitcher_project/`

這區像是較獨立的拼接實驗/正式流程：

- `run_practical_stitch.py` / `.ps1`
- `run_formal_stitch.py`
- `run_stitch.py`
- `manual_align_gui.py`
- `export_manual_alignment.py`
- `microscope_stitcher/` package
- `reference/` golden placements / learned template
- `tools/` 比對、產生 demo、practice validation

此區通常不應併入 `stitched_output`，應保留為可重跑的工具與參考流程。

### 3. Legacy / runtime / GUI 區：`stitched_output/stitched_output/stitched_output/`

這是目前最大且最敏感的區塊之一。它包含：

- legacy GUI/硬體 launcher 依賴資料
- captured sessions
- 拼接輸出與中間 mosaic steps
- 偵測輸出
- 模型權重
- YOLO runs / outputs
- 部分訓練資料與 smoke test data

雖然路徑重複三層 `stitched_output`，但既有工具與文件已依賴此路徑。統整時不要直接改名或搬移。

### 4. 離線分析工具：`offline_cell_analysis/`

包含：

- `main.py` 離線影片分析 pipeline
- `offline_analysis_gui.py`
- `offline_pipeline/`
- 打包後 exe：`OfflineCellAnalysis_*.exe`
- PyInstaller/build 內容：`build/`、`OfflineCellAnalysis_fast_dir/`
- 影片：`videos/`
- 分析輸出：`outputs/`
- 裁切結果：`cropped_cells/`、`cropped_cells_single/`
- pseudo training data：`training_datasets/`

此區包含執行檔與測試/示範影片，不應在未確認交付需求前清理。

### 5. 資料集與訓練暫存

`datasets/`：

- `TXL-PBC_Dataset/`：三分類血球資料來源，含自己的 `.git`
- `coco128/`：YOLO/COCO smoke 或範例資料
- `wbc5_classification_1000x_smoke/`
- `wbc_400x/`：五分類 WBC 設定，包含 `classes.txt`、`data.yaml`

`staging/`：

- `train/`
- `confidence_boost_3cls/`
- `manual_capture_3cls/`
- `wbc_boost_3cls/`
- GPU stitch smoke input/output
- Basler smoke data

`cell_stitching_project/output/`：

- 約 2.376 GB，是目前 `cell_stitching_project/` 內最大的子資料夾，應視為 runtime/training output。

## 根目錄常用入口

`C:\Cell_Project\Cell_Project` 根目錄有多個啟動與部署腳本：

- `run_hardware_gui.bat`
- `run_live_cell_annotator.bat`
- `run_wbc_serpentine_capture.bat`
- `hardware_preflight.bat`
- `gpu_stitch.bat`
- `train_manual_annotation_3cls.bat`
- `train_augmented_manual_annotation_3cls.bat`
- `train_confidence_boost_3cls.bat`
- `train_self_training_confidence_boost_3cls.bat`
- `setup_gpu_env.ps1`
- `setup_codex_dev.ps1`
- `install_project.ps1`
- `update_project.ps1`
- `package_for_transfer.ps1`

根目錄也有 YOLO 權重：

- `yolov8n.pt`
- `yolov8s-cls.pt`
- `yolov8n-cls.pt`
- `yolo26n.pt`

## 文件區現況

`docs/` 已有安裝、部署、拼接、硬體與訓練文件：

- `PROJECT_MAP.md`
- `NEW_MACHINE_SETUP.md`
- `INSTALL_UPDATE_GUIDE.md`
- `DELIVERY_SOP.md`
- `COMPLETE_DELIVERY_AND_INSTALL_STEPS.txt`
- `GPU_INSTALL_STEPS.txt`
- `GPU_STITCH_LAUNCHER.md`
- `HARDWARE_PREFLIGHT_CHECKLIST.md`
- `STITCHING_SOP.md`
- `STITCHING_LEARNED_RULES_20260521.md`
- `BASLER_PFS_CAMERA_PROFILE.md`
- `MANUAL_CAPTURE_TRAINING_DATASET.md`
- `BLOOD_CELLS_3CLS_TRAINING_20260610.md`
- `LAB13_REFERENCE_INTEGRATION.md`
- `28BYJ48_MOTION_TUNING.md`

部分既有中文文件在目前終端顯示為亂碼，可能是編碼或歷史轉碼問題。這份新文件使用 UTF-8 撰寫。

## 主要檔案類型

依容量排序的大宗類型：

- `.png`：約 6.779 GB，主要是拼接、mosaic、訓練/輸出影像
- `.dll`：約 1.002 GB，主要來自 Python/torch/Basler/打包環境
- `.pt`：約 715.89 MB，YOLO/分類模型權重
- `.pyd`：約 667.18 MB，Python native extensions
- 無副檔名：約 493.36 MB，多半來自 Git objects、環境或模型/資料殘留
- `.jpg`：約 477.68 MB，資料集與輸出影像
- `.pyc`：約 404.54 MB，Python cache
- `.py`：約 324.76 MB，包含專案程式與環境/套件程式碼
- `.mp4`：約 235.17 MB，離線分析測試影片

## 測試與驗證

目前有 `tests/`，涵蓋：

- config / io_utils
- cell identification
- Basler and live detection
- hardware preflight
- coordinate overlay stitch
- serpentine stitch / recording / capture
- dataset preparation
- pseudo training
- SSD pipeline
- environment verification

建議未來在重構或移動前先跑：

```powershell
cd C:\Cell_Project\Cell_Project
python -m pytest tests
```

若機器沒有完整 GPU、Basler、Pylon 或模型環境，部分硬體/整合測試可能需要跳過或改用 smoke test。

## 安全統整原則

目前最安全的整理方式是：

1. 先保留所有現有路徑，新增索引文件，不移動資料。
2. 把 `cell_stitching_project/` 視為核心 source code。
3. 把 `microscope_stitcher_project/` 視為獨立拼接工具。
4. 把 `stitched_output/` 視為 legacy/runtime 資料，短期不要改路徑。
5. 把 `offline_cell_analysis/` 視為離線工具與交付包，短期不要清理。
6. 把 `.venv/`、`.venv312/`、`.conda-verify-*` 視為可重建環境，但目前先保留。
7. 把 `staging/`、`output/`、`cell_stitching_project/output/` 視為實驗與產出資料，清理前要先確認哪些是交付必需。
8. 先處理 Git 邊界，再決定是否要把忽略規則、備份、資料集與模型權重分流。

## 建議的下一步

若要繼續「真正整理結構」，建議分階段做：

### Phase 1：只補文件與索引

- 保留目前所有檔案。
- 建立最新專案地圖。
- 建立模型、資料集、輸出、launcher 清單。
- 標記哪些路徑是 source、runtime output、training data、external env。

目前本文件已完成 Phase 1 的第一步。

### Phase 2：建立非破壞式索引工具

可新增 `tools/project_inventory.ps1`，每次掃描後輸出：

- 資料夾大小
- 大檔清單
- 模型清單
- dataset yaml/classes 清單
- launcher 清單
- Git 狀態摘要

這仍不會移動或刪除資料。

### Phase 3：經確認後再做結構整理

只有在確認功能入口與依賴後，才考慮：

- 把 legacy app 明確標成 `legacy`
- 把可重建的 output/archive 移到外部備份
- 把模型權重集中到固定位置，並保留相容性 wrapper 或設定
- 修正 README / docs 編碼與內容
- 清理重複虛擬環境或 PyInstaller build

任何 Phase 3 動作都應先有備份與可回復步驟。


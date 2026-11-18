# 新機建置指南

這份文件說明如何在新的 Windows 機器上重建 `Cell_Project`，包含：

- 主線 `cell_stitching_project`
- legacy GUI 與硬體控制
- Basler 相機支援
- GPU 拼接環境
- 模型與封裝資產

## 適用範圍

這個 repo 目前包含兩個部分：

- `cell_stitching_project`
  - 拼接主流程
  - YOLO ROI 輔助
  - GPU / CPU 執行路徑
  - Basler 擷取
  - Basler 即時偵測
  - VOC 資料集整理
  - SSD 訓練、評估與 ONNX 匯出
- `stitched_output/stitched_output/stitched_output`
  - legacy Tk GUI
  - Arduino 步進馬達控制
  - legacy 細胞辨識與掃描流程
  - 舊版模型與 launcher 依賴

## 建議一起帶走的內容

搬到新機時，至少保留：

- 整個 repo
- `stitched_output/stitched_output/stitched_output/models/`
  - `cell_detect_1000x_v2.pt`
  - `yolov8n.pt`
  - 其他你實際在 GUI / live detection / fallback 中會用到的模型
- 若有自訓練模型，也一起保留：
  - `.pt`
  - `.pth`
  - `.onnx`

如果要產生可攜式封裝，可用：

```powershell
.\package_for_transfer.ps1 `
  -Destination "E:\Cell_Project_portable.zip" `
  -IncludeModels `
  -IncludeStitchedOutput
```

參數說明：

- `-IncludeModels`
  - 會把常見模型副檔名一起打包
- `-IncludeStitchedOutput`
  - 會把 legacy GUI 與其依賴一併打包

## 主機需求

建議新機至少具備：

- Windows 10 或 Windows 11
- Python 3.12
- Conda 或 Miniconda
- NVIDIA 顯示卡
- Basler Pylon runtime / SDK
- 若要跑 legacy GUI，還需要 Arduino / serial 對應驅動與可用 COM 埠

目前專案驗證過的 GPU 基線包含：

- PyTorch `2.7.1+cu118`
- CUDA runtime `11.8`
- `NVIDIA GeForce GTX 1050`

若你不是同一張 GPU，不代表不能跑；重點是 `torch.cuda.is_available()` 要成立，而且實際 `device=cuda` 要能啟動。

## 建立 GPU 環境

建議直接使用專案附帶腳本：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\setup_gpu_env.ps1 -EnvPath "E:\Cell_Project_gpu_env" -RequireCuda
```

這個腳本會做的事：

- 建立 Python 3.12 conda 環境
- 安裝 PyTorch CUDA 11.8 wheels
- 安裝 `cell_stitching_project/requirements.txt`
- 安裝 `cell_stitching_project/requirements-gpu.txt`
- 最後執行驗證

如果你只想先建環境、不跑驗證：

```powershell
.\setup_gpu_env.ps1 -EnvPath "E:\Cell_Project_gpu_env" -SkipVerify
```

## 手動安裝方式

若你不想用腳本，可以手動安裝：

```powershell
conda create -p E:\Cell_Project_gpu_env python=3.12 -y
conda run -p E:\Cell_Project_gpu_env python -m pip install --upgrade pip
conda run -p E:\Cell_Project_gpu_env python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
conda run -p E:\Cell_Project_gpu_env python -m pip install -r .\cell_stitching_project\requirements.txt -r .\cell_stitching_project\requirements-gpu.txt ultralytics
```

如果要使用 Basler，還要另外安裝：

- Basler Pylon runtime / SDK
- `pypylon`

## 驗證新機

基本 GPU 驗證：

```powershell
E:\Cell_Project_gpu_env\python.exe -m cell_stitching_project.verify_environment `
  --workspace-root "C:\Cell_Project\Cell_Project" `
  --require-cuda
```

若 Basler 也必須可用：

```powershell
E:\Cell_Project_gpu_env\python.exe -m cell_stitching_project.verify_environment `
  --workspace-root "C:\Cell_Project\Cell_Project" `
  --require-cuda `
  --require-basler
```

這個驗證會檢查：

- Python interpreter
- 主要 Python 模組是否能 import
- CUDA 是否真的啟動
- Basler `pypylon` 是否可用
- 主線 CLI entrypoints 是否可 import
- legacy launcher / GUI / models / tests 是否存在

## Smoke Test 建議

建議至少跑以下幾種測試：

單元測試：

```powershell
E:\Cell_Project_gpu_env\python.exe -m unittest discover -s tests -v
```

拼接主流程：

```powershell
E:\Cell_Project_gpu_env\python.exe -m cell_stitching_project.main `
  --input_dir "C:\path\to\sample_images" `
  --output_dir "C:\path\to\stitch_output" `
  --compute_device cuda `
  --yolo_device 0
```

Basler 裝置列舉：

```powershell
C:\Cell_Project\Cell_Project\stitched_output\stitched_output\device_auto_launcher.bat --pylon_list
```

Basler 擷取：

```powershell
E:\Cell_Project_gpu_env\python.exe -m cell_stitching_project.capture_basler `
  --output-dir "C:\path\to\captures"
```

legacy GUI：

```powershell
C:\Cell_Project\Cell_Project\stitched_output\stitched_output\device_auto_launcher.bat
```

## 重要入口清單

- 拼接 CLI
  - `python -m cell_stitching_project.main`
- 細胞辨識 CLI
  - `python -m cell_stitching_project.cell_identification`
- Basler 擷取
  - `python -m cell_stitching_project.capture_basler`
- 即時偵測
  - `python -m cell_stitching_project.detect_live`
- VOC 資料集整理
  - `python -m cell_stitching_project.prepare_voc_dataset`
- SSD 訓練
  - `python -m cell_stitching_project.train_ssd`
- SSD 評估
  - `python -m cell_stitching_project.eval_ssd`
- SSD 匯出
  - `python -m cell_stitching_project.export_ssd_onnx`
- legacy GUI 啟動器
  - `stitched_output/stitched_output/device_auto_launcher.bat`

## 目前預設模型位置

legacy GUI 目前預設依賴：

- `stitched_output/stitched_output/stitched_output/models/cell_detect_1000x_v2.pt`
- `stitched_output/stitched_output/stitched_output/models/yolov8n.pt`

如果這兩個模型缺失，GUI 與部分 legacy 流程通常會出問題。

## 已知執行注意事項

- OpenCV CUDA 的可用性不代表所有 GPU 路徑都完整可用
- `cv2.cuda` 可用，也不代表 PyTorch CUDA 一定正常
- 部分預處理和 fallback 路徑仍可能落到 CPU
- 大量影像時會改用 chunked / streaming blending
- 輸入檔名若含座標資訊，會影響排序與佈局

## 建議搬遷順序

1. 先把 repo 和模型完整複製
2. 安裝 Basler Pylon runtime / SDK
3. 建立 GPU 環境
4. 跑 `verify_environment`
5. 跑 `unittest` smoke tests
6. 檢查 Basler 裝置是否能列出
7. 測試 Basler 擷取
8. 測試 legacy GUI
9. 再測試完整掃描/拼接流程

## 驗證失敗時先看什麼

`pypylon` import 失敗：

- 檢查是否已安裝 `pypylon`
- 檢查 Basler Pylon runtime / SDK 是否安裝完成

`device=cuda` 沒起來：

- 檢查 NVIDIA 驅動
- 檢查 PyTorch 是否安裝 `cu118` 版本
- 檢查是否其實落到 CPU interpreter

legacy GUI 啟不來：

- 檢查 `cell_detect_1000x_v2.pt` 是否存在於 `models/`
- 檢查 launcher 使用的 Python 環境是否正確
- 檢查 serial / Arduino / COM 埠是否正常

# MSH Main Python Package

`cell_stitching_project` is the main Python package of
Microscope-Scanner-Helper_MSH (MSH). It contains the primary WBC detection,
stitching, Basler, SSD, training, and environment-verification workflows.

Most model weights and research datasets are external or machine-local assets;
they are not automatically provided by a normal Git clone unless explicitly
tracked. The `C:\path\to\...` paths below are portable examples to replace with
paths appropriate for the current machine.

## 400x WBC-Only Detection

Manually select preset `wbc_400x` for the 400x single-class white-blood-cell model.

The following D-drive locations are B-machine local-storage examples, not
universal requirements. Generated 400x WBC-only datasets and training runs may
be stored there:

- `D:\Cell_Project_Datasets\MLL23`
- `D:\Cell_Project_training_staging\wbc400_wbc_only`
- `D:\Cell_Project_training_staging\train\wbc_400x`

```powershell
python -m cell_stitching_project.detect_live `
  --preset wbc_400x `
  --output-dir "C:\path\to\session_output" `
  --save-crops
```

For offline images:

```powershell
python -m cell_stitching_project.cell_identification `
  --model "stitched_output\stitched_output\stitched_output\models\wbc_focus_yolov8n_20260611.pt" `
  --class-file "stitched_output\stitched_output\stitched_output\models\wbc_400x_labels.txt" `
  --source "C:\path\to\400x_images" `
  --output-dir "C:\path\to\output\wbc_400x"
```

## Five-Class WBC Detection

The built-in default class names for `cell_identification` are now the five major white-blood-cell classes: `neutrophil`, `lymphocyte`, `monocyte`, `eosinophil`, and `basophil`.

Use these files when training or running a five-class model:

- `datasets\wbc_400x\classes.txt`
- `datasets\wbc_400x\data.yaml`

For 400x WBC fine-tuning:

```powershell
python -m cell_stitching_project.train_yolo_wbc400 `
  --data "datasets\wbc_400x\data.yaml" `
  --model "yolov8s.pt" `
  --epochs 260 `
  --imgsz 1280 `
  --batch 4 `
  --device 0
```

這個資料夾是目前專案的主線 Python 套件。

它負責的範圍包含：

- 影像拼接
- YOLO ROI 輔助對位
- CPU / GPU 執行路徑切換
- Basler 相機擷取
- Basler 即時偵測
- VOC 資料集整理
- SSD 訓練、評估與 ONNX 匯出
- 拼接後細胞辨識

如果你要新增功能或修主流程，優先改這裡，不要先去動 legacy 的 `stitched_output/...`。

## 主要入口

拼接：

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
  --output-dir "C:\path\to\captures"
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
  --checkpoint-folder "C:\path\to\models"
```

SSD 評估：

```powershell
python -m cell_stitching_project.eval_ssd `
  --trained-model "C:\path\to\models\mb1-ssd-Epoch-0-Loss-1.234567.pth" `
  --dataset "C:\path\to\voc_dataset" `
  --label-file "C:\path\to\models\labels.txt"
```

SSD 匯出 ONNX：

```powershell
python -m cell_stitching_project.export_ssd_onnx `
  --model-dir "C:\path\to\models"
```

相容舊拼字的入口：

```powershell
python -m cell_stitching_project.cell_identfication `
  --model "C:\path\to\best.pt" `
  --source "C:\path\to\images"
```

## 重要模組

- `main.py`：拼接主流程
- `alignment.py`：相鄰影像對位與 YOLO 輔助
- `blending.py`：CPU / GPU blending
- `preprocess.py`：預處理
- `runtime.py`：執行環境探測與 CUDA 判斷
- `cell_identification.py`：細胞辨識流程
- `config.py`：共用設定
- `camera/basler.py`：Basler 相機介面
- `ssd/`：內嵌 SSD runtime 與模型元件
- `train_ssd.py`：SSD 訓練入口
- `eval_ssd.py`：SSD 評估入口
- `export_ssd_onnx.py`：SSD 匯出入口
- `verify_environment.py`：整機驗證

## 執行特性

- `compute_device=cuda` 時，會優先使用 GPU 路徑
- 若某些 GPU 階段不可用，部分流程會退回 CPU
- 當影像數量較大時，會切換到 streaming / chunked 模式以降低記憶體壓力
- 高解析輸出與對位縮圖是分開處理的
- 輸出格式可為 `png`、`tif`、`tiff`

## 目前主線與 legacy 的關係

這個套件大致獨立，但還有兩個地方與 legacy 專案相連：

- `verify_environment.py` 會檢查 legacy launcher 和 GUI 是否存在
- `tests/test_slide_scan_workflow.py` 仍會載入 legacy GUI 中的部分 helper 邏輯

所以整理專案時，要把它理解成：

- 主線套件已經獨立
- 但還沒有完全與 legacy 切開

## 依賴

CPU 依賴：

```powershell
pip install -r cell_stitching_project\requirements.txt
```

GPU 額外依賴：

```powershell
pip install -r cell_stitching_project\requirements-gpu.txt
```

Basler 功能還需要：

- `pypylon`
- 主機已安裝 Basler Pylon runtime / SDK

SSD ONNX 匯出還需要：

- `onnx`
- `onnxscript`

## Live Detection Default and Waste Sorting Preset

`detect_live` 預設使用病理主流程的 `blood_cells_3cls` preset（WBC、RBC、Platelets）。`waste_sorting_v1` 保留為 alternate / experimental preset，需明確指定。

```powershell
python -m cell_stitching_project.detect_live `
  --preset waste_sorting_v1 `
  --output-dir "C:\path\to\session_output" `
  --save-crops `
  --stabilization-window 10 `
  --stabilization-threshold 7
```

上面這組設定會明確選用 `waste_sorting_v1`，不是 `detect_live` 的預設主流程。

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

Live detection controls:

- 預設 `detect_live` 會走 `blood_cells_3cls`
- 穩定判斷事件會寫到 `stable_events.jsonl`
- 按 `r` 會重新載入目前的 `--labels` 檔案
- 可以用 `--export-label-template C:\path\to\labels.txt` 匯出目前模型的類別名稱範本
- 可以用 `--command-template "{label}" --serial-port COM3` 在穩定事件發生時送出序列埠命令

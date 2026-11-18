# 智慧化顯微鏡病理影像掃描與 AI 輔助分析系統 - 期末專題成果報告

整理日期：2026-06-18  
專案路徑：`C:\Cell_Project\Cell_Project`  
適用範圍：期末成果報告、專題展示、程式說明文件

## 摘要

本專案以顯微鏡病理影像為主要應用場景，整合「影像擷取」、「蛇形掃描」、「多張影像拼接」、「AI 血球偵測」、「即時顯微鏡辨識」、「資料集製作與模型訓練」等功能，形成一套可用於智慧化顯微鏡掃描與 AI 輔助分析的系統。

系統的核心設計是將顯微鏡視野中的局部影像自動串接成較大的樣本視野，並在拼接前後使用 YOLO、ONNX 或 SSD 模型進行細胞偵測。對於白血球分析，專案已支援 400x 白血球單類別偵測，以及五種主要白血球類型辨識：`neutrophil`、`lymphocyte`、`monocyte`、`eosinophil`、`basophil`。

本系統屬於 AI 輔助分析與教學研究用途，目的在於提升影像整理、掃描紀錄、候選細胞定位與資料集製作效率，不取代醫師或病理專業人員的診斷判斷。

## 一、專題目標

1. 建立可自動處理顯微鏡影像的軟體流程，從多張重疊影像輸入到輸出完整拼接圖。
2. 讓系統可以使用 AI 模型自動標出白血球、紅血球、血小板或白血球子類型。
3. 支援 Basler 工業相機的即時取像與即時辨識，提供實驗室現場操作流程。
4. 支援蛇形路徑掃描，讓載物台能依照固定路徑移動，逐格掃描樣本。
5. 支援遇到白血球後暫停、置中、切換高倍率拍攝並保存細胞裁切圖。
6. 提供資料集準備、模型訓練、模型匯出與模型驗證工具，讓專案能持續改善辨識效果。

## 二、系統功能完整整理

### 1. 顯微鏡影像自動拼接

主要檔案：`cell_stitching_project/main.py`

此功能會讀取同一樣本下連續拍攝的多張顯微鏡影像，經過前處理、相鄰影像對位、座標排版與影像融合，最後輸出完整拼接圖。

主要流程：

1. 讀取輸入資料夾中的 `.jpg`、`.png`、`.tif` 等影像。
2. 使用 `StitchingConfig` 統一管理拼接參數。
3. 對每張影像做灰階化、去雜訊、CLAHE 對比增強、平場校正與必要的縮放。
4. 使用 phase correlation、ECC、ORB 或 SIFT 估計相鄰影像的位移。
5. 若啟用 YOLO guidance，系統會先偵測細胞 ROI，再將 ROI mask 加入對位流程，提高重點區域的對位可靠度。
6. 根據 pairwise shifts 建立整體 canvas layout。
7. 根據資料量選擇 average、feather 或 multiband blending。
8. 對拼接結果執行 post-stitch detection，輸出細胞偵測 JSON 與標註圖。

輸出成果：

| 輸出檔案或資料夾 | 說明 |
|---|---|
| `stitched_result.png` | 最終拼接影像 |
| `overlay_preview.png` | 拼接排列預覽 |
| `shifts.json` | 拼接設定、runtime 狀態、每組影像位移、canvas 資訊 |
| `shifts.csv` | 相鄰影像位移紀錄 |
| `debug_matches/` | 對位偵錯圖 |
| `intermediate/` | 中間拼接成果 |
| `post_stitch_detection/` | 拼接後 AI 偵測結果 |

### 2. 離線 AI 細胞偵測

主要檔案：`cell_stitching_project/cell_identification.py`

此功能可對單張影像或整個資料夾執行細胞偵測，支援 Ultralytics YOLO `.pt` 模型與 ONNX `.onnx` 模型。系統會輸出標註後影像與 JSON 結果，方便後續統計與報告使用。

支援類別：

| 模型類型 | 類別 |
|---|---|
| 五分類白血球 | `neutrophil`, `lymphocyte`, `monocyte`, `eosinophil`, `basophil` |
| 400x WBC 單類別 | `WBC` |
| 三分類血球 | `WBC`, `RBC`, `Platelets` |

主要特色：

1. 自動依副檔名判斷推論 backend，`.onnx` 使用 ONNX Runtime，其他預設使用 Ultralytics。
2. 支援 class file，可讀取 `.txt`、`.yaml`、`.yml`。
3. 支援整體 confidence threshold 與 per-class confidence threshold。
4. 內建 NMS 與座標縮放處理，讓 ONNX 輸出能轉回原圖座標。
5. 自動輸出標註圖與結構化 JSON。

### 3. Basler 即時顯微鏡偵測

主要檔案：

| 檔案 | 功能 |
|---|---|
| `cell_stitching_project/camera/basler.py` | Basler 相機封裝，負責開啟相機、設定曝光/增益/FPS、讀取 BGR frame |
| `cell_stitching_project/capture_basler.py` | 單純取像與預覽 |
| `cell_stitching_project/detect_live.py` | 即時 AI 偵測、裁切、穩定判斷、事件輸出 |

即時偵測流程：

1. 啟動 Basler 相機。
2. 依 preset 載入模型，例如 `blood_cells_3cls`、`wbc_400x`、`wbc_5cls`。
3. 每個 frame 執行 AI 偵測。
4. 在預覽畫面畫出 bounding box、label、confidence 與 count。
5. 可選擇保存每個 frame 或保存偵測到的 ROI crop。
6. 使用滑動視窗投票判斷穩定標籤，避免單一 frame 誤判。
7. 穩定事件可輸出到 `stable_events.jsonl`，也可透過 serial port 傳送控制命令。

### 4. 蛇形掃描與白血球擷取

主要檔案：

| 檔案 | 功能 |
|---|---|
| `cell_stitching_project/serpentine_recording.py` | 連續蛇形掃描錄影，可使用模擬 stage、OpenCV camera、Basler camera 或 serial XY stage |
| `cell_stitching_project/wbc_serpentine_capture.py` | 白血球掃描擷取流程，遇到 WBC 後暫停、置中、高倍率拍攝與裁切 |
| `cell_stitching_project/serpentine_stitch.py` | 評估蛇形座標順序，選擇最佳 traversal 後呼叫拼接流程 |

白血球擷取功能是本專案的重點之一。系統會依照垂直蛇形路徑移動載物台，在 400x 低倍率下掃描。當 AI 偵測到符合條件的白血球時，系統會暫停 stage，嘗試將白血球移到畫面中央，提示使用者切換至 1000x 高倍率並重新對焦，接著拍攝高解析影像並裁切白血球。

輸出資料包含：

| 輸出 | 說明 |
|---|---|
| `original_frames/` | 高倍率原始影像 |
| `cropped_cells/` | 裁切後的白血球影像 |
| `metadata.csv` | 每個細胞的座標、confidence、bbox、輸出路徑與保存狀態 |
| `summary.json` | 掃描總結 |

### 5. 座標式拼接與內容式修正

主要檔案：`cell_stitching_project/coordinate_overlay_stitch.py`

當輸入影像檔名已包含座標，例如 `x_y.jpg`，系統可以直接根據座標建立 mosaic。此流程也支援多種疊合策略，例如 ownership、strip ownership、pairwise strip、content phase。若實際移動與座標不完全一致，系統可用 ORB、phase correlation 或偵測特徵補正相鄰影像位移。

### 6. 模型 preset 與推論設定

主要檔案：`cell_stitching_project/model_presets.py`

目前專案整合的偵測 preset：

| Preset | 用途 |
|---|---|
| `wbc_400x` | 400x 白血球單類別 YOLOv8 偵測 |
| `wbc_5cls` | 五分類白血球 YOLOv8n |
| `wbc_5cls_400x` | 針對 400x 白血球五分類微調 |
| `blood_cells_3cls` | 三分類血球偵測，WBC/RBC/Platelets |
| `waste_sorting_v1` | 其他實驗模型，不屬於病理主流程 |

系統預設 live detection 使用 `blood_cells_3cls`，也可手動指定其他 preset。

### 7. 資料集準備與模型訓練

主要檔案：

| 檔案 | 功能 |
|---|---|
| `prepare_wbc400_wbc_only_dataset.py` | 將人工擷取的 WBC anchor 與 MLL23 crops 整合成 400x WBC-only YOLO 資料集 |
| `prepare_voc_dataset.py` | 將資料整理成 VOC 格式，供 SSD 訓練使用 |
| `prepare_manual_capture_yolo_dataset.py` | 將手動擷取資料轉成 YOLO 格式 |
| `train_yolo_wbc400.py` | 400x WBC YOLO 訓練入口 |
| `train_ssd.py` | SSD 訓練入口 |
| `eval_ssd.py` | SSD 評估 |
| `export_ssd_onnx.py` | SSD 匯出 ONNX |

400x WBC 五分類訓練設定使用 `datasets/wbc_400x/data.yaml`，目前定義：

```yaml
train: ./images/train/
val: ./images/val/
test: ./images/test/
nc: 5
names: ['neutrophil', 'lymphocyte', 'monocyte', 'eosinophil', 'basophil']
```

### 8. 環境檢查與部署輔助

主要檔案：

| 檔案 | 功能 |
|---|---|
| `cell_stitching_project/verify_environment.py` | 檢查 Python、CUDA、套件、模型與必要路徑 |
| `cell_stitching_project/hardware_preflight.py` | 檢查 Basler、serial port、legacy launcher 與硬體連線 |
| `hardware_preflight.bat` | Windows 一鍵硬體預檢 |
| `setup_gpu_env.ps1` | 建立或修復 GPU 環境 |
| `package_for_transfer.ps1` | 專案移轉封裝 |

### 9. 測試覆蓋

專案有 pytest 測試，範圍包含：

| 測試檔案 | 覆蓋內容 |
|---|---|
| `test_cell_identification.py` | 細胞偵測資料結構、class name、推論流程 |
| `test_serpentine_recording.py` | 蛇形路徑、錄影流程、模擬 stage/camera |
| `test_wbc_serpentine_capture.py` | WBC 擷取、置中、裁切與 metadata |
| `test_coordinate_overlay_stitch.py` | 座標式拼接與特徵修正 |
| `test_train_yolo_wbc400.py` | YOLO 資料設定與訓練參數 |
| `test_prepare_*dataset.py` | 資料集轉換流程 |
| `test_hardware_preflight.py` | 硬體預檢 |

## 三、系統架構

整體系統可分成六層：

```text
顯微鏡與硬體層
  Basler camera / OpenCV camera / Arduino XY stage / 模擬 stage

影像擷取層
  capture_basler.py / detect_live.py / serpentine_recording.py / wbc_serpentine_capture.py

影像處理層
  preprocess.py / alignment.py / blending.py / layout.py / visualization.py

AI 分析層
  cell_identification.py / model_presets.py / ssd/ / YOLO or ONNX models

資料與訓練層
  prepare_*dataset.py / train_* / eval_ssd.py / export_ssd_onnx.py

成果輸出層
  stitched image / annotated image / cropped cells / metadata.csv / JSON / logs
```

主要資料流：

```text
顯微鏡取像
  -> 影像前處理
  -> 影像對位
  -> 拼接排版
  -> 影像融合
  -> 拼接後 AI 偵測
  -> 標註圖、JSON、CSV、裁切圖與報告資料
```

白血球高倍率擷取資料流：

```text
400x 蛇形掃描
  -> AI 偵測 WBC
  -> 停止載物台
  -> WBC 置中
  -> 使用者切換 1000x 並對焦
  -> 高倍率拍攝
  -> 裁切白血球
  -> 寫入 metadata.csv
```

## 四、核心程式碼導讀

### 1. `StitchingConfig` - 拼接流程的統一設定中心

檔案：`cell_stitching_project/config.py`

`StitchingConfig` 是整個拼接系統的設定核心，包含輸入輸出路徑、前處理設定、對位方法、融合方法、YOLO guidance、拼接後偵測、GPU/CPU runtime 與效能 profile。

重點：

1. `performance_profile` 有 `quality`、`balanced`、`resource` 三種模式。
2. `compute_device` 可選 `auto`、`cuda`、`cpu`。
3. `gpu_fallback_allowed` 可決定 GPU 失敗時是否改用 CPU。
4. `post_stitch_detection_enabled` 可在拼接後自動執行 AI 偵測。
5. `describe()` 會把設定轉成 JSON，方便記錄實驗條件。

### 2. `run_stitch_pipeline()` - 自動拼接主流程

檔案：`cell_stitching_project/main.py`

此函式是拼接系統最重要的入口。它做的事情包含：

1. 建立輸出資料夾與 log。
2. 偵測 runtime，例如 CUDA 是否可用、GPU 名稱、YOLO device。
3. 讀取影像清單並排序。
4. 判斷是否進入 streaming mode，處理大量影像。
5. 執行影像前處理。
6. 若啟用 YOLO guidance，先偵測 ROI 並產生 mask。
7. 對每一組相鄰影像計算位移。
8. 建立全域 canvas layout。
9. 根據 profile 與影像數量選擇 blending 方法。
10. 輸出拼接圖、預覽圖、位移紀錄、偵錯圖。
11. 執行 post-stitch detection。

### 3. `preprocess_image()` - 影像前處理

檔案：`cell_stitching_project/preprocess.py`

此函式負責建立兩份影像：

| 影像 | 用途 |
|---|---|
| `alignment_gray` | 用於對位，通常是灰階、增強、降噪後的影像 |
| `blend_bgr` | 用於最後融合，保留彩色資訊 |

處理方法包含：

1. flat-field correction：修正照明不均。
2. denoise：降低雜訊。
3. CLAHE：提升局部對比。
4. percentile normalize：改善亮度動態範圍。
5. alignment resize：只縮小對位用影像，不縮小最後輸出影像。

### 4. `estimate_pairwise_shift()` - 相鄰影像對位

檔案：`cell_stitching_project/alignment.py`

此函式估計兩張相鄰 tile 的位移。它會根據設定嘗試多種方法：

| 方法 | 說明 |
|---|---|
| phase | 速度快，適合平移估計 |
| ECC | 可處理小幅度旋轉與亮度差異 |
| ORB | 使用特徵點配對 |
| SIFT | 特徵較穩定但計算成本較高 |

如果檔名含座標，系統會推論移動方向，例如 right、left、up、down，降低錯配機率。若 YOLO guidance 可用，系統會先用 ROI mask 對位，失敗時再回到未使用 mask 的對位。

### 5. `blend_tiles()` - 影像融合

檔案：`cell_stitching_project/blending.py`

此函式負責把已定位的 tiles 融合成 mosaic。若 CUDA 可用會優先嘗試 GPU blending，若發生錯誤或記憶體不足，且允許 fallback，就回到 CPU。

支援融合方法：

| 方法 | 適用情境 |
|---|---|
| average | 快速平均 |
| feather | 重疊區平滑融合 |
| multiband | 品質較高，適合少量影像與較小 canvas |

### 6. `CellIdentificationDetector` - AI 偵測封裝

檔案：`cell_stitching_project/cell_identification.py`

此類別把 YOLO 與 ONNX Runtime 封裝成相同介面。呼叫端只需要使用 `predict()` 或 `predict_and_annotate()`，不必在主流程判斷 backend。

重點：

1. `.pt` 模型使用 Ultralytics。
2. `.onnx` 模型使用 ONNX Runtime。
3. 可從模型內建 names 或外部 class file 取得類別名稱。
4. 每個偵測結果都轉成 `CellDetection`，包含 class id、label、confidence 與 bounding box。

### 7. `run_cell_identification()` - 離線偵測主流程

檔案：`cell_stitching_project/cell_identification.py`

此函式會收集所有輸入影像，逐張進行偵測與標註，最後輸出：

1. annotated images。
2. `results.json`。
3. `label_counts`。
4. 每張影像的 bounding boxes 與 confidence。

### 8. `detect_live.py` - 即時偵測與穩定事件

檔案：`cell_stitching_project/detect_live.py`

此檔案是現場操作的重要入口。它會從 Basler camera 連續讀取 frame，使用 AI detector 推論，並在畫面上顯示：

1. bounding box。
2. 類別名稱。
3. confidence。
4. 每類數量。
5. 推論時間與 preview FPS。
6. 穩定判斷狀態。

穩定判斷由 `DetectionStabilizer` 完成，使用固定長度的視窗記錄最近幾個 frame 的 top label，當某個 label 票數超過 threshold 才視為穩定事件。此設計可降低單張 frame 誤判造成的錯誤觸發。

### 9. `wbc_serpentine_capture.py` - WBC 掃描擷取主流程

此檔案結合蛇形掃描、AI 偵測、載物台暫停、WBC 置中、高倍率拍攝與細胞裁切。核心流程是 `run_serpentine_white_blood_cell_capture()`。

主要邏輯：

1. 建立輸出資料夾。
2. 產生垂直蛇形掃描路徑。
3. 每個座標移動 stage。
4. 讀取 preview frame 並偵測白血球。
5. 若偵測到可用 WBC，停止 stage。
6. 嘗試將 WBC 移到畫面中央。
7. 要求使用者切換 1000x 並手動對焦。
8. 拍攝高倍率影像。
9. 根據 bounding box 裁切 WBC。
10. 將座標、confidence、bbox 與輸出路徑寫入 `metadata.csv`。

## 五、主要執行命令

### 1. 自動拼接

```powershell
python -m cell_stitching_project.main `
  --input_dir "C:\path\to\images" `
  --output_dir "C:\path\to\output" `
  --performance_profile balanced `
  --compute_device auto
```

### 2. 離線細胞偵測

```powershell
python -m cell_stitching_project.cell_identification `
  --model "C:\path\to\best.pt" `
  --source "C:\path\to\images" `
  --class-file "datasets\wbc_400x\classes.txt" `
  --output-dir "C:\path\to\output\cell_identification"
```

### 3. Basler 即時偵測

```powershell
python -m cell_stitching_project.detect_live `
  --preset wbc_400x `
  --output-dir "C:\path\to\session_output" `
  --save-crops
```

### 4. 400x WBC YOLO 訓練

```powershell
python -m cell_stitching_project.train_yolo_wbc400 `
  --data "datasets\wbc_400x\data.yaml" `
  --model "yolov8s.pt" `
  --epochs 260 `
  --imgsz 1280 `
  --batch 4 `
  --device 0
```

### 5. 環境與硬體預檢

```powershell
python -m cell_stitching_project.verify_environment --workspace-root "C:\Cell_Project\Cell_Project"
.\hardware_preflight.bat
```

## 六、專案特色與成果亮點

1. **完整流程整合**：不是只有 AI 偵測，而是從顯微鏡取像、拼接、偵測、裁切、訓練到輸出紀錄都已整合。
2. **支援真實硬體與模擬測試**：Basler camera、OpenCV camera、serial XY stage 與 simulation mode 都有對應設計。
3. **具備大型影像處理能力**：大量影像時會使用 streaming mode，避免一次載入過多影像造成記憶體不足。
4. **GPU/CPU 彈性切換**：前處理、對位與融合可嘗試 CUDA，失敗時可 fallback 到 CPU。
5. **AI 模型可替換**：支援 Ultralytics YOLO、ONNX Runtime 與 SSD。
6. **支援細胞資料集累積**：能將高倍率擷取、人工標註與外部資料集整合成訓練資料。
7. **輸出可追蹤**：每次拼接和偵測都會保存 JSON、CSV 與 log，便於實驗重現。

## 七、系統限制

1. 顯微鏡影像品質會直接影響對位與 AI 偵測結果，若影像模糊、曝光過度或重疊區不足，拼接會變差。
2. YOLO guidance 依賴模型品質，若模型尚未適應實際顯微鏡影像，ROI mask 可能不足或錯誤。
3. 高倍率手動切換仍需人工操作，尚未完全自動化。
4. Basler、CUDA、serial stage 都與實際硬體環境有關，不同電腦可能需要重新設定。
5. 目前系統偏向輔助分析與資料整理，不能作為正式醫療診斷依據。

## 八、未來改進方向

1. 建立更完整的 400x/1000x 白血球資料集，提升五分類模型準確率。
2. 將 WBC 置中流程加入更精準的 stage calibration。
3. 加入 GUI 中的掃描任務管理、模型選擇、即時統計與報告匯出。
4. 增加拼接品質評分，例如重疊區相似度、接縫誤差與偵測一致性。
5. 建立自動產出實驗報告的功能，直接整理拼接圖、偵測統計、裁切圖與模型資訊。
6. 將資料集版本、模型版本與推論結果建立更完整的追蹤表。

## 九、結論

本專案完成了一套以顯微鏡病理影像為核心的智慧化掃描與 AI 輔助分析系統。系統不只具備影像拼接功能，也能整合 Basler 相機即時取像、蛇形掃描、白血球偵測、細胞裁切、模型訓練與環境檢查。整體設計已具備專題展示所需的完整性，並保留後續延伸成實驗室工具或教學研究平台的空間。

本專題的核心價值在於把傳統顯微鏡觀察流程轉換成可紀錄、可重現、可訓練、可分析的數位化流程，讓大量病理影像能更有效率地整理與初步分析。

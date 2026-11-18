# 細胞三分類信心度加強訓練紀錄 2026-06-10

## 目標

針對三分類血球模型加強訓練，讓 GUI 預設辨識模型在 400 倍顯微鏡影像上提高信心度與穩定度。

類別順序：

1. WBC
2. RBC
3. Platelets

## 本次訓練資料來源

- 手動標註與擴增資料：`E:\Cell_Project_training_staging\manual_annotation_augmented_3cls_latest`
- 偽標註資料：`E:\Cell_Project_training_staging\pseudo_label_3cls\latest`
- TXL-PBC 輔助資料：由訓練腳本依參數抽取
- 訓練輸出位置：`E:\Cell_Project_training_staging\train`

## 已執行訓練版本

### 1. balanced rare-class + cls boost

權重：

`E:\Cell_Project_training_staging\train\blood_cells_3cls_balanced_rare_clsboost_20260610\weights\best.pt`

資料集：

`E:\Cell_Project_training_staging\confidence_boost_3cls_balanced_rare_latest\data.yaml`

驗證結果：

- all mAP50: 0.978
- WBC mAP50: 0.991
- RBC mAP50: 0.986
- Platelets mAP50: 0.955

校準後門檻：

- WBC: 0.50
- RBC: 0.70
- Platelets: 0.55

GUI 實用門檻：

- WBC: 0.50
- RBC: 0.65
- Platelets: 0.45

判斷：目前最佳版本，已接到 GUI 預設 `blood_cells_3cls`。GUI 門檻採用較不漏血小板的折衷值，而不是完全採用最高 F1 門檻。

### 2. highres800

權重：

`E:\Cell_Project_training_staging\train\blood_cells_3cls_highres800_20260610\weights\best.pt`

驗證結果：

- all mAP50: 0.965
- WBC mAP50: 0.971
- RBC mAP50: 0.985
- Platelets mAP50: 0.938

校準後門檻：

- WBC: 0.60
- RBC: 0.40
- Platelets: 0.55

判斷：高解析未優於 balanced rare-class，不建議設為預設。

### 3. manual-heavy

權重：

`E:\Cell_Project_training_staging\train\blood_cells_3cls_manual_heavy_20260610\weights\best.pt`

驗證結果：

- all mAP50: 0.966
- WBC mAP50: 0.993
- RBC mAP50: 0.983
- Platelets mAP50: 0.921

校準後門檻：

- WBC: 0.20
- RBC: 0.65
- Platelets: 0.35

判斷：WBC 很強，但 Platelets 下降，不建議設為預設。

## 目前正式採用版本

專案內正式模型：

`C:\Cell_Project\Cell_Project\stitched_output\stitched_output\stitched_output\models\blood_cells_3cls_balanced_rare_clsboost_20260610.pt`

GUI 預設設定：

`C:\Cell_Project\Cell_Project\cell_stitching_project\model_presets.py`

目前 `blood_cells_3cls`：

- model: `blood_cells_3cls_balanced_rare_clsboost_20260610.pt`
- class_confidence: `(0.50, 0.65, 0.45)`
- iou_threshold: `0.45`

## 後續新增標註資料後續訓建議

新增資料後，優先使用 balanced rare-class 版本作為起點，不要退回舊模型。

建議流程：

1. 將新標註資料放入 `C:\Cell_Project\Cell_Project\stitched_output\stitched_output\stitched_output\captured\manual_annotation_dataset`
2. 重新產生或擴增手動標註資料集
3. 使用 `train_confidence_boost_3cls.py` 從目前最佳權重續訓
4. 使用 `calibrate_confidence_thresholds_3cls.py` 重新校準三類門檻
5. 只有當三類 mAP50 與實機結果都優於目前版本時，才替換 GUI 預設模型

## 注意事項

- 目前這台環境是 CPU-only PyTorch，訓練會很慢。
- 若新電腦正確安裝 CUDA 版 PyTorch，訓練速度會明顯提升。
- 不建議只看整體 mAP，Platelets 是目前最容易退步的類別，替換模型前必須單獨檢查 Platelets。

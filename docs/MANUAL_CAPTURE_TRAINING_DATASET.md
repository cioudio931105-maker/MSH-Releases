# 手動拍照三分類訓練資料輸出

## 功能範圍

此功能只作用於 GUI 的 `拍照` 按鈕，不會改變蛇行拍攝、整片掃描與影片錄製流程。

每次按下 `拍照` 後，程式會：

1. 保存相機原始解析度 PNG，不降階、不套用 GUI 額外濾鏡。
2. 使用目前 GUI 選定的三分類模型辨識白血球、紅血球與血小板。
3. 將辨識框裁切成個別 PNG。
4. 將裁圖分別放入三個資料夾。
5. 輸出 YOLO label、CSV 與 Excel 清單。

## 輸出結構

```text
manual_session_<時間>/
  <x>_<y>_<時間>.png
  detected/
  training_dataset/
    images/
    labels/
    crops/
      white_blood_cell/
      red_blood_cell/
      platelet/
    data.yaml
    training_manifest.csv
    training_manifest.xlsx
```

## 類別 ID

```text
0: white_blood_cell
1: red_blood_cell
2: platelet
```

## 續訓前必要步驟

這些結果是現有模型產生的預標註資料，不是人工確認過的 ground truth。正式加入續訓資料集前，必須人工檢查：

1. 刪除誤判裁圖。
2. 補上漏偵測細胞。
3. 修正錯誤類別。
4. 修正過大或過小的 bounding box。
5. 將資料拆分為獨立的 train 與 validation set。


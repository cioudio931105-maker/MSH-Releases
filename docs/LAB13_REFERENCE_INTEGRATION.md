# Lab13 範例程式整合說明

`C:\Users\will0\Downloads\Lab13\Lab13` 內的資料集類別為：

- `power`
- `soda`
- `soda2`
- `wine`
- `wine2`
- `vodka`

這些不是血球類別，不能直接加入目前的 `WBC / RBC / Platelets` 三分類模型訓練。若直接混入，YOLO 的 class id 會被污染，模型會把非血球物件當成血球類別學習。

目前已整合可用的部分：

- 參考 Lab13 的 GPU 自動選擇邏輯，目前訓練腳本會在 `--device auto` 時自動選擇 CUDA 或 CPU。
- 參考 Lab13 的結果圖檢查流程，訓練完成後會列出 `results.png`、`confusion_matrix.png`、`labels.jpg`、`best.pt`、`last.pt` 的實際路徑。
- 保留目前血球訓練資料來源：`C:\wbc`、TXL-PBC 血球資料集、GUI 手動拍照輸出的 `training_dataset`。

若未來要使用 Lab13 的影像資料，必須先重新標註成血球類別，或另開一個非血球模型，不能與血球模型共用同一組 class id。

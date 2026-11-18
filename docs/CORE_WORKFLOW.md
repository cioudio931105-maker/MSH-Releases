# MSH 核心與使用者資料流程

MSH 保留 UI 與功能；模型、影像、標註、訓練成果放在專案之外，由使用者選取。
不需要先把舊模型或舊資料放回專案，才可開啟 MSH。

## 操作與匯入模型

來源版從 MSH 桌面捷徑開啟；安裝版從 MSH.exe 開啟，日常不經 CMD。
主介面的「選擇模型」接受既有本機偵測模型；沒有選模型時不自動下載或選擇舊權重。
「清除模型」回到未選擇狀態。非 AI 的相機預覽、拍攝／拼接及平台操作程式仍保留，
但實際相機／平台操作仍需設備驅動、連線及硬體驗收。

## 醫師交付資料

醫師工具在 `tools/physician_review/`，是獨立離線 HTML 介面。

1. 醫師使用分類／框選工具整理使用者提供的原始影像。
2. 若訓練偵測定位模型，交付「匯出 YOLO」的 ZIP，解壓縮後應有 `data.yaml`、影像及對應框選標註。
3. 將資料、使用者起始模型與訓練輸出都保存在使用者資料目錄，例如 `Documents/MSH/`。
4. 訓練完成後，從主 GUI 匯入產生的 `best.pt`；程式不把新權重加回來源或安裝包。

只有整張圖片分類的 CSV 不等同定位框標註。既有分類訓練功能也保留，
但需依分類訓練流程準備對應資料；不會自動把分類標籤變成偵測框。

## 開發／維護人員的通用偵測訓練入口

`cell_stitching_project.train_user_dataset` 不預設歷史資料或模型，必須明確指定三個位置。
支援醫師工具匯出的 `images/train`、`images/val` 及相應 `labels/` 結構。
會保留 `data.yaml` 的類別名稱及 ID，包括 61 類定義，不強制合併為 WBC 單類。
訓練資料的 `path: .` 以解壓縮資料位置解析，不以 MSH 工作目錄解析。

以下路徑是使用者自行準備的位置；不包含可下載模型或資料：

```powershell
python -m cell_stitching_project.train_user_dataset `
  --data "$env:USERPROFILE\Documents\MSH\datasets\doctor_export\data.yaml" `
  --model "$env:USERPROFILE\Documents\MSH\models\my_detection_model.pt" `
  --output "$env:USERPROFILE\Documents\MSH\training" `
  --name doctor_training --dry-run
```

`--dry-run` 只核對路徑、類別與標註，不載入模型、不開始訓練。
確認後移除 `--dry-run` 才會執行；預設 CPU，依現有環境另指定 `--device`。
輸出位置必須在應用程式專案外，且不覆寫同名 run。
使用本機 `.pt` 起始權重或本機架構 YAML，不自動下載，AMP probe 亦關閉。
訓練完成不表示已驗證各類別的效果，須另外使用合適資料評估。

## 歷史資料的隔離邊界

目前方向是先備份／逐檔驗證，再把既有模型、影像、標註與實驗成果放到專案外。
搬移的實際完成與保存位置由本機驗證紀錄確認；沒有驗證結果前，不宣稱原資料已移出。
備份、Git 歷史及其他 worktree 不會因這個流程被改寫或刪除。
以前的實驗腳本仍可作相容參考；新訓練以明確的使用者輸入為準。

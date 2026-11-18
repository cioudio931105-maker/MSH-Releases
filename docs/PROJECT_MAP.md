# MSH 專案目錄

根目錄只放標準專案文件、Git 規則和必須維持原路徑的入口。新增檔案先放入下列對應目錄。

| 位置 | 用途 |
|---|---|
| `msh_app/core/` | 執行環境、版本、日誌、更新、模型／馬達政策與離線工作分派 |
| `msh_app/hardware/` | GUI、相機／平台控制與保留的韌體來源 |
| `msh_app/cell_identification/` | 辨識、分類與訓練支援 |
| `cell_stitching_project/` | 拍攝／掃描、影像處理、資料整理與訓練 |
| `microscope_stitcher_project/` | 正式離線拼接與品質報告 |
| `offline_cell_analysis/` | 錄影後抽影格、偵測／追蹤與統計 |
| `tools/physician_review/` | 醫師離線分類、框選及 YOLO 匯出工具 |
| `scripts/launch/` | 來源版啟動檢查、桌面／開始功能表捷徑工具 |
| `scripts/diagnostics/`、`scripts/maintenance/` | 診斷、開發環境與維護工具 |
| `scripts/` | 發行、稽核與其他命令工具；既有自動化入口維持原檔名 |
| `installer/` | `MSH.spec`、Inno Setup 安裝設定與更新交接工具 |
| `requirements/` | 共用、CPU、GPU、建置及鎖定的發行依賴清單 |
| `assets/`、`licenses/` | UI 圖像與第三方授權原文 |
| `tests/`、`docs/` | 軟體驗證、使用與開發文件 |
| `docs/legacy/` | 舊版文件、舊模型身分紀錄及歷史套件版本清單；不作目前執行預設 |
| `release/`、`.github/` | 發行資料範本與同庫建置／發布流程 |

## 根目錄保留理由

| 檔案 | 必須留在此處的原因 |
|---|---|
| `README.md`、`AGENTS.md` | GitHub 專案首頁與專案作業規則 |
| `LICENSE`、`THIRD_PARTY_NOTICES.md` | 標準授權入口與現有發行檔的必要聲明 |
| `.gitignore`、`.gitattributes` | Git 自動辨識的規則檔 |
| `launch_msh.pyw` | 既有無主控台來源捷徑與 PyInstaller 的固定入口 |
| `requirements.txt` | 標準 `pip install -r requirements.txt` 轉接；真正定義在 `requirements/base.txt` |
| `sitecustomize.py` | Python 按固定檔名自動載入的中文繪字啟動掛鉤 |
| `serpentine_recording.py`、`wbc_serpentine_capture.py` | 保留原有 CLI／匯入相容性的小型轉接，實作已在套件內 |

共用程式現在使用 `from msh_app.core.msh_runtime import ...` 等明確套件路徑。
啟動檢查：`.\scripts\launch\launch_hardware_gui.ps1 -CheckOnly`。
建置仍使用 `scripts/build_release.ps1`，由它讀取 `installer/MSH.spec`。
依賴範例：`python -m pip install -r requirements/cpu.txt -r requirements/build.txt`。

## 舊模型與本機內容

目前模型使用規則見 [USER_MODELS.md](USER_MODELS.md)。
舊模型的名稱／SHA-256 與當時指標放在 `docs/legacy/model-release-v0.1.1/`，
沒有隨附權重，也不由目前應用程式匯入。歸檔不會抹除已存在的 Git 歷史。
歷史驗證文件內的舊路徑反映當時狀態，查詢現行位置請以本頁為準。

Python 環境、快取、建置結果及 `.migration-local/` 屬本機忽略內容；不是要搬入來源的程式檔。
使用中的環境與既有研究資料保留，不為了外觀整齊移動或刪除。
原私人專案和其他工作階段保留原結構；本次整理先在新的正式開發分支驗證。

本機 Python 基底、三個實體環境、工作階段連結與封存前檢查見 [DEVELOPMENT_ENVIRONMENTS.md](DEVELOPMENT_ENVIRONMENTS.md)。

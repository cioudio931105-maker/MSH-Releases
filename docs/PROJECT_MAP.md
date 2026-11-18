# MSH 核心目錄

| 位置 | 保留功能 |
|---|---|
| `launch_msh.pyw`、`msh_*.py` | 日常啟動、版本、日誌、使用者模型政策與共用功能 |
| `msh_app/hardware/` | 操作 GUI、相機／平台控制及保留的韌體來源 |
| `msh_app/cell_identification/` | 辨識、分類與分類訓練支援 |
| `cell_stitching_project/` | 拍攝／掃描、影像處理、資料整理與訓練 |
| `microscope_stitcher_project/` | GUI 使用的離線拼接與品質報告 |
| `offline_cell_analysis/` | 錄影後抽影格、偵測／追蹤與統計 |
| `tools/physician_review/` | 醫師離線分類、框選及 YOLO 匯出介面 |
| `scripts/`、`installer/`、`MSH.spec` | 維護、診斷、資料工具與安裝包建置 |
| `assets/`、`licenses/` | UI 圖像及必要第三方聲明 |
| `tests/`、`docs/` | 軟體驗證與操作／發行說明 |

使用者資料與權重不是上述程式的內附內容。新資料流程見 [CORE_WORKFLOW.md](CORE_WORKFLOW.md)。
本機 Python 環境與 Git worktree 屬開發環境，不加入交接來源或安裝包；使用中的環境另行保留。

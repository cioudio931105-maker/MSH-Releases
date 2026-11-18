# RELEASE 目錄與 Artifact 邊界

> 2026-11-09 後續決策：使用者要求只保留核心 UI／功能，現有研究資料獨立保存。
> 日常流程以 [CORE_WORKFLOW.md](CORE_WORKFLOW.md) 為準。
> 下方「原位置保留／瀏覽候選」是先前階段紀錄，不能當作目前已完成搬移的證明。

## 日常操作介面

正式安裝版以 `MSH.exe` 啟動；PyInstaller 設定 `console=False`。
來源版桌面／開始功能表捷徑直接指向 `pythonw.exe → launch_msh.pyw`，不經 CMD。
`scripts/launch/install_gui_shortcut.ps1 -CheckOnly` 可唯讀查看預計使用的 runtime／路徑。
故障診斷明確保留在 `scripts/diagnostics/run_hardware_gui.bat`，其 console 是診斷用途。
命令列訓練／資料整理功能保留在 `scripts/commands/`，不要求一般使用者開終端機。

```powershell
.\scripts\launch\install_gui_shortcut.ps1 -CheckOnly
.\scripts\launch\install_gui_shortcut.ps1 -Location Both
.\scripts\launch\launch_hardware_gui.ps1 -CheckOnly
```

## 應用程式結構

| 位置 | 責任 |
|---|---|
| `launch_msh.pyw` | 統一 GUI 啟動器、版本、日誌與單一執行個體 |
| `msh_app/hardware/` | GUI、相機／平台控制、driver 與保留的 Arduino 韌體 |
| `msh_app/cell_identification/` | GUI 使用的辨識／分類及本機訓練支援 |
| `msh_app/scripts/` | 保留的拼接、資料整理及訓練入口 |
| `cell_stitching_project/` | 拼接、偵測、資料處理與訓練的主要 Python 套件／CLI |
| `scripts/commands/` | 進階使用者的命令列工具 |
| `scripts/diagnostics/` | 明確保留主控台的故障診斷入口 |
| `scripts/maintenance/` | 開發環境、安裝、更新及純來源交接工具 |
| `docs/release/` | BUILD、發行檢查表與歷史 release notes |
| `tools/release_audit/` | 本機 artifact 盤點、離線審閱與決策匯出 |

根目錄只保留標準文件、Git 規則及必要啟動／相容入口；共用模組使用 `msh_app.core` 匯入。完整現行配置與保留理由見 [PROJECT_MAP.md](PROJECT_MAP.md)。
根目錄 `serpentine_recording.py`、`wbc_serpentine_capture.py` 是相容 CLI，未刪除。

| 舊位置 | 新位置 |
|---|---|
| 三層 `stitched_output/.../` 中的程式 | `msh_app/`，保留原檔名與函式／class |
| 根目錄一般 `.bat` 工具 | `scripts/commands/`，保留原檔名及參數 |
| `run_hardware_gui.bat` | `scripts/diagnostics/run_hardware_gui.bat` |
| 舊 `device_auto_launcher.bat` | `scripts/legacy/device_auto_launcher.bat`，不作日常 GUI 入口 |
| `install_project.ps1`、`setup_*.ps1`、`update_project.ps1`、`package_for_transfer.ps1` | `scripts/maintenance/` |
| `BUILD.md`、`RELEASE_CHECKLIST.md`、`RELEASE_NOTES_*.md` | `docs/release/` |

不使用 junction 或另一份程式副本重建三層目錄。這是檔案／載入路徑整理，
不改 COM、camera serial、速度、步距、方向、掃描範圍、安全邊界或韌體內容。
已搬移的 `.ino` 逐檔 SHA-256 必須與整理前一致。

封裝會收進 GUI 所需的 `microscope_stitcher_project` 純程式來源，排除 reference
研究資料。`msh_app/core/msh_workers.py` 僅允許 practical-stitch 與 golden-compare 兩個離線工作；
凍結 EXE 以該工作入口執行拼接，不再把 EXE 當成 Python 解譯器開啟腳本或第二個 GUI。

## 模型與訓練資料 Artifact

使用者於 2026-11-09 選擇先建立瀏覽清單／刪除候選，原檔保留。
`tools/release_audit/inventory.py` 產生本機離線 HTML、JSON 摘要與完整 JSONL metadata。
Artifact 是原資料的可審閱索引，不是已備份、已搬移或已壓縮封存的證明。

```powershell
.\.venv312-cpu\Scripts\python.exe tools\release_audit\inventory.py --output tmp\release-artifact-review
```

審閱可標記保留、刪除候選或待確認，再匯出決策 JSON；不執行檔案刪除。
模型、資料集、標註、研究影像、舊安裝包及設備 profile 不加入 Git 或來源交接包。
`tmp/` 可能含錄影、訓練成果、歷史驗證證據；`stitched_output/` 也不是可整體刪除的垃圾目錄。
`.git` 歷史及其他 worktree 不在容量盤點內，也不改寫歷史或接管其他工作。

原位置的模型與研究資料保留原位。`msh_app/research_paths.py` 僅替舊工具解析既有
資料位置；GUI 仍由使用者明確選擇本機模型，不自動下載或套用設備 profile。
只有已核對 SHA-256 的檔案才標為確定重複；仍須保留至少一份且確認使用位置／備份。
本機環境、可重建產物和研究原件分開列示，不因檔案大或被 Git 忽略而自動建議刪除。
整理程式結構不代表已釋放磁碟空間；容量回收須待使用者選定項目並另行授權。

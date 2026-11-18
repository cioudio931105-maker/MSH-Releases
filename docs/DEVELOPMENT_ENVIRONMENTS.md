# 本機開發環境

開發環境不加入 Git，也不包進來源交接檔。使用者安裝的 APP 另有已封裝的執行環境。
依賴版本以 `requirements/release-cpu.txt`、`requirements/release-gpu.txt` 為準。

## 正式開發副本的環境位置

| 本機目錄 | 用途 |
|---|---|
| `.venv312-base/` | 獨立 Python 3.12.13 基底，包含標準庫及 Tk；其他環境依賴此處 |
| `.venv312/` | 日常來源版 GUI／開發，NVIDIA GPU 套件與 CPU 備用 |
| `.venv312-cpu/` | CPU 套件、軟體測試及 CPU 建置 |
| `.venv312-release-gpu/` | 獨立的 GPU 測試／建置環境 |

正式副本中的四個目錄都是實體資料夾。Python 的 `home` 與 `base_prefix`
使用本專案的 `.venv312-base/`，不依賴舊研究專案中的環境。
日常 GPU 與發行 GPU 環境分開，避免開發安裝影響已核對的建置環境。

其他獨立工作階段可用本機 junction 共用正式副本的環境；這些箭頭的目標是新的正式副本。
新增工作階段時，先確認連結目標，不要再指回舊研究專案。
環境內的腳本包含安裝時的絕對路徑；更換位置應重建，不能直接拖曳整個環境。

## 重建與驗證

先準備經確認的 Python 3.12.13，再在最終使用位置建立 venv。
使用對應的發行鎖定清單，例如從專案根目錄執行：

```powershell
.\.venv312-base\python.exe -m venv .venv312-cpu
.\.venv312-cpu\Scripts\python.exe -m pip install -r requirements/release-cpu.txt
.\.venv312-cpu\Scripts\python.exe -m pip check
.\.venv312-cpu\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py'
.\scripts\launch\launch_hardware_gui.ps1 -CheckOnly
```

GPU 環境使用 `requirements/release-gpu.txt`。先核對 Python、套件版本與資源路徑，
再使用 `launch_msh.pyw --msh-environment-report <本機報告路徑>` 驗證運算環境。
該報告不開啟相機或 COM；舊拍攝 CLI 沒有 `--help` 參數解析，不能拿它做安全啟動檢查。

軟體測試、GPU 運算與打包驗證分別記錄。Basler USB、COM、平台與完整掃描仍需實體設備驗收。

## 封存舊專案前

1. 比對所有舊來源參照、未提交變更與新工作階段，確認已保留。
2. 核對新環境、其他工作階段與來源版桌面捷徑都不再依賴舊資料夾。
3. 將新副本的未提交工作依專案規則審查、提交及同步。
4. 確認 B 地沒有尚未交接的工作，再決定是否把舊 GitHub repository 設為唯讀封存。

封存是保留研究資料、模型、舊 Git 歷史及恢復方式。停止日常開發不代表可刪除原件，
也不能把來源遷移完成視為硬體或正式發行驗收完成。

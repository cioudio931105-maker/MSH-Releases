> 歷史架構快照；目前結構見 docs/PROJECT_MAP.md。

# 專案地圖

> 2026-11-09 目錄整理：目前 GUI／driver／韌體原始碼已移至單一 `msh_app/`；
> 根目錄工具分入 `scripts/commands/`、`scripts/maintenance/` 與 `scripts/diagnostics/`，
> 發行文件移至 `docs/release/`。最新結構與原資料保留規則見 [RELEASE_LAYOUT.md](RELEASE_LAYOUT.md)。
> 以下保留為搬移前的架構背景，三層 `stitched_output` 已不再是目前程式位置。

這個 repo 目前其實不是單一系統，而是兩套系統共存在同一個工作區：

1. 主線 Python 套件：`cell_stitching_project/`
2. legacy GUI 與硬體控制：`stitched_output/stitched_output/stitched_output/`

會覺得專案很亂，主要就是因為這兩套系統在資料夾層級混在一起，但測試與驗證流程又還保留部分橋接。

## 目前頂層結構

`cell_stitching_project/`
- 主線 Python 套件
- 負責拼接、細胞辨識、Basler 擷取、即時偵測、VOC 整理、SSD 訓練/評估/匯出

`tests/`
- 主線自動化測試
- 大多數測試對象是 `cell_stitching_project/`
- 其中一支 workflow test 仍會載入 legacy GUI helper

`docs/`
- 專案文件
- 包含新機建置與目前的架構說明

`datasets/`
- 輸入資料集與資料集整理產物

`output/`
- 主線流程預設輸出位置

`stitched_output/stitched_output/stitched_output/`
- legacy 專案快照
- 內含 Tk GUI、Arduino 步進馬達控制、舊版細胞辨識、模型與各種執行產物

`.venv/`、`.venv312/`、`.conda-gpu/`
- 本機環境
- 這些不是核心原始碼，應視為機器本地資產

## 現在的主線在哪裡

目前真正的主線程式在：

- `cell_stitching_project/main.py`
- `cell_stitching_project/cell_identification.py`
- `cell_stitching_project/camera/basler.py`
- `cell_stitching_project/capture_basler.py`
- `cell_stitching_project/detect_live.py`
- `cell_stitching_project/prepare_voc_dataset.py`
- `cell_stitching_project/train_ssd.py`
- `cell_stitching_project/eval_ssd.py`
- `cell_stitching_project/export_ssd_onnx.py`
- `cell_stitching_project/runtime.py`
- `cell_stitching_project/verify_environment.py`

如果你要加功能、修主流程、補 CLI、調模型流程，優先從這裡開始。

## 哪些屬於 legacy

legacy 區主要是：

- `stitched_output/stitched_output/stitched_output/hardware/`
- `stitched_output/stitched_output/stitched_output/cell_identification/`
- `stitched_output/stitched_output/device_auto_launcher.bat`

這裡仍然重要，因為它保存了：

- Tk GUI 控制流程
- Arduino 馬達控制腳本與韌體
- 舊版 slide scan helper
- launcher 依賴的模型位置

但它不是主線套件，不應再當成新功能的預設落點。

## 主線與 legacy 目前還有哪些耦合

這個 repo 還沒完全拆開，主要耦合點有兩個：

- `cell_stitching_project/verify_environment.py`
  - 會檢查 legacy launcher 與 GUI 是否存在
- `tests/test_slide_scan_workflow.py`
  - 會直接載入 legacy GUI 與 legacy cell-identification 裡的 helper

也就是說，legacy 雖然不是主線，但目前仍是 repo contract 的一部分。

## 為什麼現在看起來特別亂

主要原因如下：

- `stitched_output` 這個名字看起來像輸出資料夾，但裡面其實放了原始碼
- legacy 專案被巢狀放在 `stitched_output/stitched_output/stitched_output/`
- 文件同時描述主線與 legacy 流程
- 部分文件之前有編碼毀損
- 本機環境、生成產物、原始碼都擺在 repo 頂層附近
- 既有 `cell_identification`，也保留了 typo 相容的 `cell_identfication`

## 實際上應該怎麼理解這個 repo

建議用這個心智模型：

- 新套件功能看 `cell_stitching_project/`
- 測試看 `tests/`
- 操作文檔看 `docs/`
- GUI 與馬達控制看 `stitched_output/.../hardware/`
- legacy launcher 與模型依賴也在 legacy 樹裡

## 建議整理階段

不要一次大搬家，建議分階段整理。

### 第一階段：先把邊界講清楚

- 不搬檔案
- 補齊文件，說清楚主線與 legacy 的分界
- 把 `stitched_output/...` 明確標成 legacy
- 修正編碼毀損文件

### 第二階段：清理 repo 衛生

- 不再把本機環境當成專案結構的一部分
- 區分原始碼與生成輸出
- 統一模型預設位置
- 統一主線流程的輸出目錄規則

### 第三階段：隔離 legacy

- 把 legacy app 改放到更明確的路徑，例如 `legacy_app/` 或 `legacy_gui/`
- 更新 `verify_environment.py` 與測試的引用位置
- 若需要，相容 launcher 保留一層 wrapper 即可

### 第四階段：抽共用邏輯

- 找出 legacy 中仍被測試或主線借用的 helper
- 抽成小而明確的 shared module
- 不要再讓測試直接依賴大型 Tk GUI 檔案

## 建議的責任分工規則

之後若要維持 repo 不再失控，建議固定規則：

- 新的拼接與偵測功能放 `cell_stitching_project/`
- 新的測試放 `tests/`
- GUI 與馬達控制修改先留在 legacy 區，直到正式遷移完成
- 文件要明確標示是 `主線` 還是 `legacy`

## 下一步最值得做的事

如果繼續整理，優先順序建議是：

1. 修好所有文件，尤其是入口說明與建置說明
2. 加一份統一的架構/入口總覽
3. 把 legacy 原始碼從 `stitched_output/.../stitched_output/` 這種命名中解放出來
4. 降低測試對 `stepper_drag_gui.py` 的直接依賴

## 短結論

這個 repo 不是單純「一團亂碼」。

它其實是：

- 一個主線套件
- 一個 legacy 應用快照
- 再加上一層尚未拆乾淨的橋接

整理時應該保留這個事實，而不是把所有東西當成同一層次來看。

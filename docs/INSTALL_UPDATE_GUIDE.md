# 開發環境安裝與更新指南

> 這是開發／原始碼環境參考，不是一般使用者的安裝方法。
> 一般使用者請依 [MSH 直接安裝與往後發佈流程](DIRECT_INSTALL_RELEASE_WORKFLOW_zh_TW.md) 下載安裝檔。
> 現行交付不包含模型或研究資料；模型由使用者提供，舊版 IncludeModels 等參數已停用。

這份文件是給「另一台幾乎沒有相關環境的 Windows 電腦」使用的。

目標是讓對方可以：

1. 安裝這個專案的完整可用環境
2. 依照機器狀況自動選擇 CPU 或 NVIDIA GPU 對應的 PyTorch 執行時
3. 後續在專案更新後，快速同步與重建依賴

## 這套流程會自動處理什麼

- 偵測是否有 NVIDIA GPU
- 自動安裝 Miniconda（若機器上沒有 Conda）
- 建立專案 Conda 環境
- 自動嘗試安裝可用的 PyTorch runtime
  - 有 NVIDIA GPU 時，會依序嘗試 `cu124`、`cu118`
  - 若 GPU 路徑不可用，會退回 `cpu`
- 安裝專案 Python 依賴
- 安裝 Ultralytics
- 執行專案驗證
- 記錄安裝狀態，供後續更新腳本使用

## 這套流程不會完全自動處理的部分

以下屬於廠商或驅動層安裝，不適合只靠 `pip` 解決：

- NVIDIA 顯示卡驅動
- Basler Pylon runtime / SDK

注意：

- PyTorch 的 wheel 已經包含對應 CUDA runtime 與 cuDNN，不需要另外手動裝 CUDA Toolkit 才能跑本專案的 PyTorch 路徑
- 但如果顯示卡驅動本身不完整，GPU 仍然不會正常啟動
- Basler 功能要完整可用，仍然建議安裝官方 Pylon runtime / SDK

## 你應該交付給對方哪些東西

建議至少交付：

- 整個專案資料夾
- 模型由使用者自行保存與提供，不隨專案交付
- legacy GUI 與硬體控制檔

如果要先打包成 zip，可用：

```powershell
.\package_for_transfer.ps1 `
  -Destination "E:\Cell_Project_portable.zip"
```

## 新機安裝方式

對方拿到專案後，在專案根目錄執行：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install_project.ps1
```

如果你要求一定要啟用 CUDA，改用：

```powershell
.\install_project.ps1 -RequireCuda
```

如果對方手上已經有 Basler Pylon 安裝程式，也可以一起帶入：

```powershell
.\install_project.ps1 -PylonInstallerPath "C:\Installers\Basler_pylon.exe"
```

## 腳本說明

### `install_project.ps1`

用途：

- 新機第一次安裝時使用
- 會呼叫 `setup_gpu_env.ps1`
- 會自動安裝 Miniconda

### `setup_gpu_env.ps1`

用途：

- 實際建立或更新環境
- 自動選擇 PyTorch runtime
- 安裝依賴並執行驗證

常用範例：

```powershell
.\setup_gpu_env.ps1 -EnvPath ".conda-gpu"
```

要求一定要有 CUDA：

```powershell
.\setup_gpu_env.ps1 -EnvPath ".conda-gpu" -RequireCuda
```

只更新既有環境：

```powershell
.\setup_gpu_env.ps1 -EnvPath ".conda-gpu" -UpdateOnly
```

指定固定 runtime：

```powershell
.\setup_gpu_env.ps1 -EnvPath ".conda-gpu" -TorchRuntime cu118
```

可用的 `TorchRuntime`：

- `auto`
- `cpu`
- `cu118`
- `cu124`

### `update_project.ps1`

用途：

- 專案程式更新後，重新同步依賴
- 可選擇先做 `git pull`
- 會優先讀取 `.cell_project_install.json` 內記錄的環境設定

若這份專案本身是 Git clone，可用：

```powershell
.\update_project.ps1 -Pull
```

若只是覆蓋了新版本檔案，不需要 `git pull`，直接：

```powershell
.\update_project.ps1
```

若更新後要求重新確認 CUDA：

```powershell
.\update_project.ps1 -RequireCuda
```

## 建議的實際交付模式

### 模式 A：可更新的 Git 交付

適合長期維護。

做法：

1. 在新機把 repo clone 下來
2. 執行 `.\install_project.ps1`
3. 後續更新時執行 `.\update_project.ps1 -Pull`

優點：

- 更新最簡單
- 不用每次整包重傳

### 模式 B：zip 封裝交付

適合不能用 Git 的機器。

做法：

1. 用 `package_for_transfer.ps1` 打包
2. 對方解壓縮
3. 對方執行 `.\install_project.ps1`
4. 之後若有新版本，重新提供更新過的檔案
5. 對方覆蓋後執行 `.\update_project.ps1`

優點：

- 交付簡單
- 不依賴 Git

缺點：

- 後續版本同步較笨重

## 安裝完成後建議驗證

執行：

```powershell
python -m cell_stitching_project.verify_environment --workspace-root "C:\Cell_Project\Cell_Project"
```

如果使用的是專案 Conda 環境，建議直接：

```powershell
.\.conda-gpu\python.exe -m cell_stitching_project.verify_environment --workspace-root "C:\Cell_Project\Cell_Project"
```

若一定要確認 CUDA：

```powershell
.\.conda-gpu\python.exe -m cell_stitching_project.verify_environment `
  --workspace-root "C:\Cell_Project\Cell_Project" `
  --require-cuda
```

## 更新時的建議流程

### 開發端

1. 修改程式
2. 測試
3. 提交新版本
4. 通知新機端更新

### 使用端

如果是 Git clone：

```powershell
.\update_project.ps1 -Pull
```

如果是 zip 覆蓋：

```powershell
.\update_project.ps1
```

## 常見情況

### 有 NVIDIA GPU，但最後落到 CPU

原因通常是：

- 顯示卡驅動不完整
- 該機器上的 GPU runtime 驗證失敗

腳本會自動退回 CPU，避免整體安裝直接失敗。

如果你不接受 CPU fallback，請用：

```powershell
.\install_project.ps1 -RequireCuda
```

### Basler 功能不完整

通常要檢查：

- 是否安裝 `pypylon`
- 是否安裝 Basler Pylon runtime / SDK
- 是否真的有接上 Basler 相機

### 更新後功能不一致

通常先做：

```powershell
.\update_project.ps1
```

如果仍有問題，再重新驗證：

```powershell
.\.conda-gpu\python.exe -m cell_stitching_project.verify_environment --workspace-root .
```

## 建議你現在採用的交付方案

如果你要的是：

- 能交給別台 Windows 機器安裝
- 盡量自動化
- 後面還能更新

最務實的做法是：

1. 專案用 Git 管理
2. 新機第一次執行 `.\install_project.ps1`
3. 後續執行 `.\update_project.ps1 -Pull`

若新機不能用 Git，則改成：

1. 用 zip 交付
2. 新機第一次執行 `.\install_project.ps1`
3. 之後每次覆蓋新版本後執行 `.\update_project.ps1`

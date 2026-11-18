# MSH 原始碼環境交付 SOP

> 這是開發／原始碼環境參考，不是一般使用者的安裝方法。
> 一般使用者請依 [MSH 直接安裝與往後發佈流程](DIRECT_INSTALL_RELEASE_WORKFLOW_zh_TW.md) 下載安裝檔。
> 現行交付不包含模型或研究資料；模型由使用者提供，舊版 IncludeModels 等參數已停用。

## 1. 交付內容

請提供對方以下內容：

- `Cell_Project` 專案完整資料夾
- 模型由使用者自行保存與提供，不隨專案交付
- legacy GUI 與硬體控制檔

若要打包成 zip：

```powershell
.\package_for_transfer.ps1 `
  -Destination "E:\Cell_Project_portable.zip"
```

## 2. 新機安裝

在對方電腦上：

1. 解壓縮或放好專案資料夾
2. 用 PowerShell 進入專案根目錄
3. 執行：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install_project.ps1
```

若這台電腦必須使用 NVIDIA GPU：

```powershell
.\install_project.ps1 -RequireCuda
```

若要一起串 Basler 官方安裝包：

```powershell
.\install_project.ps1 -PylonInstallerPath "C:\Installers\Basler_pylon.exe"
```

## 3. 腳本會自動處理的事

- 沒有 Conda 時，自動安裝 Miniconda
- 自動建立專案環境
- 自動偵測是否有 NVIDIA GPU
- 自動安裝對應的 PyTorch runtime
  - 依序嘗試 `cu124`、`cu118`
  - 不可用時退回 `cpu`
- 安裝專案 Python 依賴
- 執行環境驗證

## 4. 不會完全自動處理的事

- NVIDIA 顯示卡驅動
- Basler Pylon runtime / SDK

說明：

- PyTorch wheel 已包含對應 CUDA runtime 與 cuDNN，通常不需要另外手動安裝 CUDA Toolkit
- 但若顯示卡驅動有問題，GPU 仍然無法使用
- Basler 功能若要完整可用，仍建議安裝官方 Pylon runtime / SDK

## 5. 安裝完成後驗證

```powershell
.\.conda-gpu\python.exe -m cell_stitching_project.verify_environment `
  --workspace-root "C:\Cell_Project\Cell_Project"
```

若要強制確認 CUDA：

```powershell
.\.conda-gpu\python.exe -m cell_stitching_project.verify_environment `
  --workspace-root "C:\Cell_Project\Cell_Project" `
  --require-cuda
```

## 6. 後續更新

### 如果對方是 Git 版本

```powershell
.\update_project.ps1 -Pull
```

### 如果對方是 zip 覆蓋版本

1. 用新版檔案覆蓋專案資料夾
2. 執行：

```powershell
.\update_project.ps1
```

## 7. 常見問題

### 安裝後落到 CPU

先檢查：

- 是否有 NVIDIA GPU
- 顯示卡驅動是否正常
- 是否真的需要強制 GPU

若一定要 GPU，請改用：

```powershell
.\install_project.ps1 -RequireCuda
```

### Basler 功能不能用

先檢查：

- 是否已安裝 `pypylon`
- 是否已安裝 Basler Pylon runtime / SDK
- 是否有接上 Basler 相機

### 更新後功能異常

先執行：

```powershell
.\update_project.ps1
```

再重新驗證：

```powershell
.\.conda-gpu\python.exe -m cell_stitching_project.verify_environment --workspace-root .
```

## 8. 建議標準流程

### 第一次交付

1. 提供專案完整資料夾或 zip
2. 對方執行 `.\install_project.ps1`
3. 驗證功能是否正常

### 後續版本更新

1. 你提供新版程式
2. 對方執行 `.\update_project.ps1`
3. 必要時重新跑驗證

## 9. 文件位置

- 安裝與更新詳版：[INSTALL_UPDATE_GUIDE.md](INSTALL_UPDATE_GUIDE.md)
- 新機建置詳版：[NEW_MACHINE_SETUP.md](NEW_MACHINE_SETUP.md)
- 專案地圖：[PROJECT_MAP.md](PROJECT_MAP.md)

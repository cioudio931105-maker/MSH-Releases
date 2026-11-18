# 智慧化顯微鏡病理影像掃描與 AI 輔助分析系統新電腦安裝步驟

本文件用於將本專案搬移到新電腦，並恢復完整功能：1000 倍顯微影像擷取、Basler 相機拍攝、XY 馬達控制、AI 白血球偵測、偵測後暫停拍攝、繼續掃描、影像儲存與選擇性影像拼接。

## 一、交付檔案

放到新電腦前，建議準備以下檔案：

- `Cell_Project_New_PC_Full_Install_20260703.zip`：完整專案程式壓縮檔。
- `Cell_Project_New_PC_Install_Steps_20260703.pptx`：新電腦安裝步驟簡報。
- Basler Pylon Camera Software Suite 安裝檔：如需使用 Basler 工業相機，請先準備官方安裝程式。

壓縮檔內應包含：

- `cell_stitching_project/`：主要 Python 程式碼。
- `stitched_output/`：legacy GUI、硬體控制、模型與相關資源。
- `docs/`：專案說明與安裝文件。
- `tests/`：環境與功能測試。
- `*.bat`、`*.ps1`：啟動、安裝與打包腳本。
- `*.pt`、`*.pth`、`*.onnx`：AI 模型檔案。

壓縮檔不包含：

- `.venv/`、`.venv312/`、`.conda-gpu/` 等本機虛擬環境。
- `.git/` 版本控制資料夾。
- Python 快取、暫存檔與舊 zip 檔。

## 二、新電腦前置需求

建議環境：

- Windows 10 或 Windows 11 64-bit。
- NVIDIA GPU 與最新版 NVIDIA 顯示卡驅動。
- 可連接 Basler 相機的 USB 或網路介面。
- 可連接 XY 馬達控制板的 USB 序列埠。
- 穩定網路，第一次安裝會下載 Miniconda、PyTorch 與 Python 套件。

Basler 相機功能需要另外安裝：

- Basler Pylon Camera Software Suite。
- Python 套件 `pypylon`，此專案安裝腳本會透過 requirements 安裝。

## 三、解壓縮專案

建議將壓縮檔解壓縮到：

```powershell
C:\Cell_Project\Cell_Project
```

如果解壓到其他位置也可以，但後續指令請切換到實際專案資料夾。

確認專案根目錄中能看到以下檔案：

```text
install_project.ps1
setup_gpu_env.ps1
update_project.ps1
package_for_transfer.ps1
cell_stitching_project
stitched_output
docs
tests
```

## 四、安裝 Basler Pylon

如果新電腦需要使用 Basler 相機，請先安裝 Basler Pylon Camera Software Suite。

安裝後可使用 Pylon Viewer 確認相機是否能被偵測到。若 Pylon Viewer 無法看到相機，專案內的 Python 程式通常也無法正常讀取相機。

## 五、建立 Python 與 GPU 環境

以系統管理員或一般 PowerShell 開啟專案資料夾：

```powershell
cd C:\Cell_Project\Cell_Project
Set-ExecutionPolicy -Scope Process Bypass
```

如果電腦有 NVIDIA GPU，執行：

```powershell
.\install_project.ps1 -RequireCuda
```

此腳本會自動完成：

- 尋找或安裝 Miniconda。
- 建立 Python 3.12 conda 環境。
- 安裝 PyTorch CUDA 版本。
- 安裝 OpenCV、Ultralytics、pypylon、ONNX 等專案套件。
- 執行專案環境檢查。

如果要指定環境放在 E 槽，可以使用：

```powershell
.\install_project.ps1 -RequireCuda -EnvPath "E:\Cell_Project_gpu_env"
```

如果沒有 GPU，則使用：

```powershell
.\install_project.ps1
```

## 六、驗證安裝結果

GPU 驗證：

```powershell
.\.conda-gpu\python.exe -c "import torch; print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NO CUDA')"
```

專案環境驗證：

```powershell
.\.conda-gpu\python.exe -m cell_stitching_project.verify_environment --workspace-root . --require-cuda
```

Basler 驗證：

```powershell
.\.conda-gpu\python.exe -m cell_stitching_project.verify_environment --workspace-root . --require-cuda --require-basler
```

如果使用自訂環境路徑，例如 `E:\Cell_Project_gpu_env`，請改用：

```powershell
E:\Cell_Project_gpu_env\python.exe -m cell_stitching_project.verify_environment --workspace-root "C:\Cell_Project\Cell_Project" --require-cuda
```

## 七、硬體預檢

確認 Basler 相機、XY 馬達控制板、序列埠與 CUDA 環境：

```powershell
.\hardware_preflight.bat
```

預設會檢查常用相機序號與 COM7、COM8。若新電腦的序列埠不同，請依裝置管理員顯示的 COM 編號調整指令或程式設定。

## 八、啟動主要功能

Basler 即時拍攝：

```powershell
.\.conda-gpu\python.exe -m cell_stitching_project.capture_basler --output-dir "C:\Cell_Project\captures"
```

即時 AI 偵測：

```powershell
.\.conda-gpu\python.exe -m cell_stitching_project.detect_live --output-dir "C:\Cell_Project\session_output" --save-crops
```

GPU 影像拼接：

```powershell
.\gpu_stitch.bat
```

硬體 GUI：

```powershell
.\run_hardware_gui.bat
```

完成環境驗證後，建立無 CMD 視窗的日常桌面捷徑：

```powershell
.\install_gui_shortcut.ps1
```

`run_hardware_gui.bat` 保留為診斷模式。若日常捷徑啟動失敗，請先用診斷模式查看錯誤，並檢查 `logs/hardware_gui_startup.log`。移動或重新 clone 專案後，請重新執行捷徑安裝腳本。

白血球蛇形掃描、偵測後暫停拍攝與繼續掃描：

```powershell
.\run_wbc_serpentine_capture.bat
```

## 九、常見問題

`nvidia-smi` 找不到：

- 代表 NVIDIA 驅動未安裝或未加入系統路徑。
- 請先安裝或更新 NVIDIA 驅動，重開機後再執行安裝腳本。

`torch.cuda.is_available()` 顯示 `False`：

- 可能是 PyTorch CUDA 版本或驅動不匹配。
- 可重新執行：

```powershell
.\update_project.ps1 -RequireCuda
```

`pypylon` 匯入失敗：

- 請確認 Basler Pylon Camera Software Suite 已安裝。
- 再重新執行專案安裝或更新腳本。

Pylon Viewer 看不到相機：

- 請檢查 USB/網路線、相機電源、驅動與防火牆。
- 先讓 Pylon Viewer 能看到相機，再回到專案測試。

馬達無反應：

- 檢查 Arduino 或馬達控制板是否插入。
- 檢查裝置管理員中的 COM 編號。
- 確認程式內設定的序列埠與實際 COM 編號一致。

## 十、交付前檢查清單

- 已成功解壓縮專案。
- 已安裝 Basler Pylon。
- 已成功建立 Python / GPU 環境。
- `torch.cuda.is_available()` 回傳 `True`。
- `verify_environment` 顯示通過。
- Pylon Viewer 能偵測 Basler 相機。
- `hardware_preflight.bat` 可完成硬體檢查。
- 可啟動 Basler 拍攝、AI 偵測、XY 馬達控制與白血球掃描流程。

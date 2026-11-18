# MSH 線上安裝與自動更新

本文件為 2026-11-17 核定的新流程。來源版本 `0.1.5-dev.4` 使用獨立的 `MSH-Releases` 發行來源，仍屬內部候選，非正式交付版。
不需要使用者安裝 Git、Python 或 Conda。模型與研究資料政策維持原狀。
既有 `dev.2` 二進位仍包含先前的來源設定，原樣保留；其已驗證項目見[候選版驗證報告](ONLINE_INSTALL_VALIDATION_20261117.md)，不能視為已改用新來源。`dev.3` GPU 候選超過 Release 附件上限，由交付檢查攔下，未發布；`dev.4` 改用較高壓縮並保留自動更新進度視窗。

## 使用者流程

1. 下載並開啟 `MSH_Setup_v<版本>_ONLINE.exe`。
2. 安裝器盤點顯示卡，預選 NVIDIA GPU 套件；未找到 NVIDIA 時預選 CPU 備用。
   這只是安裝選擇，不能證明 CUDA 相容。可手動切換 GPU／CPU。
3. 透過 HTTPS 下載固定版本的完整套件，用安裝器內固定的 SHA-256 驗證後，才啟動套件安裝。
   套件包含 Python、依賴與必要 DLL；不在目標機臨時執行 pip 或安裝開發環境。
4. 缺少 Basler pylon 安裝紀錄時，可選擇安裝已核定的官方元件。官方安裝介面保留授權確認及 USB 元件選擇，可能要求管理員權限與重新開機。
   找到既有 pylon 時不自動替換或升級；安裝紀錄不能證明 USB 驅動完整或版本相容。
5. 從桌面／開始功能表開啟 MSH。實際執行小型 CUDA 運算，成功才將 GPU 用於 GUI 辨識；失敗時顯示 CPU 備用原因。
   CPU 套件即使放在 NVIDIA 電腦上仍是 CPU 版；需要改裝 GPU 套件才能啟用 CUDA。
6. 「說明 → 環境診斷」顯示系統、PyTorch、運算能力與 Basler 軟體紀錄；檢查不開啟相機／COM。
   NVIDIA 驅動下載與 Basler 官方下載頁也保留在說明選單。NVIDIA 驅動不會被 MSH 靜默改裝。

Windows 10/11、Intel/AMD x64 為支援目標；不涵蓋 Windows ARM。
GPU 架構／驅動／CUDA 相容性、USB 相機與即時掃描速度都需要逐項驗證，不能保證所有設備。

## 更新流程與設備安全

- 啟動後背景檢查新版；離線、GitHub 被封鎖、Private repository 無存取權或更新檔缺失時，不阻擋主程式。
- 手動按「檢查更新」即啟動新版下載；背景檢查找到新版時先徵求同意。下載進度可取消；中斷或雜湊不符時移除本次 partial，不執行它。
- 安裝檔只接受 `cioudio931105-maker/MSH-Releases` 的 GitHub HTTPS Release URL，重新導向僅允許 GitHub 的指定附件網域；原 Private 原始碼庫的附件不在允許清單中。
- 下載完成後，相機／馬達仍連線、手動移動、拍攝／掃描／預覽／其他背景執行緒或已登記子程序尚未結束時，顯示等待狀態，不關閉 MSH。
  使用者自行正常結束工作與斷線後自動繼續，也可按「稍後再更新」保留下載。
- 安全條件滿足後，呼叫既有正常關閉流程。PowerShell 輔助程序等待原 MSH 程序退出，重新驗證 SHA-256，再自動安裝並重新啟動 APP。Windows 權限或官方驅動授權介面仍可能要求使用者操作。
  自動模式跳過安裝精靈的逐步確認，但保留下載／安裝進度與取消入口；不採完全隱藏的安裝模式。
  等待逾時即取消，沒有 taskkill、強制終止、自動重開機或強制關閉設備。
- 安裝器使用 MSH 的具名 mutex，停用 Windows Restart Manager 自動關閉 APP。若另一個 MSH 已開啟，必須先正常關閉。
- 原始碼模式可檢查／下載，但不自動關閉並安裝；安裝 APP 不會更新 Git checkout。
- 這不是整台機器的工作排程管理器；MSH 之外獨立啟動的訓練／其他設備程式需由使用者自行妥善結束。

## GitHub 位置

- 原始碼與研究歷史留在 Private 的 `cioudio931105-maker/Microscope-Scanner-Helper_MSH`；不變更其可見性或改寫歷史。
- 經審核的安裝附件、checksum、manifest、說明與必要授權／對應來源交付資訊，發布到 Public 的 `cioudio931105-maker/MSH-Releases`；不搬入原庫 Git 歷史或研究資料。
- 更新器讀取 `MSH-Releases/main/latest.json`，不是讀取原始碼庫的 main 或最新 commit 來直接執行程式碼。
- 更新範本為 `release/latest.example.json`；不能直接當成有效 manifest 發布。
- 新版附件與有效 `latest.json` 尚未發布前維持手動提供測試包。APP 沒有內嵌 token，也不借用開發者的 Git 登入資訊。
- 發行前仍需審查附件、授權／對應來源與驗收證據，再取得發布授權；本次改設定不執行 Release、tag 或上傳。
- 只有 CPU/GPU 附件及線上安裝入口都已可匿名下載、驗證完成後，才發布真實 `latest.json`。

## 建置（開發／發行端）

CPU／GPU 各使用獨立、已驗證的 Python 3.12 環境，先執行現有來源測試。
不新增第三方 Python 依賴；新增程式只使用標準函式庫及現有 Tk。

```powershell
.\scripts\build_release.ps1 -Runtime cpu -PythonPath .\.venv312-cpu\Scripts\python.exe -Candidate
.\scripts\build_release.ps1 -Runtime gpu -PythonPath .\.venv312-release-gpu\Scripts\python.exe -Candidate
python scripts/build_online_installer.py --candidate --cpu dist/release/v0.1.5-dev.4/MSH_Setup_v0.1.5-dev.4_CPU_CANDIDATE.exe --gpu dist/release/v0.1.5-dev.4/MSH_Setup_v0.1.5-dev.4_GPU_CANDIDATE.exe
```

`build_online_installer.py` 要求 CPU/GPU 版本、mode、來源 commit、來源雜湊及純應用程式政策一致，並核對實際套件 checksum。
更新器 `msh_update.py` 的來源雜湊也必須相符，避免把仍指向 Private 原庫的舊 APP 與新發行庫的線上入口混用；改來源後須重建 CPU／GPU 與 ONLINE 三個包。
正式模式仍沿用乾淨來源與版本 tag 的建置要求；不允許把 candidate 直接改名成 release，也不覆寫既有產物。
產物位於 `dist/release/v<版本>/`，包含安裝檔、`.sha256` 與 `.build-manifest.json`。
正式版不能使用 `-Candidate`／`--candidate`；本次不建立或發布正式版。
完整的一鍵建置、私人 artifact 審核及跨庫發行方式見[自動建置與發行](AUTOMATED_RELEASE_zh_TW.md)。

Basler 自動下載需提供三個參數：

```powershell
python scripts/build_online_installer.py --candidate --cpu <CPU安裝檔> --gpu <GPU安裝檔> --pylon-installer <本機已檢閱的官方安裝檔> --pylon-url <該版本的Basler官方HTTPS網址> --pylon-license-reviewed
```

程式由本機已檢閱檔案計算 SHA-256，固定到 bootstrapper。
未提供時，僅內部 candidate 可以編譯，Basler 選項會明示只能開啟官方下載頁；不能宣稱已完成自動驅動安裝。
正式線上安裝版缺少已核定 Basler 來源／雜湊時拒絕建置。
官方下載位址、授權檢閱與 USB 元件的實際相容版本需完成後，才可移除此限制。

軟體診斷可由自動驗收呼叫，不會建立硬體物件：

```powershell
.\dist\gpu\MSH\MSH.exe --msh-environment-report <驗收文字檔絕對路徑>
```

## 發行前驗收清單

- [ ] Windows 10 x64 乾淨機：無 Python/Git/Conda，安裝、啟動、功能、升級、解除安裝及資料保留。
- [ ] Windows 11 x64 乾淨機：相同流程；新帳號但已有系統依賴不等於乾淨機。
- [ ] 線上安裝：GPU／CPU 選擇、離線、代理／封鎖、取消、損壞附件與重試。
- [ ] 更新：匿名可下載、實際版本遞增、下載／驗證、正常退出與安裝、再次啟動。
- [ ] 設備／工作進行時禁止安裝；既有安裝器不強制終止程序。
- [ ] 核定官方 Basler runtime 版本、HTTPS URL、SHA-256、授權聲明及 USB 元件。
- [ ] B 地 NVIDIA 型號／驅動／CUDA 運算及 GPU 不相容時的 CPU 備用測試。
- [ ] B 地 Basler USB 驅動、實際取像、COM／韌體／平台與停止流程；遵守既有硬體限制。
- [ ] 公開前 Git 歷史、依賴授權／來源交付、簽章或明確的未簽章標示與下載完整性。

離線安裝包依使用者決定延後到功能與驗收穩定後處理，不把目前 GPU/CPU 內部套件當作已完成最終離線交付。

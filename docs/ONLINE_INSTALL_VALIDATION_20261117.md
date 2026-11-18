# MSH 線上安裝與自動更新：開發候選驗證

日期：2026-11-17（Asia/Taipei）。版本：`0.1.5-dev.2`。狀態：內部驗證候選，尚非正式交付版。
後續變更：來源 `0.1.5-dev.3` 已改回獨立 Public `MSH-Releases`；本報告的 `dev.2` 安裝檔與雜湊保留不變，仍含先前設定，不能當作新來源版本交付。`dev.3` 尚需重新建置與驗收。
分支：`codex/online-install-update`；基底 HEAD：`8026e2f34db896baea2de26ccc58e38988ef7c9c`。實際內容包含本次尚未提交的修改，manifest 明示 candidate／dirty source，不能把基底 commit 當成全部新程式碼已保存。

## 已完成的軟體範圍

- 線上入口按顯示卡盤點優先選 NVIDIA GPU，CPU 為備用；套件內附 Python、依賴與 DLL。
- 啟動後背景檢查更新，離線／Private／發行資訊缺失時保留既有程式使用；確認後下載及驗證 SHA-256。
- 更新僅接受目前 MSH repository 的 Release URL 與指定 GitHub 附件重新導向。取消、截斷、錯誤 checksum 或來源異常不執行下載內容。
- 連線、預覽、移動、拍攝／掃描、登記執行緒／子程序等狀態會阻止安裝；由既有正常關閉流程退出，再由 helper 等待程序退出及重驗雜湊後開啟安裝器。
- 清理子程序的開發／舊版 DLL 搜尋環境；不改使用者的全域環境或強制終止程序。
- 實際 CUDA kernel 測試通過才選 GPU；GUI 辨識與核心 runtime 採用此判斷。提供環境診斷及官方驅動下載入口。
- AGENTS.md 補充執行環境可隨安裝包交付，仍禁止提交開發環境／秘密資訊，並保留所有設備安全與 Git 授權限制。

## 驗證證據

| 項目 | 結果／範圍 |
| --- | --- |
| CPU 完整來源測試 | 196 項：195 通過、1 項因可選 ONNX 依賴略過；無失敗 |
| GPU 環境針對性測試 | 42 項通過；另實測 RTX 2060 的小型 CUDA 運算 |
| Windows PowerShell helper | 正常等待／交接、hash 改動、父程序逾時及 installer 失敗測試通過；程序啟動以 recorder 取代，沒有安裝 fixture |
| 真實 Tk 元件 | 說明選單、下載視窗與進度更新建立成功；無下載或硬體動作 |
| Inno 編譯 | 主安裝器、有／無 Basler 固定安裝來源的線上入口皆編譯成功 |
| CPU payload | 4876 檔、303 個第一方檔案，0 issues |
| GPU payload | 4925 檔、303 個第一方檔案，0 issues |
| 封裝 EXE 軟體診斷 | CPU／GPU 退出碼皆 0；GPU 包實際 CUDA 運算通過 |
| 移除開發 PATH 後診斷 | 僅保留 Windows 系統 PATH，移除 PYTHONHOME/PYTHONPATH、使用隔離 profile 與 cwd，CPU／GPU 仍皆退出 0；不是乾淨 OS 驗收 |
| 實際 GPU GUI | 主畫面啟動，X/Y 未連線、預覽未啟動；診斷顯示 RTX 2060／CUDA，關於顯示 v0.1.5-dev.2；更新失敗提示後仍可操作，最後正常關閉、程序消失 |
| 安裝檔完整性 | 三個 candidate 的實際 SHA-256 均與 sidecar 相符 |
| 來源政策與秘密掃描 | 本次來源檔案通過 allowlist、秘密候選規則及 diff 格式檢查；未 stage |

GUI 驗證使用 computer-use 技能，只操作本次 `dist/gpu/MSH/MSH.exe` 視窗。沒有連線、預覽、取像、馬達移動或硬體參數修改。
本機已有 MSH 安裝登錄與桌面捷徑，因此沒有覆蓋安裝、解除安裝或搬動使用者現有安裝。不能宣稱新候選版的實際遷移／資料保留已驗收。

## 候選檔案

檔案都在 `dist/release/v0.1.5-dev.2/`，未簽章、未上傳。`dev.1` 是已被取代的中途建置，不作本次交接依據。

| 檔名 | Bytes | SHA-256 |
| --- | ---: | --- |
| `MSH_Setup_v0.1.5-dev.2_CPU_CANDIDATE.exe` | 229365386 | `7178d25af16f82d9d75d255055bb0fec724039a00a184b6f5b974654247ada7b` |
| `MSH_Setup_v0.1.5-dev.2_GPU_CANDIDATE.exe` | 1651316923 | `3b36f7761dd3a8fc9f864b237cf5154cc1a3b923d1b8a2f3889451dd3340220b` |
| `MSH_Setup_v0.1.5-dev.2_ONLINE_CANDIDATE.exe` | 2275235 | `dfd228ef9524d9bbfd56ed0cb3fc09a5f7502578758d248bf0e7a957e8967466` |

ONLINE candidate 尚未設定已核定的 Basler runtime 安裝來源／hash，因此只提供官方下載頁引導；不能宣稱已完成 Basler 自動安裝。
它內附的 CPU/GPU 下載網址是目前 Private repository 的預期 Release 附件位置，附件尚未發布，不能把此候選當作現成可對外使用的線上下載服務。
CPU/GPU 完整套件可供後續受控人工安裝驗收，但目前沒有完成最終離線交付承諾。

## 仍需完成

1. 核定與實際 USB 相機相容的 Basler 官方 runtime 版本、HTTPS URL、SHA-256、授權／來源交付條件。正式 online builder 在缺少它時拒絕建置。
2. 無 Python／Git／Conda 的乾淨 Windows 10 與 Windows 11 x64：首次安裝、功能、更新、解除安裝及資料保留。
3. B 地 NVIDIA 型號／驅動、Basler USB 取像、COM／韌體／平台與停止流程，並評估 CPU 備用即時掃描速度。不得清空實驗室電腦來代替備份與測試規劃。
4. 已發布且可匿名取得的真實版本資訊與附件，及實際下載 → 正常退出 → 安裝 → 重開的完整驗收。
5. 現有 Git 歷史及依賴授權／對應來源審查完成並取得公開授權後，才考慮 Public、Release、簽章等發行動作。
6. 線上版穩定後另完成最終離線版。

既有 v0.1.4／B 地韌體或其他分支的整合與實機驗收，不因本次封裝而自動完成。
沒有 commit、push、merge、tag、公開 repository、發布 Release 或執行驅動安裝。既有 `Ultralytics/` 保留。
Global 待辦：MSH-041（驗收）、MSH-042（延後的完整離線版）。

## 本次修改檔案

- `docs/ONLINE_INSTALL_VALIDATION_20261117.md`
- `AGENTS.md`
- `MSH.spec`
- `README.md`
- `cell_stitching_project/runtime.py`
- `docs/DIRECT_INSTALL_RELEASE_WORKFLOW_zh_TW.md`
- `docs/release/BUILD.md`
- `docs/release/RELEASE_CHECKLIST.md`
- `installer/MSH.iss`
- `installer/PREREQUISITES.txt`
- `launch_msh.pyw`
- `msh_app/cell_identification/object_detection.py`
- `msh_update.py`
- `msh_version.py`
- `msh_workers.py`
- `release/latest.example.json`
- `scripts/audit_packaged_application.py`
- `scripts/build_release.ps1`
- `docs/ONLINE_INSTALL_AND_UPDATE_zh_TW.md`
- `installer/MSH_Online.iss`
- `installer/run_update.ps1`
- `msh_environment.py`
- `msh_update_safety.py`
- `msh_update_ui.py`
- `scripts/build_online_installer.py`
- `tests/test_online_installer.py`
- `tests/test_online_update.py`
- `tests/test_update_handoff_powershell.py`

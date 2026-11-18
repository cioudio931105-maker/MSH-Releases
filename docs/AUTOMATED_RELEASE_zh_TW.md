# 單一 repo 開發與發行

日後只在 `cioudio931105-maker/MSH-Releases` 維護應用程式原始碼、建置與發版。
舊 Private `Microscope-Scanner-Helper_MSH` 保留原有研究歷史、模型與本機資料，無須每次同步程式碼回去。
一般使用者仍下載安裝版，不需要 Git、Python 或 GitHub 登入。

## 遷移方式與目前狀態

本機乾淨副本位於 `C:\Projects\MSH-Releases`，使用獨立的 `codex/single-repo-development` branch。
它以公開庫原本的 README 歷史為基礎，帶入目前可發行的應用程式快照；沒有複製舊 `.git`、模型、資料、開發環境或舊安裝檔。
程式碼會公開，適用既有 AGPL-3.0-only 及第三方聲明。
來源提交／推送與 main 整合須完成審查並取得使用者明確授權，狀態以 Git 紀錄為準。本文件不代表已完成硬體或正式發行驗收。

## 為何不需要設定個人 token

GitHub 在每個 Actions job 開始時，自動提供限於此 repo 的 `GITHUB_TOKEN`，工作結束後失效。
建置／檢查工作只保留讀取權限；只有使用者明確執行的 publish job 取得 Contents 寫入權限。
不需要建立 `MSH_RELEASE_TOKEN` 或其他個人存取金鑰，也沒有跨庫上傳步驟。
APP 下載更新使用公開的 `main/latest.json` 與 Release 附件，不攜帶 token。

## 日常開發

1. 在新的本機 `MSH-Releases` 專案開工；模型與研究資料仍放在本機或專案外。
2. 修改、執行適用測試、檢閱 diff，再依原有明確授權規則 commit／push／PR。
3. 原私人專案不用每次搬動或同步，只保留歷史及原檔。

模型與資料沒有搬進新庫。開發環境也沒有複製成 Git 檔案；本機驗證可明確指定既有 Python 執行檔。
此機的新副本可透過忽略的本機連結共用已驗證的 CPU／GPU 環境。新的開發機則使用 Python 3.12 的獨立環境，安裝對應的 `requirements-release-cpu.txt` 或 `requirements-release-gpu.txt`。
不要在兩個資料夾交錯修改同一功能。既有已安裝 MSH 與桌面捷徑不因來源遷移而改動。

## GitHub Actions

在此 repo 的 **Actions → MSH installer delivery → Run workflow**，Branch 選 main：

- `candidate`：測試、打包 CPU／GPU、檢查 fresh payload 與軟體報告。沒有公開二進位 artifact 或 Release；驗收前的內部測試包由本機建置保存。
- `prepare-release`：只接受穩定版、匹配來源 tag、乾淨來源及完整驗收。成功後產生可檢閱的交付 artifact，包含 CPU／GPU／ONLINE 安裝檔與來源。
- `publish`：填入已檢閱的成功 prepare-release `build_run_id`，以當次內建授權發布同一份產物，不重新建置或手動搬檔。

此 repo 是公開的：工作紀錄及可存取的 artifact 不應視為私密儲存。
`release/acceptance.json` 只准放公開安全摘要，格式沿用範本，不能放病患資料、研究影像、原始紀錄、私人附件或憑證。
可在同 repo 的證據 branch 保存摘要，以 `evidence_ref` 指定，避免改掉實際受驗收的來源 commit。
程式檢查摘要欄位、版本、來源 commit 與常見秘密候選，但不能判斷所有敏感文字；提交前仍須人工檢閱。

Basler 來源、SHA-256、授權與 USB 相容性核定後，才設定非秘密的 Actions variables `MSH_PYLON_URL`、`MSH_PYLON_SHA256`。
流程只下載並驗證官方 prerequisite，不在 CI 安裝相機驅動或操作設備。
GitHub Windows runner 沒有實體 NVIDIA／Basler／XY 平台；CI 成功不等於 B 地硬體驗收。
正式二進位仍須完成第三方再散布／對應來源與 Windows 10／11／B 地驗收，才會被公開上傳。

## 發行順序

交付清單包含 14 個明確附件：三種安裝檔各自搭配 SHA-256 與建置清單，
應用程式來源 ZIP 及 checksum、發行說明、LICENSE、第三方聲明。
來源 ZIP 不帶舊 Git 歷史或研究資料；第一方來源 ZIP 不能取代第三方另有要求的對應來源。

先建立 draft、上傳白名單檔案並核對 GitHub 雜湊，再公開 Release 並匿名下載驗證；
全部通過後才條件式寫入同庫 `main/latest.json`，最後讀回比對。
上傳／下載失敗不改更新指標；不覆寫不同內容的既有附件、不降版、不強制改遠端歷史。
若公開 Release 後的匿名驗證失敗，Release 可能已可見，更新指標仍保持前版，需查明原因再重試。

`latest.json` 是正常的同庫更新設定，允許追蹤；模型、原始資料及本機 `.env` 仍禁止提交。
來源與更新指標由同一個 repo 管理，不代表每個 main commit 都會立即更新使用者 APP；正式發布仍是明確的操作。

## 本機候選建置

```powershell
<CPU環境的python.exe> scripts/release_pipeline.py build --candidate --cpu-python <CPU環境的python.exe> --gpu-python <GPU環境的python.exe> --notes release/NOTES.md
```

流程測試、平行打包、檢查實際 payload 與軟體報告，再組合線上入口及交付清單。
所有附件必須小於 2 GiB；同名產物不覆寫，重建需升版。開發／建置環境不是 Git 內容。
既有 dev.4 候選是遷移前快照，留在原專案；新副本是 dev.5，不能把舊二進位改名充當本版。

```powershell
python scripts/publish_release.py dist/delivery/v<版本>/release-plan.json
```

上述預設為 dry-run，只核對檔案；真正發布只允許在此 repo 的 main publish job，使用 GitHub 自動提供的短效授權。
正式離線交付依既定順序另做，線上安裝仍須連得到 GitHub 及必要官方元件站。

參考：[GitHub 內建授權的範圍與期限](https://docs.github.com/en/actions/concepts/security/github_token)。

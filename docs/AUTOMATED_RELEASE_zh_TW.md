# 自動建置與發行

只維護 `Microscope-Scanner-Helper_MSH` 這個私人開發庫。
`MSH-Releases` 是公開下載站，由程式上傳已核對的交付檔案；不需要複製程式碼、Git 歷史或手動搬安裝檔。

## 一次性啟用

目前流程已加入本機工作樹，尚未 commit／push，也尚未在 GitHub 執行。
經使用者授權提交、推送與整合後，工作流程必須存在於私人庫的 `main`。
不會因為修改本機檔案就自動上線。

1. 在私人庫啟用 GitHub Actions。Windows runner 會使用該帳號的 Actions 額度，超出免費額度可能計費；不要因此開放含研究歷史的原庫。
2. 建立 fine-grained GitHub token：只選公開的 `MSH-Releases`，權限 **Contents: Read and write**，設定適當到期日。
3. 在私人庫 **Settings → Secrets and variables → Actions → New repository secret** 建立 `MSH_RELEASE_TOKEN`。只在 GitHub 的秘密欄位輸入；不放入程式、APP、安裝檔或對話。
4. Basler 官方版本、SHA-256、再散布與相容性確認後，才設定 Actions variables `MSH_PYLON_URL` 與 `MSH_PYLON_SHA256`。流程只在 CI 下載並驗證官方安裝檔，不會執行驅動安裝。

原庫的 `GITHUB_TOKEN` 只保留來源及 Actions 讀取權限；跨庫寫入只在最後的 publish 步驟使用上述專用 token。
無須在公開庫另建 workflow，也不會修改兩個庫的可見性。

## 平常開發

在私人庫 **Actions → MSH installer delivery → Run workflow**：

- Branch 固定選 `main`。
- `operation = candidate`：自動測試、建立 CPU／GPU／ONLINE 候選安裝檔並產生私人 `msh-delivery` artifact。
- 候選版僅供內部驗證，不會送到公開 Release，也不能成為 APP 的正式更新。

此時不需要發版 token。GPU 建置使用 CUDA 套件，但 GitHub Windows runner 沒有實體 NVIDIA GPU；CI 的成功不能當作 GPU 或相機實機驗收。
目前鎖定 Windows x64、Python 3.12.13、Inno Setup 6.7.4 及已驗證的 Python 套件版本。
CPU／GPU 在各自 runner 建置，避免混用環境。

## 正式交付：先產物，後批准

1. 完成穩定版本、來源檢閱及對應 tag，例如版本 `1.2.3` 與 `v1.2.3` 指向同一個已整合的 main commit。
2. 完成乾淨 Windows 10／11、B 地硬體及再散布／來源交付驗收。依 `release/acceptance.example.json` 填寫真實的版本、**完整來源 commit** 和證據。
3. 將驗收紀錄保存於私人庫的 `release/acceptance.json`；可放在獨立證據 branch，執行時以 `evidence_ref` 指定。這避免為了新增驗收文字而改掉受驗收的來源 commit。不得把 pending 改成 passed 來跳過測試。
4. Run workflow 選 `prepare-release`。它只建置與準備私人 artifact，摘要會列出來源 commit、14 個公開交付檔案的名稱、大小與 SHA-256。
5. 檢閱該次成功執行的 `msh-delivery`。確認後，再 Run workflow 選 `publish`，在 `build_run_id` 填入該次執行編號。

publish 直接使用已檢閱的同一份 artifact，不重新建置，不需要下載再上傳。
只接受成功的 main 工作流程、正式版及完整驗收。artifact 保留 14 天，逾期需重新準備與檢閱。

## 自動上傳的內容與順序

交付共 14 個檔案：CPU／GPU／ONLINE 安裝檔各自搭配 checksum 與建置清單，
一份不含 Git 歷史的應用程式來源 ZIP 及 checksum、發行說明、LICENSE、第三方聲明。
來源 ZIP 排除模型、研究影像、設備 profile、`.env`、虛擬環境及實際的私人驗收紀錄。
第一方來源 ZIP 不能取代第三方套件另有要求的對應來源；正式驗收必須處理既有授權／來源交付缺項。

流程先建立 draft、上傳白名單檔案、核對 GitHub SHA-256，再公開 Release 並匿名重新下載驗證。
全部通過後，最後才寫入 `MSH-Releases/main/latest.json`，再讀回比對。
APP 只讀公開庫這份 main 更新清單；不會登入或讀取私人來源庫。

上傳失敗、公開下載失敗或 latest.json 同時被更動時，流程會停止，保留現有更新指標。
同版本可以安全重試，但不覆寫／刪除不同內容的既有附件、不降版，也不自動修復遠端資料。
若 Release 已公開但匿名驗證失敗，它可能已可見；APP 更新清單仍維持舊版，須查明原因後重試。

## 本機建置

保留原本開發環境，另外準備兩個已安裝對應鎖定檔的 Python 3.12 環境。
目前本機預設 CPU 為 `.venv312-cpu`，GPU 為 `.venv312-release-gpu`：

```powershell
.\.venv312-cpu\Scripts\python.exe scripts/release_pipeline.py build --candidate --notes release/NOTES.md
```

整個流程會測試、平行打包、檢查實際 frozen payload、執行不接硬體的環境報告，再建立交付清單。
安裝套件採較高壓縮與分塊平行壓縮；每個 Release 附件必須小於 2 GiB，超限即停止，不能上傳不完整的交付。
產物保存在 `dist/release/v<版本>`；交付清單在 `dist/delivery/v<版本>/release-plan.json`。
既有同名產物不覆寫，重建前應升版。建置過程不要修改來源。

```powershell
python scripts/publish_release.py dist/delivery/v<版本>/release-plan.json
```

上述預設是離線 dry-run，驗證檔案及來源一致性，不上傳。
真正發布須在已獲授權的發版環境明確加 `--publish` 並提供 `MSH_RELEASE_TOKEN`。
線上安裝需要可連線到 GitHub 與官方元件站；沒有網路仍可使用既有已安裝版本。
最終離線交付包依既定決定另行製作。

參考：[GitHub workflow 手動執行](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow)、
[GITHUB_TOKEN 權限](https://docs.github.com/en/actions/tutorials/authenticate-with-github_token)、
[Inno Setup 6.7.4](https://github.com/jrsoftware/issrc/releases/tag/is-6_7_4)。

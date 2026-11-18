# AGENTS.md — Microscope-Scanner-Helper_MSH 作業規則

## 專案身分

本專案正式名稱為 `Microscope-Scanner-Helper_MSH`，簡稱 `MSH`。

MSH 是顯微鏡掃描研究專案，涵蓋：

- Basler camera 影像擷取
- XY platform 與步進馬達控制
- Arduino firmware
- 白血球（WBC）AI detection、classification 與訓練
- 顯微影像 stitching
- 掃描、辨識與硬體操作 GUI
- 實驗資料、模型、輸出與驗證流程

## Git repository 與工作地點

- A 地主要負責軟體開發、文件與 Git 整理。
- B 地主要負責實體顯微鏡、Basler camera、XY platform、Arduino 與整合硬體驗證。
- `origin` 是 `cioudio931105-maker/MSH-Releases`，同時用於應用程式來源開發與發行。
- 原 Private `Microscope-Scanner-Helper_MSH` 保留舊研究歷史與本機資料，不再作為這個乾淨來源副本的日常編輯位置；不得搬入它的 `.git` 或重新公開其歷史。
- `legacy-origin` 只作舊版歷史參考，不應 push。
- 除非使用者明確解除限制，禁止 push。
- 除非使用者明確要求，禁止 commit。

## 開始修改前

1. 先閱讀題目、README、相關文件、相關程式碼與本檔規則。
2. 每次修改前先執行並檢查：
   - `git branch --show-current`
   - `git status`
3. 若工作樹已有修改或 untracked 檔案，先說明風險。
4. 不得把既有修改當作自己的修改覆蓋、清除或還原。
5. 非瑣碎任務先提出最小修改計畫。
6. 題意不明時，採最保守、最小影響的方案並明列假設。

## 禁止的 Git 操作

未經使用者明確授權，禁止：

- `git pull`
- `git push`
- `git merge`
- `git rebase`
- `git reset`
- `git checkout --`
- `git restore` 大量還原
- force push
- 刪除 branch
- 改寫已發布歷史

永遠禁止使用：

- `git add .`
- `git add -A`
- 對未確認範圍做大量 stage

必須以明確檔名或明確目錄逐批 stage。

## 修改範圍

- 只修改完成目前任務必要的檔案與區域。
- 不要順便重構、重新命名或整理整個專案。
- 保留既有檔名、函式名、class 名、CLI、輸入輸出格式與 public API。
- 不要新增依賴，除非現有環境無法完成；新增前先說明原因與影響。
- 不要刪除 Legacy、dataset、model、實驗資料或看似重複的硬體程式。
- 不要因檔案被 `.gitignore` 排除，就將它視為可刪除垃圾。

## 硬體高風險區

以下內容屬高風險區：

- Basler camera 與 Pylon 相關程式
- Basler camera profile
- COM Port 與 serial communication
- XY motor、X motor、Y motor 與步進馬達控制
- Arduino firmware
- 掃描方向、步距、速度、延遲與安全邊界
- 相機 serial number
- 硬體 preflight 與自動移動流程

修改任何硬體控制程式前，必須先說明：

1. 將修改哪個檔案與參數。
2. 對相機、平台、馬達、掃描路徑或安全性的可能影響。
3. 是否可能造成方向反轉、超程、撞擊、失步、錯誤 COM 連線或錯接相機。
4. A 地能完成哪些軟體驗證。
5. 哪些項目必須到 B 地以實體硬體驗證。

禁止自行修改：

- COM Port
- 馬達步距
- 移動方向或 axis mapping
- 軟體或實體安全邊界
- 掃描範圍
- 速度、加速度與關鍵延遲
- Basler camera serial number
- camera profile 中與特定設備綁定的關鍵值

除非使用者明確指定新值並授權修改。

## Legacy 與混合資料目錄

`stitched_output/` 不是純 output 目錄，禁止整體忽略或整體刪除。

其中可能同時包含：

- legacy GUI/source code
- hardware control code
- Arduino firmware
- Basler camera profile
- image stitching scripts
- WBC detection/classification code
- captured sessions
- dataset
- model checkpoints
- training runs
- generated output
- cache

處理 `stitched_output/` 時必須依子目錄逐項分類。

## 模型、dataset 與實驗資料

### 目前應用程式發行政策（2026-10-19）

- MSH 僅提供應用程式與辨識、分類、拼接、訓練等功能；模型及數據由使用者提供。
- 後續 Git 提交、來源交接包與安裝檔不得包含模型權重、dataset、研究影像、標註、擷取紀錄、實驗輸出或設備專用相機 profile。
- 訓練仍可在本專案進行，但輸入資料、權重、標註及輸出留在本機或外部保存，不得強制加入 Git。
- 應用程式圖示、啟動畫面、程式內的類別定義及測試時產生的合成資料不屬於真實研究資料；不得以此例外提交實際樣本。
- 停止追蹤時保留本機原檔。既有 Git 歷史及舊安裝檔不會自動變成無資料版本，不得擅自改寫歷史。
- 提交前執行 `python scripts/audit_application_files.py`，並 review 實際 diff；詳細規則見 `docs/APPLICATION_ONLY_POLICY.md`。

模型、dataset、captured sessions、training runs、實驗影像和輸出可能不適合普通 Git，但必須保留。

禁止：

- 因為檔案很大就直接刪除。
- 因為檔案被 ignore 就直接刪除。
- 把模型或 dataset 當作 cache 清除。
- 未確認備份前移動或重新命名研究資料。
- 未經授權將大型檔案改放 Git LFS 或外部服務。

應區分：

- `BASELINE_INCLUDE`：正式 source、config、docs、tests。
- `EXTERNAL_PRESERVE`：模型、dataset、captured sessions、實驗資料。
- `REGENERATABLE_IGNORE`：cache、build、temporary output、virtual environment。

## 應用程式安裝與更新環境

- 目前應用程式來源、安裝附件與 `main/latest.json` 集中於 Public `MSH-Releases`；舊 Private repository 僅保留歷史。遷移只採用目前應用程式檔案的乾淨快照，不帶研究資料、模型、個人環境或舊 `.git`。
- 自動發版只使用同庫 GitHub Actions 的短效 `GITHUB_TOKEN`；僅 publish job 可取得 Contents 寫入權限。不建立個人發版 token、不提供跨庫寫入。
- 公開 repo 的 Actions log、artifact、branch 與驗收紀錄可能被他人讀取。只能存放經檢閱的公開安全摘要；原始驗收證據、研究資料及秘密留在本機／受控位置。候選二進位不在公開 Actions 上傳，正式附件仍需完整驗收與授權。
- 發行安裝包可包含必要的 Python 執行環境、第三方套件及 DLL；開發用 `.venv`／Conda 環境目錄仍不得提交 Git。
- Windows 10／11 Intel／AMD 64 位元為支援目標；NVIDIA GPU 優先、CPU 備用。正式宣稱相容性前須有對應版本與設備驗收證據。
- 線上安裝／更新的可執行檔須固定版本、使用 HTTPS 並驗證 SHA-256；不得在 APP 內嵌 GitHub token 或其他憑證。
- Basler USB 必要元件使用官方且經授權檢閱的安裝程式；不得自動覆蓋／升級既有驅動或修改設備設定。
- 使用者手動點「檢查更新」即同意下載與自動安裝新版；背景檢查則須另行確認。安裝必須等設備斷線、背景工作結束、MSH 正常退出，並可延後；不得強制終止硬體工作來更新。
- 無網路、下載失敗或驗證失敗不得阻擋既有版本使用。乾淨 Windows 軟體驗收與 B 地硬體驗收分別記錄。

## Secrets 與本機設定

不得 commit：

- `.env`
- API key、token、password
- 私鑰與憑證
- 個人路徑或使用者專用設定
- 未確認安全性的 credential/config
- 本機安裝狀態檔

若設定檔同時包含必要專案設定與敏感值，先提出拆分或範本方案，不得直接 stage。

## 修改後驗證

修改後必須：

1. 執行與修改範圍相符的測試、lint、範例輸入或最小驗證。
2. 執行並 review `git diff`。
3. 檢查 `git status`。
4. 確認沒有 debug 殘留、暫時硬編碼、秘密資訊或無關修改。
5. 分清楚軟體測試、模擬測試與實體硬體測試。

沒有實體硬體時，不得宣稱以下測試成功：

- Basler camera 實機連線或取像
- COM Port 實際連線
- XY platform 實際移動
- 馬達方向、步距、限位或安全邊界驗證
- Arduino firmware 實機驗證
- 完整 microscope scan 實機驗證

只能回報靜態檢查、mock、軟體流程或無硬體測試結果，並清楚註明限制。

## Commit 前必做

如使用者明確授權 commit，commit 前必須：

1. 列出所有 staged files：
   - `git diff --cached --name-status`
2. Review 完整 staged diff：
   - `git diff --cached`
3. 執行適用測試。
4. 再次檢查 `git status`。
5. 確認 staged files 只包含本次任務。
6. 確認未包含：
   - secrets
   - virtual environments
   - cache、log、temp
   - build/dist
   - 未核准模型
   - dataset
   - captured sessions
   - training output
   - 大型 generated media
7. 向使用者摘要修改、驗證結果與已知限制。

## 完成回報格式

每次完成修改後，簡短回報：

- 修改了什麼
- 修改哪些檔案
- 如何驗證
- 測試結果
- 目前 Git 狀態
- 是否適合 commit / push / PR
- 仍有什麼風險或不確定點
- 是否仍需 B 地硬體驗證

## 目錄歸位規則

- 新增共用執行程式放在 `msh_app/core/`，以 `msh_app.core` 套件路徑匯入。
- 來源啟動／捷徑工具放在 `scripts/launch/`，封裝設定放在 `installer/`，依賴定義放在 `requirements/`。
- 歷史模型身分與舊版本環境紀錄放在 `docs/legacy/`，不得改回目前應用程式預設。
- 根目錄只保留 `docs/PROJECT_MAP.md` 列出的標準檔案與必要相容入口；新增例外先說明原因。
- 移動檔案時須同步檢查匯入、相對路徑、文件、測試及建置流程；不得藉整理變更硬體參數、刪除本機資料或改寫歷史。

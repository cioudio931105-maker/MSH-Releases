# MSH 純應用程式原始碼公開方案

2026-10-19 使用者選擇公開應用程式原始碼，模型與研究資料自行私有保存。
目前只準備本機 review／交付內容，尚未公開、commit、push、建 tag 或改變 repository 可見性。
目前沒有乾淨 Windows 測試機；這項驗收保留為待完成，不以本機開發環境取代。

2026-10-20 補充：[第三方部署與來源交付查核](THIRD_PARTY_RELEASE_AUDIT_v0.1.4_zh_TW.md)
已記錄新含授權候選版的實際原生依賴；pylon 原生條款與 AGPL 組合依據、完整對應來源仍未放行。
既有來源＋安裝檔 review ZIP 維持其原雜湊；新增文件／收集器修正／tqdm notice 供下一次來源凍結使用。
下文關於舊 `tmp/rc014b` 的限制指最初候選版；新的配對資訊以查核表列出的 SHA-256 為準。

同日續作的[第三方來源取得證據](THIRD_PARTY_SOURCE_INVENTORY_v0.1.4.md)記錄實際來源下載、
891 個 Python 檔案比對、FFmpeg 官方原檔配對與 128 份 notices。
這些是下一次來源凍結的補件，不回溯改變既有 review ZIP，也不取代尚未確認的原生組合權利。

使用者同日表示認為目前組合可以發佈，據此繼續本機來源整理與 review；這不是廠商已回覆或
所有條款已核對的證據。廠商詢問是釐清條款的一種方式，不把取得書面回覆一概列為本機準備的前置條件。
授權查核仍保留其事實與待確認事項。此判斷不另行授權 commit、push 或公開既有 Git 歷史。
包含最新補件的來源快照另存為 `MSH_v0.1.4_Application_Source_REVIEW_20261020.zip`；
它未與既有候選 EXE 重新建置配對，舊來源／安裝檔與交付 ZIP 保留原樣。

## 授權與交付範圍

- MSH 自有應用程式原始碼採 GNU AGPL 第 3 版（`AGPL-3.0-only`），全文見 [LICENSE](../LICENSE)。
- 第三方來源及 notice 保留原作者、原授權，不把整個第三方目錄重新宣告為 MSH 自有程式。
  詳見 [第三方盤點](../THIRD_PARTY_NOTICES.md) 與 [實際版本 notice 清單](../licenses/README.md)。
- 程式碼包包含辨識、分類、拼接、訓練、GUI、Arduino 原始碼、建置與安裝腳本、測試、文件和 UI 素材。
- 不包含模型、研究影像、dataset、標註、相機專用 profile、輸出、虛擬環境、帳密或 `.git` 內部與歷史。
- 模型／研究資料不隨 MSH 原始碼交付；使用者自備模型本身的授權與資料權利仍需獨立處理。
  本方案不宣告其他模型或資料獲得授權豁免，也不自動公開任何研究成果。

## 發佈方式

既有 Git 歷史仍含舊模型／資料，不能直接把舊 repository 改為公開，也不能把帶歷史的 branch 當成無資料版本。
使用經稽核且不含 `.git` 的來源快照，後續可作公開 Release 的來源附件，或在另行指定的乾淨 repository 中建立新歷史。
本次不建立 GitHub repository、不改寫原歷史，也不猜測新的 push 目的地。

正式二進位發行必須配對相同來源快照，保留建置／安裝腳本、依賴版本、所有適用 notice 與取得對應來源的方式。
目前 `0.1.4` 舊候選 EXE 的來源快照是 `tmp/rc014b`，建置早於本次授權包與包裝規則修改。
本次新來源 review 包不能冒稱可逐位元重現那個候選 EXE；新公開 build 仍須從 review 完成並經核准保存的來源重新建置、驗證。
收集 notice 不等於已交付所有第三方對應來源，也不等於 pylon 原生函式庫的部署條件已全部確認。

本機建立來源包：

```powershell
python scripts/audit_application_files.py
.\package_for_transfer.ps1 -Destination dist\release\v0.1.4\MSH_v0.1.4_Application_Source_REVIEW.zip
```

這是目前工作樹的純程式碼 review 快照，不是從歷史 tag 自動匯出，也不是正式版。
依賴 notice 可用 `scripts/collect_dependency_licenses.py --output <新的目錄>` 收集；它拒絕覆蓋既有目錄。
公開前仍需 review 實際內容、敏感資訊、來源配對與部署條件，並取得明確的 commit／push／發佈授權。

官方參考：

- [GNU AGPL v3](https://www.gnu.org/licenses/agpl-3.0.html)
- [Ultralytics 授權說明](https://www.ultralytics.com/license)

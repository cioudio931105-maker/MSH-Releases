# MSH v0.1.4：2026-10-20 帶往 B 地交接

本次保存純應用程式來源與最新 CPU 候選安裝版，供下一次 B 地驗收及完成剩餘工作。
仍是內部候選版，不是正式公開 Release。精確 Git commit、安裝檔／來源 SHA-256 與建置結果
以交接資料夾內 `HANDOFF_MANIFEST.json`、`BUILD_VALIDATION.md` 和 `.sha256` 為準。
檔名相同的舊 v0.1.4 不代表同一次建置；先核對交接 manifest。

## 接續順序更新（2026-10-20）

使用者回報昨日 B 地實際 GUI 不是 0.1.4，且可能有未提交修改。先保存當地修改、
核對實際啟動路徑與版本，再安全更新所需程式及確認配套；優先處理 RELEASE 工作，
之後追查方向鍵／按鍵延遲、互換 COM 後 X／Y 幾乎只有正轉可動的問題。
正式發佈仍須如實保留尚未完成的整合與硬體驗收狀態。
詳見 [GUI／馬達相容性與 B 地接續事項](MOTOR_GUI_COMPATIBILITY_20261020_zh_TW.md)。
本次補充只有文件，未重建或變更既有候選安裝版／交接包。

## 先看：馬達 GUI／driver／韌體尚未配對

本分支 `codex/user-supplied-models` 沒有合併固定 RPM 與 launcher 分支。
目前 `hardware/arduino_stepper.py` 的舊連線／能力探測流程仍可能送出 `SPEED_MS` 設定。
B 地先前已燒錄固定 0.02 RPM 韌體；**本候選版不得直接用來做 X/Y 連線或移動驗收**。
先在另外核准的整合工作中對齊 GUI／driver／firmware，完成軟體與唯讀身分查驗，再安排實機動作。
不要因為此包較新就覆蓋或重燒 B 地韌體，也不要調整 COM、速度、步距、方向或安全範圍。

待整合的已知分支包括 `codex/msh-015-stop-hold`（固定 RPM／停止語意，需確認可取得的遠端 ref）
與 `codex/msh-009-launcher-diagnostics`。保留現有 B 地安裝、韌體與回復資料；本次不自動 merge。

## 交接內容與資料政策

- 最新提交來源 ZIP：包含 GUI、辨識／拼接／訓練程式、建置腳本、測試、文件及授權 notices。
- 由該來源重新建置的 `MSH_Setup_v0.1.4_CPU_CANDIDATE.exe`、checksum、build manifest。
- 軟體測試結果、payload 稽核摘要、此次建置的驗證範圍與空白 B 地驗收表。
- 本次不附模型、研究影像、dataset、標註、實驗輸出、設備專用 PFS 或 Git 歷史。
  模型由使用者在 B 地以既有外部檔案自行選取，原模型／研究資料留在原位置。
- D 槽既有資料夾不覆蓋、不移動；此次另建交接資料夾。不要把舊 v0.1.x 安裝包當成無模型版。

## 建議 B 地執行順序

1. 先讀 `00_先看_README.md`，核對 `HANDOFF_MANIFEST.json`、安裝檔與來源 ZIP 的 SHA-256。
2. 記錄 B 地目前 GUI／driver／韌體版本與本機未提交修改；備份設定與使用者資料。
   若 B 地 Git 工作樹有變更，先保留，不 pull、switch、restore、reset 或覆蓋。
3. 不接相機／COM，先驗收候選安裝、啟動／關閉、v0.1.4 顯示、無模型啟動、外部模型選擇／清除。
   保存／核對使用者資料後測覆蓋安裝及解除安裝。安裝版無需 Git／Python。
4. 對齊固定 RPM GUI／driver／韌體分支，先做軟體／mock 驗證，再依核准流程唯讀查驗身分。
   只有版本與安全前置確認後，才進行相機、COM、XY、STOP／RELEASE 和掃描實機驗收。
5. 用自備且可使用的模型／影像驗證原 GUI 的實際辨識；保留本機結果，不上傳資料。
   ONNX／onnxruntime 未包含在此 CPU 候選版，不列為已支援或已驗收。
6. 填寫交接資料夾的 `B_SITE_VALIDATION_RESULT.md`，記錄已測／未測／失敗與精確版本。
   回報日誌時先移除個人路徑、設備識別及研究內容，原始資料仍留在本機。
7. 完成剩餘來源／授權交付、乾淨 Windows、簽章決策與整合驗收後，再準備正式 Release／更新 manifest。

## Git 保存與取得

此次 user-supplied-models 分支保存至既有私有 origin；不改 repository 可見性、不合併 main、
不建立正式 release tag、不改寫含舊資料的歷史。
若 B 地要取得分支，先確認該 checkout 的 `git status`、branch、remote 與 upstream，
再依專案規則 fetch／選用相同分支；不要為了同步清除 B 地工作。
若只做安裝驗收，直接使用交接中的 installer 即可。

## 本機驗證的界線

提交前完整軟體／mock 測試 128 項：127 通過、1 項缺 ONNX 依賴略過。
最終 review 另封鎖 EfficientNet 缺權重時的預訓練下載與 SSD 架構的 pretrained 下載入口，
以回歸測試確認未提供本機模型時不呼叫建構／下載後端。
最新建置的額外驗證範圍以 `BUILD_VALIDATION.md` 為準，不能沿用舊候選版的結論冒稱本次有做。
乾淨 Windows 尚無測試機；B 地相機／COM／馬達／停止／完整掃描仍待實機驗證。

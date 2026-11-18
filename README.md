# Microscope-Scanner-Helper_MSH（MSH）

MSH 提供操作介面與功能，**模型及研究資料由使用者自行提供**。
程式碼採 AGPL-3.0-only；見 [LICENSE](LICENSE) 與 [第三方聲明](THIRD_PARTY_NOTICES.md)。

## 日常使用

1. 雙擊桌面／開始功能表的 **MSH** 開啟介面，不需要先開 CMD。
2. 相機、平台、拍攝、拼接使用原有介面。實體設備仍需正確的驅動與連線。
3. 需要 AI 辨識時，按 **選擇模型** 匯入自己的本機偵測模型；按 **清除模型** 可取消。

未選模型時仍可開啟 UI 與使用不依賴 AI 的功能；不會自動套用舊模型或下載替代權重。
相機 profile 由使用者明確選擇，不會自動套用設備專用設定。

## 醫師資料與後續訓練

- [醫師分類／框選工具](tools/physician_review/README.md) 保留，與 MSH 主視窗是兩個操作入口。
- 訓練功能保留。之後使用醫師交付的新資料與使用者提供的本機起始模型訓練，不需要沿用舊實驗。
- 偵測／定位訓練可使用醫師工具的 **YOLO 匯出 ZIP**；純分類 CSV 與框選資料用途不同。
- 訓練結果另存專案外，完成後再從 MSH 的 **選擇模型** 匯入。

詳見 [資料交付與訓練流程](docs/CORE_WORKFLOW.md)。訓練目前由 Python 入口執行；主 GUI 不會自動開始訓練。

## 保留範圍

核心包含 GUI、相機／平台控制、拍攝、拼接、模型匯入與推論、資料整理／訓練、醫師工具，
以及必要的來源、測試、建置工具與授權。現有模型、訓練資料、擷取影像、實驗結果及舊交接產物應獨立保存，不作為核心功能的內附資料。

執行環境是開發機的本機依賴，不是模型或訓練資料；使用中的環境不能當作資料一併清除。

## 開發與發行

- [線上安裝與自動更新（GPU 優先）](docs/ONLINE_INSTALL_AND_UPDATE_zh_TW.md)：`0.1.5-dev.5` 使用同一個 `MSH-Releases` 開發與發行；仍需乾淨 Windows 與 B 地驗收。
- [單一 repo 開發與發行](docs/AUTOMATED_RELEASE_zh_TW.md)：在 `MSH-Releases` 維護程式、建置與發版；使用 GitHub 當次工作的內建授權，不需要個人發版 token。各工作階段依對照表獨立保留；提交與同步狀態以 Git 紀錄為準。
- [專案目錄與根目錄保留理由](docs/PROJECT_MAP.md)
- [模型由使用者提供](docs/USER_MODELS.md)
- [本機開發環境與封存前檢查](docs/DEVELOPMENT_ENVIRONMENTS.md)
- [純應用程式／資料政策](docs/APPLICATION_ONLY_POLICY.md)
- [安裝版建置](docs/release/BUILD.md) · [發行檢查表](docs/release/RELEASE_CHECKLIST.md)
- [舊版 README 快照](docs/legacy/README_BEFORE_CORE_ISOLATION.md)

來源捷徑使用 `pythonw.exe → launch_msh.pyw`；獨立安裝版使用 `MSH.exe`。
故障診斷入口為 `scripts/diagnostics/run_hardware_gui.bat`。
軟體測試不能取代 Basler、COM、XY 平台與 Arduino 實機驗收。

目前所有工作階段的來源遷移對照見 [工作階段清單](docs/WORKSTAGE_MIGRATION.md)。各實驗分支獨立保留；硬體與正式發行驗收不因遷移而完成。

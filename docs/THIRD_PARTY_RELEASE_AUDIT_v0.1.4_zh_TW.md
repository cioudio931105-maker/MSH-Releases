# v0.1.4 第三方部署與來源交付查核

查核日期：2026-10-20。結果：**本機盤點完成，正式二進位公開發佈仍未放行。**
本文件記錄實際檔案與官方條款的待確認項目，不宣告授權相容性已獲法律確認。
模型與研究資料保持本機私有，不因本查核新增任何上傳範圍。

同日續作已完成 8 份來源下載／891 個 Python 檔案比對、pypylon wrapper 固定來源快照、
FFmpeg 官方 DLL SHA-256 配對及 14 份補充 notices，總數為 128 份。
下列首次盤點的缺項已有部分補齊，最新逐項狀態以[來源取得證據](THIRD_PARTY_SOURCE_INVENTORY_v0.1.4.md)為準；
pylon／AGPL 組合及完整對應來源仍未放行。

## 查核對象與可重現證據

本輪只讀取既有候選版，未重建、安裝、操作相機／馬達或改寫交付包。

| 對象 | SHA-256 |
| --- | --- |
| `source-license-candidate/MSH_Setup_v0.1.4_CPU_CANDIDATE.exe` | `5a552f33fe4d4fd254ba5eef554ff1e349b34d302e72568273f8e7ee824a1294` |
| `MSH_v0.1.4_Application_Source_REVIEW.zip` | `e2cc7e3f55b9539f9caffaf4ce25c2a6fd8425777a04f5ffa85d1621e9e1c504` |
| `MSH_v0.1.4_CPU_Source_and_Installer_REVIEW.zip` | `270d319932a4bca0ef67c0747096f89a0d4baef4f093a0386d3bd3c20477f402` |

以上檔案位於 `dist/release/v0.1.4/`，仍是內部 review 產物。新增本文件、工具及 tqdm notice
不會回溯改變這些快照，也不能把目前工作樹當成該 EXE 的精確來源快照。

使用建置環境執行離線原生檔案盤點，不 import 第三方程式、不執行封裝程式、不連線：

```powershell
.venv312-cpu\Scripts\python.exe scripts/inventory_release_dependencies.py `
  --payload tmp/pub014build/dist/cpu/MSH `
  --output tmp/native-provenance-new.json
```

輸出拒絕覆蓋既有檔案。它只盤點 `.dll`、`.pyd`、`.exe`，以檔名加 SHA-256 配對已安裝套件的
RECORD 路徑；同名不同內容不會算配對成功。RECORD 重疊與其雜湊不符也保留為查核線索。
版本與 Project-URL 來自環境 metadata，不等於所有套件都在執行檔內，也不是完整 SBOM。

| 原生檔案盤點 | 數量 | 意義 |
| --- | ---: | --- |
| 全部原生檔案 | 308 | 包含 `MSH.exe` |
| 與 pip 套件內原檔逐位元相同 | 230 | 含 pypylon、Torch、OpenCV 等；多個 RECORD 可能同時聲稱擁有相同檔案 |
| 上列未配對者中，另與基底 Conda 原檔相同 | 74 | Python、UCRT、OpenSSL、Tcl/Tk、SQLite 等 |
| 仍未配對至以上環境原檔 | 4 | 三個 Windows API DLL 與本專案產生的 `MSH.exe` |

本機證據：`tmp/lic014-native-provenance.json`、`tmp/lic014-conda-provenance.json`。
Conda 次級比對使用本機 `conda-meta` 的檔案清單及實際位元組，未複製含個人安裝路徑的原始 metadata。
三個尚未定位來源的 DLL 是 `api-ms-win-core-fibers-l1-1-1.dll`、
`api-ms-win-core-kernel32-legacy-l1-1-1.dll`、`api-ms-win-core-sysinfo-l1-2-0.dll`。
這四個項目不代表發現惡意檔案；主程式已有既有建置 manifest 配對證據，三個 DLL 仍需部署來源核對。

## pylon：需要釐清的正式發佈條件

[pypylon 26.7 官方版本說明](https://github.com/basler/pypylon/releases/tag/26.7)
指出其使用 pylon Suite 26.7.2、C++ SDK 12.2.1、Data Processing SDK 5.1.0。
已安裝 wrapper 的 BSD 類型 LICENSE 保留於 [notice 目錄](../licenses/README.md)。

實際候選版有 27 個原生檔案與 pypylon 套件配對，包含 `PylonBase_v12.dll`、
`PylonUsb_v12_TL.dll`、`PylonGigE_v12_TL.dll`、GenApi、`log4cpp`，以及
`PylonDataProcessing_v5.dll`、`PylonDataProcessingCore_v7.dll`。
雖已排除 vTool／OCR 外掛目錄，仍不能把整個 pypylon wheel 視為只有 BSD wrapper。

官方[部署指南](https://docs.baslerweb.com/pylonapi/pylon-deployment-guide)提供 copy deployment 與
runtime installer 路徑，驅動需另處理；[授權資訊](https://docs.baslerweb.com/pylonapi/cpp/licensing)
要求查閱安裝版本隨附的 License 目錄。本機未找到該版本完整 pylon 原生授權包。

目前官方 [EULA](https://docs.baslerweb.com/pylon-end-user-license-agreement) 區分取像與 vTools；
取像衍生程式的散布條件包含額外合約限制。這是 AGPL 組合需要進一步確認的線索，
**不能直接斷言已相容或必然不相容**。目前網頁也不能代替 26.7.2 隨附的精確條款。

正式放行需要：取得適用版本的 EULA／第三方 notices、確認實際 DLL 屬可散布範圍，
並釐清與 Ultralytics／MSH AGPL 組合的權利基礎。
不會自行把相機 SDK 宣告為 System Library，也不會自行加一個例外就當成已取得 Ultralytics 權利人的許可。
GNU 對[非相容函式庫與例外授權](https://www.gnu.org/licenses/gpl-faq.html#GPLIncompatibleLibs)
的說明，也區分各權利人能授予的範圍。

## 第三方對應來源與 notices

| 元件 | 已確認 | 尚需交付或核對 |
| --- | --- | --- |
| MSH 應用程式 | 既有 460 檔來源 ZIP 與候選版配對 | 最終修改後重新凍結來源；公開下載位置與安裝檔並列 |
| Ultralytics 8.4.123 | AGPL 全文；[版本來源樹](https://github.com/ultralytics/ultralytics/tree/v8.4.123)可取得 | 對應版本來源封存、校驗、建置／修改說明與持續可下載安排；不是只給專案首頁 |
| pypylon 26.7／pylon 原生庫 | wrapper notice、版本對照、實際 DLL 雜湊 | 適用原生 EULA、第三方元件 notices／來源、AGPL 組合依據 |
| OpenCV 5.0.0.93／FFmpeg | 候選版確有 `opencv_videoio_ffmpeg500_64.dll`；既有第三方 notice 含 LGPL 2.1 | 對應 FFmpeg 來源版本、建置選項／修改與取得方式，及適用的替換／重新連結條件 |
| Python 3.12.13 與基底原生元件 | 多數 DLL 與 Conda 原檔逐位元相同；本機有 `LICENSE_PYTHON.txt`；Tk notice 已在 payload | 尚未完整收集 Python／Tcl／OpenSSL 等此版本 notices 與部署依據，三個 API DLL 來源待核對 |
| 其他已安裝依賴 | 已保存版本表、notice、metadata 來源連結 | 依實際 frozen membership 整理適用來源；MPL／LGPL 不能只用頂層 permissive label 取代 |

OpenCV 官方[授權段落](https://github.com/opencv/opencv-python#licensing)也明確區分 OpenCV 與 wheel 內 FFmpeg 的授權。
不因 Linux wheel 有 Qt 說明，就推定本 Windows payload 包含 Qt。
AGPL 第 6 節的來源取得要求以本專案 [LICENSE](../LICENSE) 原文為準；版本表、notice 集合或本查核表本身都不是完整對應來源。

### 本輪已修正的收集問題

原收集器只認 `LICENSE`，漏掉英式拼法 `LICENCE`。現在同時辨識兩者，輸出檔名正規化成 `LICENSE`，
但原始位元組、作者與原授權條款不變，catalog 保留原路徑及 SHA-256。
新增 tqdm 4.70.0 notice；原 113 份文字逐一比對未改，工作樹合計 **114 份第三方文字**。
原候選版已另帶 tqdm 的 `LICENCE`，本次修正的是獨立來源 notice 集合漏項。
pyserial 與 nvidia-ml-py 在目前收集規則下仍未找到 standalone notice，不能只看 metadata 的 BSD 標籤即結案。

驗證：11 項測試通過，含同名不同二進位不能誤配、重疊 RECORD、英式拼法、原文位元組保留、拒絕覆寫，
以及既有純應用程式分發／模型防下載檢查。新工具及 notice 都供下一次來源凍結使用。

## 下一步與完成判準

1. 取得 pylon 26.7.2 適用條款及第三方資料，確認現有 AGPL 整合是否可散布。
   若需詢問權利人，先由使用者決定；本次未聯絡廠商或購買授權。
2. 將實際適用的對應來源、建置說明與缺漏 notices 整理成可校驗、可公開取得的交付內容。
3. 上述條件有依據後才重新凍結來源、建置候選版、跑 payload／安裝驗證。
4. 乾淨 Windows、B 地 GUI／韌體／相機／XY／停止及掃描驗收仍獨立待完成。
5. review 後，依使用者明確授權才 commit／push／公開發佈；既有含資料的 Git 歷史不公開。

可供使用者審閱的廠商詢問要點（草稿，未送出）：

- Basler：pypylon 26.7 隨附 pylon 26.7.2 的指定 DLL，適用哪一份 EULA、第三方 notices 與來源包？
  不含 vTools 的應用程式是否可依目前規劃與 AGPL 元件共同散布？需哪些合約與告知？
- Ultralytics：MSH 公開自有來源、使用者自備模型資料、同程序使用 proprietary Basler SDK 的情境，
  是否已有適用的相容依據／例外，或需要其他授權安排？

不在未確認權利前改成閉源、移除相機功能、替換辨識後端或增加遠端服務。
若要變更架構，另提出範圍與軟體／B 地驗證計畫。

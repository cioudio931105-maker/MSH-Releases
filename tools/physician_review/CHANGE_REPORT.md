# 醫師離線分類工具修改報告 — 2026-10-06

## A. 目標工具

真正的交付工具是使用者指定的桌面批次資料夾內 `MSH_醫師快速分類工具.html`。
它原本不在目前 repository；本機 `codex/physician-review-v1` 分支只有交接文件，亦未保存此 HTML。
本次以該 HTML 為基底，將純工具程式碼保存於 `tools/physician_review/MSH_醫師快速分類工具.html`，並更新指定桌面檔案。
CSS 與主要 JS 仍內嵌在同一入口，單檔可交付，不需要安裝或伺服器。

原版只有記憶體 `Map`／history 與 CSV download；沒有 LocalStorage、IndexedDB、JSON export/import 或 reload 恢復。
新版加入 LocalStorage 與 JSON 備份／恢復；未使用 IndexedDB。

## B. 原本架構

`webkitdirectory` 選圖 → extension filter → filename 字典排序 → 建立 Object URL → `<img>` 顯示 →
11 個舊分類按鈕或快捷鍵 → filename-keyed Map → 自動下一張 → 4 欄 CSV。
原版支援上一張、略過、復原、滾輪／按鈕縮放、拖移、符合畫面與原圖 100%。
原版另有 Google Form 上傳連結；依本次完全離線要求，以 JSON 備份取代此按鈕。

## C. 圖片 bug 的根因與證據

1. **圖片顯示位置完全落在 viewer 外。** `.viewer` 是置中的 flex 容器，而絕對定位的 `.viewer img`
   沒有 `left/top`，使用 flex 的 static-position center；`fitImage()` 又計算以左上角為原點的平移。
   在原版 `file://` 中用 3088×2064 合成圖重現：圖片成功解碼，沒有 JS exception，
   但 image 的 y=-169、height=568（終點 399），viewer 的 y=578、height=570，完全沒有垂直交集。
   修正：img 與 SVG overlay 都指定 `left:0; top:0`，共享同一縮放／位移。
2. **同名不同子目錄會清空整批。** folder change 中的 duplicate check 只比較 `file.name`；
   兩筆 `Case01/001.png`、`Case02/001.png` 即觸發 `files=[]`，顯示「尚未選取可用圖片」。
   修正：以相對根資料夾的完整 relativePath 作為 key，不要求修改原圖檔名。
3. 原版在沒有填 reviewer 時直接拒絕載入。新版允許選填工作階段代號，不阻擋圖片查看。

此外補上 natural sorting、成功／失敗統計、失敗檔名、MIME 空白的 extension fallback、同資料夾重選、
先設定 onload/onerror 再設定 src，以及預覽停止使用後才 revoke Object URL。
實際醫師當時使用的瀏覽器與操作記錄尚未確認；以上兩項已在原交付程式實際重現，未臆測其當時情境。

## D. Classification

HTML script 的 `CLASSIFICATION` 是唯一分類表，`classes` 是由它衍生的查詢 Map。
父／子 UI、validation、統計與 CSV／JSON 都使用同一份定義。
G=13、R=19、P=7、L=8、M=8、A=6；**6 個父項、61 個子項**。
已逐項與附件的 61 組 code/label 比對，完全一致。

## E. Parent/Child UI

父項初始為「請選擇分類」；子項初始「請先選擇父項」且 disabled。
選父項後只列出其子項，改父項立即清空子項。按儲存才提交影像分類，無法保存 R/G05 等錯配。
保留既有影像版面、導覽、auto-next、復原與縮放拖移；補上圖片列表、下一張、notes 與檢閱狀態。
舊快捷鍵的類別語意不能沿用新分類；保留按鍵並明示新動作，詳見 README。

## F. Image identity

每筆保存原始 `fileName`、根資料夾內的 `relativePath`、`imageWidth`、`imageHeight` 與原 bytes 的 `sha256`。
SHA-256 使用本機 Web Crypto，逐張非同步處理；沒有 upload。
相同 bytes 的複製檔得到相同 hash，同名但 bytes 改變會不同。
未來 dataset builder 應先 relativePath + hash，再考慮唯一 filename fallback；歧義不得猜測。

## G. 原圖保護

應用程式僅讀取 File、arrayBuffer 及 Object URL；沒有 source-image write API。
不 rename、overwrite、resize 回存、重新壓縮、改格式、改 bytes 或將框寫進原圖。
測試前後確認合成原圖名稱、檔案清單與 SHA-256 全部不變。
此次未開啟或改寫任何真實醫師影像，也未將影像／舊 annotation 複製到 repository。

## H. Bounding Box

框選完全選填，一張圖片支援 0..N 個框。
Pointer Events 提供拖曳新增、點選／列表選取、拖移、四角 resize、delete、重新建立與 undo。
每框保存自己的父項／子項；可同圖 G05、R18、P04，不改動影像層級分類。
框的數量在列表與統計顯示。瀏覽與框選模式分開，保持縮放／拖移可用。

## I. 座標系統

`xMin/yMin/xMax/yMax` 永遠使用原圖像素。SVG 的 inverse `getScreenCTM()` 將 pointer 的 client coordinates
轉回原圖座標，包含 CSS transform、滾動與 browser viewport 位置。
image 與 overlay 共用 translate/scale。已實測 3088×2064 圖片、視窗 resize、zoom、pan、DPR=2 及恢復後位置。
display 變化不改寫 stored annotation。超界／零面積／非法類別／重複 ID 阻止匯出；微小框會警告。

## J. Storage schema

```text
schemaVersion: 2
taxonomyVersion: morphology-61-v1
reviewer, batchName, sourceRoot, currentPath
images[]:
  fileName, relativePath, sha256, imageWidth, imageHeight
  imageClassification: null | { parentCode, parentLabel, classCode, classLabel }
  annotations[]:
    annotationId, parentCode, parentLabel, classCode, classLabel
    xMin, yMin, xMax, yMax
    reviewStatus, annotator, annotationTimestamp
  reviewStatus, notes, annotator, annotationTimestamp, loadError, hashError
  legacyClassification（若存在）
legacyRecords[], unmatchedRecords[]
```

影像與物件是獨立概念。預設 reviewStatus=`unreviewed`；影像可由醫師改為 reviewed／confirmed。
LocalStorage key 包含整批 relativePath、原始 hash 與 file size；不存圖片 bytes。
恢復需重新選原圖且通過 hash、檔名與尺寸檢查；不符合的外來記錄保存在 JSON 的 unmatchedRecords。
儲存失敗明確回報；損壞的既存 LocalStorage 不會被空白進度覆寫。

## K. 完整 CSV schema

```text
schema_version,reviewer,batch_name,file_name,relative_path,sha256,image_width,image_height,
image_parent_code,image_parent_label,image_class_code,image_class_label,annotation_id,
object_parent_code,object_parent_label,object_class_code,object_class_label,
x_min,y_min,x_max,y_max,review_status,annotation_timestamp,notes,
object_review_status,object_annotation_timestamp,legacy_classification,load_error,hash_error
```

所有圖片至少一列；有多框時一框一列。無框的 object_*／annotation_id／bbox 為空，影像分類保留。
UTF-8 BOM + CRLF；每欄雙引號包裹、內部引號加倍，已由獨立 parser 驗證逗號、引號、換行及 Unicode。

## L. Legacy compatibility

原版沒有持久化或 JSON import，因此沒有既有 browser storage 需要遷移。
新增 V1 四欄 CSV、常見 filename→label JSON 的保守匯入，原記錄保存在 legacyRecords。
**沒有任何舊類別自動 mapping**，包括 neutrophil、monocyte 等；全部顯示 Legacy / Unmapped 並重新人工判讀。
filename 不唯一回報 AMBIGUOUS_FILENAME，不存在回報 MISSING_IMAGE；V2 hash 不同回報 HASH_MISMATCH。
V2 完整進度以 JSON 恢復，V2 CSV 作交換格式，不提供 round-trip 匯入。

## M. Offline

工具沒有 fetch、遠端 API、upload、telemetry、CDN、remote CSS/JS/font/storage。
原品牌圖內嵌且 bytes 與 repository 既有資產一致；SVG namespace 的 URL 只是標準識別字，不會發出請求。
Chrome／Edge 的 file:// 測試全程封鎖 HTTP，完整操作與實際 CSV/JSON 下載成功，沒有 HTTP request 或 JS exception。
未實際停用電腦網卡；該項為 NOT RUN，不能將 request blocking 描述成實際拔網路測試。

## N. 初次功能升級測試結果（2026-10-06）

最終 Chrome 和 Edge **各 20/20 PASS，0 FAIL**，使用合成資料而非醫師／病患影像。

| 情境 | Chrome | Edge |
|---|---|---|
| 實際 folder picker：JPG/JPEG/PNG、大小寫、nested、自然排序、reviewer 選填 | PASS | PASS |
| 圖片確實可見且置中 | PASS | PASS |
| 六父項／61 子項、父項改變清除子項 | PASS | PASS |
| G10 exact labels、只有影像分類的列、notes/review 狀態 | PASS | PASS |
| Pointer 新增三框，G05/R18/P04，原圖座標 | PASS | PASS |
| 移動、resize、修改單框類別、刪除、重建、undo | PASS | PASS |
| zoom、pan、window resize、DPR=2 對齊與座標不變 | PASS | PASS |
| CSV 獨立 parse、逗號／引號／換行／Unicode、一框一列及無框列 | PASS | PASS |
| 原 bytes hash、複製不變、同名改 bytes 不同 | PASS | PASS |
| reload、重選同資料夾，分類／框／notes／review／導覽恢復 | PASS | PASS |
| JSON 恢復與 HASH_MISMATCH／MISSING_IMAGE／非法分類隔離 | PASS | PASS |
| 超界／零面積／重複 ID／錯配父子驗證 | PASS | PASS |
| 損壞圖片不阻擋、空 MIME、真實 WebP/BMP、保留 TIFF 候選 | PASS | PASS |
| 同名子資料夾分開、V1 JSON/CSV 不猜測、filename 歧義 | PASS | PASS |
| auto-next、previous/next/skip、數字捷徑、Ctrl+Z | PASS | PASS |
| 真實 CSV/JSON download，HTTP request／JS exception 都為零 | PASS | PASS |
| 操作／匯出前後原圖檔名與 bytes 不變 | PASS | PASS |
| LocalStorage 拒絕有警告、仍可 JSON 備份 | PASS | PASS |
| 損壞 LocalStorage 明確回報且原內容保留 | PASS | PASS |
| 微小框警告、零面積拒絕、座標邊界 clamp | PASS | PASS |

另：61 項附件精確比對、JS syntax、remote behavior 靜態掃描、品牌 bytes 比對為 PASS。
實際拔網路後人工操作、醫師原圖／真實分類資料驗收、大型資料集壓力測試、有效 TIFF 解碼測試為 NOT RUN。
相機、COM、Arduino、XY、拼接、inference、模型訓練為 NOT RUN，且不在本次範圍。

## O. Known issues / limits

- TIFF/TIF 未新增 decoder；只能依瀏覽器支援，不能解碼時明確顯示失敗。
- Web Crypto 不可用時 hash 缺漏會記錄；未驗證 hash 的備份不自動套用，請使用近期 Chrome／Edge。
- private mode、換瀏覽器、清除 browser data 或封鎖 storage 會影響自動恢復，請下載 JSON。
- 匯出不等於 confirmed ground truth；需先檢查 reviewStatus、未分類、Legacy、hash／load errors。
- 保留原批次欄位 `batch_20260903_A01` 的唯讀設定；本次不擅自更改交付批次。
- 其他桌面鏡像 HTML 和既有 7z 未更新，避免混淆既有交付版本；此次只更新使用者指定副本。
- 未新增 dataset builder、YOLO conversion 或訓練。未修改任何硬體／其他 GUI。

## P. 初次交付紀錄（2026-10-06）

分支保持 `codex/msh-037-preview-controls`，HEAD 保持 `603e2be`；未 stage、commit、push、release 或切換分支。
由於原版在 repository 外，新增來源仍為 untracked，普通 `git diff --stat` 為空。
已用 `git diff --no-index` 完整 review 原交付 HTML 與新版；新增測試、README 和本報告亦已 review。

```text
git status --short
?? tests/physician_review.test.cjs
?? tools/
```

repository 新增檔案僅有：入口 HTML、同目錄 README、本報告、`tests/physician_review.test.cjs`。
合成圖片、測試報告 JSON、截圖及工作腳本位於本機暫存／Git 忽略目錄，不加入正式來源。
Global WORK_STATE 只增加本工作流，保留其他工作流；未修改 My-Codex-Profile repository。

指定桌面原版已備份為 `MSH_醫師快速分類工具.html.original-20261006.bak`。
原版備份 SHA-256：`b481733f0db4ed14e9b4723ad036ad21ca5cf424c7a9eefbda5a22fb3e8d1a35`。
新版 source／desktop SHA-256：`8d781047aab3529ba5a3c86b59c8b16ad86228c3ab9cade7b2b1865a4b8dd8e6`。

軟體修改可供 review，commit／push／PR 仍需使用者後續明確授權。
本工具不依賴顯微鏡設備，不需要 B 地硬體驗證；專案其他硬體待辦不受本次結果影響。

## 後續介面用語調整（2026-10-06）

依使用者回饋，主分類欄位改為「細胞／物件類別」與「形態分類」。
框選欄位、下拉選單初始提示、快捷鍵說明及錯誤訊息同步採用相同用語。
僅變更介面文字；61 組 code/label、CSV／JSON schema 與保存邏輯保持原值。
Chrome 最小驗證 PASS：四個欄位名稱、初始提示、不顯示父項／子項術語、G05 儲存、改類別清空選擇、61 項字典、無 JS exception。
本次未重跑完整 20 項套件；前述完整測試是功能升級時的驗證結果。
桌面指定 HTML 與 repository 原始碼再次確認 bytes 一致，原版 .bak 備份保留。

## 後續導覽按鈕位置調整（2026-10-06）

依使用者回饋，上一張、下一張、略過及復原上一步移到圖片下方、判讀結果上方的導覽列。
上一張／下一張／略過依序靠左，復原上一步靠右；窄視窗可換行。
沿用原有按鈕 ID；JavaScript 逐字比對一致，分類字典及資料格式未變更。
Chrome 最小驗證 PASS：按鈕唯一性、導覽列位置、儲存後自動下一張與復原、上一張／下一張／略過、1280px／400px 排列及無 JS exception。
靜態檢查 PASS：6 類／61 項與題目完全一致、品牌圖未變更、無外部載入行為及腳本語法有效。
本次未重跑完整 20 項套件；前述完整測試是功能升級時的驗證結果。
桌面指定 HTML 與 repository 原始碼 bytes 一致，原版 .bak 備份保留。

## 後續判讀與框選整合（2026-10-06）

判讀結果新增「判讀對象」選擇整張影像或框選物件，共用細胞／物件類別與形態分類。
移除獨立框選區與重複分類欄位；框選模式才顯示框列表及刪除按鈕。
新增框在拖曳完成時保存；選取既有框後按儲存或 Enter 更新分類。
框選時停用自動下一張，影像分類與每個框的分類維持分開，CSV／JSON schema 未改。
填寫備註不會清除尚未儲存的分類選擇。
Chrome、Edge 最新各 21/21 PASS；新增共用分類對象測試，保留匯出／恢復／座標／原圖保護驗證。
1100px／400px 兩種對象模式排列檢查 PASS；6 類／61 項字典、品牌圖及腳本語法靜態檢查 PASS。
表單入口問題：前次依離線需求移除，原版網址保留在 .bak；本次已向使用者詢問是否恢復手動連網入口，尚未恢復。
桌面指定 HTML 與 repository 原始碼 bytes 一致；原版 .bak 保留。

## 後續直接動作與操作情境調整（2026-10-06）

依使用者指出下拉選單容易忽略／誤導的回饋，移除可見的判讀對象下拉選單。
選分類後直接使用並列的「儲存整張影像分類」或「框選這個分類的物件」按鈕。
框選入口驗證分類完整，進入後將圖片捲入畫面，顯示正在框選的分類提示。
選取既有框時明確顯示框號，儲存按鈕標示「儲存選取框分類」；新增框在拖曳完成時保存。
待拖曳期間主按鈕停用並提示在圖片上拖曳；自動下一張只在整張影像分類時顯示。
完成框選按鈕或 Escape 返回影像分類；換圖及重選資料夾也回到影像分類，避免殘留框選情境。
已有框的圖片在瀏覽時仍顯示框列表，可直接選取編輯。
Chrome／Edge 各 23/23 PASS，新增直接入口／分類未完成阻擋、情境提示／取消／換圖防誤操作驗證。
950px／400px 兩種情境排列驗證 PASS；6 類／61 項字典、原品牌圖、CSV／JSON schema 均保留。
桌面指定 HTML 與 repository 原始碼 bytes 一致，原版 .bak 備份保留；未 commit／push。

## 後續精簡操作與單檔攜帶驗證（2026-10-06）

依使用者回饋，檢閱狀態／備註從介面移除；既有 JSON 的 reviewStatus／notes 及 CSV 欄位仍完整保存。
移除兩個大動作按鈕及長提示，改為同列分類選單與單一「儲存」。框選採短開關並以 aria-pressed 表示啟用。
儲存對象以標題旁「整張影像／新增框／框 #1」標記顯示；輔助技術可讀取完整儲存對象 aria-label。
框選期間圖片僅顯示短提示；新增／刪框按鈕按情境顯示，Escape 及換圖返回影像分類。
所有操作按鈕改短標籤，例如匯出 CSV、備份 JSON、復原、框選；快捷鍵集中到預設收起的說明，原綁定保留。
原版圖標來源是 assets/msh-cyberpunk-splash-640.png；HTML 單獨搬移時會缺失此相對路徑。
新版仍使用既有內嵌 PNG，品牌 bytes 未變。新增攜帶測試：複製唯一 HTML 到無 assets 的獨立中文路徑，Chrome／Edge 均可 decode 640px 圖標，無 HTTP 請求。
Chrome／Edge 各 24/24 PASS；涵蓋圖標攜帶、短按鈕、隱藏檢閱欄位後舊 metadata 還原、分類框選、CSV／JSON、雜湊與原圖保護。
1043px／400px 影像及框選情境排列驗證 PASS，classification 61 項與 CSV／JSON schema 未變。
桌面指定 HTML 與 repository 原始碼 bytes 一致；原版 .bak 保留。其他既有交付副本及壓縮包本次未覆寫。

## 工作收尾（2026-10-07）

使用者以「結束工作」授權本分支正常 commit／push；本次只納入工具 HTML、README、本報告及測試。
收尾重新驗證 Chrome／Edge 各 24/24 PASS、分類字典／品牌圖／腳本語法檢查 PASS。
表單按鈕與「網頁宣告」列為下次修改時須一併提醒的兩項待決策事項，記錄在 MSH-038 及 README；本次不修改網頁或恢復表單。
原始影像、桌面原版備份、合成測試資料、截圖與暫存腳本不加入 Git。
此紀錄不代替醫師驗收、TIFF 瀏覽器支援或專案其他分支／硬體工作流的驗證；實際 commit／push 結果以 Git 與 WORK_STATE 為準。

使用者追加限制：工具只提交於現有 codex 分支，不合併 main。staged 內容只有程式、說明及合成測試；內嵌圖片只包含既有品牌 PNG，未提交病患影像、標註檔、可識別個資或真實研究材料。
此檢查只確認提交範圍與離線軟體行為；尚未取得或查核研究計畫／同意文件，不能宣稱整個研究已符合 IRB。實際研究及其變更、研究資訊保密須依核准計畫及[人體研究法第 5、21 條](https://law.moj.gov.tw/LawClass/LawAll.aspx?pcode=L0020176)辦理；未在網頁新增宣告。

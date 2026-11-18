# 醫師離線形態分類與框選工具

此工具以使用者指定、先前交付的 `MSH_醫師快速分類工具.html` 為基底修改，保留其版面與操作。
原交付版本位於專案外；本目錄只保存可 review 的工具原始碼與說明，不包含影像、CSV、研究資料或模型。

## 開啟與操作

直接以近期 Chrome 或 Edge 開啟同目錄的 **MSH_醫師快速分類工具.html**。
所有 CSS、JavaScript、分類字典與既有品牌圖片均內嵌，不需要 server、網路或額外依賴。

1. 選取原始圖片根資料夾；檢閱者代號可選填一次。
2. 選「細胞／物件」與「形態」，按「儲存」或 Enter。標題旁的「整張影像」表示目前儲存對象；預設儲存後換圖，可取消勾選。
3. 可用圖片列表導覽；圖片下方的導覽列提供上一張、下一張、略過與復原上一步，回到已分類圖片可修改並儲存。
4. 選好分類後按標題旁的「框選」，直接在圖片拖曳新增框，完成後自動保存。每張可有多框，按「新增框」繼續。
5. 從標註框列表選取既有框會進入編輯；框選時亦可點框。標題旁顯示「框 #1」等框號，修改分類後按「儲存」或 Enter。拖曳移動、拖曳四角 resize、「刪框」或 Delete 刪除、Ctrl+Z 復原。框與影像分類分開，不會自動換圖。
6. 再按「結束框選」或 Escape 返回整張影像分類。上一張／下一張／略過／圖片列表也會返回此狀態。瀏覽時可拖移與滾輪縮放；適合視窗、100% 與放大／縮小保持可用。
7. 依使用者回饋，檢閱狀態與備註不再顯示。舊 JSON 的 reviewStatus／notes 仍保留、驗證並匯出，不會因介面精簡而刪除。
8. 下載 CSV 交付結果，另存 JSON 備份；將 CSV 與未修改的原始圖片一起交付。

## YOLO 偵測資料匯出（2026-10-21）

按「匯出 YOLO」可下載單一 ZIP，包含原圖 bytes 的副本、每張圖對應的 YOLO `.txt`、`data.yaml`、`classes.txt`、`class_mapping.json`、來源／切分清單與原格式 JSON 備份。整個 ZIP 解壓縮後，訓練程式指定其 `data.yaml`；工具本身不執行訓練。

- **必須有物件框。** 只有整張影像分類不足以訓練定位；無框影像會略過，不自動產生整圖框或負樣本。請框出圖中所有要學習的目標，並核對分類。
- **保留全部61類。** ID固定按既有字典順序為0至60；例如G01=0、G05=4、R18=30、P04=35。每次匯出均保留同一對照，不因只選了某些類別而重新編號，也不合併成WBC單類。這是新的61類訓練設定，與既有WBC單類權重的類別定義不同。
- 每個框一行`class_id x_center y_center width height`，中心、寬、高以原圖尺寸正規化為0至1。使用物件本身的類別，不以整張影像分類覆蓋物件分類。[格式依據：Ultralytics官方偵測資料說明](https://docs.ultralytics.com/datasets/detect/)
- 為本次操作示範，以原圖SHA-256分組做約80/20切分，至少需要兩張內容不同且有框的圖片；四張不同且有框的圖會分成3張train、1張val。完全相同原圖保留在同一split；相同圖若標註不同則拒絕匯出，要求先核對。**這不提供病人／玻片層級獨立性，也沒有test set**；正式研究需另外依適當群組切分。匯出前顯示實際張數供確認。
- 匯出影像採唯一編號，避免不同子資料夾同名、或同stem不同副檔名的label互相覆蓋；原始名稱／相對路徑與hash在`export_manifest.json`對照。原圖不改名、不覆寫、不重編碼。
- 匯出不代表醫師簽核。影像與框原有的檢閱狀態保留在清單／JSON；少量示意資料無法證明61類的模型效能。新ZIP沒有patient/slide資訊時，不會猜測該資訊。
- 完全離線，ZIP不壓縮、不加入依賴；單次打包上限512MiB，超過時請拆批。圖片、標註及產生的ZIP均為使用者本機資料，不加入Git。
- 仍可使用CSV與JSON備份／還原；匯出後圖片改為編號，若要用`annotations.json`還原工具進度，請選回原始圖片資料夾。

快捷鍵：`S` / `→` 下一張、`←` 上一張、`Ctrl+Z` 復原、`Enter` 儲存。
`1–8` 改為目前類別的前八個形態分類並儲存；新字典不能沿用舊快捷鍵的臨床類別語意。
快捷鍵說明收在可展開的「快捷鍵」中。`M` / `N`、`U` 保留舊檢閱標記相容行為，不猜測 morphology；一般分類不需要此步驟。
`Delete` 在框選模式刪除所選框，`Escape` 取消未完成框操作並返回影像分類。輸入框／下拉選單內使用原生鍵盤行為。

## 圖片與資料保護

圖標已內嵌在此 HTML 中，移動或交付時只需這一個 HTML。原版使用 `assets/msh-cyberpunk-splash-640.png` 相對路徑，單獨移動原版 HTML 會缺少圖標；其他尚未更新的交付副本／壓縮包不會自動變成新版。

- JPG、JPEG、PNG、WEBP、BMP 大小寫皆可；保留 TIFF/TIF 和其他瀏覽器 image MIME 的候選支援。
- TIFF/TIF 能否顯示取決於瀏覽器解碼能力；未加入 decoder。不能解碼的檔案會顯示失敗狀態，不阻擋其他圖片。
- relativePath 是相對所選根資料夾的路徑；不輸出 Windows 絕對路徑。同名子資料夾圖片分別記錄。
- 圖片採自然排序。副檔名可在 MIME 空白時作為 fallback。
- 圖片只透過 File API 讀取；未使用圖片寫入、改名、重編碼、覆寫或 canvas 回存。
- SHA-256 直接對原始 File bytes 使用 Web Crypto，逐張非同步處理。失敗或不支援會顯示缺漏。
- 所有框保存原圖像素座標，不因 CSS 尺寸、縮放、拖移、視窗大小或 DPR 改變。
- CSV 包含所有圖片：沒有框的圖片仍有一列，多框圖片一框一列。
- 未分類、Legacy、載入失敗、hash 缺漏均保留且明確標記；不能將整份匯出直接當成已確認 ground truth。

## 儲存與恢復

LocalStorage namespace 為 `msh-physician-morphology-v2:`，資料集 key 使用 relativePath、原始 hash 與檔案大小。
不保存圖片 bytes。JSON `schemaVersion: 2` / `taxonomyVersion: morphology-61-v1` 區分影像分類與物件陣列。

重新開啟工具後，選取相同的圖片根資料夾，才可讀取原圖並恢復進度。
瀏覽器封鎖 LocalStorage、private mode、清除瀏覽資料或換瀏覽器都可能使自動恢復不可用；**請持續保存 JSON 備份**。
可先匯入 JSON，再選圖；也可先選圖再匯入。SHA-256 或影像身分不符合的記錄不套用，保存在 `unmatchedRecords`。

舊 V1 CSV（`reviewer,batch_name,image_id,doctor_category`）和舊 label JSON 可匯入：
僅在 filename 唯一時將舊值顯示為 **Legacy / Unmapped**，`imageClassification` 保持空白，必須重新人工分類。
同名 fallback 回報 `AMBIGUOUS_FILENAME`，缺圖回報 `MISSING_IMAGE`。無任何舊類別會自動轉成 morphology code。
舊記錄完整保存在 JSON 的 `legacyRecords`。V2 CSV 是交換格式；恢復完整進度請使用 JSON。

## 分類與驗證

唯一分類定義是 HTML script 中的 `CLASSIFICATION`，父／子 UI、驗證、統計與匯出均由此取得。
數量：G=13、R=19、P=7、L=8、M=8、A=6，合計 6 個父項 / 61 個子項。
更換類別立即清除形態分類選擇；按儲存才更新目前判讀對象的分類。新增框在完成拖曳時保存；修改既有框分類需按儲存或 Enter。

非法分類、重複 annotationId、非數值／超界／零面積框會阻止匯出。
邊長小於 3 原圖像素的框顯示警告，匯出需明確確認。
reviewStatus 預設 `unreviewed`，可選 `reviewed` / `confirmed`；物件狀態預留在 schema。

## CSV 欄位（順序固定）

```text
schema_version,reviewer,batch_name,file_name,relative_path,sha256,image_width,image_height,
image_parent_code,image_parent_label,image_class_code,image_class_label,annotation_id,
object_parent_code,object_parent_label,object_class_code,object_class_label,
x_min,y_min,x_max,y_max,review_status,annotation_timestamp,notes,
object_review_status,object_annotation_timestamp,legacy_classification,load_error,hash_error
```

含 UTF-8 BOM，所有欄位以雙引號包住，內部雙引號加倍；逗號、換行、Unicode 可正確 round-trip。
影像與物件分類不共用欄位。無框列的 annotation_id、object_* 與 bbox 為空。

未來 dataset builder 應先以 relativePath 匹配原圖並驗證 SHA-256，再處理唯一 filename fallback。
歧義、hash mismatch、缺圖、未分類圖片需明確拒絕或送複核。YOLO匯出會驗證有框圖片的身分、框與類別；未實作臨床研究資料集建置或模型訓練pipeline。

## 驗證

既有環境有 Playwright 時，可執行：

```powershell
node tests/physician_review.test.cjs
```

若 Playwright 在共用 runtime，使用環境的 `NODE_PATH` 指向其 node_modules；不用修改專案依賴。
`MSH_TEST_BROWSER=msedge` 使用 Edge；預設 Chrome。
`MSH_PHYSICIAN_HTML` 可指定交付 HTML 以測試相同檔案。
測試在暫存目錄建立合成影像，封鎖 HTTP，驗證真實 file://、Pointer Events、下載、恢復與原圖不可變。
未連接相機、COM、Arduino 或馬達；本工具不需要 B 地硬體驗證。

## 後續提醒（2026-10-07）

下次修改此工具時，一併提醒使用者討論「表單按鈕」與「網頁宣告」。表單按鈕是否恢復、網頁宣告的內容都待使用者決定；不要自行恢復連結、上傳功能或新增宣告。本次收尾不變更網頁。

本次工具提交只保留在 `codex/msh-037-preview-controls`，不合併 main。提交包含程式、說明與合成測試，不包含病患影像、醫師標註或其他真實研究資料。
這些程式檢查不代表研究取得 IRB 核准；實際資料使用、保存、交付與研究方法變更仍須符合核准計畫及機構要求。[人體研究法第 5、21 條](https://law.moj.gov.tw/LawClass/LawAll.aspx?pcode=L0020176)。

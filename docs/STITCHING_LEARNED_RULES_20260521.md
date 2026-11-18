# 2026-05-21 拼接成功結果學習紀錄

本文件把 `session_20260521_181641_759929` 的人工確認成功結果固定成拼接標準答案。之後自動拼接或半自動拼接都應該用這份結果回歸測試，避免又退回「座標排版」而不是真正影像拼接。

## 標準答案

- 來源資料夾：`C:/Cell_Project/Cell_Project/stitched_output/stitched_output/stitched_output/captured/session_20260521_181641_759929`
- 成功輸出：`C:/Cell_Project/Cell_Project/output/session_20260521_181641_759929_add_56m8_locked_content_to_64m8_48m8`
- 標準座標：`microscope_stitcher_project/reference/session_20260521_181641_759929_golden_placements.csv`
- 已確認拼接張數：21 張
- 未納入標準答案：`8_0.jpg`

## 這次成功的核心原因

1. 不再把 stage position 當最終位置。stage position 只提供初始方向，最後座標由相鄰影像內容決定。
2. 已確認的拼接內容被鎖住。新增 tile 時只允許擴張畫布，不允許改動前面已確認的細胞位置。
3. 單一 anchor 不直接升級成正式結果。至少要兩個以上已確認鄰居收斂到相近位置，才當正式拼接。
4. 可以晚點補上中間缺的 tile。`56_-8.jpg`、`64_-8.jpg` 一開始不穩，但在 `72_0`、`72_-8`、`64_0` 等鄰居確認後，就能被穩定放回正確位置。
5. 血小板可作為強定位特徵，但不能只看血小板。因為顯微鏡畫面中小圓點重複很多，必須同時檢查紅血球輪廓與鄰接 tile 的整體一致性。

## 失敗結果和成功結果的差異

舊失敗模式：

- tile 被固定在 row/col grid，看起來像排版。
- 邊界明顯，細胞不會自然跨 tile 延續。
- 單一 overlap 看起來可用時就硬拼，導致後續整排漂移。
- 已經拼好的大圖會因新增 tile 被重新移動。
- 低信心 pair 仍被硬拉在一起，造成殘影。

成功模式：

- 每次只新增一張 tile，且不動已確認內容。
- 新 tile 需要多個 anchor 支持。
- anchor 候選若互相衝突，先輸出 candidate/debug，不升級成正式 baseline。
- 若沒有可靠 overlap，保留黑色空洞比硬拼更好。
- 後續 tile 確認後，可以反向補強前面不確定的 tile。

## 可操作規則

- 正式接受門檻：至少 2 個 anchor 的全解析度位置差距小於約 25 px。
- 強烈建議：有 3 個以上 anchor 時，使用加權平均或選擇最高共識 cluster。
- 單一 anchor 即使 score 高，也只輸出 candidate，除非人工確認。
- 新 tile 先貼到畫布，再把舊 mosaic 的非黑色內容覆蓋回去，確保舊內容完全不變。
- 對 `y=-8` 這排，不要強迫與同 x 的 `y=0` 直接上下拼；左右鄰居和斜向鄰居有時更可靠。
- 黑色 gap 是合法結果，代表此處沒有足夠證據，不應用 blending 掩蓋錯位。

## 後續自動化方向

- 把本次標準答案當 regression test。
- 每次修改拼接演算法後，用 `tools/compare_against_golden.py` 比對輸出座標。
- 若平均誤差變大，不能只看 stitched preview，必須檢查 `placements.csv` 與 pair debug。
- 新增正式 baseline 時，要保留 `stitch_summary.json` 內的 anchor 分數與共識位置，方便追蹤為何接受或拒絕。

## 反覆練習結果

本次已把人工確認成功的拼接結果當成 golden answer，反覆用不同條件練習自動定位。

- 嚴格設定：`min_score=0.55`、`cluster_tolerance=35 px`、`max_anchors=6`。正式通過 16 筆，最大誤差 20.44 px，沒有超過 25 px 的錯誤。
- 放寬設定：`min_score=0.45`、`cluster_tolerance=50 px`、`max_anchors=6`。正式通過 17 筆，最大誤差 20.44 px，沒有超過 25 px 的錯誤。
- 多 anchor 設定：`min_score=0.40`、`cluster_tolerance=65 px`、`max_anchors=10`。正式通過 18 筆，最大誤差 20.44 px，沒有超過 25 px 的錯誤。

練習後更新的判斷：

- 多找鄰居 anchor 有幫助，比單純降低分數門檻更有效。
- 同一個 anchor 產生多個接近候選點時，只能算 1 個 anchor，不能誤判成多 anchor 共識。
- 單 anchor 即使誤差很小，也只能當 candidate，不能直接進正式拼接。
- 目前 progressive 失敗的主因不是 overlap score 太高，而是前面缺少已確認鄰居時，後續 tile 沒有足夠 anchor 可以收斂。
- 對後續自動化，建議先用嚴格設定輸出正式結果，再用多 anchor 設定輸出候選結果給人工確認。

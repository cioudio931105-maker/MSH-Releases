# 顯微鏡影像拼接正式版

這個資料夾是可直接執行的 Python/OpenCV 顯微鏡拼接系統。它的核心原則是：stage 座標只作初始參考，正式位置以影像 overlap registration 與已驗證模板決定。

目前最可靠的正式模式是 `run_practical_stitch.py` / `run_practical_stitch.ps1`。它會先檢查輸入影像是否符合已人工驗證的掃描版型；符合時套用已確認正確的 placements 作為鎖定 anchor，並輸出 `verified_learned_template` 品質報告。不符合時仍會執行保守自動拼接，但報告會標成需要人工複核，避免錯誤結果被誤交付。

## 專案結構

```text
microscope_stitcher_project/
  run_practical_stitch.py              # 正式實用入口，建議優先使用
  run_practical_stitch.ps1             # PowerShell 一鍵執行入口
  run_formal_stitch.py                 # 保守 formal preset
  run_stitch.py                        # 底層 stitching CLI
  manual_align_gui.py                  # 手動拖曳校正工具
  export_manual_alignment.py           # 匯出手動校正結果
  reference/
    session_20260521_181641_759929_golden_placements.csv
    session_20260521_181641_759929_learning.json
  microscope_stitcher/
    config.py                          # 參數設定
    io_utils.py                        # 影像與座標讀取
    preprocess.py                      # flat-field / CLAHE 前處理
    registration.py                    # phase correlation / ECC / NCC / ORB fallback
    progressive.py                     # progressive multi-anchor placement
    pose_graph.py                      # global pose graph solver
    blending.py                        # subpixel placement / max-weight / feather blending
    pipeline.py                        # 完整 pipeline
```

## 安裝

```powershell
cd C:\Cell_Project\Cell_Project\microscope_stitcher_project
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

若使用主專案已建立好的 Python 環境，也可以直接在該環境執行，不一定要重新建 venv。

## 正式拼接

建議使用 PowerShell 入口：

```powershell
cd C:\Cell_Project\Cell_Project\microscope_stitcher_project
.\run_practical_stitch.ps1 `
  -InputPath "C:\Cell_Project\Cell_Project\stitched_output\stitched_output\stitched_output\captured\session_20260521_181641_759929" `
  -OutputPath "C:\Cell_Project\Cell_Project\output\practical_result" `
  -Overlap 0.35 `
  -UseCuda auto
```

等效 Python 指令：

```powershell
python run_practical_stitch.py `
  --input "C:\Cell_Project\Cell_Project\stitched_output\stitched_output\stitched_output\captured\session_20260521_181641_759929" `
  --output "C:\Cell_Project\Cell_Project\output\practical_result" `
  --coords "C:\Cell_Project\Cell_Project\stitched_output\stitched_output\stitched_output\captured\session_20260521_181641_759929\virtual_coordinates.csv" `
  --overlap 0.35 `
  --use-cuda auto `
  --export-format tif
```

## GUI 使用

主 GUI 的「正式拼接最近蛇行」按鈕已改成呼叫 `run_practical_stitch.py`。按下後會輸出：

```text
output/
  stitched.tif
  stitched_preview.jpg
  stitch_summary.json
  practical_stitch_report.json
  debug/
    placements.csv
    pair_edges.json
    progressive_steps.json
```

判斷方式請看 `practical_stitch_report.json`：

```text
verified_learned_template              可作為正式輸出
auto_candidate_needs_review            自動候選，需要人工檢查
partial_candidate_needs_manual_review  部分成功，需要人工修正
insufficient_alignment                 不足以交付
```

## 目前正式可交付範圍

已驗證資料：

```text
C:\Cell_Project\Cell_Project\stitched_output\stitched_output\stitched_output\captured\session_20260521_181641_759929
```

驗證結果：

```text
common_count = 21
missing_in_candidate = []
extra_in_candidate = []
rmse_px = 2.829e-13
max_error_px = 9.095e-13
quality_status = verified_learned_template
```

這代表目前「相同掃描版型、相同檔名座標集合」可以直接套用已確認結果。任意新掃描版型仍需累積更多 golden examples，不能直接宣稱完全自動完善。

## 重要參數

- `--axis-profile microscope-v1`：預設啟用，因為目前機台 X 正向移動時畫面往左，所以 X 座標需反轉。
- `--overlap 0.35`：目前實測比 0.15 穩定，GUI 40% overlap 也已可用於 learned template。
- `--min-template-anchors 12` 與 `--min-template-match-ratio 0.80`：避免只撞到少數檔名就誤套用 learned template。
- `--no-learned-template`：強制不用已學習模板，只跑保守自動候選。
- `--keep-unconfirmed-tiles`：不建議正式使用，會把不確定 tile 用 stage 估計硬放上去，容易造成殘影。

## 品質原則

- 不強制 grid placement。
- 不把 stage position 當最終位置。
- 不可靠 pair 允許黑色間隔，不硬拼。
- 已確認 mosaic 不因新 tile 加入而重新漂移。
- 非模板資料必須看 `practical_stitch_report.json`，通過人工檢查後才能交付。

# Basler PFS 相機參數使用說明

## 已整合的參數檔

專案已內建以下 Basler Pylon Viewer 參數檔：

```text
stitched_output\stitched_output\stitched_output\hardware\camera_profiles\acA3088-57uc_24536563.pfs
```

此檔案適用於：

```text
型號：acA3088-57uc
序號：24536563
```

內容包含 ROI、像素格式、自動曝光、自動增益、自動白平衡、Gamma、FPS 與色彩矩陣等相機參數。

## GUI 使用方式

1. 關閉 Pylon Viewer。Basler 相機無法同時被 Pylon Viewer 與 GUI 獨占開啟。
2. 開啟馬達控制 GUI。
3. 保持勾選 `啟動時套用`。
4. 保持勾選 `保留 PFS 原始畫面`，避免 GUI 額外濾鏡改變 PFS 輸出。
5. 按下 `開始預覽`。GUI 會自動載入專案內建 PFS。

若要改用其他 PFS：

1. 按下 `選擇 PFS`。
2. 選擇新的 `.pfs` 檔案。
3. 若相機已開啟，按下 `立即套用 PFS`。

## 注意事項

- PFS 應由相同型號相機匯出。不同型號可能缺少部分節點，載入會失敗。
- 若 PFS 載入失敗，GUI 會記錄錯誤並退回內建相機參數。
- Pylon Viewer 的部分顯示效果可能只作用於 Viewer 視窗，不一定寫入 PFS。GUI 使用 PFS 後會盡可能保留相機原始輸出。
- 重新打包專案時，硬體 GUI、Arduino 程式與 `camera_profiles` 會預設納入壓縮檔，不需要另外加 `-IncludeStitchedOutput`。
- 若要一併交付大量拍攝影像與拼接結果，仍需使用 `-IncludeStitchedOutput`。


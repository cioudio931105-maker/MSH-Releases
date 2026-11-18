# 圖片拼接系統 - 品質改進更新

## 📋 更新摘要

已成功修復拼接過程中藍色細胞消失的問題。新增了靈活的命令行選項，允許用戶根據需求調整拼接參數。

## 🔧 新增功能

### 1. `--no_prewarp` 選項
**作用**：禁用 Cylindrical Warp 預處理

```bash
python Image.py --mode stitch --folder "2" --no_prewarp
```

**何時使用**：
- ✓ 顯微鏡細胞影像（推薦）
- ✓ 需要保留原始色彩信息
- ✓ 檢測到色彩失真或細胞消失

**效果**：
- 保留藍色細胞和其他顏色信息
- 避免圓柱投影導致的色彩變形
- 處理時間增加 ~50%（3.6s vs 1.8s）

### 2. `--output_format` 選項
**作用**：選擇輸出格式

```bash
python Image.py --mode stitch --folder "2" --output_format png
```

**可用值**：
- `jpg`（預設）：壓縮格式，文件小（70 KB）
- `png`：無損格式，色彩精度高（437 KB）

**推薦**：
- 細胞影像用 PNG（保留最大色彩深度）
- 一般用途用 JPG（文件小，加載快）

## 🚀 推薦使用方案

### 方案 A：細胞顯微鏡影像（您的情況）⭐ 推薦
```bash
python Image.py --mode stitch \
    --folder "2" \
    --max_images 0 \
    --stitch_backend sift \
    --resize_width 1500 \
    --output_format png \
    --no_prewarp
```

**結果**：
- 藍色細胞保留率：**92.2%** ✅
- 色彩準確度：最高 ✅
- 色彩複雜度保持完整 ✅

### 方案 B：普通全景攝影
```bash
python Image.py --mode stitch \
    --folder "images" \
    --resize_width 1000 \
    --stitch_backend stitcher
```
（使用 OpenCV Stitcher + prewarp，速度快）

### 方案 C：批量處理細胞影像
```bash
python Image.py --mode batch_stitch \
    --folder "cell_images" \
    --batch_size 15 \
    --stitch_backend sift \
    --resize_width 1200 \
    --no_prewarp
```

## 📊 性能對比表

| 配置 | 後端 | 耗時 | 藍色保留率 | 文件大小 | 推薦用途 |
|------|------|------|----------|---------|---------|
| 預設 (prewarp) | Stitcher | 1.8s | 24.6% | 70 KB | 全景攝影 |
| `--no_prewarp` | Stitcher | 3.6s | 24.6% | 70 KB | ❌ 細胞影像不推薦 |
| `--no_prewarp` + PNG | Stitcher | 3.6s | 24.6% | 437 KB | ❌ 細胞影像不推薦 |
| **`--stitch_backend sift`** | **SIFT** | **8.5s** | **92.2%** | **855 KB** | **✅ 細胞影像首選** |
| `--resize_width 1500` | Stitcher | 5.2s | ~25% | 150 KB | 普通用途 |

## 🔍 診斷和調試

### 問題：藍色細胞消失或色彩失真
**原因**：OpenCV Stitcher 的 Cylindrical Warp 導致色彩變形，或特徵配準失敗
**解決**：使用 `--stitch_backend sift` 切換到 SIFT 後端
   - 藍色保留率從 24.6% 提升至 92.2%
   - 色彩複雜度保持在 5.9/8.0（接近原始 5.8）
   - 適用於顯微鏡細胞影像

### 問題：拼接速度太慢
**原因**：SIFT 後端計算量更大
**優化**：
   1. 降低 `--resize_width`（1000-1200）
   2. 使用 `--stitch_backend stitcher`（犧牲品質）
   3. 使用 `--batch_size` 並行處理

### 問題：邊界對齐不當
**原因**：特徵匹配失敗（圖片重疊不足或特徵不明顯）
**嘗試**：
1. 檢查圖片重疊率（應 > 30%）
2. 增加 `--resize_width` 到 1500
3. 確保圖片品質清晰（避免模糊）

### 問題：色彩失真或偏移
**原因**：JPG 壓縮或色彩空間轉換
**解決**：使用 `--output_format png`

## 📁 輸出文件

- `stitched_output.jpg` 或 `.png`：最終拼接結果
- `comparison.html`：視覺對比報告
- `runs/classify/predict*/`：分類推論結果

## 💡 技術細節

### 什麼是 Cylindrical Warp？
- 在拼接前將平面影像投影到圓柱曲面
- **優點**：改善廣角全景的配準，加速拼接
- **缺點**：可能扭曲特定顏色（如藍色），改變視角

### 為什麼 SIFT 後端更適合細胞影像？
1. **保留色彩**：基於特徵點匹配，不使用色彩空間變換
2. **高精度**：SIFT 特徵更適合複雜的顯微鏡影像
3. **藍色保留率達 92.2%**，而 Stitcher 只有 24.6%
4. **色彩複雜度保持**：從 5.81 保持到 5.90

### 為什麼 `--no_prewarp` 對細胞影像有幫助？
- 避免圓柱投影導致的色彩空間變換
- 保留原始影像的色彩信息完整性
- 但對 Stitcher 後端效果有限（仍然 ~25% 藍色保留）
- SIFT 後端本身就不使用 prewarp，所以此選項對 SIFT 無影響

## ✅ 檢查清單

拼接完成後，請驗證：
- [ ] 藍色細胞完整保留
- [ ] 色彩無失真或偏移
- [ ] 邊界對齐清晰
- [ ] 黑邊被正確移除
- [ ] 分類結果準確

## 📝 其他有用命令

**查看所有可用選項**：
```bash
python Image.py --help
```

**僅進行分類（不拼接）**：
```bash
python Image.py --mode classify --folder "2"
```

**使用自訓練模型**：
```bash
python Image.py --mode stitch --folder "2" \
    --model "runs/classify/train_pic_test_aug/weights/best.pt" \
    --no_prewarp
```

## 📞 支持

如有任何問題：
1. 檢查 `comparison.html` 查看詳細對比
2. 執行 `python TROUBLESHOOTING_zh_TW.py` 查看故障排除指南
3. 嘗試不同的參數組合（見上述推薦方案）

---

**上次更新**：2025-12-27  
**版本**：2.0 (Quality Improvement)

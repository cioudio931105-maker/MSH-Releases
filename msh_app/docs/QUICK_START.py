#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Quick-start guide for stitching and classification workflows."""


def print_guide() -> None:
    guide_text = """
顯微影像拼接快速指南
======================================================================

建議先用這組參數做第一輪測試：
python Image.py --mode stitch --folder "2" \
    --max_images 0 \
    --stitch_backend sift \
    --resize_width 1500 \
    --output_format png \
    --no_prewarp

常用操作：
1. 一般拼接
python Image.py --mode stitch --folder "images" --resize_width 1000 --output_format jpg

2. 分批拼接（資料量很大時）
python Image.py --mode batch_stitch --folder "cell_images" --batch_size 15 --stitch_backend sift

3. 分類
python Image.py --mode classify --folder "2"

參數重點：
- --stitch_backend sift        品質優先
- --stitch_backend stitcher    速度優先
- --no_prewarp                 關閉 cylindrical warp
- --resize_width 1200~1500     多數顯微影像較穩定
- --output_format png          保留更多細節

故障檢查：
- 看不到輸出圖：先確認 --folder 路徑與圖片副檔名
- 拼接失敗率高：切到 --stitch_backend sift
- 細節糊掉：提高 --resize_width，並改用 PNG

更多排錯請看：docs/TROUBLESHOOTING_zh_TW.py
"""
    print(guide_text)


if __name__ == "__main__":
    print_guide()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Troubleshooting guide (Traditional Chinese)."""


def print_guide() -> None:
    guide = """
顯微影像拼接疑難排解
======================================================================

1) 找不到圖片或圖片數量為 0
- 確認 --folder 路徑正確
- 確認副檔名為 jpg/jpeg/png/bmp
- 檢查圖片是否可正常開啟（避免損毀檔）

2) OpenCV Stitcher 失敗
- 改用 SIFT：--stitch_backend sift
- 提高解析寬度：--resize_width 1200 或 1500
- 先加上 --no_prewarp 測試

3) 拼接結果出現黑邊或變形
- 改用 --output_format png
- 減少 batch_size（例如 10~15）
- 檢查原始圖片是否過度旋轉或曝光差異太大

4) 品質不穩定（有時成功有時失敗）
- 固定拍攝條件（曝光、焦距、白平衡）
- 優先使用重疊區較大的圖片序列
- 減少一次拼接張數，改採分批拼接

5) 建議基線命令
python Image.py --mode stitch --folder "2" \
    --stitch_backend sift \
    --resize_width 1500 \
    --output_format png \
    --no_prewarp

6) 快速檢查輸出品質
python quality_report.py

======================================================================
"""
    print(guide)


if __name__ == "__main__":
    print_guide()

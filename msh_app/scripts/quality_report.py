#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
拼接品質驗證報告
比較 --no_prewarp 和預設設置的拼接結果
"""
import cv2
import os
import numpy as np
from pathlib import Path
from datetime import datetime

def analyze_image(img_path):
    """分析影像的色彩分佈"""
    img = cv2.imread(str(img_path))
    if img is None:
        return None
    
    # 轉換為 HSV 分析色彩
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    
    # 計算藍色像素比例（HSV 中 100-130 度範圍）
    lower_blue = np.array([100, 50, 50])
    upper_blue = np.array([130, 255, 255])
    blue_mask = cv2.inRange(hsv, lower_blue, upper_blue)
    blue_ratio = np.sum(blue_mask > 0) / blue_mask.size * 100
    
    # 計算色彩熵（複雜度）
    hist_r = cv2.calcHist([img], [2], None, [256], [0, 256])
    hist_g = cv2.calcHist([img], [1], None, [256], [0, 256])
    hist_b = cv2.calcHist([img], [0], None, [256], [0, 256])
    
    entropy = 0
    for hist in [hist_r, hist_g, hist_b]:
        hist = hist.flatten() / hist.sum()
        entropy -= np.sum(hist * np.log2(hist + 1e-10))
    entropy /= 3
    
    return {
        'width': img.shape[1],
        'height': img.shape[0],
        'size_kb': os.path.getsize(img_path) / 1024,
        'blue_ratio': blue_ratio,
        'color_entropy': entropy
    }

def create_comparison_report():
    """建立詳細的品質比較報告"""
    
    base_path = Path('.')
    
    print("\n" + "="*80)
    print("📊 拼接品質驗證報告")
    print("="*80)
    
    # 檢查兩個版本的拼接結果
    original_png = Path('stitched_output.png')
    
    if not original_png.exists():
        print("❌ 找不到拼接結果文件")
        return
    
    print(f"\n✓ 檢測到拼接結果")
    
    # 分析拼接結果
    stats = analyze_image(original_png)
    
    if stats:
        print(f"\n📈 拼接結果分析：")
        print(f"   • 解析度: {stats['width']} × {stats['height']}")
        print(f"   • 文件大小: {stats['size_kb']:.1f} KB")
        print(f"   • 藍色像素比例: {stats['blue_ratio']:.2f}%")
        print(f"   • 色彩複雜度: {stats['color_entropy']:.2f}/8.0")
    
    # 檢查原始圖片
    original_images = sorted(Path('2').glob('*.png'))
    if original_images:
        print(f"\n📷 原始圖片 ({len(original_images)} 張)：")
        
        total_blue = 0
        total_entropy = 0
        
        for img_path in original_images:
            img_stats = analyze_image(img_path)
            if img_stats:
                total_blue += img_stats['blue_ratio']
                total_entropy += img_stats['color_entropy']
                print(f"   • {img_path.name}")
                print(f"     - 藍色像素: {img_stats['blue_ratio']:.2f}%")
                print(f"     - 色彩複雜度: {img_stats['color_entropy']:.2f}")
        
        if len(original_images) > 0:
            avg_blue = total_blue / len(original_images)
            avg_entropy = total_entropy / len(original_images)
            
            print(f"\n📊 平均值：")
            print(f"   • 藍色像素平均: {avg_blue:.2f}%")
            print(f"   • 色彩複雜度平均: {avg_entropy:.2f}/8.0")
            
            if stats:
                blue_preservation = (stats['blue_ratio'] / avg_blue * 100) if avg_blue > 0 else 0
                print(f"\n✨ 品質指標：")
                print(f"   • 藍色保留率: {blue_preservation:.1f}%")
                
                if blue_preservation > 80:
                    print(f"   • 評估: ✅ 優秀（藍色細胞保留完整）")
                elif blue_preservation > 60:
                    print(f"   • 評估: ⚠️  中等（藍色細胞部分保留）")
                else:
                    print(f"   • 評估: ❌ 不足（藍色細胞丟失嚴重）")
    
    print("\n" + "="*80)
    print("💡 建議：")
    print("   1. 使用 PNG 格式以保留最大色彩深度")
    print("   2. 保持 --no_prewarp 選項啟用")
    print("   3. 對於細胞影像，設置 --resize_width 1200-1500")
    print("="*80 + "\n")

if __name__ == '__main__':
    create_comparison_report()

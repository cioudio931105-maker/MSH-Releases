#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
比較拼接前後的結果
"""
import cv2
import os
import sys
from pathlib import Path

def compare_images(folder_path, stitched_image_path, output_html='comparison.html'):
    """
    建立 HTML 報告比較原始圖片和拼接結果
    """
    folder = Path(folder_path)
    if not folder.exists():
        print(f"資料夾不存在: {folder}")
        return
    
    # 蒐集原始圖片
    image_exts = ['.jpg', '.jpeg', '.png', '.bmp']
    images = sorted([f for f in folder.glob('*') 
                    if f.suffix.lower() in image_exts])
    
    if not images:
        print(f"在 {folder} 中找不到圖片")
        return
    
    # 檢查拼接結果
    stitched_path = Path(stitched_image_path)
    if not stitched_path.exists():
        print(f"拼接結果不存在: {stitched_image_path}")
        return
    
    print(f"找到 {len(images)} 張原始圖片")
    print(f"拼接結果: {stitched_path.name}")
    
    # 讀取圖片以取得尺寸資訊
    img_info = []
    for img_path in images:
        img = cv2.imread(str(img_path))
        if img is not None:
            h, w = img.shape[:2]
            size_kb = img_path.stat().st_size / 1024
            img_info.append({
                'path': img_path.name,
                'width': w,
                'height': h,
                'size': f"{size_kb:.1f} KB"
            })
    
    stitched_img = cv2.imread(str(stitched_path))
    if stitched_img is not None:
        h, w = stitched_img.shape[:2]
        size_kb = stitched_path.stat().st_size / 1024
        stitched_info = {
            'width': w,
            'height': h,
            'size': f"{size_kb:.1f} KB"
        }
    
    # 生成 HTML 報告
    from datetime import datetime
    
    html_content = f"""
    <!DOCTYPE html>
    <html lang="zh-TW">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>圖片拼接比較</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }}
            .container {{ max-width: 1200px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 8px; }}
            h1 {{ color: #333; }}
            h2 {{ color: #666; border-bottom: 2px solid #007bff; padding-bottom: 10px; margin-top: 30px; }}
            .section {{ margin: 20px 0; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
            th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
            th {{ background-color: #007bff; color: white; }}
            tr:hover {{ background-color: #f9f9f9; }}
            .image-container {{ text-align: center; margin: 20px 0; }}
            .image-container img {{ max-width: 100%; height: auto; border: 1px solid #ddd; border-radius: 4px; margin: 10px 0; }}
            .info-box {{ background-color: #f0f8ff; padding: 15px; border-radius: 4px; border-left: 4px solid #007bff; }}
            .warning {{ background-color: #fff3cd; padding: 15px; border-radius: 4px; border-left: 4px solid #ffc107; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>📊 圖片拼接結果比較</h1>
            <div class="info-box">
                <p><strong>拼接方式:</strong> OpenCV Stitcher (無 cylindrical warp)</p>
                <p><strong>分析日期:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            </div>
            
            <h2>原始圖片資訊</h2>
            <table>
                <tr>
                    <th>文件名</th>
                    <th>解析度</th>
                    <th>文件大小</th>
                </tr>
    """
    
    for info in img_info:
        html_content += f"""
                <tr>
                    <td>{info['path']}</td>
                    <td>{info['width']} × {info['height']}</td>
                    <td>{info['size']}</td>
                </tr>
        """
    
    html_content += f"""
            </table>
            
            <h2>拼接結果資訊</h2>
            <div class="info-box">
                <p><strong>文件名:</strong> {stitched_path.name}</p>
                <p><strong>解析度:</strong> {stitched_info['width']} × {stitched_info['height']}</p>
                <p><strong>文件大小:</strong> {stitched_info['size']}</p>
            </div>
            
            <h2>拼接結果預覽</h2>
            <div class="image-container">
                <img src="{stitched_path.name}" alt="拼接結果" style="max-width: 800px;">
                <p><em>拼接結果 (已禁用 cylindrical warp)</em></p>
            </div>
            
            <h2>檢查清單</h2>
            <div class="warning">
                <ul>
                    <li>✓ 藍色細胞是否完整保留？</li>
                    <li>✓ 色彩失真或偏移現象？</li>
                    <li>✓ 邊界對齐是否正確？</li>
                    <li>✓ 黑邊被正確移除？</li>
                </ul>
            </div>
        </div>
    </body>
    </html>
    """
    
    output_file = Path(output_html)
    output_file.write_text(html_content, encoding='utf-8')
    print(f"\n✓ 比較報告已保存: {output_file}")
    print(f"  在瀏覽器中打開: file:///{output_file.absolute()}")

if __name__ == '__main__':
    folder = '2'
    stitched = 'stitched_output.png'
    compare_images(folder, stitched)

"""
資料增強：從少量圖片生成更多訓練樣本
透過旋轉、翻轉、亮度調整、雜訊等方式擴充資料集
"""
import cv2
import numpy as np
import os
from pathlib import Path
import random


def augment_image(img):
    """
    對單張圖片進行隨機增強，回傳增強後的圖片
    """
    # 隨機旋轉 (-15 到 15 度)
    if random.random() > 0.5:
        angle = random.uniform(-15, 15)
        h, w = img.shape[:2]
        M = cv2.getRotationMatrix2D((w/2, h/2), angle, 1.0)
        img = cv2.warpAffine(img, M, (w, h), borderMode=cv2.BORDER_REFLECT)
    
    # 隨機水平翻轉
    if random.random() > 0.5:
        img = cv2.flip(img, 1)
    
    # 隨機垂直翻轉
    if random.random() > 0.5:
        img = cv2.flip(img, 0)
    
    # 隨機亮度調整
    if random.random() > 0.5:
        factor = random.uniform(0.7, 1.3)
        img = np.clip(img * factor, 0, 255).astype(np.uint8)
    
    # 隨機對比度調整
    if random.random() > 0.5:
        factor = random.uniform(0.8, 1.2)
        mean = img.mean()
        img = np.clip((img - mean) * factor + mean, 0, 255).astype(np.uint8)
    
    # 隨機高斯模糊
    if random.random() > 0.7:
        ksize = random.choice([3, 5])
        img = cv2.GaussianBlur(img, (ksize, ksize), 0)
    
    # 隨機高斯雜訊
    if random.random() > 0.7:
        noise = np.random.normal(0, 10, img.shape).astype(np.float32)
        img = np.clip(img.astype(np.float32) + noise, 0, 255).astype(np.uint8)
    
    # 隨機縮放 (0.9 到 1.1 倍)
    if random.random() > 0.5:
        scale = random.uniform(0.9, 1.1)
        h, w = img.shape[:2]
        new_h, new_w = int(h * scale), int(w * scale)
        img = cv2.resize(img, (new_w, new_h))
        
        # 裁剪或填充回原始大小
        if scale > 1.0:
            start_h = (new_h - h) // 2
            start_w = (new_w - w) // 2
            img = img[start_h:start_h+h, start_w:start_w+w]
        else:
            pad_h = (h - new_h) // 2
            pad_w = (w - new_w) // 2
            img = cv2.copyMakeBorder(img, pad_h, h-new_h-pad_h, pad_w, w-new_w-pad_w, 
                                    cv2.BORDER_REFLECT)
    
    return img


def augment_dataset(source_dir, output_dir, num_augments_per_image=20):
    """
    對資料集進行增強
    
    Args:
        source_dir: 來源資料夾（包含類別子資料夾）
        output_dir: 輸出資料夾
        num_augments_per_image: 每張圖片生成的增強版本數量
    """
    source_path = Path(source_dir)
    output_path = Path(output_dir)
    
    print(f"開始資料增強：{source_dir} -> {output_dir}")
    print(f"每張圖片將生成 {num_augments_per_image} 個增強版本")
    
    # 遍歷所有類別資料夾
    class_folders = [d for d in source_path.iterdir() if d.is_dir()]
    
    total_original = 0
    total_generated = 0
    
    for class_folder in class_folders:
        class_name = class_folder.name
        
        # 跳過 test 資料夾
        if class_name == 'test':
            continue
        
        # 建立輸出目錄
        output_class_dir = output_path / class_name
        output_class_dir.mkdir(parents=True, exist_ok=True)
        
        # 取得所有圖片
        image_files = []
        for ext in ['*.jpg', '*.jpeg', '*.png', '*.bmp']:
            image_files.extend(class_folder.glob(ext))
        
        if len(image_files) == 0:
            print(f"  {class_name}: 沒有圖片")
            continue
        
        print(f"\n處理類別: {class_name} ({len(image_files)} 張原始圖片)")
        
        class_generated = 0
        
        for img_file in image_files:
            # 讀取原始圖片
            img = cv2.imread(str(img_file))
            
            if img is None:
                print(f"    無法讀取: {img_file.name}")
                continue
            
            # 複製原始圖片
            original_name = img_file.stem
            original_ext = img_file.suffix
            output_original = output_class_dir / f"{original_name}_original{original_ext}"
            cv2.imwrite(str(output_original), img)
            
            # 生成增強版本
            for i in range(num_augments_per_image):
                augmented_img = augment_image(img.copy())
                output_file = output_class_dir / f"{original_name}_aug{i:03d}{original_ext}"
                cv2.imwrite(str(output_file), augmented_img)
                class_generated += 1
            
            total_original += 1
        
        total_generated += class_generated
        print(f"  生成 {class_generated} 張增強圖片")
    
    print(f"\n資料增強完成！")
    print(f"  原始圖片: {total_original} 張")
    print(f"  生成圖片: {total_generated} 張")
    print(f"  總計: {total_original + total_generated} 張")
    print(f"  輸出路徑: {output_path.absolute()}")


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='資料增強')
    parser.add_argument('--source', default='pic test', help='來源資料夾')
    parser.add_argument('--output', default='pic test_augmented', help='輸出資料夾')
    parser.add_argument('--num_augments', type=int, default=20, 
                       help='每張圖片生成的增強版本數量')
    
    args = parser.parse_args()
    
    augment_dataset(args.source, args.output, args.num_augments)

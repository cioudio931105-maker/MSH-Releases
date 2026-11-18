#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
拼接 experiments/2 目錄中的圖像
"""
import logging
import traceback
import os
import cv2
from pathlib import Path

from Image import load_images_from_folder, stitch_images


def main():
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s %(levelname)s: %(message)s',
                        handlers=[
                            logging.FileHandler('stitch_log.txt', mode='a', encoding='utf-8'),
                            logging.StreamHandler()
                        ])

    # 目標目錄
    target_folder = Path(__file__).parent.parent / 'experiments' / '2'
    
    logging.info(f'開始拼接: {target_folder}')
    
    try:
        images = load_images_from_folder(str(target_folder), resize_width=800)
    except Exception:
        logging.error('載入影像時發生例外')
        logging.error(traceback.format_exc())
        return

    if not images:
        logging.error('未載入任何影像，結束拼接')
        return

    logging.info(f'已載入 {len(images)} 張影像')

    try:
        result = stitch_images(images, prewarp=True)
    except Exception:
        logging.error('執行拼接時發生例外')
        logging.error(traceback.format_exc())
        result = None

    outpath = str(target_folder / 'stitched_result.jpg')
    if result is not None:
        ok = cv2.imwrite(outpath, result)
        if ok:
            logging.info(f'拼接結果已儲存為 {outpath}')
            info = os.path.getsize(outpath)
            logging.info(f'輸出檔案大小: {info} bytes')
        else:
            logging.error('儲存拼接結果失敗')
    else:
        logging.error('拼接沒有產生輸出影像')


if __name__ == '__main__':
    main()


from __future__ import annotations

# Direct source entrypoints also resolve shared modules from the workspace.
import sys as _msh_sys
from pathlib import Path as _MshPath
if not getattr(_msh_sys, "frozen", False):
    _msh_sys.path.insert(0, str(_MshPath(__file__).resolve().parents[2]))


import argparse
import glob
import logging
import os
import sys
import traceback
from pathlib import Path
from typing import List, Optional

import cv2
import numpy as np

try:
    from seam_utils import autocrop_black, fill_inner_black, remove_seam_lines, trim_dark_borders
except Exception:
    def autocrop_black(img, crop=True, thr=5):
        return img
    def fill_inner_black(img, **kwargs):
        return img
    def remove_seam_lines(img):
        return img
    def trim_dark_borders(img, thr=25, frac=0.9, max_trim=50):
        return img

from msh_app.research_paths import original_research_root

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from cell_identification.object_detection import (
        ObjectDetector,
        annotate_detections,
        build_detection_mask,
        resolve_detect_model_path,
    )
except Exception:
    ObjectDetector = None  # type: ignore[assignment]
    annotate_detections = None  # type: ignore[assignment]
    build_detection_mask = None  # type: ignore[assignment]
    resolve_detect_model_path = None  # type: ignore[assignment]


def _run_infer(model_path: str | None, source: str, save_dir: str) -> None:
    from cell_identification.classify import infer
    infer(model_path, source, save_dir=save_dir)


def _create_object_detector(model_path: str | None, conf: float) -> Optional[ObjectDetector]:
    if ObjectDetector is None:
        return None
    try:
        resolved = resolve_detect_model_path(PROJECT_ROOT, model_path) if resolve_detect_model_path else (model_path or '')
        return ObjectDetector(model_path=resolved, conf_threshold=float(conf))
    except Exception as exc:
        logging.warning('Object detector init failed: %s', exc)
        return None


def _run_detect_on_output(detector: Optional[ObjectDetector], image_path: str, save_dir: str, conf: float) -> None:
    if detector is None or annotate_detections is None:
        return
    image = cv2.imread(image_path)
    if image is None:
        return
    detections = detector.detect(image, conf_threshold=conf)
    annotated = annotate_detections(image, detections)
    os.makedirs(save_dir, exist_ok=True)
    base = Path(image_path)
    out_img = os.path.join(save_dir, f"{base.stem}_detected{base.suffix or '.jpg'}")
    out_txt = os.path.join(save_dir, f"{base.stem}_detected.txt")
    cv2.imwrite(out_img, annotated)
    with open(out_txt, 'w', encoding='utf-8') as f:
        f.write(f"source: {image_path}\n")
        f.write(f"detections: {len(detections)}\n")
        for i, d in enumerate(detections, 1):
            f.write(f"{i}: bbox=[{d.x1},{d.y1},{d.x2},{d.y2}], label={d.label}, conf={d.conf:.4f}\n")


def _resize_if_needed(img: np.ndarray, resize_width: int) -> np.ndarray:
    if resize_width and resize_width > 0 and img.shape[1] > resize_width:
        scale = resize_width / float(img.shape[1])
        return cv2.resize(img, (resize_width, int(img.shape[0] * scale)), interpolation=cv2.INTER_AREA)
    return img


def load_images_from_folder(folder: str, max_images: int | None = None, resize_width: int = 0) -> List[np.ndarray]:
    files: list[str] = []
    for ext in ('*.jpg', '*.jpeg', '*.png', '*.bmp', '*.JPG', '*.JPEG', '*.PNG', '*.BMP'):
        files.extend(glob.glob(os.path.join(folder, ext)))
    files = sorted(set(files), key=lambda p: Path(p).name.lower())
    if not files:
        print(f'No images found: {folder}')
        return []
    selected = files if max_images is None or max_images <= 0 else files[:max_images]
    images: list[np.ndarray] = []
    for p in selected:
        img = cv2.imread(p)
        if img is None:
            continue
        images.append(_resize_if_needed(img, resize_width))
    return images


def load_images_from_paths(paths: List[str], resize_width: int = 0) -> List[np.ndarray]:
    images: list[np.ndarray] = []
    for p in paths:
        img = cv2.imread(p)
        if img is None:
            continue
        images.append(_resize_if_needed(img, resize_width))
    return images


def cylindrical_warp(image: np.ndarray, focal: Optional[float] = None) -> np.ndarray:
    h, w = image.shape[:2]
    focal = float(w) if focal is None else float(focal)
    x, y = np.meshgrid(np.arange(w), np.arange(h))
    x_c = x - w / 2.0
    y_c = y - h / 2.0
    theta = np.arctan2(x_c, focal)
    hyp = np.sqrt(x_c * x_c + focal * focal)
    map_x = (focal * theta + w / 2.0).astype(np.float32)
    map_y = (focal * y_c / hyp + h / 2.0).astype(np.float32)
    return cv2.remap(image, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)


def stitch_2x2_grid(images: List[np.ndarray]) -> Optional[np.ndarray]:
    if len(images) < 4:
        return None
    return np.vstack([np.hstack([images[0], images[1]]), np.hstack([images[2], images[3]])])

def _detect_features(detector, gray: np.ndarray, mask: Optional[np.ndarray]):
    if mask is not None:
        k, d = detector.detectAndCompute(gray, mask)
        if d is not None and len(k) >= 12:
            return k, d
    return detector.detectAndCompute(gray, None)


def _blend_warp(base: np.ndarray, img: np.ndarray, H: np.ndarray) -> Optional[np.ndarray]:
    bh, bw = base.shape[:2]
    ih, iw = img.shape[:2]
    c_img = np.float32([[0, 0], [iw, 0], [iw, ih], [0, ih]]).reshape(-1, 1, 2)
    c_warp = cv2.perspectiveTransform(c_img, H)
    c_base = np.float32([[0, 0], [bw, 0], [bw, bh], [0, bh]]).reshape(-1, 1, 2)
    all_c = np.concatenate((c_warp, c_base), axis=0)
    xmin, ymin = np.floor(all_c.min(axis=0).ravel()).astype(int)
    xmax, ymax = np.ceil(all_c.max(axis=0).ravel()).astype(int)
    tx, ty = -xmin, -ymin
    w, h = xmax - xmin, ymax - ymin
    if w <= 0 or h <= 0 or w > 12000 or h > 12000:
        return None
    T = np.array([[1, 0, tx], [0, 1, ty], [0, 0, 1]], dtype=np.float64)
    warp_img = cv2.warpPerspective(img, T @ H, (w, h))
    warp_base = np.zeros((h, w, 3), dtype=base.dtype)
    warp_base[ty : ty + bh, tx : tx + bw] = base
    m_img = warp_img.sum(axis=2) > 0
    m_base = warp_base.sum(axis=2) > 0
    out = warp_base.copy()
    out[m_img & (~m_base)] = warp_img[m_img & (~m_base)]
    overlap = m_img & m_base
    if np.any(overlap):
        out[overlap] = ((warp_base[overlap].astype(np.float32) + warp_img[overlap].astype(np.float32)) * 0.5).astype(np.uint8)
    return out


def sift_stitch(
    images: List[np.ndarray],
    max_width: Optional[int] = None,
    object_detector: Optional[ObjectDetector] = None,
    object_guided: bool = False,
) -> Optional[np.ndarray]:
    if len(images) < 2:
        return images[0] if images else None
    if max_width and max_width > 0:
        images = [_resize_if_needed(im, int(max_width)) for im in images]

    if hasattr(cv2, 'SIFT_create'):
        feat = cv2.SIFT_create()
        matcher = cv2.BFMatcher(cv2.NORM_L2, crossCheck=False)
    else:
        feat = cv2.ORB_create(5000)
        matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)

    def _feature_mask(bgr: np.ndarray) -> Optional[np.ndarray]:
        if not object_guided or object_detector is None or build_detection_mask is None:
            return None
        try:
            dets = object_detector.detect(bgr)
        except Exception:
            return None
        if not dets:
            return None
        m = build_detection_mask(bgr.shape[:2], dets, expand_ratio=0.1)
        if m is None or cv2.countNonZero(m) < 32:
            return None
        return m

    base = images[0]
    remaining = list(images[1:])
    remaining_masks = [_feature_mask(im) for im in remaining]

    while remaining:
        kb, db = _detect_features(feat, cv2.cvtColor(base, cv2.COLOR_BGR2GRAY), _feature_mask(base))
        if db is None or len(kb) < 10:
            return None

        best_idx = -1
        best_H = None
        best_score = -1.0

        for i, cand in enumerate(remaining):
            kc, dc = _detect_features(feat, cv2.cvtColor(cand, cv2.COLOR_BGR2GRAY), remaining_masks[i])
            if dc is None or len(kc) < 10:
                continue
            raw = matcher.knnMatch(db, dc, k=2)
            good = [m for pair in raw if len(pair) == 2 for m, n in [pair] if m.distance < 0.85 * n.distance]
            if len(good) < 10:
                continue
            src = np.float32([kb[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
            dst = np.float32([kc[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
            H, mask = cv2.findHomography(dst, src, cv2.RANSAC, 3.0)
            if H is None or mask is None:
                continue
            score = float(mask.sum()) / max(1, len(good))
            if score > best_score:
                best_idx, best_H, best_score = i, H, score

        if best_idx < 0 or best_H is None:
            return None

        merged = _blend_warp(base, remaining[best_idx], best_H)
        if merged is None:
            return None
        base = merged
        remaining.pop(best_idx)
        remaining_masks.pop(best_idx)

    return base


def stitch_images(
    images: List[np.ndarray],
    prewarp: bool = True,
    backend: str = 'stitcher',
    stitcher_mode: str = 'panorama',
    keep_black_edges: bool = False,
    black_thr: int = 5,
    edge_trim_thr: int = 25,
    edge_trim_frac: float = 0.90,
    edge_trim_max: int = 0,
    fill_holes: bool = False,
    fill_holes_thr: int = 10,
    fill_holes_min_ratio: float = 0.0005,
    fill_holes_max_ratio: float = 0.08,
    fill_holes_dilate: int = 2,
    fill_holes_open: int = 0,
    fill_holes_sat_thr: int = 0,
    fill_holes_dark_thr: int = 0,
    fill_holes_dark_sat_thr: int = 0,
    fill_holes_local_thr: int = 0,
    fill_holes_local_sigma: float = 9.0,
    fill_holes_local_gray_max: float = 0.0,
    stitch_mode: str = 'linear',
    seam_removal: str = 'auto',
    sift_max_width: Optional[int] = None,
    object_guided: bool = False,
    detect_model_path: Optional[str] = None,
    detect_conf: float = 0.25,
) -> Optional[np.ndarray]:
    if not images:
        return None
    if stitch_mode == '2x2':
        return stitch_2x2_grid(images)

    imgs = [cylindrical_warp(im) for im in images] if prewarp else images
    detector = _create_object_detector(detect_model_path, detect_conf) if object_guided else None

    result = None
    if backend == 'sift':
        result = sift_stitch(imgs, max_width=sift_max_width, object_detector=detector, object_guided=object_guided)
    else:
        if int(cv2.__version__.split('.')[0]) >= 4:
            if hasattr(cv2, 'Stitcher_SCANS'):
                mode = cv2.Stitcher_SCANS if (stitcher_mode or '').lower() == 'scans' else cv2.Stitcher_PANORAMA
                st = cv2.Stitcher_create(mode)
            else:
                st = cv2.Stitcher_create()
        else:
            st = cv2.createStitcher(False)
        status, stitched = st.stitch(imgs)
        if status == cv2.Stitcher_OK:
            result = stitched
        if result is None and prewarp:
            status, stitched = st.stitch(images)
            if status == cv2.Stitcher_OK:
                result = stitched
        if result is None:
            result = sift_stitch(images, max_width=sift_max_width, object_detector=detector, object_guided=object_guided)

    if result is None:
        return None

    if seam_removal == 'on' or (seam_removal == 'auto' and backend != 'sift'):
        result = remove_seam_lines(result)
    if not keep_black_edges:
        result = autocrop_black(result, crop=True, thr=max(1, int(black_thr)))
        trim_limit = int(edge_trim_max) if edge_trim_max and edge_trim_max > 0 else int(min(200, max(5, int(min(result.shape[:2]) * 0.05))))
        result = trim_dark_borders(result, thr=max(1, int(edge_trim_thr)), frac=float(max(0.0, min(1.0, edge_trim_frac))), max_trim=trim_limit)
    if fill_holes:
        result = fill_inner_black(
            result,
            thr=max(1, int(fill_holes_thr)),
            min_area_ratio=float(max(0.0, fill_holes_min_ratio)),
            max_area_ratio=float(max(fill_holes_min_ratio, fill_holes_max_ratio)),
            dilate=max(0, int(fill_holes_dilate)),
            open_ksize=max(0, int(fill_holes_open)),
            sat_thr=max(0, int(fill_holes_sat_thr)),
            dark_thr=max(0, int(fill_holes_dark_thr)),
            dark_sat_thr=max(0, int(fill_holes_dark_sat_thr)),
            local_diff_thr=max(0, int(fill_holes_local_thr)),
            local_diff_sigma=float(max(0.1, fill_holes_local_sigma)),
            local_gray_max=float(max(0.0, fill_holes_local_gray_max)),
        )
    return result

def batch_stitch_images(
    images: List[np.ndarray],
    batch_size: int = 15,
    prewarp: bool = True,
    backend: str = 'stitcher',
    stitcher_mode: str = 'panorama',
    output_dir: str = '.',
    output_format: str = 'jpg',
    keep_black_edges: bool = False,
    black_thr: int = 5,
    edge_trim_thr: int = 25,
    edge_trim_frac: float = 0.90,
    edge_trim_max: int = 0,
    fill_holes: bool = False,
    fill_holes_thr: int = 10,
    fill_holes_min_ratio: float = 0.0005,
    fill_holes_max_ratio: float = 0.08,
    fill_holes_dilate: int = 2,
    fill_holes_open: int = 0,
    fill_holes_sat_thr: int = 0,
    fill_holes_dark_thr: int = 0,
    fill_holes_dark_sat_thr: int = 0,
    fill_holes_local_thr: int = 0,
    fill_holes_local_sigma: float = 9.0,
    fill_holes_local_gray_max: float = 0.0,
    stitch_mode: str = 'linear',
    seam_removal: str = 'auto',
    sift_max_width: Optional[int] = None,
    object_guided: bool = False,
    detect_model_path: Optional[str] = None,
    detect_conf: float = 0.25,
    detect_callback=None,
) -> List[str]:
    if not images:
        return []
    os.makedirs(output_dir, exist_ok=True)
    batch_size = max(1, int(batch_size))
    out: list[str] = []
    total = len(images)
    for i in range((total + batch_size - 1) // batch_size):
        chunk = images[i * batch_size : min((i + 1) * batch_size, total)]
        stitched = stitch_images(
            chunk,
            prewarp=prewarp,
            backend=backend,
            stitcher_mode=stitcher_mode,
            keep_black_edges=keep_black_edges,
            black_thr=black_thr,
            edge_trim_thr=edge_trim_thr,
            edge_trim_frac=edge_trim_frac,
            edge_trim_max=edge_trim_max,
            fill_holes=fill_holes,
            fill_holes_thr=fill_holes_thr,
            fill_holes_min_ratio=fill_holes_min_ratio,
            fill_holes_max_ratio=fill_holes_max_ratio,
            fill_holes_dilate=fill_holes_dilate,
            fill_holes_open=fill_holes_open,
            fill_holes_sat_thr=fill_holes_sat_thr,
            fill_holes_dark_thr=fill_holes_dark_thr,
            fill_holes_dark_sat_thr=fill_holes_dark_sat_thr,
            fill_holes_local_thr=fill_holes_local_thr,
            fill_holes_local_sigma=fill_holes_local_sigma,
            fill_holes_local_gray_max=fill_holes_local_gray_max,
            stitch_mode=stitch_mode,
            seam_removal=seam_removal,
            sift_max_width=sift_max_width,
            object_guided=object_guided,
            detect_model_path=detect_model_path,
            detect_conf=detect_conf,
        )
        if stitched is None:
            continue
        ext = '.png' if output_format == 'png' else '.jpg'
        p = os.path.join(output_dir, f'stitched_batch_{i+1:03d}{ext}')
        if cv2.imwrite(p, stitched):
            out.append(p)
            if detect_callback is not None:
                try:
                    detect_callback(p)
                except Exception:
                    pass
    return out


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description='Image stitching and/or classification helper')
    p.add_argument('--mode', choices=('stitch', 'classify', 'batch_stitch'), default='stitch')
    p.add_argument('--folder', default=str(original_research_root() / 'scripts' / 'cell_images'))
    p.add_argument('--max_images', type=int, default=10)
    p.add_argument('--resize_width', type=int, default=0)
    p.add_argument('--model', default=None)
    p.add_argument('--stitch_backend', choices=('stitcher', 'sift'), default='stitcher')
    p.add_argument('--stitcher_mode', choices=('panorama', 'scans'), default='panorama')
    p.add_argument('--batch_size', type=int, default=15)
    p.add_argument('--no_prewarp', action='store_true')
    p.add_argument('--sift_max_width', type=int, default=0)
    p.add_argument('--seam_removal', choices=('auto', 'on', 'off'), default='auto')
    p.add_argument('--output_format', choices=('jpg', 'png'), default='jpg')
    p.add_argument('--keep_black_edges', action='store_true')
    p.add_argument('--black_thr', type=int, default=5)
    p.add_argument('--edge_trim_thr', type=int, default=25)
    p.add_argument('--edge_trim_frac', type=float, default=0.90)
    p.add_argument('--edge_trim_max', type=int, default=0)
    p.add_argument('--fill_holes', action='store_true')
    p.add_argument('--fill_holes_thr', type=int, default=10)
    p.add_argument('--fill_holes_min_ratio', type=float, default=0.0005)
    p.add_argument('--fill_holes_max_ratio', type=float, default=0.08)
    p.add_argument('--fill_holes_dilate', type=int, default=2)
    p.add_argument('--fill_holes_open', type=int, default=0)
    p.add_argument('--fill_holes_sat_thr', type=int, default=0)
    p.add_argument('--fill_holes_dark_thr', type=int, default=0)
    p.add_argument('--fill_holes_dark_sat_thr', type=int, default=0)
    p.add_argument('--fill_holes_local_thr', type=int, default=0)
    p.add_argument('--fill_holes_local_sigma', type=float, default=9.0)
    p.add_argument('--fill_holes_local_gray_max', type=float, default=0.0)
    p.add_argument('--stitch_mode', choices=('linear', '2x2'), default='linear')
    p.add_argument('--skip_infer', action='store_true')
    p.add_argument('--merge_batches', action='store_true')
    p.add_argument('--object_guided', action='store_true')
    p.add_argument('--detect_model', default=None)
    p.add_argument('--detect_conf', type=float, default=0.25)
    p.add_argument('--skip_detect_output', action='store_true')
    p.add_argument('--detect_output_dir', default='detected')
    return p


def main() -> int:
    args = _build_parser().parse_args()
    log_path = os.path.join(os.path.dirname(__file__), 'stitch_log.txt')
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s', handlers=[logging.FileHandler(log_path, mode='a', encoding='utf-8'), logging.StreamHandler()])

    output_dir = os.path.normpath(str(original_research_root() / 'output'))
    os.makedirs(output_dir, exist_ok=True)
    detect_conf = float(max(0.01, min(1.0, args.detect_conf)))
    detect_output_dir = args.detect_output_dir if os.path.isabs(args.detect_output_dir) else os.path.join(output_dir, args.detect_output_dir)
    os.makedirs(detect_output_dir, exist_ok=True)

    output_detector = None if args.skip_detect_output else _create_object_detector(args.detect_model, detect_conf)

    def detect_cb(path: str) -> None:
        _run_detect_on_output(output_detector, path, detect_output_dir, detect_conf)

    images = load_images_from_folder(args.folder, None if args.max_images <= 0 else args.max_images, args.resize_width)
    if args.mode == 'classify':
        _run_infer(args.model, args.folder, save_dir='runs/classify/infer')
        return 0
    if not images:
        return 1

    common = dict(
        prewarp=(not args.no_prewarp), backend=args.stitch_backend, stitcher_mode=args.stitcher_mode,
        keep_black_edges=args.keep_black_edges, black_thr=args.black_thr, edge_trim_thr=args.edge_trim_thr,
        edge_trim_frac=args.edge_trim_frac, edge_trim_max=args.edge_trim_max, fill_holes=args.fill_holes,
        fill_holes_thr=args.fill_holes_thr, fill_holes_min_ratio=args.fill_holes_min_ratio,
        fill_holes_max_ratio=args.fill_holes_max_ratio, fill_holes_dilate=args.fill_holes_dilate,
        fill_holes_open=args.fill_holes_open, fill_holes_sat_thr=args.fill_holes_sat_thr,
        fill_holes_dark_thr=args.fill_holes_dark_thr, fill_holes_dark_sat_thr=args.fill_holes_dark_sat_thr,
        fill_holes_local_thr=args.fill_holes_local_thr, fill_holes_local_sigma=args.fill_holes_local_sigma,
        fill_holes_local_gray_max=args.fill_holes_local_gray_max, stitch_mode=args.stitch_mode,
        seam_removal=args.seam_removal, sift_max_width=(None if args.sift_max_width <= 0 else args.sift_max_width),
        object_guided=args.object_guided, detect_model_path=args.detect_model, detect_conf=detect_conf,
    )

    if args.mode == 'batch_stitch':
        batch = batch_stitch_images(images, batch_size=args.batch_size, output_dir=output_dir, output_format=args.output_format, detect_callback=detect_cb, **common)
        if args.merge_batches and len(batch) > 1:
            merged = stitch_images(load_images_from_paths(batch, 0), **common)
            if merged is not None:
                ext = '.png' if args.output_format == 'png' else '.jpg'
                final_path = os.path.join(output_dir, f'stitched_output{ext}')
                cv2.imwrite(final_path, merged)
                detect_cb(final_path)
        if batch and not args.skip_infer:
            for b in batch:
                try:
                    _run_infer(args.model, b, save_dir='runs/classify/batch_infer')
                except Exception:
                    logging.error(traceback.format_exc())
        return 0

    result = stitch_images(images, **common)
    if result is None:
        if not args.skip_infer:
            _run_infer(args.model, args.folder, save_dir='runs/classify/infer_from_stitch')
        return 1

    ext = '.png' if args.output_format == 'png' else '.jpg'
    outpath = os.path.join(output_dir, f'stitched_output{ext}')
    cv2.imwrite(outpath, result)
    detect_cb(outpath)
    if not args.skip_infer:
        try:
            _run_infer(args.model, outpath, save_dir='runs/classify/infer_from_stitch')
        except Exception:
            logging.error(traceback.format_exc())
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

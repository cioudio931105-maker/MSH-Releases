from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import cv2
import numpy as np
import tifffile

from .config import StitchConfig
from .io_utils import read_image_bgr
from .types import Tile


def compose_mosaic(
    tiles: list[Tile],
    positions_full: np.ndarray,
    config: StitchConfig,
    final_path: Path,
    preview_path: Path,
) -> dict[str, object]:
    first, _ = read_image_bgr(tiles[0].path)
    tile_h, tile_w = first.shape[:2]
    min_xy = np.floor(np.min(positions_full, axis=0)).astype(int)
    shifted = positions_full - min_xy
    max_x = int(np.ceil(np.max(shifted[:, 0]) + tile_w + 3))
    max_y = int(np.ceil(np.max(shifted[:, 1]) + tile_h + 3))

    if config.blend_mode == "max_weight":
        estimated_mb = (max_x * max_y * 3 + max_x * max_y * 4) / (1024 * 1024)
    else:
        estimated_mb = (max_x * max_y * 3 * 4 + max_x * max_y * 4) / (1024 * 1024)
    temp_dir = None
    if estimated_mb > config.memmap_threshold_mb:
        temp_dir = Path(tempfile.mkdtemp(prefix="microscope_stitch_"))
        if config.blend_mode == "max_weight":
            mosaic = np.memmap(temp_dir / "mosaic.dat", dtype=np.uint8, mode="w+", shape=(max_y, max_x, 3))
            owner_weight = np.memmap(temp_dir / "owner_weight.dat", dtype=np.float32, mode="w+", shape=(max_y, max_x))
            mosaic[:] = 0
            owner_weight[:] = 0
        else:
            accum = np.memmap(temp_dir / "accum.dat", dtype=np.float32, mode="w+", shape=(max_y, max_x, 3))
            weight = np.memmap(temp_dir / "weight.dat", dtype=np.float32, mode="w+", shape=(max_y, max_x))
            accum[:] = 0
            weight[:] = 0
    else:
        if config.blend_mode == "max_weight":
            mosaic = np.zeros((max_y, max_x, 3), dtype=np.uint8)
            owner_weight = np.zeros((max_y, max_x), dtype=np.float32)
        else:
            accum = np.zeros((max_y, max_x, 3), dtype=np.float32)
            weight = np.zeros((max_y, max_x), dtype=np.float32)

    base_mask = feather_mask(tile_h, tile_w, max(4, config.feather_width))
    for tile, pos in zip(tiles, shifted):
        image, _ = read_image_bgr(tile.path)
        if image.shape[:2] != (tile_h, tile_w):
            image = cv2.resize(image, (tile_w, tile_h), interpolation=cv2.INTER_AREA)
        x_floor = int(np.floor(pos[0]))
        y_floor = int(np.floor(pos[1]))
        frac_x = float(pos[0] - x_floor)
        frac_y = float(pos[1] - y_floor)
        warped_image, warped_mask = _subpixel_shift(image, base_mask, frac_x, frac_y)
        h, w = warped_mask.shape[:2]
        x0 = max(0, x_floor)
        y0 = max(0, y_floor)
        x1 = min(max_x, x_floor + w)
        y1 = min(max_y, y_floor + h)
        sx0 = x0 - x_floor
        sy0 = y0 - y_floor
        sx1 = sx0 + (x1 - x0)
        sy1 = sy0 + (y1 - y0)
        mask = warped_mask[sy0:sy1, sx0:sx1]
        tile_region = warped_image[sy0:sy1, sx0:sx1]
        if config.blend_mode == "max_weight":
            current_weight = owner_weight[y0:y1, x0:x1]
            replace = mask > current_weight
            if np.any(replace):
                mosaic_region = mosaic[y0:y1, x0:x1]
                mosaic_region[replace] = tile_region[replace]
                current_weight[replace] = mask[replace]
        else:
            accum[y0:y1, x0:x1] += tile_region.astype(np.float32) * mask[:, :, None]
            weight[y0:y1, x0:x1] += mask

    if config.blend_mode == "max_weight":
        output = np.asarray(mosaic).copy()
        valid_weight = owner_weight
    else:
        output = _normalize(accum, weight)
        valid_weight = weight
    crop_box = None
    if config.crop:
        crop_box = crop_nonzero_weight(valid_weight)
        if crop_box is not None:
            x0, y0, x1, y1 = crop_box
            output = output[y0:y1, x0:x1]

    write_image(final_path, output)
    preview = make_preview(output, config.preview_long_side)
    cv2.imwrite(str(preview_path), preview)

    if temp_dir is not None:
        shutil.rmtree(temp_dir, ignore_errors=True)

    return {
        "canvas_size": [int(output.shape[1]), int(output.shape[0])],
        "uncropped_canvas_size": [max_x, max_y],
        "crop_box": crop_box,
        "used_memmap": temp_dir is not None,
        "estimated_accumulator_mb": estimated_mb,
        "blend_mode": config.blend_mode,
    }


def feather_mask(height: int, width: int, feather_width: int) -> np.ndarray:
    y = np.minimum(np.arange(height), np.arange(height)[::-1]).astype(np.float32)
    x = np.minimum(np.arange(width), np.arange(width)[::-1]).astype(np.float32)
    dist = np.minimum(y[:, None], x[None, :])
    mask = np.clip(dist / float(max(1, feather_width)), 0.0, 1.0)
    return np.maximum(mask, 0.05).astype(np.float32)


def _subpixel_shift(image: np.ndarray, mask: np.ndarray, frac_x: float, frac_y: float):
    if abs(frac_x) < 1e-4 and abs(frac_y) < 1e-4:
        return image, mask
    h, w = mask.shape
    matrix = np.array([[1.0, 0.0, frac_x], [0.0, 1.0, frac_y]], dtype=np.float32)
    warped_image = cv2.warpAffine(image, matrix, (w + 2, h + 2), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    warped_mask = cv2.warpAffine(mask, matrix, (w + 2, h + 2), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    return warped_image, warped_mask


def _normalize(accum: np.ndarray, weight: np.ndarray) -> np.ndarray:
    safe = np.maximum(weight, 1e-6)
    out = accum / safe[:, :, None]
    out[weight <= 1e-6] = 0
    return np.clip(out, 0, 255).astype(np.uint8)


def crop_nonzero_weight(weight: np.ndarray) -> tuple[int, int, int, int] | None:
    ys, xs = np.where(weight > 1e-5)
    if len(xs) == 0 or len(ys) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max() + 1), int(ys.max() + 1)


def write_image(path: Path, image_bgr: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() in {".tif", ".tiff"}:
        tifffile.imwrite(str(path), cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB), bigtiff=True)
    else:
        cv2.imwrite(str(path), image_bgr)


def make_preview(image_bgr: np.ndarray, long_side: int) -> np.ndarray:
    h, w = image_bgr.shape[:2]
    scale = min(1.0, long_side / float(max(h, w)))
    if scale >= 0.999:
        return image_bgr
    return cv2.resize(image_bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

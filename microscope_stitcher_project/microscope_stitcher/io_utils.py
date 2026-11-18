from __future__ import annotations

import csv
import re
from pathlib import Path

import cv2
import numpy as np
import tifffile

from .types import Tile

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"}
COORD_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)_(-?\d+(?:\.\d+)?)\s*$")


def discover_tiles(
    input_dir: Path,
    coords_csv: Path | None = None,
    invert_x: bool = False,
    invert_y: bool = False,
) -> list[Tile]:
    csv_path = coords_csv or (input_dir / "virtual_coordinates.csv")
    if csv_path.exists():
        return _tiles_from_csv(input_dir, csv_path, invert_x, invert_y)
    return _tiles_from_filenames(input_dir, invert_x, invert_y)


def _tiles_from_csv(input_dir: Path, csv_path: Path, invert_x: bool, invert_y: bool) -> list[Tile]:
    tiles: list[Tile] = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row_index, row in enumerate(reader):
            filename = (row.get("filename") or "").strip()
            if not filename:
                continue
            path = input_dir / filename
            if not path.exists():
                continue
            x = float(row.get("x", 0.0))
            y = float(row.get("y", 0.0))
            if invert_x:
                x = -x
            if invert_y:
                y = -y
            index = int(float(row.get("index", row_index + 1)))
            tiles.append(Tile(path=path, filename=filename, x=x, y=y, index=index))
    if not tiles:
        raise ValueError(f"No tiles loaded from CSV: {csv_path}")
    return sorted(tiles, key=lambda item: item.index)


def _tiles_from_filenames(input_dir: Path, invert_x: bool, invert_y: bool) -> list[Tile]:
    tiles: list[Tile] = []
    for index, path in enumerate(sorted(input_dir.iterdir())):
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        match = COORD_RE.match(path.stem)
        if not match:
            continue
        x = float(match.group(1))
        y = float(match.group(2))
        if invert_x:
            x = -x
        if invert_y:
            y = -y
        tiles.append(Tile(path=path, filename=path.name, x=x, y=y, index=index + 1))
    if not tiles:
        raise ValueError(f"No coordinate-named tiles like x_y.jpg were found in {input_dir}")
    return sorted(tiles, key=lambda item: (item.y, item.x, item.index))


def read_image_bgr(path: Path, scale: float = 1.0, max_side: int | None = None) -> tuple[np.ndarray, float]:
    image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    loaded_by_tifffile = False
    if image is None:
        image = tifffile.imread(str(path))
        loaded_by_tifffile = True

    image = _ensure_bgr_uint8(image, loaded_by_tifffile=loaded_by_tifffile)
    actual_scale = min(1.0, max(0.01, scale))
    if max_side is not None and max(image.shape[:2]) * actual_scale > max_side:
        actual_scale = max_side / float(max(image.shape[:2]))
    if actual_scale < 0.999:
        image = cv2.resize(image, None, fx=actual_scale, fy=actual_scale, interpolation=cv2.INTER_AREA)
    return image, actual_scale


def _ensure_bgr_uint8(image: np.ndarray, loaded_by_tifffile: bool) -> np.ndarray:
    if image.ndim == 2:
        image = normalize_to_uint8(image)
        return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    if image.ndim == 3 and image.shape[2] == 4:
        image = image[:, :, :3]
    if image.dtype != np.uint8:
        image = normalize_to_uint8(image)
    if loaded_by_tifffile and image.ndim == 3 and image.shape[2] == 3:
        image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
    return np.ascontiguousarray(image)


def normalize_to_uint8(image: np.ndarray) -> np.ndarray:
    arr = image.astype(np.float32)
    lo, hi = np.percentile(arr, (0.5, 99.5))
    if hi <= lo:
        return np.zeros(arr.shape, dtype=np.uint8)
    arr = np.clip((arr - lo) * 255.0 / (hi - lo), 0, 255)
    return arr.astype(np.uint8)

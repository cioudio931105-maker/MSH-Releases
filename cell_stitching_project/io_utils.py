from __future__ import annotations

import csv
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import cv2
import numpy as np

try:
    import tifffile
except Exception:  # pragma: no cover - optional dependency
    tifffile = None  # type: ignore[assignment]

try:
    import imageio.v3 as imageio_v3
except Exception:  # pragma: no cover - optional dependency
    imageio_v3 = None  # type: ignore[assignment]


SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff"}
_NATURAL_SPLIT = re.compile(r"(\d+)")
_COORD_TUPLE_PATTERN = re.compile(r"[\(\[]\s*(-?\d+(?:\.\d+)?)\s*[,x]\s*(-?\d+(?:\.\d+)?)\s*[\)\]]", re.IGNORECASE)
_ROW_PATTERN = re.compile(r"(?:^|[_\-\s\(\[])(?:row|y|r)\s*[:=]?\s*(-?\d+(?:\.\d+)?)", re.IGNORECASE)
_COL_PATTERN = re.compile(r"(?:^|[_\-\s\(\[])(?:col|column|x|c)\s*[:=]?\s*(-?\d+(?:\.\d+)?)", re.IGNORECASE)
_PLAIN_XY_PATTERN = re.compile(r"^(?P<x>-?\d+(?:\.\d+)?)_(?P<y>-?\d+(?:\.\d+)?)$")


def parse_image_coordinates(path: str | Path) -> tuple[float, float] | None:
    """Extract a `(row, col)` coordinate pair from a filename stem when available."""

    stem = Path(path).stem
    tuple_match = _COORD_TUPLE_PATTERN.search(stem)
    if tuple_match is not None:
        return float(tuple_match.group(1)), float(tuple_match.group(2))

    row_match = _ROW_PATTERN.search(stem)
    col_match = _COL_PATTERN.search(stem)
    if row_match is not None and col_match is not None:
        return float(row_match.group(1)), float(col_match.group(1))

    # Plain microscope tiles are commonly named as `x_y.jpg`.
    plain_match = _PLAIN_XY_PATTERN.match(stem)
    if plain_match is not None:
        return float(plain_match.group("y")), float(plain_match.group("x"))
    return None


def parse_xy_coordinates(path: str | Path) -> tuple[float, float] | None:
    """Extract an `(x, y)` coordinate pair from a filename when available."""

    row_col = parse_image_coordinates(path)
    if row_col is None:
        return None
    row, col = row_col
    return col, row


@dataclass(slots=True)
class OutputPaths:
    root: Path
    debug_dir: Path
    debug_matches_dir: Path
    intermediate_dir: Path
    log_path: Path
    result_path: Path
    shifts_json_path: Path
    shifts_csv_path: Path
    overlay_preview_path: Path


def natural_sort_key(value: str) -> list[object]:
    parts = _NATURAL_SPLIT.split(value.lower())
    return [int(part) if part.isdigit() else part for part in parts]


def _coordinate_sort_key(path: Path, coordinate_priority: str) -> tuple[float, float, list[object]]:
    coordinates = parse_image_coordinates(path)
    if coordinates is None:
        raise ValueError(f"Filename does not contain a parseable coordinate pair: {path.name}")
    row, col = coordinates
    if coordinate_priority == "column-major":
        return col, row, natural_sort_key(path.name)
    return row, col, natural_sort_key(path.name)


def _sort_paths(
    paths: list[Path],
    input_order: str,
    coordinate_priority: str,
) -> list[Path]:
    naturally_sorted = sorted(paths, key=lambda item: natural_sort_key(item.name))
    if input_order == "natural":
        return naturally_sorted

    all_have_coordinates = all(parse_image_coordinates(path) is not None for path in naturally_sorted)
    if input_order == "coordinates":
        if not all_have_coordinates:
            missing = [path.name for path in naturally_sorted if parse_image_coordinates(path) is None][:5]
            joined = ", ".join(missing)
            raise ValueError(
                "Coordinate ordering was requested, but some filenames do not contain parseable coordinates. "
                f"Examples: {joined}"
            )
        return sorted(naturally_sorted, key=lambda item: _coordinate_sort_key(item, coordinate_priority))

    if input_order == "auto" and all_have_coordinates:
        return sorted(naturally_sorted, key=lambda item: _coordinate_sort_key(item, coordinate_priority))
    return naturally_sorted


def list_image_paths(
    input_dir: str | Path,
    image_extension: str = "auto",
    explicit_paths: Sequence[str] | None = None,
    max_images: int | None = None,
    input_order: str = "auto",
    coordinate_priority: str = "row-major",
) -> list[Path]:
    """Return microscope image paths ordered by filename or explicit coordinates."""

    if image_extension != "auto":
        requested = image_extension if image_extension.startswith(".") else f".{image_extension}"
        requested = requested.lower()
        if requested not in SUPPORTED_EXTENSIONS:
            raise ValueError(f"Unsupported extension filter: {requested}")
        allowed = {requested}
    else:
        allowed = SUPPORTED_EXTENSIONS

    if explicit_paths:
        paths = [Path(p) for p in explicit_paths]
        existing = [path for path in paths if path.exists() and path.is_file() and path.suffix.lower() in allowed]
        return existing[:max_images] if max_images else existing

    root = Path(input_dir)
    if not root.exists():
        raise FileNotFoundError(f"Input directory does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Input path is not a directory: {root}")

    paths = [path for path in root.iterdir() if path.is_file() and path.suffix.lower() in allowed]
    paths = _sort_paths(paths, input_order=input_order, coordinate_priority=coordinate_priority)
    return paths[:max_images] if max_images else paths


def _scale_to_uint8(image: np.ndarray) -> np.ndarray:
    if image.dtype == np.uint8:
        return image
    image_f32 = image.astype(np.float32)
    min_value = float(np.min(image_f32))
    max_value = float(np.max(image_f32))
    if max_value <= min_value:
        return np.zeros(image.shape, dtype=np.uint8)
    scaled = (image_f32 - min_value) * (255.0 / (max_value - min_value))
    return np.clip(scaled, 0, 255).astype(np.uint8)


def _ensure_bgr(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    if image.ndim == 3 and image.shape[2] == 4:
        return cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
    if image.ndim == 3 and image.shape[2] == 3:
        return image
    raise ValueError(f"Unsupported image shape: {image.shape}")


def read_image(path: str | Path) -> np.ndarray:
    """Read a microscope image and normalize it to BGR uint8."""

    image_path = Path(path)
    image = cv2.imread(str(image_path), cv2.IMREAD_UNCHANGED)

    if image is None and image_path.suffix.lower() in {".tif", ".tiff"}:
        if tifffile is not None:
            image = tifffile.imread(str(image_path))
        elif imageio_v3 is not None:
            image = imageio_v3.imread(str(image_path))

    if image is None:
        raise ValueError(f"Failed to read image: {image_path}")

    if isinstance(image, np.ndarray) and image.dtype != np.uint8:
        image = _scale_to_uint8(image)

    if not isinstance(image, np.ndarray):
        raise ValueError(f"Unsupported image payload: {image_path}")

    return _ensure_bgr(image)


def create_output_paths(output_dir: str | Path, result_name: str, shifts_json_name: str, shifts_csv_name: str, overlay_name: str, log_name: str, debug_matches_dirname: str, intermediate_dirname: str) -> OutputPaths:
    """Create the output folder tree used by the stitching pipeline."""

    root = Path(output_dir)
    debug_dir = root / "debug"
    debug_matches_dir = debug_dir / debug_matches_dirname
    intermediate_dir = root / intermediate_dirname
    for directory in (root, debug_dir, debug_matches_dir, intermediate_dir):
        directory.mkdir(parents=True, exist_ok=True)

    return OutputPaths(
        root=root,
        debug_dir=debug_dir,
        debug_matches_dir=debug_matches_dir,
        intermediate_dir=intermediate_dir,
        log_path=root / log_name,
        result_path=root / result_name,
        shifts_json_path=root / shifts_json_name,
        shifts_csv_path=root / shifts_csv_name,
        overlay_preview_path=root / overlay_name,
    )


def configure_logger(log_path: str | Path) -> logging.Logger:
    """Create a dedicated logger that writes to both console and file."""

    logger = logging.getLogger("cell_stitching")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.propagate = False

    formatter = logging.Formatter("%(asctime)s %(levelname)s: %(message)s")
    file_handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    return logger


def save_image(path: str | Path, image: np.ndarray) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(target), image):
        raise IOError(f"Failed to write image: {target}")
    return target


def _json_default(value: object) -> object:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(f"Object of type {value.__class__.__name__} is not JSON serializable")


def save_json(path: str | Path, payload: dict[str, object]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, default=_json_default)
    return target


def append_jsonl(path: str | Path, payload: dict[str, object]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, default=_json_default))
        handle.write("\n")
    return target


def save_text_lines(path: str | Path, lines: Sequence[str]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(str(line) for line in lines)
    if content and not content.endswith("\n"):
        content += "\n"
    target.write_text(content, encoding="utf-8")
    return target


def save_shift_records_csv(path: str | Path, rows: Iterable[dict[str, object]]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    rows = list(rows)
    fieldnames = list(rows[0].keys()) if rows else ["pair_index", "ref_image", "mov_image", "dx", "dy", "angle", "score", "method", "direction", "used_yolo_guidance"]
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return target

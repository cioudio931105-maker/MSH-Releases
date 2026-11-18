from __future__ import annotations

from msh_model_policy import require_local_model

import argparse
import csv
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .io_utils import SUPPORTED_EXTENSIONS, read_image, save_image
from .io_utils import save_json

try:
    from .config import resolve_default_detection_model_path
except Exception:  # pragma: no cover - optional in stripped-down deployments
    resolve_default_detection_model_path = None  # type: ignore[assignment]


_PLAIN_COORD_PATTERN = re.compile(r"^(-?\d+(?:\.\d+)?)_(-?\d+(?:\.\d+)?)$")


@dataclass(slots=True)
class CoordinateTile:
    path: Path
    x: float
    y: float
    order: int = 0


@dataclass(slots=True)
class DetectionFeature:
    cx: float
    cy: float
    width: float
    height: float
    area: float
    cls_id: int
    label: str
    conf: float


def _feature_to_payload(feature: DetectionFeature) -> dict[str, object]:
    return {
        "cx": feature.cx,
        "cy": feature.cy,
        "width": feature.width,
        "height": feature.height,
        "area": feature.area,
        "cls_id": feature.cls_id,
        "label": feature.label,
        "conf": feature.conf,
    }


def _feature_from_payload(payload: dict[str, object]) -> DetectionFeature:
    return DetectionFeature(
        cx=float(payload["cx"]),
        cy=float(payload["cy"]),
        width=float(payload["width"]),
        height=float(payload["height"]),
        area=float(payload["area"]),
        cls_id=int(payload["cls_id"]),
        label=str(payload["label"]),
        conf=float(payload["conf"]),
    )


def parse_plain_coordinate_tile(path: str | Path) -> CoordinateTile | None:
    candidate = Path(path)
    match = _PLAIN_COORD_PATTERN.match(candidate.stem)
    if match is None:
        return None
    return CoordinateTile(path=candidate, x=float(match.group(1)), y=float(match.group(2)))


def list_coordinate_tiles(input_dir: str | Path) -> list[CoordinateTile]:
    root = Path(input_dir)
    if not root.exists():
        raise FileNotFoundError(f"Input directory does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Input path is not a directory: {root}")

    tiles: list[CoordinateTile] = []
    for order, path in enumerate(sorted(root.iterdir(), key=lambda item: item.name)):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        tile = parse_plain_coordinate_tile(path)
        if tile is not None:
            tiles.append(CoordinateTile(path=tile.path, x=tile.x, y=tile.y, order=order))

    if not tiles:
        raise ValueError(f"No plain coordinate images like 'x_y.jpg' were found in {root}")
    return tiles


def _load_virtual_coordinate_tiles(input_dir: str | Path) -> list[CoordinateTile] | None:
    root = Path(input_dir)
    csv_path = root / "virtual_coordinates.csv"
    if not csv_path.exists():
        return None

    tiles: list[CoordinateTile] = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for fallback_order, row in enumerate(reader):
            filename = (row.get("filename") or "").strip()
            x_value = (row.get("x") or "").strip()
            y_value = (row.get("y") or "").strip()
            if not filename or not x_value or not y_value:
                continue
            path = (root / filename).resolve()
            if not path.exists() or not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            index_value = (row.get("index") or "").strip()
            try:
                order = int(index_value)
            except ValueError:
                order = fallback_order
            tiles.append(CoordinateTile(path=path, x=float(x_value), y=float(y_value), order=order))

    return tiles or None


def load_coordinate_tiles(
    input_dir: str | Path,
    explicit_paths: list[str] | None = None,
    prefer_virtual_coordinates: bool = True,
) -> tuple[list[CoordinateTile], str]:
    root = Path(input_dir)
    tiles = _load_virtual_coordinate_tiles(root) if prefer_virtual_coordinates else None
    source = "virtual_coordinates.csv" if tiles is not None else "filename"
    if tiles is None:
        tiles = list_coordinate_tiles(root)

    if explicit_paths is None:
        return tiles, source

    selected_lookup = {Path(path).resolve(): index for index, path in enumerate(explicit_paths)}
    filtered = [tile for tile in tiles if tile.path.resolve() in selected_lookup]
    filtered.sort(key=lambda tile: selected_lookup[tile.path.resolve()])
    if not filtered:
        raise ValueError("Explicit image selection did not match any coordinate tiles")
    return filtered, source


def _resolve_detection_feature_model_path(requested: str | None = None) -> str:
    if requested:
        return requested
    if resolve_default_detection_model_path is not None:
        resolved = resolve_default_detection_model_path(Path(__file__).resolve().parents[1])
        if resolved:
            return resolved
    return ""


def _load_ultralytics_model(model_path: str):
    try:
        from ultralytics import YOLO
    except Exception as exc:  # pragma: no cover - depends on optional runtime package
        raise RuntimeError("ultralytics is required for detection-feature stitching.") from exc
    return YOLO(require_local_model(model_path))


def _name_from_detection_model(names: Any, cls_id: int) -> str:
    if isinstance(names, dict):
        return str(names.get(cls_id, cls_id))
    if isinstance(names, (list, tuple)) and 0 <= cls_id < len(names):
        return str(names[cls_id])
    return str(cls_id)


def _annotate_detection_features(image: np.ndarray, features: list[DetectionFeature]) -> np.ndarray:
    annotated = image.copy()
    palette = {
        0: (0, 255, 0),
        1: (0, 255, 255),
        2: (0, 0, 255),
    }
    for index, feature in enumerate(features, start=1):
        x1 = int(round(feature.cx - feature.width / 2.0))
        y1 = int(round(feature.cy - feature.height / 2.0))
        x2 = int(round(feature.cx + feature.width / 2.0))
        y2 = int(round(feature.cy + feature.height / 2.0))
        x1 = max(0, min(annotated.shape[1] - 1, x1))
        y1 = max(0, min(annotated.shape[0] - 1, y1))
        x2 = max(0, min(annotated.shape[1] - 1, x2))
        y2 = max(0, min(annotated.shape[0] - 1, y2))
        if x2 <= x1 or y2 <= y1:
            continue
        color = palette.get(feature.cls_id, (255, 255, 0))
        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
        label = f"{index}:{feature.label} {feature.conf:.2f}"
        cv2.putText(annotated, label, (x1, max(15, y1 - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)
    return annotated


def _detect_features_for_tile(
    model: Any,
    tile: CoordinateTile,
    confidence: float,
    max_features: int,
) -> tuple[list[DetectionFeature], np.ndarray]:
    image = read_image(tile.path)
    results = model.predict(source=image.copy(), conf=float(confidence), iou=0.45, max_det=int(max_features), verbose=False)
    if not results:
        return [], _annotate_detection_features(image, [])
    result = results[0]
    boxes = getattr(result, "boxes", None)
    names: Any = getattr(result, "names", {})
    if boxes is None:
        return [], _annotate_detection_features(image, [])

    features: list[DetectionFeature] = []
    for box in boxes:
        xyxy = box.xyxy[0].tolist()
        x1, y1, x2, y2 = [float(value) for value in xyxy]
        width = max(0.0, x2 - x1)
        height = max(0.0, y2 - y1)
        if width <= 2.0 or height <= 2.0:
            continue
        conf = float(box.conf[0]) if box.conf is not None else 0.0
        cls_id = int(box.cls[0]) if box.cls is not None else -1
        features.append(
            DetectionFeature(
                cx=(x1 + x2) / 2.0,
                cy=(y1 + y2) / 2.0,
                width=width,
                height=height,
                area=width * height,
                cls_id=cls_id,
                label=_name_from_detection_model(names, cls_id),
                conf=conf,
            )
        )
    features.sort(key=lambda item: item.conf, reverse=True)
    features = features[:max_features]
    return features, _annotate_detection_features(image, features)


def _prepare_detection_feature_cache(
    tiles: list[CoordinateTile],
    output_root: Path,
    model_path: str | None,
    confidence: float,
    max_features: int,
) -> tuple[dict[str, list[DetectionFeature]], list[dict[str, object]], str]:
    resolved_model_path = _resolve_detection_feature_model_path(model_path)
    model = _load_ultralytics_model(resolved_model_path)
    feature_root = output_root / "detection_features"
    feature_root.mkdir(parents=True, exist_ok=True)

    cache: dict[str, list[DetectionFeature]] = {}
    records: list[dict[str, object]] = []
    for tile in sorted(tiles, key=lambda item: (item.order, item.path.name)):
        features, annotated = _detect_features_for_tile(
            model=model,
            tile=tile,
            confidence=confidence,
            max_features=max_features,
        )
        json_path = feature_root / f"{tile.path.stem}_features.json"
        annotated_path = feature_root / f"{tile.path.stem}_features.jpg"
        save_image(annotated_path, annotated)
        save_json(
            json_path,
            {
                "image": tile.path.name,
                "coord": [tile.x, tile.y],
                "order": tile.order,
                "model_path": resolved_model_path,
                "confidence": confidence,
                "feature_count": len(features),
                "features": [_feature_to_payload(feature) for feature in features],
                "annotated_path": str(annotated_path.resolve()),
            },
        )
        cache[tile.path.name] = features
        records.append(
            {
                "image": tile.path.name,
                "coord": [tile.x, tile.y],
                "order": tile.order,
                "feature_count": len(features),
                "json_path": str(json_path.resolve()),
                "annotated_path": str(annotated_path.resolve()),
            }
        )
    return cache, records, resolved_model_path


def _load_existing_detection_feature_cache(
    tiles: list[CoordinateTile],
    input_dir: str | Path,
) -> tuple[dict[str, list[DetectionFeature]], list[dict[str, object]], str | None]:
    root = Path(input_dir)
    search_roots = [root / "detected", root / "detection_features"]
    cache: dict[str, list[DetectionFeature]] = {}
    records: list[dict[str, object]] = []
    model_path: str | None = None

    for tile in tiles:
        feature_path: Path | None = None
        for search_root in search_roots:
            candidate = search_root / f"{tile.path.stem}_features.json"
            if candidate.is_file():
                feature_path = candidate
                break
        if feature_path is None:
            continue

        with feature_path.open("r", encoding="utf-8-sig") as handle:
            payload = json.load(handle)
        raw_features = payload.get("features", [])
        if not isinstance(raw_features, list):
            raw_features = []
        features = [
            _feature_from_payload(item)
            for item in raw_features
            if isinstance(item, dict)
            and all(key in item for key in ("cx", "cy", "width", "height", "area", "cls_id", "label", "conf"))
        ]
        cache[tile.path.name] = features
        if model_path is None and payload.get("model_path"):
            model_path = str(payload.get("model_path"))
        records.append(
            {
                "image": tile.path.name,
                "coord": [tile.x, tile.y],
                "order": tile.order,
                "feature_count": len(features),
                "json_path": str(feature_path.resolve()),
                "annotated_path": str(payload.get("annotated_path", "")),
                "source": "capture_time",
            }
        )

    return cache, records, model_path


def _feather_weight_map(height: int, width: int) -> np.ndarray:
    mask = np.ones((height, width), dtype=np.uint8)
    mask[0, :] = 0
    mask[-1, :] = 0
    mask[:, 0] = 0
    mask[:, -1] = 0
    distance = cv2.distanceTransform(mask, cv2.DIST_L2, 3)
    if float(distance.max()) <= 0.0:
        return np.ones((height, width), dtype=np.float32)
    weight = distance / float(distance.max())
    return np.clip(weight, 0.05, 1.0).astype(np.float32)


def _preview_image(image: np.ndarray, max_long_side: int) -> np.ndarray:
    if max_long_side <= 0:
        return image
    height, width = image.shape[:2]
    long_side = max(height, width)
    if long_side <= max_long_side:
        return image
    scale = max_long_side / float(long_side)
    return cv2.resize(image, (int(round(width * scale)), int(round(height * scale))), interpolation=cv2.INTER_AREA)


def _build_intervals(origins: list[int], tile_extent: int) -> dict[int, tuple[int, int]]:
    if not origins:
        return {}
    ordered = sorted(origins)
    centers = [origin + (tile_extent / 2.0) for origin in ordered]
    boundaries = [ordered[0]]
    for index in range(len(centers) - 1):
        boundaries.append(int(round((centers[index] + centers[index + 1]) / 2.0)))
    boundaries.append(ordered[-1] + tile_extent)
    return {origin: (boundaries[index], boundaries[index + 1]) for index, origin in enumerate(ordered)}


def _dominant_coordinate_step(values: list[float]) -> float | None:
    unique_values = sorted({round(float(value), 6) for value in values})
    diffs = [round(abs(b - a), 6) for a, b in zip(unique_values, unique_values[1:]) if abs(b - a) > 1e-9]
    if not diffs:
        return None
    counts = Counter(diffs)
    return float(counts.most_common(1)[0][0])


def _compose_ownership_mosaic(
    placements: list[tuple[CoordinateTile, int, int]],
    tile_width: int,
    tile_height: int,
    canvas_width: int,
    canvas_height: int,
    row_keep_threshold: float,
) -> np.ndarray:
    rows: dict[int, list[tuple[CoordinateTile, int, int]]] = {}
    for tile, x, y in placements:
        rows.setdefault(y, []).append((tile, x, y))

    max_row_count = max(len(row_tiles) for row_tiles in rows.values())
    kept_rows = {y: row_tiles for y, row_tiles in rows.items() if len(row_tiles) >= max_row_count * row_keep_threshold}
    y_intervals = _build_intervals(list(kept_rows.keys()), tile_height)

    canvas = np.zeros((canvas_height, canvas_width, 3), dtype=np.uint8)
    for y, row_tiles in kept_rows.items():
        x_intervals = _build_intervals([x for _, x, _ in row_tiles], tile_width)
        y0, y1 = y_intervals[y]
        for tile, x, _ in sorted(row_tiles, key=lambda item: item[1]):
            x0, x1 = x_intervals[x]
            src_x0 = max(0, x0 - x)
            src_x1 = min(tile_width, x1 - x)
            src_y0 = max(0, y0 - y)
            src_y1 = min(tile_height, y1 - y)
            if src_x1 <= src_x0 or src_y1 <= src_y0:
                continue
            image = read_image(tile.path)
            crop = image[src_y0:src_y1, src_x0:src_x1]
            dst_x0 = x + src_x0
            dst_x1 = x + src_x1
            dst_y0 = y + src_y0
            dst_y1 = y + src_y1
            canvas[dst_y0:dst_y1, dst_x0:dst_x1] = crop
    return canvas


def _choose_strip_axis(tiles: list[CoordinateTile]) -> str:
    unique_x = {round(tile.x, 6) for tile in tiles}
    unique_y = {round(tile.y, 6) for tile in tiles}
    return "x" if len(unique_x) <= len(unique_y) else "y"


def _compose_strip_ownership_mosaic(
    placements: list[tuple[CoordinateTile, int, int]],
    tile_width: int,
    tile_height: int,
    canvas_width: int,
    canvas_height: int,
    strip_axis: str,
    output_root: Path,
) -> tuple[np.ndarray, list[dict[str, object]]]:
    if strip_axis not in {"x", "y"}:
        raise ValueError("strip_axis must be 'x' or 'y'")

    strip_root = output_root / "coordinate_strips"
    strip_root.mkdir(parents=True, exist_ok=True)
    groups: dict[float, list[tuple[CoordinateTile, int, int]]] = {}
    for tile, x, y in placements:
        key = tile.x if strip_axis == "x" else tile.y
        groups.setdefault(key, []).append((tile, x, y))

    strip_records: list[dict[str, object]] = []
    strip_images: list[tuple[float, Path, np.ndarray]] = []
    for strip_index, key in enumerate(sorted(groups)):
        group = groups[key]
        min_group_x = min(x for _tile, x, _y in group)
        min_group_y = min(y for _tile, _x, y in group)
        normalized = [(tile, x - min_group_x, y - min_group_y) for tile, x, y in group]
        strip_width = max(x + tile_width for _tile, x, _y in normalized)
        strip_height = max(y + tile_height for _tile, _x, y in normalized)
        strip_image = _compose_ownership_mosaic(
            placements=normalized,
            tile_width=tile_width,
            tile_height=tile_height,
            canvas_width=strip_width,
            canvas_height=strip_height,
            row_keep_threshold=0.0,
        )
        strip_path = strip_root / f"strip_{strip_axis}_{strip_index:03d}_{key:g}.png"
        save_image(strip_path, strip_image)
        strip_images.append((key, min_group_x, min_group_y, strip_image))
        strip_records.append(
            {
                "index": strip_index,
                "axis": strip_axis,
                "coordinate": key,
                "origin": [min_group_x, min_group_y],
                "size": [strip_width, strip_height],
                "tile_count": len(group),
                "path": str(strip_path.resolve()),
                "tiles": [tile.path.name for tile, _x, _y in group],
            }
        )

    canvas = np.zeros((canvas_height, canvas_width, 3), dtype=np.uint8)
    if strip_axis == "x":
        origins = [origin_x for _key, origin_x, _origin_y, _image in strip_images]
        intervals = _build_intervals(origins, tile_width)
        for _key, origin_x, origin_y, strip_image in strip_images:
            x0, x1 = intervals[origin_x]
            src_x0 = max(0, x0 - origin_x)
            src_x1 = min(strip_image.shape[1], x1 - origin_x)
            if src_x1 <= src_x0:
                continue
            dst_y1 = min(canvas_height, origin_y + strip_image.shape[0])
            dst_x0 = origin_x + src_x0
            dst_x1 = origin_x + src_x1
            canvas[origin_y:dst_y1, dst_x0:dst_x1] = strip_image[: dst_y1 - origin_y, src_x0:src_x1]
    else:
        origins = [origin_y for _key, _origin_x, origin_y, _image in strip_images]
        intervals = _build_intervals(origins, tile_height)
        for _key, origin_x, origin_y, strip_image in strip_images:
            y0, y1 = intervals[origin_y]
            src_y0 = max(0, y0 - origin_y)
            src_y1 = min(strip_image.shape[0], y1 - origin_y)
            if src_y1 <= src_y0:
                continue
            dst_x1 = min(canvas_width, origin_x + strip_image.shape[1])
            dst_y0 = origin_y + src_y0
            dst_y1 = origin_y + src_y1
            canvas[dst_y0:dst_y1, origin_x:dst_x1] = strip_image[src_y0:src_y1, : dst_x1 - origin_x]

    return canvas, strip_records


def _estimate_orb_pair_increment(ref_path: Path, mov_path: Path) -> tuple[float, float, dict[str, object]]:
    ref = cv2.imread(str(ref_path), cv2.IMREAD_GRAYSCALE)
    mov = cv2.imread(str(mov_path), cv2.IMREAD_GRAYSCALE)
    if ref is None or mov is None:
        raise ValueError(f"Failed to read pair for alignment: {ref_path.name}, {mov_path.name}")

    orb = cv2.ORB_create(8000)
    ref_keypoints, ref_desc = orb.detectAndCompute(ref, None)
    mov_keypoints, mov_desc = orb.detectAndCompute(mov, None)
    if ref_desc is None or mov_desc is None:
        raise ValueError(f"Not enough ORB features for pair: {ref_path.name} -> {mov_path.name}")

    matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
    raw_matches = matcher.knnMatch(ref_desc, mov_desc, k=2)
    good_matches = []
    for pair in raw_matches:
        if len(pair) < 2:
            continue
        match, next_match = pair
        if match.distance < 0.75 * next_match.distance:
            good_matches.append(match)
    if len(good_matches) < 8:
        raise ValueError(f"Not enough ORB matches for pair: {ref_path.name} -> {mov_path.name}")

    ref_points = np.float32([ref_keypoints[match.queryIdx].pt for match in good_matches]).reshape(-1, 1, 2)
    mov_points = np.float32([mov_keypoints[match.trainIdx].pt for match in good_matches]).reshape(-1, 1, 2)
    matrix, inliers = cv2.estimateAffinePartial2D(
        ref_points,
        mov_points,
        method=cv2.RANSAC,
        ransacReprojThreshold=5,
        maxIters=5000,
        confidence=0.99,
    )
    if matrix is None:
        raise ValueError(f"ORB affine estimation failed for pair: {ref_path.name} -> {mov_path.name}")

    inlier_count = int(inliers.sum()) if inliers is not None else 0
    dx = float(-matrix[0, 2])
    dy = float(-matrix[1, 2])
    return dx, dy, {
        "ref": ref_path.name,
        "mov": mov_path.name,
        "good_matches": len(good_matches),
        "inliers": inlier_count,
        "increment": [dx, dy],
    }


def _blend_positioned_images(
    positioned: list[tuple[Path, int, int]],
    canvas_width: int,
    canvas_height: int,
) -> np.ndarray:
    accum = np.zeros((canvas_height, canvas_width, 3), dtype=np.float32)
    weight_accum = np.zeros((canvas_height, canvas_width), dtype=np.float32)
    for path, x, y in positioned:
        image = read_image(path)
        height, width = image.shape[:2]
        weight = _feather_weight_map(height, width)
        accum[y : y + height, x : x + width] += image.astype(np.float32) * weight[:, :, None]
        weight_accum[y : y + height, x : x + width] += weight
    return np.clip(accum / np.maximum(weight_accum[:, :, None], 1e-6), 0, 255).astype(np.uint8)


def _flat_field_correct_image(image: np.ndarray) -> np.ndarray:
    image_f32 = image.astype(np.float32)
    height, width = image.shape[:2]
    sigma = max(24.0, min(height, width) * 0.08)
    if image.ndim == 2:
        background = cv2.GaussianBlur(image_f32, (0, 0), sigma)
        corrected = image_f32 / np.maximum(background, 1.0) * float(np.mean(background))
    else:
        corrected_channels = []
        for channel in cv2.split(image_f32):
            background = cv2.GaussianBlur(channel, (0, 0), sigma)
            corrected_channels.append(channel / np.maximum(background, 1.0) * float(np.mean(background)))
        corrected = cv2.merge(corrected_channels)
    return np.clip(corrected, 0, 255).astype(np.uint8)


def _read_alignment_gray(path: Path) -> np.ndarray:
    gray = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if gray is None:
        raise ValueError(f"Failed to read image for alignment: {path}")
    return _flat_field_correct_image(gray)


def _blend_float_positioned_tiles(
    positioned: list[tuple[CoordinateTile, float, float]],
    tile_width: int,
    tile_height: int,
) -> np.ndarray:
    min_x = min(x for _tile, x, _y in positioned)
    min_y = min(y for _tile, _x, y in positioned)
    normalized = [(tile, x - min_x, y - min_y) for tile, x, y in positioned]
    canvas_width = int(np.ceil(max(x + tile_width for _tile, x, _y in normalized)))
    canvas_height = int(np.ceil(max(y + tile_height for _tile, _x, y in normalized)))
    accum = np.zeros((canvas_height, canvas_width, 3), dtype=np.float32)
    weight_accum = np.zeros((canvas_height, canvas_width), dtype=np.float32)
    base_weight = _feather_weight_map(tile_height, tile_width)
    loaded_images: list[tuple[CoordinateTile, float, float, np.ndarray, float]] = []
    for tile, x, y in normalized:
        image = _flat_field_correct_image(read_image(tile.path))
        if image.shape[1] != tile_width or image.shape[0] != tile_height:
            image = cv2.resize(image, (tile_width, tile_height), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        loaded_images.append((tile, x, y, image, float(np.median(gray))))
    target_luma = float(np.median([luma for *_prefix, luma in loaded_images])) if loaded_images else 128.0

    for _tile, x, y, image, luma in loaded_images:
        gain = float(np.clip(target_luma / max(luma, 1.0), 0.75, 1.35))
        image = np.clip(image.astype(np.float32) * gain, 0, 255).astype(np.uint8)
        matrix = np.array([[1.0, 0.0, float(x)], [0.0, 1.0, float(y)]], dtype=np.float32)
        warped_image = cv2.warpAffine(
            image.astype(np.float32),
            matrix,
            (canvas_width, canvas_height),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=0,
        )
        warped_weight = cv2.warpAffine(
            base_weight,
            matrix,
            (canvas_width, canvas_height),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=0,
        )
        accum += warped_image * warped_weight[:, :, None]
        weight_accum += warped_weight

    return np.clip(accum / np.maximum(weight_accum[:, :, None], 1e-6), 0, 255).astype(np.uint8)


def _compose_positioned_ownership(
    positioned: list[tuple[Path, int, int]],
    canvas_width: int,
    canvas_height: int,
) -> np.ndarray:
    canvas = np.zeros((canvas_height, canvas_width, 3), dtype=np.uint8)
    for path, x, y in positioned:
        image = read_image(path)
        height, width = image.shape[:2]
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        mask = gray > 5
        roi = canvas[y : y + height, x : x + width]
        roi[mask] = image[mask]
    return canvas


def _save_pair_alignment_preview(
    ref_path: Path,
    mov_path: Path,
    dx: float,
    dy: float,
    output_path: Path,
) -> Path:
    ref_image = read_image(ref_path)
    mov_image = read_image(mov_path)
    ref_height, ref_width = ref_image.shape[:2]
    mov_height, mov_width = mov_image.shape[:2]
    raw_positions = [(ref_path, 0, 0), (mov_path, int(round(dx)), int(round(dy)))]
    min_x = min(x for _path, x, _y in raw_positions)
    min_y = min(y for _path, _x, y in raw_positions)
    positions = [(path, x - min_x, y - min_y) for path, x, y in raw_positions]
    canvas_width = max(
        x + (ref_width if path == ref_path else mov_width)
        for path, x, _y in positions
    )
    canvas_height = max(
        y + (ref_height if path == ref_path else mov_height)
        for path, _x, y in positions
    )
    preview = _blend_positioned_images(positions, canvas_width=canvas_width, canvas_height=canvas_height)
    return save_image(output_path, preview)


def _repair_axis_increments(
    increments: list[tuple[float, float]],
    strip_axis: str,
) -> tuple[list[tuple[float, float]], list[dict[str, object]]]:
    if not increments:
        return increments, []

    primary_values = [abs(dy) if strip_axis == "x" else abs(dx) for dx, dy in increments]
    candidates = sorted(value for value in primary_values if value >= 80.0)
    if not candidates:
        return increments, []

    typical_primary = float(candidates[len(candidates) // 2])
    repaired = list(increments)
    repair_records: list[dict[str, object]] = []
    for index, ((dx, dy), primary) in enumerate(zip(increments, primary_values)):
        if primary >= max(60.0, typical_primary * 0.35):
            continue

        neighbor_indexes = [item for item in (index - 1, index + 1) if 0 <= item < len(increments)]
        neighbor_dx = [increments[item][0] for item in neighbor_indexes if primary_values[item] >= typical_primary * 0.35]
        neighbor_dy = [increments[item][1] for item in neighbor_indexes if primary_values[item] >= typical_primary * 0.35]
        if not neighbor_dx or not neighbor_dy:
            continue

        replacement = (float(np.median(neighbor_dx)), float(np.median(neighbor_dy)))
        repaired[index] = replacement
        repair_records.append(
            {
                "index": index,
                "reason": "near_zero_increment",
                "original": [dx, dy],
                "replacement": [replacement[0], replacement[1]],
                "typical_primary": typical_primary,
            }
        )

    return repaired, repair_records


def _overlap_rois(
    ref: np.ndarray,
    mov: np.ndarray,
    dx: int,
    dy: int,
) -> tuple[np.ndarray, np.ndarray] | None:
    height, width = ref.shape[:2]
    mov_height, mov_width = mov.shape[:2]
    overlap_x0 = max(0, dx)
    overlap_y0 = max(0, dy)
    overlap_x1 = min(width, dx + mov_width)
    overlap_y1 = min(height, dy + mov_height)
    if overlap_x1 <= overlap_x0 or overlap_y1 <= overlap_y0:
        return None

    ref_roi = ref[overlap_y0:overlap_y1, overlap_x0:overlap_x1]
    mov_roi = mov[overlap_y0 - dy : overlap_y1 - dy, overlap_x0 - dx : overlap_x1 - dx]
    return ref_roi, mov_roi


def _normalized_correlation_score(ref_roi: np.ndarray, mov_roi: np.ndarray) -> float:
    ref_values = ref_roi.astype(np.float32) - float(ref_roi.mean())
    mov_values = mov_roi.astype(np.float32) - float(mov_roi.mean())
    denominator = float(np.linalg.norm(ref_values) * np.linalg.norm(mov_values))
    if denominator <= 1e-6:
        return -1.0
    return float((ref_values * mov_values).sum() / denominator)


def _estimate_constrained_axis_increment(
    ref_path: Path,
    mov_path: Path,
    strip_axis: str,
    typical_primary: float,
    tile_width: int,
    tile_height: int,
) -> tuple[float, float, dict[str, object]]:
    ref = _read_alignment_gray(ref_path)
    mov = _read_alignment_gray(mov_path)

    scale = 0.25
    ref_small = cv2.resize(ref, (0, 0), fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    mov_small = cv2.resize(mov, (0, 0), fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    ref_edge = cv2.Laplacian(cv2.GaussianBlur(ref_small, (0, 0), 1.0), cv2.CV_32F, ksize=3)
    mov_edge = cv2.Laplacian(cv2.GaussianBlur(mov_small, (0, 0), 1.0), cv2.CV_32F, ksize=3)

    primary_min = int(round(max(80.0, typical_primary * 0.45) * scale))
    primary_max = int(round(min(max(tile_width, tile_height) * 0.9, typical_primary * 1.65) * scale))
    secondary_limit = int(round((tile_width if strip_axis == "x" else tile_height) * 0.22 * scale))
    min_overlap_width = max(20, int(round(tile_width * 0.18 * scale)))
    min_overlap_height = max(20, int(round(tile_height * 0.18 * scale)))

    best_score = -1.0
    best_shift = (0, 0)
    for primary in range(primary_min, primary_max + 1):
        for secondary in range(-secondary_limit, secondary_limit + 1):
            dx, dy = (secondary, primary) if strip_axis == "x" else (primary, secondary)
            rois = _overlap_rois(ref_edge, mov_edge, dx, dy)
            if rois is None:
                continue
            ref_roi, mov_roi = rois
            if ref_roi.shape[1] < min_overlap_width or ref_roi.shape[0] < min_overlap_height:
                continue
            score = _normalized_correlation_score(ref_roi, mov_roi)
            if score > best_score:
                best_score = score
                best_shift = (dx, dy)

    dx = float(best_shift[0] / scale)
    dy = float(best_shift[1] / scale)
    return dx, dy, {
        "constrained_score": best_score,
        "search_primary_range": [float(primary_min / scale), float(primary_max / scale)],
        "search_secondary_range": [float(-secondary_limit / scale), float(secondary_limit / scale)],
    }


def _expected_canvas_increment(
    previous: CoordinateTile,
    current: CoordinateTile,
    x_pixels_per_unit: float,
    y_pixels_per_unit: float,
    tile_scale: float,
) -> tuple[float, float]:
    expected_dx = (current.x - previous.x) * x_pixels_per_unit * tile_scale
    expected_dy = (previous.y - current.y) * y_pixels_per_unit * tile_scale
    return float(expected_dx), float(expected_dy)


def _estimate_expected_constrained_increment(
    ref_path: Path,
    mov_path: Path,
    expected_dx: float,
    expected_dy: float,
    tile_width: int,
    tile_height: int,
) -> tuple[float, float, dict[str, object]]:
    ref = cv2.imread(str(ref_path), cv2.IMREAD_GRAYSCALE)
    mov = cv2.imread(str(mov_path), cv2.IMREAD_GRAYSCALE)
    if ref is None or mov is None:
        raise ValueError(f"Failed to read pair for constrained alignment: {ref_path.name}, {mov_path.name}")

    max_side = max(ref.shape[:2] + mov.shape[:2])
    scale = 0.25 if max_side <= 5000 else 0.12
    ref_small = cv2.resize(ref, (0, 0), fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    mov_small = cv2.resize(mov, (0, 0), fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    ref_edge = cv2.Laplacian(cv2.GaussianBlur(ref_small, (0, 0), 1.0), cv2.CV_32F, ksize=3)
    mov_edge = cv2.Laplacian(cv2.GaussianBlur(mov_small, (0, 0), 1.0), cv2.CV_32F, ksize=3)

    primary_is_y = abs(expected_dy) >= abs(expected_dx)
    primary_expected = expected_dy if primary_is_y else expected_dx
    secondary_expected = expected_dx if primary_is_y else expected_dy
    primary_extent = tile_height if primary_is_y else tile_width
    secondary_extent = tile_width if primary_is_y else tile_height
    primary_radius = min(primary_extent * 0.28, max(90.0, abs(primary_expected) * 0.22))
    secondary_radius = min(secondary_extent * 0.06, max(24.0, secondary_extent * 0.035))

    primary_center = int(round(primary_expected * scale))
    secondary_center = int(round(secondary_expected * scale))
    primary_radius_scaled = max(1, int(round(primary_radius * scale)))
    secondary_radius_scaled = max(1, int(round(secondary_radius * scale)))
    min_overlap_width = max(16, int(round(tile_width * 0.08 * scale)))
    min_overlap_height = max(16, int(round(tile_height * 0.08 * scale)))

    best_score = -1.0
    best_similarity = -1.0
    best_shift = (int(round(expected_dx * scale)), int(round(expected_dy * scale)))
    for primary in range(primary_center - primary_radius_scaled, primary_center + primary_radius_scaled + 1):
        # Keep the movement direction constrained by the coordinate direction.
        if primary_expected > 0 and primary <= 0:
            continue
        if primary_expected < 0 and primary >= 0:
            continue
        for secondary in range(secondary_center - secondary_radius_scaled, secondary_center + secondary_radius_scaled + 1):
            dx, dy = (secondary, primary) if primary_is_y else (primary, secondary)
            rois = _overlap_rois(ref_edge, mov_edge, dx, dy)
            if rois is None:
                continue
            ref_roi, mov_roi = rois
            if ref_roi.shape[1] < min_overlap_width or ref_roi.shape[0] < min_overlap_height:
                continue
            similarity = _normalized_correlation_score(ref_roi, mov_roi)
            primary_penalty = ((primary - primary_center) / max(primary_radius_scaled, 1)) ** 2
            secondary_penalty = ((secondary - secondary_center) / max(secondary_radius_scaled, 1)) ** 2
            score = similarity - 0.04 * primary_penalty - 0.08 * secondary_penalty
            if score > best_score:
                best_score = score
                best_similarity = similarity
                best_shift = (dx, dy)

    dx = float(best_shift[0] / scale)
    dy = float(best_shift[1] / scale)
    fallback_used = False
    if best_similarity < 0.02:
        dx = float(expected_dx)
        dy = float(expected_dy)
        fallback_used = True
    refine_record: dict[str, object] = {}
    if not fallback_used:
        refined = _refine_increment_with_overlap_phase(
            ref,
            mov,
            coarse_dx=dx,
            coarse_dy=dy,
            tile_width=tile_width,
            tile_height=tile_height,
        )
        if refined is not None:
            dx, dy, refine_record = refined

    if "ecc_score" in refine_record:
        method = "content_ncc_ecc_refined"
    elif refine_record:
        method = "content_ncc_phase_refined"
    else:
        method = "coordinate_constrained_correlation"
    return dx, dy, {
        "method": method,
        "expected_increment": [expected_dx, expected_dy],
        "increment": [dx, dy],
        "constrained_score": best_score,
        "similarity": best_similarity,
        "fallback_to_expected": fallback_used,
        "subpixel": bool(refine_record),
        "search_primary_range": [
            float((primary_center - primary_radius_scaled) / scale),
            float((primary_center + primary_radius_scaled) / scale),
        ],
        "search_secondary_range": [
            float((secondary_center - secondary_radius_scaled) / scale),
            float((secondary_center + secondary_radius_scaled) / scale),
        ],
        **refine_record,
    }


def _phase_correlation_input(image: np.ndarray) -> np.ndarray:
    if image.ndim == 3 and image.shape[2] == 1:
        image = image[:, :, 0]
    elif image.ndim == 3:
        image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    image_f32 = image.astype(np.float32)
    blur_sigma = max(1.0, min(image.shape[:2]) * 0.025)
    low_frequency = cv2.GaussianBlur(image_f32, (0, 0), blur_sigma)
    high_pass = image_f32 - low_frequency
    std = float(high_pass.std())
    if std <= 1e-6:
        return high_pass
    return (high_pass - float(high_pass.mean())) / std


def _estimate_phase_overlap_increment(
    ref_path: Path,
    mov_path: Path,
    expected_dx: float,
    expected_dy: float,
    tile_width: int,
    tile_height: int,
) -> tuple[float, float, dict[str, object]] | None:
    ref = _read_alignment_gray(ref_path)
    mov = _read_alignment_gray(mov_path)

    expected_dx_i = int(round(expected_dx))
    expected_dy_i = int(round(expected_dy))
    rois = _overlap_rois(ref, mov, expected_dx_i, expected_dy_i)
    if rois is None:
        return None
    ref_roi, mov_roi = rois
    min_overlap_width = max(64, int(round(tile_width * 0.08)))
    min_overlap_height = max(64, int(round(tile_height * 0.08)))
    if ref_roi.shape[1] < min_overlap_width or ref_roi.shape[0] < min_overlap_height:
        return None

    scale = 1.0
    max_side = max(ref_roi.shape[:2])
    if max_side > 1200:
        scale = 1200.0 / float(max_side)
        ref_roi = cv2.resize(ref_roi, (0, 0), fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        mov_roi = cv2.resize(mov_roi, (0, 0), fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

    ref_phase = _phase_correlation_input(ref_roi)
    mov_phase = _phase_correlation_input(mov_roi)
    if ref_phase.shape[0] < 8 or ref_phase.shape[1] < 8:
        return None
    window = cv2.createHanningWindow((ref_phase.shape[1], ref_phase.shape[0]), cv2.CV_32F)
    residual_shift, response = cv2.phaseCorrelate(ref_phase * window, mov_phase * window)
    residual_x = float(residual_shift[0] / scale)
    residual_y = float(residual_shift[1] / scale)

    # phaseCorrelate returns the shift that aligns the moving overlap ROI to the
    # reference ROI. Since the ROI was cut at the stage-based expected shift, the
    # true tile placement is expected minus that residual.
    dx = float(expected_dx - residual_x)
    dy = float(expected_dy - residual_y)
    primary_is_y = abs(expected_dy) >= abs(expected_dx)
    primary_residual = abs(residual_y if primary_is_y else residual_x)
    secondary_residual = abs(residual_x if primary_is_y else residual_y)
    primary_limit = max(160.0, (tile_height if primary_is_y else tile_width) * 0.35)
    secondary_extent = tile_width if primary_is_y else tile_height
    secondary_limit = max(16.0, min(45.0, secondary_extent * 0.035))
    rejected = (
        float(response) < 0.015
        or primary_residual > primary_limit
        or secondary_residual > secondary_limit
    )
    if rejected:
        return None
    refined = _refine_increment_with_overlap_phase(
        ref,
        mov,
        coarse_dx=dx,
        coarse_dy=dy,
        tile_width=tile_width,
        tile_height=tile_height,
    )
    refine_record: dict[str, object] = {}
    if refined is not None:
        dx, dy, refine_record = refined
    method = "phase_ecc_refined" if "ecc_score" in refine_record else ("phase_overlap_subpixel_refined" if refine_record else "phase_overlap_subpixel")

    return dx, dy, {
        "method": method,
        "expected_increment": [expected_dx, expected_dy],
        "increment": [dx, dy],
        "phase_residual": [residual_x, residual_y],
        "phase_response": float(response),
        "overlap_shape": [int(ref_roi.shape[1]), int(ref_roi.shape[0])],
        "subpixel": True,
        **refine_record,
    }


def _refine_increment_with_overlap_phase(
    ref: np.ndarray,
    mov: np.ndarray,
    coarse_dx: float,
    coarse_dy: float,
    tile_width: int,
    tile_height: int,
) -> tuple[float, float, dict[str, object]] | None:
    rois = _overlap_rois(ref, mov, int(round(coarse_dx)), int(round(coarse_dy)))
    if rois is None:
        return None
    ref_roi, mov_roi = rois
    min_overlap_width = max(64, int(round(tile_width * 0.08)))
    min_overlap_height = max(64, int(round(tile_height * 0.08)))
    if ref_roi.shape[1] < min_overlap_width or ref_roi.shape[0] < min_overlap_height:
        return None

    ref_ecc = _phase_correlation_input(ref_roi).astype(np.float32)
    mov_ecc = _phase_correlation_input(mov_roi).astype(np.float32)
    if ref_ecc.shape[0] < 16 or ref_ecc.shape[1] < 16:
        return None
    warp = np.eye(2, 3, dtype=np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 80, 1e-5)
    try:
        ecc_score, warp = cv2.findTransformECC(
            ref_ecc,
            mov_ecc,
            warp,
            cv2.MOTION_TRANSLATION,
            criteria,
            None,
            3,
        )
    except cv2.error:
        ecc_score = -1.0
    if ecc_score > 0.02:
        residual_x = float(warp[0, 2])
        residual_y = float(warp[1, 2])
        primary_is_y = abs(coarse_dy) >= abs(coarse_dx)
        secondary_residual = abs(residual_x if primary_is_y else residual_y)
        if abs(residual_x) <= 32.0 and abs(residual_y) <= 32.0 and secondary_residual <= 16.0:
            return float(coarse_dx - residual_x), float(coarse_dy - residual_y), {
                "ecc_residual": [residual_x, residual_y],
                "ecc_score": float(ecc_score),
                "ecc_overlap_shape": [int(ref_roi.shape[1]), int(ref_roi.shape[0])],
                "ecc_motion": "translation",
            }

    ref_phase = _phase_correlation_input(ref_roi)
    mov_phase = _phase_correlation_input(mov_roi)
    if ref_phase.shape[0] < 8 or ref_phase.shape[1] < 8:
        return None
    window = cv2.createHanningWindow((ref_phase.shape[1], ref_phase.shape[0]), cv2.CV_32F)
    residual_shift, response = cv2.phaseCorrelate(ref_phase * window, mov_phase * window)
    residual_x = float(residual_shift[0])
    residual_y = float(residual_shift[1])
    primary_is_y = abs(coarse_dy) >= abs(coarse_dx)
    secondary_residual = abs(residual_x if primary_is_y else residual_y)
    if float(response) < 0.01 or abs(residual_x) > 24.0 or abs(residual_y) > 24.0:
        return None
    if secondary_residual > 10.0:
        return None
    return float(coarse_dx - residual_x), float(coarse_dy - residual_y), {
        "phase_refine_residual": [residual_x, residual_y],
        "phase_refine_response": float(response),
        "phase_refine_overlap_shape": [int(ref_roi.shape[1]), int(ref_roi.shape[0])],
    }


def _is_rbc_feature(feature: DetectionFeature) -> bool:
    label = feature.label.lower()
    return (
        "rbc" in label
        or "red" in label
        or "eryth" in label
        or feature.cls_id == 1
    ) and feature.width >= 20.0 and feature.height >= 20.0


def _rbc_constellation_descriptors(
    features: list[DetectionFeature],
    k_neighbors: int = 6,
) -> list[tuple[DetectionFeature, np.ndarray]]:
    rbc_features = [feature for feature in features if _is_rbc_feature(feature)]
    if len(rbc_features) < 4:
        return []

    centers = np.asarray([[feature.cx, feature.cy] for feature in rbc_features], dtype=np.float32)
    descriptors: list[tuple[DetectionFeature, np.ndarray]] = []
    for index, feature in enumerate(rbc_features):
        deltas = centers - centers[index]
        distances = np.linalg.norm(deltas, axis=1)
        order = [item for item in np.argsort(distances).tolist() if item != index][:k_neighbors]
        if len(order) < 3:
            continue
        neighbor_vectors = deltas[order]
        neighbor_distances = distances[order]
        local_scale = float(np.median(neighbor_distances))
        if local_scale <= 1e-6:
            continue
        normalized_vectors = neighbor_vectors / local_scale
        normalized_distances = (neighbor_distances / local_scale).reshape(-1, 1)
        # Translation-invariant local geometry: nearest-neighbor vectors plus
        # their normalized radii. RBCs are repetitive, so a single point is not
        # distinctive; the local constellation is more stable.
        descriptor = np.hstack([normalized_vectors, normalized_distances]).astype(np.float32).reshape(-1)
        descriptors.append((feature, descriptor))
    return descriptors


def _descriptor_distance(left: np.ndarray, right: np.ndarray) -> float:
    length = min(left.size, right.size)
    if length == 0:
        return float("inf")
    return float(np.mean(np.abs(left[:length] - right[:length])))


def _estimate_rbc_constellation_increment(
    ref_path: Path,
    mov_path: Path,
    ref_features: list[DetectionFeature],
    mov_features: list[DetectionFeature],
    expected_dx: float,
    expected_dy: float,
    tile_width: int,
    tile_height: int,
    min_matches: int,
) -> tuple[float, float, dict[str, object]] | None:
    ref_descriptors = _rbc_constellation_descriptors(ref_features)
    mov_descriptors = _rbc_constellation_descriptors(mov_features)
    if len(ref_descriptors) < max(4, min_matches) or len(mov_descriptors) < max(4, min_matches):
        return None

    primary_is_y = abs(expected_dy) >= abs(expected_dx)
    primary_radius = max(120.0, min((tile_height if primary_is_y else tile_width) * 0.35, abs(expected_dy if primary_is_y else expected_dx) * 0.30))
    secondary_radius = max(60.0, min((tile_width if primary_is_y else tile_height) * 0.16, 180.0))
    votes: list[tuple[float, float, float, DetectionFeature, DetectionFeature, float]] = []
    for ref_feature, ref_descriptor in ref_descriptors:
        for mov_feature, mov_descriptor in mov_descriptors:
            area_ratio = min(ref_feature.area, mov_feature.area) / max(ref_feature.area, mov_feature.area, 1.0)
            if area_ratio < 0.35:
                continue
            dx = ref_feature.cx - mov_feature.cx
            dy = ref_feature.cy - mov_feature.cy
            primary_delta = abs((dy if primary_is_y else dx) - (expected_dy if primary_is_y else expected_dx))
            secondary_delta = abs((dx if primary_is_y else dy) - (expected_dx if primary_is_y else expected_dy))
            if primary_delta > primary_radius or secondary_delta > secondary_radius:
                continue
            descriptor_error = _descriptor_distance(ref_descriptor, mov_descriptor)
            if descriptor_error > 0.55:
                continue
            stage_score = 1.0 - min(1.0, primary_delta / max(primary_radius, 1.0)) * 0.45 - min(1.0, secondary_delta / max(secondary_radius, 1.0)) * 0.25
            score = stage_score + (1.0 - min(1.0, descriptor_error / 0.55)) * 0.70 + area_ratio * 0.25 + min(ref_feature.conf, mov_feature.conf) * 0.20
            votes.append((score, dx, dy, ref_feature, mov_feature, descriptor_error))

    if len(votes) < max(4, min_matches):
        return None

    bin_size = 24.0
    bins: dict[tuple[int, int], list[tuple[float, float, float, DetectionFeature, DetectionFeature, float]]] = {}
    for vote in votes:
        _score, dx, dy, _ref_feature, _mov_feature, _descriptor_error = vote
        key = (int(round(dx / bin_size)), int(round(dy / bin_size)))
        bins.setdefault(key, []).append(vote)
    best_cluster = max(
        bins.values(),
        key=lambda cluster: (len(cluster), float(sum(item[0] for item in cluster))),
    )
    if len(best_cluster) < max(3, min_matches):
        return None

    dx_values = np.asarray([item[1] for item in best_cluster], dtype=np.float32)
    dy_values = np.asarray([item[2] for item in best_cluster], dtype=np.float32)
    weights = np.asarray([item[0] for item in best_cluster], dtype=np.float32)
    dx = float(np.average(dx_values, weights=weights))
    dy = float(np.average(dy_values, weights=weights))
    dx_mad = float(np.median(np.abs(dx_values - dx)))
    dy_mad = float(np.median(np.abs(dy_values - dy)))
    if dx_mad > 45.0 or dy_mad > 45.0:
        return None

    ref = _read_alignment_gray(ref_path)
    mov = _read_alignment_gray(mov_path)
    refine_record: dict[str, object] = {}
    refined = _refine_increment_with_overlap_phase(
        ref,
        mov,
        coarse_dx=dx,
        coarse_dy=dy,
        tile_width=tile_width,
        tile_height=tile_height,
    )
    if refined is not None:
        dx, dy, refine_record = refined

    return dx, dy, {
        "method": "rbc_constellation_ecc" if "ecc_score" in refine_record else ("rbc_constellation_phase" if refine_record else "rbc_constellation"),
        "expected_increment": [expected_dx, expected_dy],
        "increment": [dx, dy],
        "rbc_ref_count": len(ref_descriptors),
        "rbc_mov_count": len(mov_descriptors),
        "constellation_votes": len(votes),
        "constellation_inliers": len(best_cluster),
        "dx_mad": dx_mad,
        "dy_mad": dy_mad,
        "search_primary_radius": primary_radius,
        "search_secondary_radius": secondary_radius,
        "subpixel": bool(refine_record),
        "sample_matches": [
            {
                "score": float(score),
                "descriptor_error": float(descriptor_error),
                "dx": float(match_dx),
                "dy": float(match_dy),
                "ref": {"cx": ref_feature.cx, "cy": ref_feature.cy, "conf": ref_feature.conf},
                "mov": {"cx": mov_feature.cx, "cy": mov_feature.cy, "conf": mov_feature.conf},
            }
            for score, match_dx, match_dy, ref_feature, mov_feature, descriptor_error in sorted(best_cluster, key=lambda item: item[0], reverse=True)[:10]
        ],
        **refine_record,
    }


def _rbc_density_map(
    features: list[DetectionFeature],
    tile_width: int,
    tile_height: int,
) -> np.ndarray:
    density = np.zeros((tile_height, tile_width), dtype=np.float32)
    for feature in features:
        if not _is_rbc_feature(feature):
            continue
        radius = max(8, int(round((feature.width + feature.height) * 0.055)))
        center = (int(round(feature.cx)), int(round(feature.cy)))
        cv2.circle(density, center, radius, float(max(feature.conf, 0.1)), -1)
    if float(density.max()) <= 0.0:
        return density
    density = cv2.GaussianBlur(density, (0, 0), max(6.0, min(tile_width, tile_height) * 0.012))
    return density / max(float(density.max()), 1e-6)


def _estimate_rbc_density_increment(
    ref_path: Path,
    mov_path: Path,
    ref_features: list[DetectionFeature],
    mov_features: list[DetectionFeature],
    expected_dx: float,
    expected_dy: float,
    tile_width: int,
    tile_height: int,
) -> tuple[float, float, dict[str, object]] | None:
    ref_rbc_count = sum(1 for feature in ref_features if _is_rbc_feature(feature))
    mov_rbc_count = sum(1 for feature in mov_features if _is_rbc_feature(feature))
    if ref_rbc_count < 4 or mov_rbc_count < 4:
        return None

    ref_density = _rbc_density_map(ref_features, tile_width=tile_width, tile_height=tile_height)
    mov_density = _rbc_density_map(mov_features, tile_width=tile_width, tile_height=tile_height)
    primary_is_y = abs(expected_dy) >= abs(expected_dx)
    primary_expected = expected_dy if primary_is_y else expected_dx
    secondary_expected = expected_dx if primary_is_y else expected_dy
    primary_radius = min((tile_height if primary_is_y else tile_width) * 0.30, max(120.0, abs(primary_expected) * 0.24))
    secondary_radius = min((tile_width if primary_is_y else tile_height) * 0.14, max(60.0, (tile_width if primary_is_y else tile_height) * 0.06))
    primary_center = int(round(primary_expected))
    secondary_center = int(round(secondary_expected))
    primary_range = range(int(round(primary_center - primary_radius)), int(round(primary_center + primary_radius)) + 1, 4)
    secondary_range = range(int(round(secondary_center - secondary_radius)), int(round(secondary_center + secondary_radius)) + 1, 4)
    min_overlap_width = max(80, int(round(tile_width * 0.08)))
    min_overlap_height = max(80, int(round(tile_height * 0.08)))

    best_score = -1.0
    best_shift = (float(expected_dx), float(expected_dy))
    for primary in primary_range:
        if primary_expected > 0 and primary <= 0:
            continue
        if primary_expected < 0 and primary >= 0:
            continue
        for secondary in secondary_range:
            dx, dy = (secondary, primary) if primary_is_y else (primary, secondary)
            rois = _overlap_rois(ref_density, mov_density, dx, dy)
            if rois is None:
                continue
            ref_roi, mov_roi = rois
            if ref_roi.shape[1] < min_overlap_width or ref_roi.shape[0] < min_overlap_height:
                continue
            score = _normalized_correlation_score(ref_roi, mov_roi)
            if score > best_score:
                best_score = score
                best_shift = (float(dx), float(dy))

    if best_score < 0.06:
        return None

    dx, dy = best_shift
    refine_record: dict[str, object] = {}
    refined = _refine_increment_with_overlap_phase(
        ref_density,
        mov_density,
        coarse_dx=dx,
        coarse_dy=dy,
        tile_width=tile_width,
        tile_height=tile_height,
    )
    if refined is not None:
        dx, dy, refine_record = refined

    return dx, dy, {
        "method": "rbc_density_ecc" if "ecc_score" in refine_record else ("rbc_density_phase" if refine_record else "rbc_density_ncc"),
        "expected_increment": [expected_dx, expected_dy],
        "increment": [dx, dy],
        "rbc_ref_count": ref_rbc_count,
        "rbc_mov_count": mov_rbc_count,
        "rbc_density_score": float(best_score),
        "search_primary_radius": float(primary_radius),
        "search_secondary_radius": float(secondary_radius),
        "subpixel": bool(refine_record),
        **refine_record,
    }


def _estimate_detection_feature_increment(
    ref_features: list[DetectionFeature],
    mov_features: list[DetectionFeature],
    expected_dx: float,
    expected_dy: float,
    tile_width: int,
    tile_height: int,
    min_matches: int,
) -> tuple[float, float, dict[str, object]] | None:
    if not ref_features or not mov_features:
        return None

    primary_is_y = abs(expected_dy) >= abs(expected_dx)
    primary_radius = max(90.0, min((tile_height if primary_is_y else tile_width) * 0.22, abs(expected_dy if primary_is_y else expected_dx) * 0.24))
    secondary_radius = max(45.0, min((tile_width if primary_is_y else tile_height) * 0.12, 160.0))
    candidates: list[tuple[float, float, float, DetectionFeature, DetectionFeature]] = []
    for ref_feature in ref_features:
        for mov_feature in mov_features:
            if ref_feature.cls_id != mov_feature.cls_id:
                continue
            area_ratio = min(ref_feature.area, mov_feature.area) / max(ref_feature.area, mov_feature.area, 1.0)
            if area_ratio < 0.45:
                continue
            dx = ref_feature.cx - mov_feature.cx
            dy = ref_feature.cy - mov_feature.cy
            primary_delta = abs((dy if primary_is_y else dx) - (expected_dy if primary_is_y else expected_dx))
            secondary_delta = abs((dx if primary_is_y else dy) - (expected_dx if primary_is_y else expected_dy))
            if primary_delta > primary_radius or secondary_delta > secondary_radius:
                continue
            distance_score = 1.0 - min(1.0, primary_delta / max(primary_radius, 1.0)) * 0.65 - min(1.0, secondary_delta / max(secondary_radius, 1.0)) * 0.35
            score = distance_score + area_ratio * 0.35 + min(ref_feature.conf, mov_feature.conf) * 0.25
            candidates.append((score, dx, dy, ref_feature, mov_feature))

    if len(candidates) < min_matches:
        return None

    candidates.sort(key=lambda item: item[0], reverse=True)
    selected = candidates[: min(50, len(candidates))]
    dx_values = np.array([item[1] for item in selected], dtype=np.float32)
    dy_values = np.array([item[2] for item in selected], dtype=np.float32)
    dx = float(np.median(dx_values))
    dy = float(np.median(dy_values))
    dx_mad = float(np.median(np.abs(dx_values - dx)))
    dy_mad = float(np.median(np.abs(dy_values - dy)))

    if abs(dx - expected_dx) > max(secondary_radius * 1.2, primary_radius if not primary_is_y else secondary_radius * 1.2):
        return None
    if abs(dy - expected_dy) > max(primary_radius * 1.2 if primary_is_y else secondary_radius * 1.2, secondary_radius):
        return None

    return dx, dy, {
        "method": "detection_feature_median",
        "expected_increment": [expected_dx, expected_dy],
        "increment": [dx, dy],
        "feature_matches": len(selected),
        "candidate_matches": len(candidates),
        "dx_mad": dx_mad,
        "dy_mad": dy_mad,
        "search_primary_radius": primary_radius,
        "search_secondary_radius": secondary_radius,
        "sample_matches": [
            {
                "score": float(score),
                "ref": {
                    "cx": ref_feature.cx,
                    "cy": ref_feature.cy,
                    "cls_id": ref_feature.cls_id,
                    "label": ref_feature.label,
                    "conf": ref_feature.conf,
                },
                "mov": {
                    "cx": mov_feature.cx,
                    "cy": mov_feature.cy,
                    "cls_id": mov_feature.cls_id,
                    "label": mov_feature.label,
                    "conf": mov_feature.conf,
                },
                "dx": match_dx,
                "dy": match_dy,
            }
            for score, match_dx, match_dy, ref_feature, mov_feature in selected[:10]
        ],
    }


def _is_near_zero_axis_increment(
    increment: tuple[float, float],
    typical_primary: float | None,
    strip_axis: str,
) -> bool:
    if typical_primary is None:
        return False
    dx, dy = increment
    primary = abs(dy) if strip_axis == "x" else abs(dx)
    return primary < max(60.0, typical_primary * 0.35)


def _typical_axis_increment(increments: list[tuple[float, float]], strip_axis: str) -> float | None:
    primary_values = [abs(dy) if strip_axis == "x" else abs(dx) for dx, dy in increments]
    candidates = sorted(value for value in primary_values if value >= 80.0)
    if not candidates:
        return None
    return float(candidates[len(candidates) // 2])


def _compose_pairwise_strip_mosaic(
    tiles: list[CoordinateTile],
    tile_width: int,
    tile_height: int,
    strip_axis: str,
    output_root: Path,
    x_pixels_per_unit: float,
    y_pixels_per_unit: float,
    tile_scale: float,
    skip_near_zero: bool = False,
    detection_features: dict[str, list[DetectionFeature]] | None = None,
    detection_feature_min_matches: int = 4,
) -> tuple[np.ndarray, list[dict[str, object]], list[dict[str, object]]]:
    if strip_axis not in {"x", "y"}:
        raise ValueError("strip_axis must be 'x' or 'y'")

    strip_root = output_root / "pairwise_strips"
    pair_root = output_root / "pairwise_pairs"
    strip_root.mkdir(parents=True, exist_ok=True)
    pair_root.mkdir(parents=True, exist_ok=True)
    groups: dict[float, list[CoordinateTile]] = {}
    for tile in tiles:
        key = tile.x if strip_axis == "x" else tile.y
        groups.setdefault(key, []).append(tile)

    strip_records: list[dict[str, object]] = []
    pair_records: list[dict[str, object]] = []
    strip_images: list[tuple[float, int, int, np.ndarray]] = []

    for strip_index, key in enumerate(sorted(groups)):
        group = groups[key]
        ordered = sorted(group, key=lambda tile: (tile.order, tile.path.name))

        increments: list[tuple[float, float]] = []
        local_pair_records: list[dict[str, object]] = []
        pair_items = list(zip(ordered, ordered[1:]))
        for pair_index, (previous, current) in enumerate(pair_items):
            expected_dx, expected_dy = _expected_canvas_increment(
                previous=previous,
                current=current,
                x_pixels_per_unit=x_pixels_per_unit,
                y_pixels_per_unit=y_pixels_per_unit,
                tile_scale=tile_scale,
            )
            detection_estimate = None
            if detection_features is not None:
                detection_estimate = _estimate_detection_feature_increment(
                    detection_features.get(previous.path.name, []),
                    detection_features.get(current.path.name, []),
                    expected_dx=expected_dx,
                    expected_dy=expected_dy,
                    tile_width=tile_width,
                    tile_height=tile_height,
                    min_matches=detection_feature_min_matches,
                )
            if detection_estimate is not None:
                dx, dy, pair_record = detection_estimate
            else:
                dx, dy, pair_record = _estimate_expected_constrained_increment(
                    previous.path,
                    current.path,
                    expected_dx=expected_dx,
                    expected_dy=expected_dy,
                    tile_width=tile_width,
                    tile_height=tile_height,
                )
                if detection_features is not None:
                    pair_record["detection_feature_fallback"] = "not_enough_reliable_detection_matches"
            pair_record["ref"] = previous.path.name
            pair_record["mov"] = current.path.name
            pair_record["strip_coordinate"] = key
            pair_record["coordinate_ref"] = [previous.x, previous.y]
            pair_record["coordinate_mov"] = [current.x, current.y]
            pair_preview_path = pair_root / f"pair_{strip_axis}_{strip_index:03d}_{pair_index:03d}_{previous.path.stem}_to_{current.path.stem}.png"
            _save_pair_alignment_preview(previous.path, current.path, dx, dy, pair_preview_path)
            pair_record["preview_path"] = str(pair_preview_path.resolve())
            increments.append((dx, dy))
            local_pair_records.append(pair_record)

        selected_ordered = [ordered[0]]
        skipped_tiles: list[str] = []
        selected_ordered.extend(ordered[1:])

        repaired_increments = increments
        raw_positions: list[tuple[float, float]] = [(0.0, 0.0)]
        for pair_index, ((dx, dy), pair_record) in enumerate(zip(repaired_increments, local_pair_records)):
            last_x, last_y = raw_positions[-1]
            raw_positions.append((last_x + dx, last_y + dy))
            pair_records.append(pair_record)

        min_x = min(x for x, _y in raw_positions)
        min_y = min(y for _x, y in raw_positions)
        normalized_positions = [
            (int(round(x - min_x)), int(round(y - min_y)))
            for x, y in raw_positions
        ]
        strip_width = max(x + tile_width for x, _y in normalized_positions)
        strip_height = max(y + tile_height for _x, y in normalized_positions)
        strip_image = _compose_ownership_mosaic(
            placements=[(tile, x, y) for tile, (x, y) in zip(selected_ordered, normalized_positions)],
            tile_width=tile_width,
            tile_height=tile_height,
            canvas_width=strip_width,
            canvas_height=strip_height,
            row_keep_threshold=0.0,
        )
        strip_path = strip_root / f"pairwise_strip_{strip_axis}_{strip_index:03d}_{key:g}.png"
        save_image(strip_path, strip_image)
        strip_images.append((key, strip_path, strip_image))
        strip_records.append(
            {
                "index": strip_index,
                "axis": strip_axis,
                "coordinate": key,
                "origin": [0, 0],
                "size": [strip_width, strip_height],
                "tile_count": len(selected_ordered),
                "path": str(strip_path.resolve()),
                "tiles": [tile.path.name for tile in selected_ordered],
                "skipped_tiles": skipped_tiles,
            }
        )

    if strip_axis == "x":
        min_key = min(key for key, _path, _image in strip_images)
        raw_strip_positions = [((key - min_key) * x_pixels_per_unit * tile_scale, 0.0) for key, _path, _image in strip_images]
    else:
        max_key = max(key for key, _path, _image in strip_images)
        raw_strip_positions = [(0.0, (max_key - key) * y_pixels_per_unit * tile_scale) for key, _path, _image in strip_images]

    for previous, current, previous_position, current_position in zip(
        strip_images,
        strip_images[1:],
        raw_strip_positions,
        raw_strip_positions[1:],
    ):
        prev_key, prev_path, _prev_image = previous
        cur_key, cur_path, _cur_image = current
        dx = current_position[0] - previous_position[0]
        dy = current_position[1] - previous_position[1]
        pair_records.append(
            {
                "ref": prev_path.name,
                "mov": cur_path.name,
                "strip_to_strip": True,
                "method": "coordinate_expected_strip_to_strip",
                "strip_coordinate_ref": prev_key,
                "strip_coordinate_mov": cur_key,
                "expected_increment": [dx, dy],
                "increment": [dx, dy],
            }
        )

    min_strip_x = min(x for x, _y in raw_strip_positions)
    min_strip_y = min(y for _x, y in raw_strip_positions)
    strip_positions = [
        (int(round(x - min_strip_x)), int(round(y - min_strip_y)))
        for x, y in raw_strip_positions
    ]
    for record, (origin_x, origin_y) in zip(strip_records, strip_positions):
        record["origin"] = [origin_x, origin_y]

    canvas_width = max(origin_x + image.shape[1] for (_key, _path, image), (origin_x, _origin_y) in zip(strip_images, strip_positions))
    canvas_height = max(origin_y + image.shape[0] for (_key, _path, image), (_origin_x, origin_y) in zip(strip_images, strip_positions))
    canvas = np.zeros((canvas_height, canvas_width, 3), dtype=np.uint8)
    for (_key, _path, image), (origin_x, origin_y) in zip(strip_images, strip_positions):
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        mask = gray > 5
        roi = canvas[origin_y : origin_y + image.shape[0], origin_x : origin_x + image.shape[1]]
        roi[mask] = image[mask]

    return canvas, strip_records, pair_records


def _estimate_content_phase_increment(
    previous: CoordinateTile,
    current: CoordinateTile,
    tile_width: int,
    tile_height: int,
    x_pixels_per_unit: float,
    y_pixels_per_unit: float,
    tile_scale: float,
    detection_features: dict[str, list[DetectionFeature]] | None,
    detection_feature_min_matches: int,
) -> tuple[float, float, dict[str, object]]:
    expected_dx, expected_dy = _expected_canvas_increment(
        previous=previous,
        current=current,
        x_pixels_per_unit=x_pixels_per_unit,
        y_pixels_per_unit=y_pixels_per_unit,
        tile_scale=tile_scale,
    )
    estimate = _estimate_phase_overlap_increment(
        previous.path,
        current.path,
        expected_dx=expected_dx,
        expected_dy=expected_dy,
        tile_width=tile_width,
        tile_height=tile_height,
    )
    fallback_chain: list[str] = []
    if estimate is None:
        fallback_chain.append("phase_overlap_failed")
        rbc_estimate = None
        if detection_features is not None:
            rbc_estimate = _estimate_rbc_constellation_increment(
                ref_path=previous.path,
                mov_path=current.path,
                ref_features=detection_features.get(previous.path.name, []),
                mov_features=detection_features.get(current.path.name, []),
                expected_dx=expected_dx,
                expected_dy=expected_dy,
                tile_width=tile_width,
                tile_height=tile_height,
                min_matches=detection_feature_min_matches,
            )
        estimate = rbc_estimate
    if estimate is None:
        fallback_chain.append("rbc_constellation_failed")
        rbc_density_estimate = None
        if detection_features is not None:
            rbc_density_estimate = _estimate_rbc_density_increment(
                ref_path=previous.path,
                mov_path=current.path,
                ref_features=detection_features.get(previous.path.name, []),
                mov_features=detection_features.get(current.path.name, []),
                expected_dx=expected_dx,
                expected_dy=expected_dy,
                tile_width=tile_width,
                tile_height=tile_height,
            )
        estimate = rbc_density_estimate
    if estimate is None:
        fallback_chain.append("rbc_density_failed")
        constrained_dx, constrained_dy, constrained_record = _estimate_expected_constrained_increment(
            previous.path,
            current.path,
            expected_dx=expected_dx,
            expected_dy=expected_dy,
            tile_width=tile_width,
            tile_height=tile_height,
        )
        if not constrained_record.get("fallback_to_expected", False):
            estimate = (constrained_dx, constrained_dy, constrained_record)
        else:
            fallback_chain.append("correlation_constrained_failed")
    if estimate is None:
        detection_estimate = None
        if detection_features is not None:
            detection_estimate = _estimate_detection_feature_increment(
                detection_features.get(previous.path.name, []),
                detection_features.get(current.path.name, []),
                expected_dx=expected_dx,
                expected_dy=expected_dy,
                tile_width=tile_width,
                tile_height=tile_height,
                min_matches=detection_feature_min_matches,
            )
        estimate = detection_estimate
    if estimate is None:
        fallback_chain.append("detection_features_failed")
        dx, dy, pair_record = _estimate_expected_constrained_increment(
            previous.path,
            current.path,
            expected_dx=expected_dx,
            expected_dy=expected_dy,
            tile_width=tile_width,
            tile_height=tile_height,
        )
    else:
        dx, dy, pair_record = estimate

    pair_record["ref"] = previous.path.name
    pair_record["mov"] = current.path.name
    pair_record["coordinate_ref"] = [previous.x, previous.y]
    pair_record["coordinate_mov"] = [current.x, current.y]
    pair_record["initial_guess_from_stage"] = [expected_dx, expected_dy]
    if fallback_chain:
        pair_record["fallback_chain"] = fallback_chain
    return dx, dy, pair_record


def _content_alignment_weight(record: dict[str, object]) -> float:
    if record.get("fallback_to_expected", False):
        return 0.05
    method = str(record.get("method", ""))
    if method == "phase_ecc_refined":
        return max(1.2, min(8.0, float(record.get("phase_response", 0.0)) * 80.0 + float(record.get("ecc_score", 0.0)) * 2.0))
    if method in {"phase_overlap_subpixel", "phase_overlap_subpixel_refined"}:
        return max(1.0, min(8.0, float(record.get("phase_response", 0.0)) * 80.0))
    if method == "rbc_constellation_ecc":
        return max(1.2, min(6.0, float(record.get("constellation_inliers", 0)) * 0.35 + float(record.get("ecc_score", 0.0)) * 2.0))
    if method in {"rbc_constellation", "rbc_constellation_phase"}:
        return max(0.8, min(4.0, float(record.get("constellation_inliers", 0)) * 0.30))
    if method == "rbc_density_ecc":
        return max(1.0, min(5.0, float(record.get("rbc_density_score", 0.0)) * 18.0 + float(record.get("ecc_score", 0.0)) * 2.0))
    if method in {"rbc_density_ncc", "rbc_density_phase"}:
        return max(0.8, min(3.5, float(record.get("rbc_density_score", 0.0)) * 18.0))
    if method == "content_ncc_ecc_refined":
        return max(1.0, min(6.0, float(record.get("similarity", 0.0)) * 60.0 + float(record.get("ecc_score", 0.0)) * 2.0))
    if method == "content_ncc_phase_refined":
        return max(0.8, min(5.0, float(record.get("similarity", 0.0)) * 60.0))
    if method == "coordinate_constrained_correlation":
        return max(0.4, min(2.5, float(record.get("similarity", 0.0)) * 40.0))
    if method == "detection_feature_median":
        return max(0.4, min(2.0, float(record.get("match_count", 0)) * 0.3))
    return 0.2


def _solve_content_graph_positions(
    ordered_tiles: list[CoordinateTile],
    edges: list[tuple[str, str, float, float, float]],
) -> dict[str, tuple[float, float]]:
    if not ordered_tiles:
        return {}
    index_by_name = {tile.path.name: index for index, tile in enumerate(ordered_tiles)}
    rows: list[np.ndarray] = []
    bx: list[float] = []
    by: list[float] = []
    for ref_name, mov_name, dx, dy, weight in edges:
        if ref_name not in index_by_name or mov_name not in index_by_name:
            continue
        row = np.zeros(len(ordered_tiles), dtype=np.float64)
        scale = float(np.sqrt(max(weight, 1e-6)))
        row[index_by_name[ref_name]] = -scale
        row[index_by_name[mov_name]] = scale
        rows.append(row)
        bx.append(float(dx) * scale)
        by.append(float(dy) * scale)

    anchor = np.zeros(len(ordered_tiles), dtype=np.float64)
    anchor[0] = 1.0
    rows.append(anchor)
    bx.append(0.0)
    by.append(0.0)

    matrix = np.vstack(rows)
    solved_x = np.linalg.lstsq(matrix, np.asarray(bx, dtype=np.float64), rcond=None)[0]
    solved_y = np.linalg.lstsq(matrix, np.asarray(by, dtype=np.float64), rcond=None)[0]
    return {
        tile.path.name: (float(solved_x[index]), float(solved_y[index]))
        for index, tile in enumerate(ordered_tiles)
    }


def _compose_content_phase_mosaic(
    tiles: list[CoordinateTile],
    tile_width: int,
    tile_height: int,
    output_root: Path,
    x_pixels_per_unit: float,
    y_pixels_per_unit: float,
    tile_scale: float,
    detection_features: dict[str, list[DetectionFeature]] | None = None,
    detection_feature_min_matches: int = 4,
) -> tuple[np.ndarray, list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    pair_root = output_root / "content_phase_pairs"
    pair_root.mkdir(parents=True, exist_ok=True)
    if not tiles:
        raise ValueError("No tiles to align")

    row_groups: dict[float, list[CoordinateTile]] = {}
    column_groups: dict[float, list[CoordinateTile]] = {}
    for tile in tiles:
        row_groups.setdefault(tile.y, []).append(tile)
        column_groups.setdefault(tile.x, []).append(tile)

    pair_records: list[dict[str, object]] = []
    graph_edges: list[tuple[str, str, float, float, float]] = []
    pair_index = 0
    for row_index, row_key in enumerate(sorted(row_groups)):
        ordered = sorted(row_groups[row_key], key=lambda tile: (tile.x, tile.path.name))
        for row_pair_index, (previous, current) in enumerate(zip(ordered, ordered[1:])):
            dx, dy, pair_record = _estimate_content_phase_increment(
                previous=previous,
                current=current,
                tile_width=tile_width,
                tile_height=tile_height,
                x_pixels_per_unit=x_pixels_per_unit,
                y_pixels_per_unit=y_pixels_per_unit,
                tile_scale=tile_scale,
                detection_features=detection_features,
                detection_feature_min_matches=detection_feature_min_matches,
            )
            pair_record["content_phase_scope"] = "row"
            pair_record["row_coordinate"] = row_key
            pair_record["row_index"] = row_index
            pair_record["global_optimization_weight"] = _content_alignment_weight(pair_record)
            pair_preview_path = pair_root / f"row_{row_index:03d}_{row_pair_index:03d}_{previous.path.stem}_to_{current.path.stem}.png"
            _save_pair_alignment_preview(previous.path, current.path, dx, dy, pair_preview_path)
            pair_record["preview_path"] = str(pair_preview_path.resolve())
            graph_edges.append((previous.path.name, current.path.name, dx, dy, float(pair_record["global_optimization_weight"])))
            pair_records.append(pair_record)
            pair_index += 1

    for column_index, column_key in enumerate(sorted(column_groups)):
        ordered = sorted(column_groups[column_key], key=lambda tile: (tile.y, tile.path.name))
        for column_pair_index, (previous, current) in enumerate(zip(ordered, ordered[1:])):
            dx, dy, pair_record = _estimate_content_phase_increment(
                previous=previous,
                current=current,
                tile_width=tile_width,
                tile_height=tile_height,
                x_pixels_per_unit=x_pixels_per_unit,
                y_pixels_per_unit=y_pixels_per_unit,
                tile_scale=tile_scale,
                detection_features=detection_features,
                detection_feature_min_matches=detection_feature_min_matches,
            )
            pair_record["content_phase_scope"] = "column"
            pair_record["column_coordinate"] = column_key
            pair_record["column_index"] = column_index
            pair_record["global_optimization_weight"] = _content_alignment_weight(pair_record)
            pair_preview_path = pair_root / f"column_{column_index:03d}_{column_pair_index:03d}_{previous.path.stem}_to_{current.path.stem}.png"
            _save_pair_alignment_preview(previous.path, current.path, dx, dy, pair_preview_path)
            pair_record["preview_path"] = str(pair_preview_path.resolve())
            graph_edges.append((previous.path.name, current.path.name, dx, dy, float(pair_record["global_optimization_weight"])))
            pair_records.append(pair_record)
            pair_index += 1

    ordered_tiles = sorted(tiles, key=lambda tile: (tile.order, tile.path.name))
    solved_positions = _solve_content_graph_positions(ordered_tiles, graph_edges)
    raw_positioned = [(tile, *solved_positions[tile.path.name]) for tile in ordered_tiles]

    min_x = min(x for _tile, x, _y in raw_positioned)
    min_y = min(y for _tile, _x, y in raw_positioned)
    positioned = [(tile, x - min_x, y - min_y) for tile, x, y in raw_positioned]
    stitched = _blend_float_positioned_tiles(positioned, tile_width=tile_width, tile_height=tile_height)
    aligned_placements = [
        {
            "image": tile.path.name,
            "coord": [tile.x, tile.y],
            "x": float(x),
            "y": float(y),
            "width": tile_width,
            "height": tile_height,
        }
        for tile, x, y in positioned
    ]
    strip_records = [
        {
            "index": 0,
            "axis": "content_graph",
            "coordinate": None,
            "origin": [0.0, 0.0],
            "size": [int(stitched.shape[1]), int(stitched.shape[0])],
            "tile_count": len(ordered_tiles),
            "path": "",
            "tiles": [tile.path.name for tile in ordered_tiles],
            "edge_count": len(graph_edges),
            "solver": "weighted_least_squares",
        }
    ]
    return stitched, strip_records, pair_records, aligned_placements


def stitch_by_coordinates(
    input_dir: str | Path,
    output_dir: str | Path,
    pixels_per_unit: float | None = None,
    x_pixels_per_unit: float | None = None,
    y_pixels_per_unit: float | None = None,
    tile_scale: float = 1.0,
    blend_mode: str = "ownership",
    preview_long_side: int = 8000,
    row_keep_threshold: float = 0.5,
    explicit_paths: list[str] | None = None,
    prefer_virtual_coordinates: bool = True,
    overlap_ratio: float | None = None,
    result_name: str = "coordinate_stitched.png",
    preview_name: str = "coordinate_stitched_preview.jpg",
    metadata_name: str = "coordinate_stitched.json",
    strip_axis: str | None = None,
    skip_near_zero: bool = False,
    use_detection_features: bool = False,
    detection_model_path: str | None = None,
    detection_confidence: float = 0.35,
    detection_feature_max_features: int = 300,
    detection_feature_min_matches: int = 4,
) -> dict[str, object]:
    if tile_scale <= 0.0:
        raise ValueError("tile_scale must be positive")
    if blend_mode not in {"average", "feather", "ownership", "strip_ownership", "pairwise_strip", "content_phase"}:
        raise ValueError("blend_mode must be 'average', 'feather', 'ownership', 'strip_ownership', 'pairwise_strip', or 'content_phase'")
    if overlap_ratio is not None and not (0.0 <= overlap_ratio < 1.0):
        raise ValueError("overlap_ratio must be in [0.0, 1.0)")
    if strip_axis is not None and strip_axis not in {"auto", "x", "y"}:
        raise ValueError("strip_axis must be 'auto', 'x', or 'y'")
    detection_confidence = float(min(1.0, max(0.01, detection_confidence)))
    detection_feature_max_features = int(max(1, detection_feature_max_features))
    detection_feature_min_matches = int(max(1, detection_feature_min_matches))

    tiles, coordinate_source = load_coordinate_tiles(
        input_dir=input_dir,
        explicit_paths=explicit_paths,
        prefer_virtual_coordinates=prefer_virtual_coordinates,
    )
    first_image = read_image(tiles[0].path)
    if tile_scale != 1.0:
        first_image = cv2.resize(first_image, (0, 0), fx=tile_scale, fy=tile_scale, interpolation=cv2.INTER_AREA)
    tile_height, tile_width = first_image.shape[:2]

    dominant_x_step = _dominant_coordinate_step([tile.x for tile in tiles])
    dominant_y_step = _dominant_coordinate_step([tile.y for tile in tiles])

    if pixels_per_unit is not None and pixels_per_unit <= 0.0:
        raise ValueError("pixels_per_unit must be positive")
    if x_pixels_per_unit is not None and x_pixels_per_unit <= 0.0:
        raise ValueError("x_pixels_per_unit must be positive")
    if y_pixels_per_unit is not None and y_pixels_per_unit <= 0.0:
        raise ValueError("y_pixels_per_unit must be positive")

    if x_pixels_per_unit is None or y_pixels_per_unit is None:
        if overlap_ratio is not None:
            expected_x_shift = tile_width * (1.0 - overlap_ratio)
            expected_y_shift = tile_height * (1.0 - overlap_ratio)
            inferred_x_ppu = (
                expected_x_shift / dominant_x_step
                if dominant_x_step is not None and dominant_x_step > 0.0
                else pixels_per_unit
            )
            inferred_y_ppu = (
                expected_y_shift / dominant_y_step
                if dominant_y_step is not None and dominant_y_step > 0.0
                else pixels_per_unit
            )
        else:
            inferred_x_ppu = pixels_per_unit
            inferred_y_ppu = pixels_per_unit
        x_pixels_per_unit = x_pixels_per_unit or inferred_x_ppu
        y_pixels_per_unit = y_pixels_per_unit or inferred_y_ppu

    if x_pixels_per_unit is None or y_pixels_per_unit is None:
        raise ValueError("Unable to resolve coordinate scale; provide overlap_ratio or explicit X/Y pixels-per-unit")

    min_x = min(tile.x for tile in tiles)
    max_x = max(tile.x for tile in tiles)
    max_y = max(tile.y for tile in tiles)

    placements: list[tuple[CoordinateTile, int, int]] = []
    max_canvas_x = 0
    max_canvas_y = 0
    for tile in tiles:
        x = int(round((tile.x - min_x) * x_pixels_per_unit * tile_scale))
        # Keep larger Y values near the top so negative scan steps extend downward.
        y = int(round((max_y - tile.y) * y_pixels_per_unit * tile_scale))
        placements.append((tile, x, y))
        max_canvas_x = max(max_canvas_x, x + tile_width)
        max_canvas_y = max(max_canvas_y, y + tile_height)

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    resolved_strip_axis = _choose_strip_axis(tiles) if strip_axis in {None, "auto"} else strip_axis
    strip_records: list[dict[str, object]] = []
    pair_records: list[dict[str, object]] = []
    aligned_placements: list[dict[str, object]] = []
    detection_feature_records: list[dict[str, object]] = []
    resolved_detection_model_path: str | None = None
    detection_feature_cache: dict[str, list[DetectionFeature]] | None = None
    detection_feature_source = "disabled"
    if use_detection_features:
        existing_cache, existing_records, existing_model_path = _load_existing_detection_feature_cache(
            tiles=tiles,
            input_dir=input_dir,
        )
        if len(existing_cache) == len(tiles):
            detection_feature_cache = existing_cache
            detection_feature_records = existing_records
            resolved_detection_model_path = existing_model_path
            detection_feature_source = "capture_time_existing"
        else:
            detection_feature_cache, detection_feature_records, resolved_detection_model_path = _prepare_detection_feature_cache(
                tiles=tiles,
                output_root=output_root,
                model_path=detection_model_path,
                confidence=detection_confidence,
                max_features=detection_feature_max_features,
            )
            detection_feature_source = "generated_before_stitch"

    if blend_mode == "ownership":
        stitched = _compose_ownership_mosaic(
            placements=placements,
            tile_width=tile_width,
            tile_height=tile_height,
            canvas_width=max_canvas_x,
            canvas_height=max_canvas_y,
            row_keep_threshold=row_keep_threshold,
        )
    elif blend_mode == "strip_ownership":
        stitched, strip_records = _compose_strip_ownership_mosaic(
            placements=placements,
            tile_width=tile_width,
            tile_height=tile_height,
            canvas_width=max_canvas_x,
            canvas_height=max_canvas_y,
            strip_axis=resolved_strip_axis,
            output_root=output_root,
        )
    elif blend_mode == "pairwise_strip":
        stitched, strip_records, pair_records = _compose_pairwise_strip_mosaic(
            tiles=tiles,
            tile_width=tile_width,
            tile_height=tile_height,
            strip_axis=resolved_strip_axis,
            output_root=output_root,
            x_pixels_per_unit=float(x_pixels_per_unit),
            y_pixels_per_unit=float(y_pixels_per_unit),
            tile_scale=tile_scale,
            skip_near_zero=skip_near_zero,
            detection_features=detection_feature_cache,
            detection_feature_min_matches=detection_feature_min_matches,
        )
        max_canvas_y, max_canvas_x = stitched.shape[:2]
    elif blend_mode == "content_phase":
        stitched, strip_records, pair_records, aligned_placements = _compose_content_phase_mosaic(
            tiles=tiles,
            tile_width=tile_width,
            tile_height=tile_height,
            output_root=output_root,
            x_pixels_per_unit=float(x_pixels_per_unit),
            y_pixels_per_unit=float(y_pixels_per_unit),
            tile_scale=tile_scale,
            detection_features=detection_feature_cache,
            detection_feature_min_matches=detection_feature_min_matches,
        )
        max_canvas_y, max_canvas_x = stitched.shape[:2]
    else:
        accum = np.zeros((max_canvas_y, max_canvas_x, 3), dtype=np.float32)
        weight_accum = np.zeros((max_canvas_y, max_canvas_x), dtype=np.float32)
        shared_weight = np.ones((tile_height, tile_width), dtype=np.float32) if blend_mode == "average" else _feather_weight_map(tile_height, tile_width)

        for index, (tile, x, y) in enumerate(placements):
            image = first_image if index == 0 else read_image(tile.path)
            if index != 0 and tile_scale != 1.0:
                image = cv2.resize(image, (tile_width, tile_height), interpolation=cv2.INTER_AREA)
            y1 = y + tile_height
            x1 = x + tile_width
            accum[y:y1, x:x1] += image.astype(np.float32) * shared_weight[:, :, None]
            weight_accum[y:y1, x:x1] += shared_weight

        stitched = accum / np.maximum(weight_accum[:, :, None], 1e-6)
        stitched = np.clip(stitched, 0, 255).astype(np.uint8)

    result_path = output_root / result_name
    preview_path = output_root / preview_name
    metadata_path = output_root / metadata_name
    save_image(result_path, stitched)
    save_image(preview_path, _preview_image(stitched, max_long_side=preview_long_side))
    payload: dict[str, Any] = {
        "input_dir": str(Path(input_dir)),
        "output_dir": str(output_root),
        "coordinate_source": coordinate_source,
        "tile_count": len(tiles),
        "x_range": [min_x, max_x],
        "y_range": [min(tile.y for tile in tiles), max_y],
        "tile_size": [tile_width, tile_height],
        "canvas_size": [max_canvas_x, max_canvas_y],
        "pixels_per_unit": pixels_per_unit,
        "x_pixels_per_unit": x_pixels_per_unit,
        "y_pixels_per_unit": y_pixels_per_unit,
        "dominant_x_step": dominant_x_step,
        "dominant_y_step": dominant_y_step,
        "overlap_ratio": overlap_ratio,
        "tile_scale": tile_scale,
        "blend_mode": blend_mode,
        "content_stitching_pipeline": {
            "flat_field_correction": blend_mode == "content_phase",
            "subpixel_registration": "cv2.findTransformECC translation refinement with phase fallback" if blend_mode == "content_phase" else None,
            "global_optimization": "weighted least squares pose graph" if blend_mode == "content_phase" else None,
            "blending": "flat-field gain-compensated feather blending" if blend_mode == "content_phase" else blend_mode,
        },
        "stage_motion_convention": {
            "x_positive_image_motion": "left",
            "y_positive_image_motion": "down",
            "mosaic_effect": "+X tiles are placed to the right; +Y tiles are placed upward",
        },
        "strip_axis": resolved_strip_axis if blend_mode in {"strip_ownership", "pairwise_strip"} else ("capture_order" if blend_mode == "content_phase" else None),
        "strips": strip_records,
        "pairwise_alignments": pair_records,
        "aligned_placements": aligned_placements,
        "use_detection_features": use_detection_features,
        "detection_feature_source": detection_feature_source,
        "detection_model_path": resolved_detection_model_path,
        "detection_confidence": detection_confidence,
        "detection_feature_max_features": detection_feature_max_features,
        "detection_feature_min_matches": detection_feature_min_matches,
        "detection_features": detection_feature_records,
        "skip_near_zero": skip_near_zero,
        "near_zero_policy": "skip" if skip_near_zero else "constrained_repair",
        "row_keep_threshold": row_keep_threshold,
        "result_path": str(result_path.resolve()),
        "preview_path": str(preview_path.resolve()),
        "placements": [
            {
                "image": tile.path.name,
                "coord": [tile.x, tile.y],
                "x": x,
                "y": y,
                "width": tile_width,
                "height": tile_height,
            }
            for tile, x, y in placements
        ],
    }
    save_json(metadata_path, payload)
    payload["metadata_path"] = str(metadata_path.resolve())
    return payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Overlay microscope tiles directly from x_y filenames")
    parser.add_argument("--input_dir", required=True, help="Directory containing images named like x_y.jpg")
    parser.add_argument("--output_dir", required=True, help="Directory where the stitched images will be written")
    parser.add_argument("--pixels_per_unit", type=float, default=None, help="Canvas pixels used for one coordinate unit")
    parser.add_argument("--x_pixels_per_unit", type=float, default=None, help="Canvas pixels used for one X coordinate unit")
    parser.add_argument("--y_pixels_per_unit", type=float, default=None, help="Canvas pixels used for one Y coordinate unit")
    parser.add_argument("--tile_scale", type=float, default=1.0, help="Optional resize factor applied to every input tile")
    parser.add_argument("--blend_mode", choices=("average", "feather", "ownership", "strip_ownership", "pairwise_strip", "content_phase"), default="ownership", help="How overlapping tiles are combined")
    parser.add_argument("--preview_long_side", type=int, default=8000, help="Max long side for the preview JPG")
    parser.add_argument("--row_keep_threshold", type=float, default=0.5, help="Keep only rows with at least this fraction of the densest row when using ownership mode")
    parser.add_argument("--overlap_ratio", type=float, default=None, help="Use image overlap to infer X/Y pixels-per-unit from coordinate steps")
    parser.add_argument("--strip_axis", choices=("auto", "x", "y"), default="auto", help="Group strips by this coordinate axis before final composition")
    parser.add_argument("--skip_near_zero", action="store_true", help="Skip adjacent images whose estimated movement is nearly zero instead of repairing them")
    parser.add_argument("--use_detection_features", action="store_true", help="Run object detection before stitching and use detected boxes as alignment features")
    parser.add_argument("--detect_model", default=None, help="YOLO model path used for pre-stitch detection features")
    parser.add_argument("--detect_conf", type=float, default=0.35, help="Detection confidence threshold for pre-stitch features")
    parser.add_argument("--detect_feature_max", type=int, default=300, help="Maximum detection features kept per tile")
    parser.add_argument("--detect_feature_min_matches", type=int, default=4, help="Minimum reliable detection-feature matches required for a pair")
    return parser


def main() -> None:
    args = _parser().parse_args()
    result = stitch_by_coordinates(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        pixels_per_unit=args.pixels_per_unit,
        x_pixels_per_unit=args.x_pixels_per_unit,
        y_pixels_per_unit=args.y_pixels_per_unit,
        tile_scale=args.tile_scale,
        blend_mode=args.blend_mode,
        preview_long_side=args.preview_long_side,
        row_keep_threshold=args.row_keep_threshold,
        overlap_ratio=args.overlap_ratio,
        strip_axis=args.strip_axis,
        skip_near_zero=args.skip_near_zero,
        use_detection_features=args.use_detection_features,
        detection_model_path=args.detect_model,
        detection_confidence=args.detect_conf,
        detection_feature_max_features=args.detect_feature_max,
        detection_feature_min_matches=args.detect_feature_min_matches,
    )
    print(f"stitched: {result['result_path']}")
    print(f"preview: {result['preview_path']}")
    print(f"canvas: {result['canvas_size'][0]}x{result['canvas_size'][1]}")
    print(f"tiles: {result['tile_count']}")


if __name__ == "__main__":
    main()

from __future__ import annotations

import json
from pathlib import Path

from .types import DetectionFeature, Tile


def load_detection_features(input_dir: Path, tiles: list[Tile], scale: float) -> dict[int, list[DetectionFeature]]:
    roots = [input_dir / "detected", input_dir / "detection_features"]
    cache: dict[int, list[DetectionFeature]] = {}
    for idx, tile in enumerate(tiles):
        path = _find_feature_file(roots, Path(tile.filename).stem)
        if path is None:
            cache[idx] = []
            continue
        cache[idx] = _read_feature_file(path, scale)
    return cache


def _find_feature_file(roots: list[Path], stem: str) -> Path | None:
    for root in roots:
        candidate = root / f"{stem}_features.json"
        if candidate.exists():
            return candidate
    return None


def _read_feature_file(path: Path, scale: float) -> list[DetectionFeature]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    features: list[DetectionFeature] = []
    for item in data.get("features", []):
        try:
            width = float(item.get("width", 0.0)) * scale
            height = float(item.get("height", 0.0)) * scale
            features.append(
                DetectionFeature(
                    cx=float(item["cx"]) * scale,
                    cy=float(item["cy"]) * scale,
                    width=width,
                    height=height,
                    area=max(1.0, float(item.get("area", width * height))) * scale * scale,
                    cls_id=int(item.get("cls_id", -1)),
                    label=str(item.get("label", "")),
                    conf=float(item.get("conf", 0.0)),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return features

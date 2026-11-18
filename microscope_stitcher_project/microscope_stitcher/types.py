from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np


@dataclass(frozen=True)
class Tile:
    path: Path
    filename: str
    x: float
    y: float
    index: int


@dataclass
class WorkTile:
    tile: Tile
    image_bgr: np.ndarray
    gray: np.ndarray
    scale: float
    features: list["DetectionFeature"] = field(default_factory=list)


@dataclass(frozen=True)
class DetectionFeature:
    cx: float
    cy: float
    width: float
    height: float
    area: float
    cls_id: int
    label: str
    conf: float


@dataclass
class PairEdge:
    ref: int
    mov: int
    expected_dx: float
    expected_dy: float
    dx: float
    dy: float
    method: str
    score: float
    success: bool
    matches: int = 0
    matrix: list[list[float]] | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class StitchResult:
    final_image: Path
    preview_image: Path
    debug_dir: Path
    summary_json: Path
    tile_count: int

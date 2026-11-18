from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class FrameRecord:
    frame_id: int
    source_frame_index: int
    timestamp_s: float
    path: Optional[Path]
    blur_score: float
    saved: bool
    skipped_reason: str = ""


@dataclass
class Detection:
    frame_id: int
    source_frame_index: int
    frame_path: Path
    detection_index: int
    class_id: int
    class_name: str
    confidence: float
    x1: float
    y1: float
    x2: float
    y2: float
    center_x: float
    center_y: float
    track_id: Optional[int] = None
    is_unique_best: bool = False

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        return self.x1, self.y1, self.x2, self.y2

    @property
    def center(self) -> tuple[float, float]:
        return self.center_x, self.center_y


@dataclass
class Track:
    track_id: int
    class_name: str
    detections: list[Detection]

    @property
    def best_detection(self) -> Detection:
        return max(self.detections, key=lambda det: det.confidence)

    @property
    def last_detection(self) -> Detection:
        return self.detections[-1]


@dataclass
class CropRecord:
    track_id: int
    class_name: str
    confidence: float
    frame_id: int
    source_frame_index: int
    crop_path: Path
    x1: int
    y1: int
    x2: int
    y2: int


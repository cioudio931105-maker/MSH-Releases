from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

import cv2

from .models import CropRecord, Detection
from .utils import ensure_dir, safe_name


def _expanded_box(
    det: Detection,
    width: int,
    height: int,
    margin_ratio: float,
) -> tuple[int, int, int, int]:
    bw = max(1.0, det.x2 - det.x1)
    bh = max(1.0, det.y2 - det.y1)
    margin_x = bw * float(margin_ratio)
    margin_y = bh * float(margin_ratio)
    x1 = max(0, int(round(det.x1 - margin_x)))
    y1 = max(0, int(round(det.y1 - margin_y)))
    x2 = min(width, int(round(det.x2 + margin_x)))
    y2 = min(height, int(round(det.y2 + margin_y)))
    return x1, y1, x2, y2


def crop_unique_cells(
    detections: list[Detection],
    output_dir: Path,
    *,
    margin_ratio: float = 0.10,
) -> list[CropRecord]:
    output_dir = ensure_dir(Path(output_dir))
    image_cache: dict[Path, object] = {}
    crops: list[CropRecord] = []

    for det in detections:
        frame_path = Path(det.frame_path)
        frame = image_cache.get(frame_path)
        if frame is None:
            frame = cv2.imread(str(frame_path))
            if frame is None:
                raise RuntimeError(f"Cannot read frame for crop: {frame_path}")
            image_cache[frame_path] = frame

        height, width = frame.shape[:2]
        x1, y1, x2, y2 = _expanded_box(det, width, height, margin_ratio)
        if x2 <= x1 or y2 <= y1:
            continue

        class_dir = ensure_dir(output_dir / safe_name(det.class_name))
        conf_pct = int(round(det.confidence * 100.0))
        filename = (
            f"{safe_name(det.class_name)}_frame{det.source_frame_index:06d}_"
            f"track{int(det.track_id or 0):05d}_conf{conf_pct:02d}.png"
        )
        crop_path = class_dir / filename
        crop = frame[y1:y2, x1:x2]
        if not cv2.imwrite(str(crop_path), crop):
            raise RuntimeError(f"Failed to write crop: {crop_path}")

        crops.append(
            CropRecord(
                track_id=int(det.track_id or 0),
                class_name=det.class_name,
                confidence=det.confidence,
                frame_id=det.frame_id,
                source_frame_index=det.source_frame_index,
                crop_path=crop_path,
                x1=x1,
                y1=y1,
                x2=x2,
                y2=y2,
            )
        )

    return crops


def write_crops_csv(crops: list[CropRecord], csv_path: Path) -> None:
    ensure_dir(csv_path.parent)
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "track_id",
                "class_name",
                "confidence",
                "frame_id",
                "source_frame_index",
                "crop_path",
                "x1",
                "y1",
                "x2",
                "y2",
            ],
        )
        writer.writeheader()
        for crop in crops:
            writer.writerow(
                {
                    "track_id": crop.track_id,
                    "class_name": crop.class_name,
                    "confidence": f"{crop.confidence:.6f}",
                    "frame_id": crop.frame_id,
                    "source_frame_index": crop.source_frame_index,
                    "crop_path": str(crop.crop_path),
                    "x1": crop.x1,
                    "y1": crop.y1,
                    "x2": crop.x2,
                    "y2": crop.y2,
                }
            )


def save_annotated_frames(detections: list[Detection], output_dir: Path) -> None:
    output_dir = ensure_dir(Path(output_dir))
    grouped: dict[Path, list[Detection]] = defaultdict(list)
    for det in detections:
        grouped[Path(det.frame_path)].append(det)

    for frame_path, frame_detections in grouped.items():
        frame = cv2.imread(str(frame_path))
        if frame is None:
            continue
        for det in frame_detections:
            color = (0, 255, 0) if det.is_unique_best else (0, 180, 255)
            x1, y1, x2, y2 = [int(round(value)) for value in det.bbox]
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            label = f"{det.class_name} {det.confidence:.2f}"
            if det.track_id is not None:
                label += f" T{det.track_id}"
            cv2.putText(frame, label, (x1, max(16, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)
        cv2.imwrite(str(output_dir / frame_path.name), frame)


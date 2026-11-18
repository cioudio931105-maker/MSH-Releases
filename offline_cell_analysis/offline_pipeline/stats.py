from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

from .models import CropRecord, Detection, FrameRecord, Track
from .utils import ensure_dir


def write_tracks_csv(tracks: list[Track], csv_path: Path) -> None:
    ensure_dir(csv_path.parent)
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "track_id",
                "class_name",
                "detections_count",
                "best_confidence",
                "best_frame_id",
                "best_source_frame_index",
            ],
        )
        writer.writeheader()
        for track in tracks:
            best = track.best_detection
            writer.writerow(
                {
                    "track_id": track.track_id,
                    "class_name": track.class_name,
                    "detections_count": len(track.detections),
                    "best_confidence": f"{best.confidence:.6f}",
                    "best_frame_id": best.frame_id,
                    "best_source_frame_index": best.source_frame_index,
                }
            )


def build_summary(
    *,
    video_path: Path,
    frame_records: list[FrameRecord],
    detections: list[Detection],
    tracks: list[Track],
    crops: list[CropRecord],
    run_dir: Path,
) -> dict:
    saved_frames = [record for record in frame_records if record.saved]
    skipped_blur = [record for record in frame_records if record.skipped_reason == "blur"]
    detection_counts = Counter(det.class_name for det in detections)
    unique_counts = Counter(track.class_name for track in tracks)
    crop_counts = Counter(crop.class_name for crop in crops)

    confidence_by_class: dict[str, list[float]] = defaultdict(list)
    for det in detections:
        confidence_by_class[det.class_name].append(det.confidence)

    mean_confidence_by_class = {
        class_name: sum(values) / len(values)
        for class_name, values in confidence_by_class.items()
        if values
    }

    return {
        "video_path": str(Path(video_path).resolve()),
        "run_dir": str(Path(run_dir).resolve()),
        "frames_sampled": len(frame_records),
        "frames_saved": len(saved_frames),
        "frames_skipped_blur": len(skipped_blur),
        "detections_total": len(detections),
        "unique_cells_total": len(tracks),
        "duplicates_removed": max(0, len(detections) - len(tracks)),
        "crops_saved": len(crops),
        "detections_by_class": dict(detection_counts),
        "unique_cells_by_class": dict(unique_counts),
        "crops_by_class": dict(crop_counts),
        "mean_confidence_by_class": {
            class_name: round(value, 6) for class_name, value in mean_confidence_by_class.items()
        },
    }


def write_summary(summary: dict, json_path: Path) -> None:
    ensure_dir(json_path.parent)
    json_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")


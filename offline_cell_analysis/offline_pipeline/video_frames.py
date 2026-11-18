from __future__ import annotations

import csv
from pathlib import Path

import cv2

from .blur import laplacian_variance
from .models import FrameRecord
from .utils import ensure_dir


def write_frame_manifest(records: list[FrameRecord], csv_path: Path) -> None:
    ensure_dir(csv_path.parent)
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "frame_id",
                "source_frame_index",
                "timestamp_s",
                "path",
                "blur_score",
                "saved",
                "skipped_reason",
            ],
        )
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    "frame_id": record.frame_id,
                    "source_frame_index": record.source_frame_index,
                    "timestamp_s": f"{record.timestamp_s:.6f}",
                    "path": str(record.path or ""),
                    "blur_score": f"{record.blur_score:.6f}",
                    "saved": int(record.saved),
                    "skipped_reason": record.skipped_reason,
                }
            )


def extract_frames(
    video_path: Path,
    output_dir: Path,
    *,
    every_n_frames: int = 1,
    every_seconds: float | None = None,
    blur_threshold: float = 0.0,
    jpeg_quality: int = 95,
    manifest_path: Path | None = None,
) -> list[FrameRecord]:
    """Extract sampled frames from a video and optionally skip blurry frames."""
    video_path = Path(video_path)
    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")
    output_dir = ensure_dir(Path(output_dir))

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    if every_seconds is not None:
        if fps <= 0:
            cap.release()
            raise RuntimeError("Video FPS is unknown; use every_n_frames instead of every_seconds.")
        interval = max(1, int(round(float(every_seconds) * fps)))
    else:
        interval = max(1, int(every_n_frames))

    records: list[FrameRecord] = []
    saved_id = 0
    source_index = 0
    encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), int(jpeg_quality)]

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            if source_index % interval != 0:
                source_index += 1
                continue

            timestamp_s = source_index / fps if fps > 0 else float(cap.get(cv2.CAP_PROP_POS_MSEC) or 0.0) / 1000.0
            blur_score = laplacian_variance(frame)
            if blur_threshold > 0 and blur_score < float(blur_threshold):
                records.append(
                    FrameRecord(
                        frame_id=saved_id + 1,
                        source_frame_index=source_index,
                        timestamp_s=timestamp_s,
                        path=None,
                        blur_score=blur_score,
                        saved=False,
                        skipped_reason="blur",
                    )
                )
                source_index += 1
                continue

            saved_id += 1
            frame_path = output_dir / f"frame_{saved_id:06d}.jpg"
            if not cv2.imwrite(str(frame_path), frame, encode_params):
                raise RuntimeError(f"Failed to write frame: {frame_path}")
            records.append(
                FrameRecord(
                    frame_id=saved_id,
                    source_frame_index=source_index,
                    timestamp_s=timestamp_s,
                    path=frame_path,
                    blur_score=blur_score,
                    saved=True,
                )
            )
            source_index += 1
    finally:
        cap.release()

    if manifest_path is not None:
        write_frame_manifest(records, manifest_path)
    return records


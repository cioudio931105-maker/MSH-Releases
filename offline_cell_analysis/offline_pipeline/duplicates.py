from __future__ import annotations

import math

from .models import Detection, Track


def box_iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    iw = max(0.0, ix2 - ix1)
    ih = max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    return 0.0 if union <= 0 else inter / union


def centroid_distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(float(a[0]) - float(b[0]), float(a[1]) - float(b[1]))


def assign_tracks(
    detections: list[Detection],
    *,
    iou_threshold: float = 0.35,
    centroid_threshold: float = 80.0,
    max_frame_gap: int = 8,
) -> list[Track]:
    """Assign simple tracks and keep the best-confidence detection per track."""
    tracks: list[Track] = []
    next_track_id = 1

    ordered = sorted(detections, key=lambda det: (det.frame_id, det.detection_index))
    for det in ordered:
        best_track: Track | None = None
        best_score = -1.0

        for track in tracks:
            if track.class_name != det.class_name:
                continue
            last = track.last_detection
            gap = det.frame_id - last.frame_id
            if gap <= 0 or gap > max_frame_gap:
                continue

            iou = box_iou(det.bbox, last.bbox)
            distance = centroid_distance(det.center, last.center)
            if iou < iou_threshold and distance > centroid_threshold:
                continue

            distance_score = max(0.0, 1.0 - distance / max(1.0, centroid_threshold))
            score = iou * 2.0 + distance_score
            if score > best_score:
                best_score = score
                best_track = track

        if best_track is None:
            det.track_id = next_track_id
            tracks.append(Track(track_id=next_track_id, class_name=det.class_name, detections=[det]))
            next_track_id += 1
        else:
            det.track_id = best_track.track_id
            best_track.detections.append(det)

    for track in tracks:
        best = track.best_detection
        best.is_unique_best = True

    return tracks


def unique_best_detections(tracks: list[Track]) -> list[Detection]:
    return sorted((track.best_detection for track in tracks), key=lambda det: (det.frame_id, det.track_id or 0))


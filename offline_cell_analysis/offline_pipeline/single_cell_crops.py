from __future__ import annotations

from .model_files import require_local_model

import csv
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Iterator

import cv2
import numpy as np

from .blur import laplacian_variance
from .utils import ensure_dir, safe_name


CANONICAL_CLASSES = (
    "Neutrophil",
    "Lymphocyte",
    "Monocyte",
    "Eosinophil",
    "Basophil",
    "Red_Blood_Cell",
    "Platelet",
)
WBC_SUBTYPES = {"Neutrophil", "Lymphocyte", "Monocyte", "Eosinophil", "Basophil"}


@dataclass
class VideoFrame:
    frame: np.ndarray
    frame_index: int
    timestamp: float


@dataclass
class CellDetection:
    cell_id: int
    cell_class: str
    bounding_box: tuple[float, float, float, float]
    confidence: float
    frame_index: int
    timestamp: float
    frame: np.ndarray | None = None
    video_name: str = ""
    raw_class: str = ""
    quality_score: float = 0.0
    status: str = "candidate"
    crop_path: str = ""


_DETECTION_MODEL: Any | None = None
_WBC_CLASSIFIER: Any | None = None
_DETECTION_CONFIDENCE = 0.25
_WBC_CONFIDENCE = 0.70
_DEVICE: str | None = None
_IMGSZ = 640
_NEXT_DETECTION_ID = 1


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[2]


def find_default_wbc_classifier() -> Path | None:
    root = _workspace_root()
    candidates = [
        root
        / "stitched_output"
        / "stitched_output"
        / "stitched_output"
        / "models"
        / "wbc_5cls_1000x_cls.pt",
        root / "staging" / "train" / "wbc_5cls_1000x_cls_20260520" / "weights" / "best.pt",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _resolve_device(device: str | None) -> str | None:
    if device in {None, "", "auto"}:
        try:
            import torch

            return "0" if torch.cuda.is_available() else "cpu"
        except Exception:
            return "cpu"
    requested = str(device).strip()
    normalized = requested.lower()
    wants_cuda = normalized == "cuda" or normalized.startswith("cuda:") or normalized.isdigit()
    if wants_cuda:
        try:
            import torch

            if not torch.cuda.is_available():
                print(f"Requested device {requested!r}, but CUDA is unavailable. Using CPU.", flush=True)
                return "cpu"
        except Exception:
            return "cpu"
    return "0" if wants_cuda else requested


def _use_half_precision() -> bool:
    return _DEVICE not in {None, "cpu"}


def configure_models(
    detection_model_path: Path,
    *,
    wbc_classifier_path: Path | None = None,
    confidence: float = 0.25,
    wbc_confidence: float = 0.70,
    device: str | None = "auto",
    imgsz: int = 640,
) -> None:
    global _DETECTION_MODEL, _WBC_CLASSIFIER, _DETECTION_CONFIDENCE, _WBC_CONFIDENCE, _DEVICE, _IMGSZ, _NEXT_DETECTION_ID
    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise RuntimeError("ultralytics is required. Install with: pip install ultralytics") from exc

    detection_model_path = Path(detection_model_path)
    if not detection_model_path.exists():
        raise FileNotFoundError(f"Detection model not found: {detection_model_path}")

    _DETECTION_MODEL = YOLO(require_local_model(str(detection_model_path)))
    _DETECTION_CONFIDENCE = float(confidence)
    _WBC_CONFIDENCE = float(wbc_confidence)
    _DEVICE = _resolve_device(device)
    _IMGSZ = int(imgsz)
    _NEXT_DETECTION_ID = 1

    if wbc_classifier_path is None:
        wbc_classifier_path = find_default_wbc_classifier()
    if wbc_classifier_path is not None and Path(wbc_classifier_path).exists():
        _WBC_CLASSIFIER = YOLO(require_local_model(str(wbc_classifier_path)))
        print(f"Loaded WBC subtype classifier: {wbc_classifier_path}", flush=True)
    else:
        _WBC_CLASSIFIER = None
        print("No WBC subtype classifier found. WBC detections cannot be saved into five subtype folders.", flush=True)


def parse_video(
    video_path: Path,
    *,
    every_n_frames: int = 1,
    every_seconds: float | None = None,
) -> Iterator[VideoFrame]:
    video_path = Path(video_path)
    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    if every_seconds is not None:
        if fps <= 0:
            cap.release()
            raise RuntimeError("Video FPS is unknown; use every_n_frames instead.")
        interval = max(1, int(round(float(every_seconds) * fps)))
    else:
        interval = max(1, int(every_n_frames))

    frame_index = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if frame_index % interval == 0:
                timestamp = frame_index / fps if fps > 0 else float(cap.get(cv2.CAP_PROP_POS_MSEC) or 0.0) / 1000.0
                yield VideoFrame(frame=frame, frame_index=frame_index, timestamp=timestamp)
            frame_index += 1
    finally:
        cap.release()


def _normalize_cell_class(label: str) -> str:
    normalized = "".join(ch for ch in str(label).lower() if ch.isalnum())
    mapping = {
        "neutrophil": "Neutrophil",
        "lymphocyte": "Lymphocyte",
        "monocyte": "Monocyte",
        "eosinophil": "Eosinophil",
        "basophil": "Basophil",
        "rbc": "Red_Blood_Cell",
        "redbloodcell": "Red_Blood_Cell",
        "redbloodcells": "Red_Blood_Cell",
        "erythrocyte": "Red_Blood_Cell",
        "erythrocytes": "Red_Blood_Cell",
        "platelet": "Platelet",
        "platelets": "Platelet",
        "plt": "Platelet",
        "wbc": "WBC",
        "whitebloodcell": "WBC",
        "whitebloodcells": "WBC",
        "leukocyte": "WBC",
        "leukocytes": "WBC",
    }
    return mapping.get(normalized, safe_name(str(label)))


def _bbox_to_int(bbox: tuple[float, float, float, float], width: int, height: int) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = bbox
    return (
        max(0, min(width, int(round(x1)))),
        max(0, min(height, int(round(y1)))),
        max(0, min(width, int(round(x2)))),
        max(0, min(height, int(round(y2)))),
    )


def _classify_wbc(frame: np.ndarray, bbox: tuple[float, float, float, float]) -> tuple[str, float] | None:
    if _WBC_CLASSIFIER is None:
        return None
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = _bbox_to_int(bbox, w, h)
    if x2 <= x1 or y2 <= y1:
        return None
    crop = frame[y1:y2, x1:x2]
    result = _WBC_CLASSIFIER.predict(
        crop,
        device=_DEVICE,
        quantize=16 if _use_half_precision() else None,
        verbose=False,
    )[0]
    probs = getattr(result, "probs", None)
    if probs is None:
        return None
    class_id = int(probs.top1)
    confidence = float(probs.top1conf)
    raw_name = result.names.get(class_id, str(class_id)) if isinstance(result.names, dict) else str(class_id)
    cell_class = _normalize_cell_class(raw_name)
    if cell_class not in WBC_SUBTYPES or confidence < _WBC_CONFIDENCE:
        return None
    return cell_class, confidence


def detect_cells(frame: np.ndarray) -> list[CellDetection]:
    global _NEXT_DETECTION_ID
    if _DETECTION_MODEL is None:
        raise RuntimeError("Detection model is not configured. Call configure_models(...) first.")

    result = _DETECTION_MODEL.predict(
        frame,
        conf=_DETECTION_CONFIDENCE,
        imgsz=_IMGSZ,
        device=_DEVICE,
        quantize=16 if _use_half_precision() else None,
        verbose=False,
    )[0]
    boxes = getattr(result, "boxes", None)
    if boxes is None or len(boxes) == 0:
        return []

    detections: list[CellDetection] = []
    xyxy = boxes.xyxy.detach().cpu().numpy()
    confs = boxes.conf.detach().cpu().numpy()
    class_ids = boxes.cls.detach().cpu().numpy().astype(int)
    names = getattr(result, "names", {}) or {}

    for bbox_arr, confidence, class_id in zip(xyxy, confs, class_ids):
        bbox = tuple(float(v) for v in bbox_arr.tolist())  # type: ignore[assignment]
        raw_name = names.get(int(class_id), str(class_id)) if isinstance(names, dict) else str(class_id)
        cell_class = _normalize_cell_class(raw_name)
        final_confidence = float(confidence)

        if cell_class == "WBC":
            subtype = _classify_wbc(frame, bbox)
            if subtype is not None:
                cell_class, subtype_conf = subtype
                final_confidence = min(final_confidence, subtype_conf)

        detections.append(
            CellDetection(
                cell_id=_NEXT_DETECTION_ID,
                cell_class=cell_class,
                bounding_box=bbox,
                confidence=final_confidence,
                frame_index=0,
                timestamp=0.0,
                frame=frame,
                raw_class=str(raw_name),
            )
        )
        _NEXT_DETECTION_ID += 1
    return detections


def _intersection_area(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    x1 = max(a[0], b[0])
    y1 = max(a[1], b[1])
    x2 = min(a[2], b[2])
    y2 = min(a[3], b[3])
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def _box_area(bbox: tuple[float, float, float, float]) -> float:
    return max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1])


def _iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    inter = _intersection_area(a, b)
    union = _box_area(a) + _box_area(b) - inter
    return 0.0 if union <= 0 else inter / union


def _center(bbox: tuple[float, float, float, float]) -> tuple[float, float]:
    return (bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0


def _centroid_distance(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ax, ay = _center(a)
    bx, by = _center(b)
    return math.hypot(ax - bx, ay - by)


def _bbox_gap(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    dx = max(b[0] - a[2], a[0] - b[2], 0.0)
    dy = max(b[1] - a[3], a[1] - b[3], 0.0)
    return math.hypot(dx, dy)


def is_crop_ambiguous(
    target_bbox: tuple[float, float, float, float],
    all_bboxes: Iterable[tuple[float, float, float, float]],
    *,
    min_gap_px: float = 6.0,
    overlap_ratio_threshold: float = 0.02,
) -> bool:
    for bbox in all_bboxes:
        if bbox == target_bbox:
            continue
        target_area = max(1.0, _box_area(target_bbox))
        overlap_ratio = _intersection_area(target_bbox, bbox) / target_area
        if overlap_ratio > overlap_ratio_threshold:
            return True
        if _bbox_gap(target_bbox, bbox) < min_gap_px:
            return True
    return False


def _expanded_crop_box(
    target_bbox: tuple[float, float, float, float],
    frame_w: int,
    frame_h: int,
    padding: int | float,
) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = target_bbox
    if isinstance(padding, float) and 0 < padding < 1:
        pad_x = (x2 - x1) * padding
        pad_y = (y2 - y1) * padding
    else:
        pad_x = pad_y = float(padding)
    return (
        max(0, int(math.floor(x1 - pad_x))),
        max(0, int(math.floor(y1 - pad_y))),
        min(frame_w, int(math.ceil(x2 + pad_x))),
        min(frame_h, int(math.ceil(y2 + pad_y))),
    )


def _crop_box_intersects_other(
    crop_box: tuple[int, int, int, int],
    target_bbox: tuple[float, float, float, float],
    other_bbox: tuple[float, float, float, float],
) -> bool:
    if other_bbox == target_bbox:
        return False
    return _intersection_area(crop_box, other_bbox) > 0


def _shrink_crop_away_from_other(
    crop_box: tuple[int, int, int, int],
    target_bbox: tuple[float, float, float, float],
    other_bbox: tuple[float, float, float, float],
) -> tuple[int, int, int, int]:
    cx1, cy1, cx2, cy2 = crop_box
    tx1, ty1, tx2, ty2 = target_bbox
    target_cx, target_cy = _center(target_bbox)
    other_cx, other_cy = _center(other_bbox)

    if abs(other_cx - target_cx) >= abs(other_cy - target_cy):
        if other_cx < target_cx:
            cx1 = max(cx1, int(math.floor((other_bbox[2] + tx1) / 2.0)))
        else:
            cx2 = min(cx2, int(math.ceil((other_bbox[0] + tx2) / 2.0)))
    else:
        if other_cy < target_cy:
            cy1 = max(cy1, int(math.floor((other_bbox[3] + ty1) / 2.0)))
        else:
            cy2 = min(cy2, int(math.ceil((other_bbox[1] + ty2) / 2.0)))

    return cx1, cy1, cx2, cy2


def crop_single_cell(
    frame: np.ndarray,
    target_bbox: tuple[float, float, float, float],
    all_bboxes: Iterable[tuple[float, float, float, float]],
    padding: int | float,
) -> np.ndarray | None:
    frame_h, frame_w = frame.shape[:2]
    target_int = _bbox_to_int(target_bbox, frame_w, frame_h)
    if target_int[2] <= target_int[0] or target_int[3] <= target_int[1]:
        return None

    crop_box = _expanded_crop_box(target_bbox, frame_w, frame_h, padding)
    for bbox in all_bboxes:
        if _crop_box_intersects_other(crop_box, target_bbox, bbox):
            crop_box = _shrink_crop_away_from_other(crop_box, target_bbox, bbox)

    cx1, cy1, cx2, cy2 = crop_box
    tx1, ty1, tx2, ty2 = target_int
    if cx1 > tx1 or cy1 > ty1 or cx2 < tx2 or cy2 < ty2:
        return None

    for bbox in all_bboxes:
        if _crop_box_intersects_other(crop_box, target_bbox, bbox):
            return None

    return frame[cy1:cy2, cx1:cx2].copy()


def classify_and_save_crop(
    crop_img: np.ndarray,
    cell_class: str,
    video_name: str,
    date_time: str,
    *,
    output_root: Path,
    frame_index: int,
    cell_id: int,
    confidence: float,
) -> Path:
    class_dir = ensure_dir(Path(output_root) / cell_class / safe_name(video_name) / date_time)
    filename = f"{cell_class}_frame{frame_index:06d}_id{cell_id:03d}_conf{confidence:.2f}.png"
    crop_path = class_dir / filename
    if not cv2.imwrite(str(crop_path), crop_img):
        raise RuntimeError(f"Failed to write crop: {crop_path}")
    return crop_path


def remove_duplicate_cells(
    detections: list[CellDetection],
    *,
    iou_threshold: float = 0.35,
    centroid_threshold: float = 60.0,
    max_frame_gap: int = 8,
) -> list[CellDetection]:
    tracks: list[list[CellDetection]] = []
    for det in sorted(detections, key=lambda item: (item.frame_index, item.cell_id)):
        if det.status != "candidate":
            continue
        best_track: list[CellDetection] | None = None
        best_score = -1.0
        for track in tracks:
            last = track[-1]
            if last.cell_class != det.cell_class:
                continue
            frame_gap = det.frame_index - last.frame_index
            if frame_gap <= 0 or frame_gap > max_frame_gap:
                continue
            iou = _iou(det.bounding_box, last.bounding_box)
            distance = _centroid_distance(det.bounding_box, last.bounding_box)
            if iou < iou_threshold and distance > centroid_threshold:
                continue
            score = iou * 2.0 + max(0.0, 1.0 - distance / max(1.0, centroid_threshold))
            if score > best_score:
                best_score = score
                best_track = track
        if best_track is None:
            tracks.append([det])
        else:
            best_track.append(det)

    kept: list[CellDetection] = []
    for track_index, track in enumerate(tracks, start=1):
        best = max(track, key=lambda item: (item.confidence, item.quality_score))
        best.cell_id = track_index
        kept.append(best)
        for det in track:
            if det is not best:
                det.cell_id = track_index
                det.status = "duplicate_skipped"
    return sorted(kept, key=lambda item: (item.frame_index, item.cell_id))


def export_csv(results: list[CellDetection], csv_path: Path) -> None:
    ensure_dir(Path(csv_path).parent)
    with Path(csv_path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "cell_id",
                "cell_class",
                "video_name",
                "frame_index",
                "timestamp",
                "confidence",
                "bbox_x1",
                "bbox_y1",
                "bbox_x2",
                "bbox_y2",
                "crop_path",
                "status",
            ],
        )
        writer.writeheader()
        for det in results:
            x1, y1, x2, y2 = det.bounding_box
            writer.writerow(
                {
                    "cell_id": det.cell_id,
                    "cell_class": det.cell_class,
                    "video_name": det.video_name,
                    "frame_index": det.frame_index,
                    "timestamp": f"{det.timestamp:.6f}",
                    "confidence": f"{det.confidence:.6f}",
                    "bbox_x1": f"{x1:.2f}",
                    "bbox_y1": f"{y1:.2f}",
                    "bbox_x2": f"{x2:.2f}",
                    "bbox_y2": f"{y2:.2f}",
                    "crop_path": det.crop_path,
                    "status": det.status,
                }
            )


def run_single_cell_crop_pipeline(
    *,
    video_path: Path,
    detection_model_path: Path,
    output_root: Path,
    csv_path: Path,
    wbc_classifier_path: Path | None = None,
    every_n_frames: int = 1,
    every_seconds: float | None = None,
    confidence: float = 0.25,
    low_confidence: float = 0.25,
    wbc_confidence: float = 0.70,
    device: str | None = "auto",
    imgsz: int = 640,
    padding: int | float = 0.10,
    duplicate_iou: float = 0.35,
    duplicate_centroid: float = 60.0,
    track_gap: int = 8,
) -> dict[str, int | str]:
    configure_models(
        detection_model_path,
        wbc_classifier_path=wbc_classifier_path,
        confidence=confidence,
        wbc_confidence=wbc_confidence,
        device=device,
        imgsz=imgsz,
    )

    video_path = Path(video_path)
    video_name = video_path.stem
    date_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    all_results: list[CellDetection] = []
    candidates: list[CellDetection] = []

    for video_frame in parse_video(video_path, every_n_frames=every_n_frames, every_seconds=every_seconds):
        frame_detections = detect_cells(video_frame.frame)
        frame_bboxes = [det.bounding_box for det in frame_detections]
        for det in frame_detections:
            det.frame_index = video_frame.frame_index
            det.timestamp = video_frame.timestamp
            det.frame = video_frame.frame
            det.video_name = video_name
            det.quality_score = laplacian_variance(
                video_frame.frame[
                    max(0, int(det.bounding_box[1])) : max(0, int(det.bounding_box[3])),
                    max(0, int(det.bounding_box[0])) : max(0, int(det.bounding_box[2])),
                ]
            )
            if det.cell_class not in CANONICAL_CLASSES or det.confidence < low_confidence:
                det.status = "low_confidence_skipped"
            elif is_crop_ambiguous(det.bounding_box, frame_bboxes):
                det.status = "ambiguous_skipped"
            else:
                candidates.append(det)
            all_results.append(det)

    kept = remove_duplicate_cells(
        candidates,
        iou_threshold=duplicate_iou,
        centroid_threshold=duplicate_centroid,
        max_frame_gap=track_gap,
    )

    kept_ids = {id(det) for det in kept}
    for det in all_results:
        if det.status == "candidate" and id(det) not in kept_ids:
            det.status = "duplicate_skipped"

    for det in kept:
        assert det.frame is not None
        frame_dets = [item for item in all_results if item.frame_index == det.frame_index]
        all_bboxes = [item.bounding_box for item in frame_dets]
        crop = crop_single_cell(det.frame, det.bounding_box, all_bboxes, padding)
        if crop is None:
            det.status = "ambiguous_skipped"
            continue
        crop_path = classify_and_save_crop(
            crop,
            det.cell_class,
            video_name,
            date_time,
            output_root=output_root,
            frame_index=det.frame_index,
            cell_id=det.cell_id,
            confidence=det.confidence,
        )
        det.crop_path = str(crop_path)
        det.status = "saved"

    export_csv(all_results, csv_path)

    status_counts = {status: 0 for status in ("saved", "duplicate_skipped", "ambiguous_skipped", "low_confidence_skipped")}
    for det in all_results:
        if det.status in status_counts:
            status_counts[det.status] += 1

    return {
        "video_name": video_name,
        "date_time": date_time,
        "total_detections": len(all_results),
        **status_counts,
        "csv_path": str(Path(csv_path).resolve()),
        "output_root": str(Path(output_root).resolve()),
    }

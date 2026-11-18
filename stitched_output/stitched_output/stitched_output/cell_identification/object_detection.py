from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import cv2
import numpy as np

from msh_runtime import local_app_data_dir

try:
    from cell_stitching_project.text_overlay import get_text_size, put_text
except Exception:
    def get_text_size(text: str, font_scale: float, thickness: int):
        (text_width, text_height), baseline = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness)
        return int(text_width), int(text_height), int(baseline)

    def put_text(
        image_bgr: np.ndarray,
        text: str,
        origin: tuple[int, int],
        font_scale: float,
        color_bgr: tuple[int, int, int],
        thickness: int = 1,
    ) -> None:
        cv2.putText(image_bgr, text, origin, cv2.FONT_HERSHEY_SIMPLEX, font_scale, color_bgr, thickness)

try:
    from ultralytics import YOLO
except Exception:  # pragma: no cover - optional during helper-only tests
    YOLO = None  # type: ignore[assignment]


@dataclass
class Detection:
    x1: int
    y1: int
    x2: int
    y2: int
    conf: float
    cls_id: int
    label: str
    wbc_subtype: str | None = None
    wbc_subtype_conf: float | None = None

    @property
    def display_label(self) -> str:
        if self.wbc_subtype:
            return f"WBC/{self.wbc_subtype}"
        return self.label


WBC_SUBTYPE_CLASS_NAMES = ("neutrophil", "lymphocyte", "monocyte", "eosinophil", "basophil")
_WBC_LABEL_ALIASES = {"wbc", "white_blood_cell", "white_blood_cell_(wbc)", "0"}


def is_wbc_label(label: str, cls_id: int | None = None) -> bool:
    normalized = str(label or "").strip().lower().replace("-", "_").replace(" ", "_")
    return normalized in _WBC_LABEL_ALIASES or cls_id == 0


def resolve_wbc_subtype_model_path(project_root: Path, requested: str | None = None) -> str | None:
    def resolve_candidate(candidate: Path) -> str | None:
        if candidate.is_file():
            return str(candidate)
        if candidate.is_dir():
            for weight_name in ("best.pt", "last.pt"):
                weight_path = candidate / "weights" / weight_name
                if weight_path.is_file():
                    return str(weight_path)
        return None

    if requested:
        candidate = Path(requested)
        resolved = resolve_candidate(candidate)
        if resolved is not None:
            return resolved
        project_candidate = project_root / requested
        resolved = resolve_candidate(project_candidate)
        if resolved is not None:
            return resolved
        return requested

    workspace_root = project_root.parents[2] if len(project_root.parents) >= 3 else project_root
    candidates = [
        local_app_data_dir() / "models" / "wbc_5cls_1000x_cls.pt",
        project_root / "models" / "wbc_5cls_1000x_cls.pt",
        workspace_root / "staging" / "train" / "wbc_5cls_1000x_cls_20260520",
        workspace_root / "output" / "training" / "wbc_400x" / "wbc_5cls_400x_yolov8s_highconf",
        workspace_root / "staging" / "train" / "wbc_5cls_400x_yolov8s_highconf",
        workspace_root / "staging" / "train" / "wbc_5cls_400x_refine_gpu_20260519",
        project_root / "models" / "wbc_5cls_400x_yolov8s.pt",
        project_root / "models" / "wbc_5cls_400x_yolov8n.pt",
        project_root / "models" / "wbc_5cls_yolov8n.pt",
    ]
    for candidate in candidates:
        resolved = resolve_candidate(candidate)
        if resolved is not None:
            return resolved
    return None


class WBCSubtypeClassifier:
    def __init__(self, model_path: str, min_confidence: float = 0.0) -> None:
        if YOLO is None:
            raise RuntimeError("ultralytics is not installed; WBC subtype model cannot be loaded.")
        self.model_path = str(model_path)
        self.min_confidence = float(max(0.0, min(1.0, min_confidence)))
        self._model = YOLO(self.model_path)

    def classify(self, crop_bgr: np.ndarray) -> tuple[str, float] | None:
        if crop_bgr.size == 0:
            return None
        results = self._model.predict(source=crop_bgr, conf=max(0.01, self.min_confidence), verbose=False)
        if not results:
            return None
        result = results[0]
        names: Any = getattr(result, "names", {})

        probs = getattr(result, "probs", None)
        if probs is not None and getattr(probs, "top1", None) is not None:
            cls_id = int(probs.top1)
            conf = float(probs.top1conf)
            label = _name_from_id(names, cls_id)
            if label in WBC_SUBTYPE_CLASS_NAMES and conf >= self.min_confidence:
                return label, conf

        boxes = getattr(result, "boxes", None)
        if boxes is None:
            return None
        best: tuple[str, float] | None = None
        for box in boxes:
            conf = float(box.conf[0]) if box.conf is not None else 0.0
            cls_id = int(box.cls[0]) if box.cls is not None else -1
            label = _name_from_id(names, cls_id)
            if label not in WBC_SUBTYPE_CLASS_NAMES or conf < self.min_confidence:
                continue
            if best is None or conf > best[1]:
                best = (label, conf)
        return best


def _name_from_id(names: Any, cls_id: int) -> str:
    if isinstance(names, dict):
        return str(names.get(cls_id, cls_id))
    if isinstance(names, Sequence) and 0 <= cls_id < len(names):
        return str(names[cls_id])
    return str(cls_id)


class ObjectDetector:
    def __init__(
        self,
        model_path: str = "yolov8n.pt",
        conf_threshold: float = 0.25,
        iou_threshold: float = 0.45,
        max_det: int = 300,
        wbc_subtype_model_path: str | None = None,
        wbc_subtype_min_conf: float = 0.0,
    ) -> None:
        self.model_path = model_path
        self.conf_threshold = float(conf_threshold)
        self.iou_threshold = float(iou_threshold)
        self.max_det = int(max_det)
        self.wbc_subtype_model_path = str(wbc_subtype_model_path) if wbc_subtype_model_path else None
        self.wbc_subtype_min_conf = float(max(0.0, min(1.0, wbc_subtype_min_conf)))
        self._model: YOLO | None = None
        self._wbc_subtype_classifier: WBCSubtypeClassifier | None = None

    def _ensure_model(self) -> YOLO:
        if YOLO is None:
            raise RuntimeError("ultralytics is not installed; object detection model cannot be loaded.")
        if self._model is None:
            self._model = YOLO(self.model_path)
        return self._model

    def _ensure_wbc_subtype_classifier(self) -> WBCSubtypeClassifier | None:
        if not self.wbc_subtype_model_path:
            return None
        if self._wbc_subtype_classifier is None:
            self._wbc_subtype_classifier = WBCSubtypeClassifier(
                self.wbc_subtype_model_path,
                min_confidence=self.wbc_subtype_min_conf,
            )
        return self._wbc_subtype_classifier

    def detect(self, frame: np.ndarray, conf_threshold: float | None = None) -> list[Detection]:
        model = self._ensure_model()
        conf = self.conf_threshold if conf_threshold is None else float(conf_threshold)
        results = model.predict(
            source=frame,
            conf=conf,
            iou=self.iou_threshold,
            max_det=self.max_det,
            verbose=False,
        )
        if not results:
            return []

        result = results[0]
        boxes = getattr(result, "boxes", None)
        if boxes is None:
            return []

        names: Any = getattr(result, "names", {})
        detections: list[Detection] = []
        for box in boxes:
            xyxy = box.xyxy[0].tolist()
            x1, y1, x2, y2 = [int(round(v)) for v in xyxy]
            conf_val = float(box.conf[0]) if box.conf is not None else 0.0
            cls_id = int(box.cls[0]) if box.cls is not None else -1
            if isinstance(names, dict):
                label = str(names.get(cls_id, cls_id))
            elif isinstance(names, Sequence) and 0 <= cls_id < len(names):
                label = str(names[cls_id])
            else:
                label = str(cls_id)
            detections.append(
                Detection(
                    x1=max(0, x1),
                    y1=max(0, y1),
                    x2=max(0, x2),
                    y2=max(0, y2),
                    conf=conf_val,
                    cls_id=cls_id,
                    label=label,
                )
            )
        self._apply_wbc_subtypes(frame, detections)
        return detections

    def _apply_wbc_subtypes(self, frame: np.ndarray, detections: list[Detection]) -> None:
        classifier = self._ensure_wbc_subtype_classifier()
        if classifier is None:
            return
        height, width = frame.shape[:2]
        for det in detections:
            if not is_wbc_label(det.label, det.cls_id):
                continue
            x1 = max(0, min(width, det.x1))
            y1 = max(0, min(height, det.y1))
            x2 = max(0, min(width, det.x2))
            y2 = max(0, min(height, det.y2))
            if x2 <= x1 or y2 <= y1:
                continue
            subtype = classifier.classify(frame[y1:y2, x1:x2])
            if subtype is None:
                continue
            det.wbc_subtype, det.wbc_subtype_conf = subtype


def annotate_detections(
    frame: np.ndarray,
    detections: list[Detection],
    show_conf: bool = True,
    color: tuple[int, int, int] = (0, 255, 0),
    font_scale: float = 0.55,
    box_thickness: int = 2,
    text_thickness: int = 2,
) -> np.ndarray:
    annotated = frame.copy()
    for det in detections:
        x1 = max(0, min(det.x1, annotated.shape[1] - 1))
        y1 = max(0, min(det.y1, annotated.shape[0] - 1))
        x2 = max(0, min(det.x2, annotated.shape[1] - 1))
        y2 = max(0, min(det.y2, annotated.shape[0] - 1))
        if x2 <= x1 or y2 <= y1:
            continue

        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, box_thickness)
        label_text = det.display_label if hasattr(det, "display_label") else det.label
        if show_conf and getattr(det, "wbc_subtype_conf", None) is not None:
            label = f"{label_text} {det.conf:.2f}/{float(det.wbc_subtype_conf):.2f}"
        else:
            label = label_text if not show_conf else f"{label_text} {det.conf:.2f}"
        tw, th, baseline = get_text_size(label, font_scale=font_scale, thickness=text_thickness)
        top = max(0, y1 - th - baseline - 8)
        cv2.rectangle(annotated, (x1, top), (x1 + tw, y1), color, -1)
        put_text(
            annotated,
            label,
            (x1, max(12, y1 - 4)),
            font_scale,
            (0, 0, 0),
            text_thickness,
        )
    return annotated


def build_detection_mask(
    image_shape: tuple[int, int] | tuple[int, int, int],
    detections: list[Detection],
    expand_ratio: float = 0.10,
) -> np.ndarray:
    return build_detection_union_mask(image_shape, detections, expand_ratio=expand_ratio)


def build_detection_union_mask(
    image_shape: tuple[int, int] | tuple[int, int, int],
    detections: list[Detection],
    expand_ratio: float = 0.0,
) -> np.ndarray:
    h = int(image_shape[0])
    w = int(image_shape[1])
    mask = np.zeros((h, w), dtype=np.uint8)
    if not detections:
        return mask

    expand_ratio = max(0.0, expand_ratio)
    expand_px = 0 if expand_ratio <= 0.0 else max(4, int(round(min(h, w) * expand_ratio)))
    for det in detections:
        x1 = max(0, det.x1 - expand_px)
        y1 = max(0, det.y1 - expand_px)
        x2 = min(w, det.x2 + expand_px)
        y2 = min(h, det.y2 + expand_px)
        if x2 <= x1 or y2 <= y1:
            continue
        mask[y1:y2, x1:x2] = 255
    return mask


def compute_detection_coverage_ratio(
    image_shape: tuple[int, int] | tuple[int, int, int],
    detections: list[Detection],
    expand_ratio: float = 0.0,
) -> float:
    h = int(image_shape[0])
    w = int(image_shape[1])
    total_area = max(1, h * w)
    union_mask = build_detection_union_mask(image_shape, detections, expand_ratio=expand_ratio)
    covered_area = int(np.count_nonzero(union_mask))
    return float(covered_area) / float(total_area)


def resolve_detect_model_path(project_root: Path, requested: str | None = None) -> str:
    def resolve_candidate(candidate: Path) -> str | None:
        if candidate.is_file():
            return str(candidate)
        if candidate.is_dir():
            for weight_name in ("best.pt", "last.pt"):
                weight_path = candidate / "weights" / weight_name
                if weight_path.is_file():
                    return str(weight_path)
        return None

    if requested:
        candidate = Path(requested)
        resolved = resolve_candidate(candidate)
        if resolved is not None:
            return resolved
        project_candidate = project_root / requested
        resolved = resolve_candidate(project_candidate)
        if resolved is not None:
            return resolved
        return requested

    workspace_root = project_root.parents[2] if len(project_root.parents) >= 3 else project_root

    candidates = [
        local_app_data_dir() / "models" / "wbc_focus_yolov8n_e_20260611.pt",
        local_app_data_dir() / "models" / "blood_cells_3cls_yolov8n_20260429.pt",
        local_app_data_dir() / "models" / "best.pt",
        project_root / "models" / "wbc_focus_yolov8n_e_20260611.pt",
        project_root / "models" / "blood_cells_3cls_yolov8n_20260429.pt",
        workspace_root / "staging" / "train" / "blood_cells_3cls_yolov8n_20260429",
        project_root / "models" / "blood_cells_3cls_400x_refine_20260517.pt",
        workspace_root / "staging" / "train" / "blood_cells_3cls_400x_refine_gpu_20260517",
        project_root / "models" / "cell_detect_1000x_v2.pt",
        project_root / "models" / "wbc_single_smoke.pt",
        project_root / "models" / "wbc_single_best.pt",
        project_root / "models" / "best.pt",
        project_root / "best.pt",
        project_root / "models" / "yolov8n.pt",
        project_root / "yolov8n.pt",
    ]
    for candidate in candidates:
        resolved = resolve_candidate(candidate)
        if resolved is not None:
            return resolved

    detect_runs_root = project_root / "outputs" / "runs" / "detect"
    if detect_runs_root.exists():
        preferred = sorted(detect_runs_root.glob("**/weights/best.pt"))
        if preferred:
            return str(preferred[-1])
        fallback = sorted(detect_runs_root.glob("**/weights/last.pt"))
        if fallback:
            return str(fallback[-1])
    return "yolov8n.pt"

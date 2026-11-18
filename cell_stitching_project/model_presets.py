from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _models_root() -> Path:
    return _workspace_root() / "stitched_output" / "stitched_output" / "stitched_output" / "models"


def _dataset_root() -> Path:
    return _workspace_root() / "datasets" / "wbc_400x"


@dataclass(frozen=True, slots=True)
class DetectionModelPreset:
    name: str
    backend: str
    model_path: Path
    class_file: Path | None = None
    confidence: float | None = None
    class_confidence: tuple[float, ...] | None = None
    iou_threshold: float | None = None
    stabilization_window: int = 0
    stabilization_threshold: int | None = None
    stable_event_cooldown: int = 0
    description: str = ""


DETECTION_PRESETS: dict[str, DetectionModelPreset] = {
    "wbc_400x": DetectionModelPreset(
        name="wbc_400x",
        backend="ultralytics",
        model_path=_models_root() / "wbc400_wbc_only_yolov8n_20260619_expanded_1000x.pt",
        class_file=_models_root() / "wbc_400x_labels.txt",
        confidence=0.30,
        iou_threshold=0.45,
        stabilization_window=5,
        stabilization_threshold=3,
        stable_event_cooldown=10,
        description="Single-class YOLOv8 model for 400x white-blood-cell detection.",
    ),
    "wbc_5cls": DetectionModelPreset(
        name="wbc_5cls",
        backend="ultralytics",
        model_path=_models_root() / "wbc_5cls_yolov8n.pt",
        class_file=_dataset_root() / "classes.txt",
        confidence=0.35,
        iou_threshold=0.45,
        stabilization_window=5,
        stabilization_threshold=3,
        stable_event_cooldown=10,
        description="YOLOv8n model trained for five major white-blood-cell classes.",
    ),
    "wbc_5cls_400x": DetectionModelPreset(
        name="wbc_5cls_400x",
        backend="ultralytics",
        model_path=_models_root() / "wbc_5cls_400x_yolov8s.pt",
        class_file=_dataset_root() / "classes.txt",
        confidence=0.25,
        iou_threshold=0.45,
        stabilization_window=5,
        stabilization_threshold=3,
        stable_event_cooldown=10,
        description="YOLOv8n model fine-tuned for 400x five-class white-blood-cell recognition.",
    ),
    "blood_cells_3cls": DetectionModelPreset(
        name="blood_cells_3cls",
        backend="ultralytics",
        model_path=_models_root() / "blood_cells_3cls_yolov8n_20260429.pt",
        class_file=_models_root() / "blood_cells_3cls_labels.txt",
        confidence=0.35,
        class_confidence=(0.50, 0.65, 0.45),
        iou_threshold=0.45,
        stabilization_window=5,
        stabilization_threshold=3,
        stable_event_cooldown=10,
        description="YOLOv8n 20260429 default model for 400x slide blood-cell detection (WBC, RBC, Platelets).",
    ),
    "waste_sorting_v1": DetectionModelPreset(
        name="waste_sorting_v1",
        backend="ultralytics",
        model_path=_models_root() / "waste_sorting_v1_best.pt",
        class_file=_models_root() / "waste_sorting_v1_labels.txt",
        confidence=0.5,
        iou_threshold=0.45,
        stabilization_window=10,
        stabilization_threshold=7,
        stable_event_cooldown=15,
        description="Integrated waste-sorting YOLOv8 model (power, soda, paper, wine, wine2, vodka).",
    ),
}


DEFAULT_LIVE_DETECTION_PRESET = "blood_cells_3cls"


def available_detection_preset_names() -> tuple[str, ...]:
    return tuple(sorted(DETECTION_PRESETS))


def resolve_detection_preset(name: str) -> DetectionModelPreset:
    preset = DETECTION_PRESETS.get(str(name).strip())
    if preset is None:
        available = ", ".join(available_detection_preset_names())
        raise ValueError(f"Unknown detection preset '{name}'. Available presets: {available}")
    return preset

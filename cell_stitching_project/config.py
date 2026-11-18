from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from .runtime import RuntimeInfo


VALID_ALIGNMENT_METHODS = ("auto", "phase", "ecc", "orb", "sift")
VALID_BLENDING_METHODS = ("auto", "average", "feather", "multiband")
VALID_PERFORMANCE_PROFILES = ("quality", "balanced", "resource")
VALID_INPUT_ORDERS = ("auto", "natural", "coordinates")
VALID_COORDINATE_PRIORITIES = ("row-major", "column-major")

PROFILE_DEFAULTS: dict[str, dict[str, object]] = {
    "quality": {
        "max_alignment_long_side": 2560,
        "gpu_memory_budget_mb": 1792,
    },
    "balanced": {
        "max_alignment_long_side": 2048,
        "gpu_memory_budget_mb": 1536,
    },
    "resource": {
        "max_alignment_long_side": 1536,
        "gpu_memory_budget_mb": 1024,
    },
}


def resolve_detection_model_candidate(candidate: Path) -> Path | None:
    if candidate.is_file():
        return candidate.resolve()
    if candidate.is_dir():
        for weight_name in ("best.pt", "last.pt"):
            weight_path = candidate / "weights" / weight_name
            if weight_path.is_file():
                return weight_path.resolve()
    return None


def default_detection_model_candidates(workspace_root: Path | None = None) -> tuple[Path, ...]:
    root = workspace_root or Path(__file__).resolve().parents[1]
    model_root = root / "stitched_output" / "stitched_output" / "stitched_output" / "models"
    return (
        model_root / "blood_cells_3cls_yolov8n_20260429.pt",
        model_root / "blood_cells_3cls_400x_refine_20260517.pt",
        root / "staging" / "train" / "blood_cells_3cls_400x_refine_gpu_20260517",
        root / "staging" / "train" / "blood_cells_3cls_yolov8n_20260429",
        model_root / "wbc_5cls_400x_yolov8s.pt",
        model_root / "wbc_5cls_400x_yolov8n.pt",
        model_root / "wbc_5cls_yolov8n.pt",
        model_root / "wbc_5cls_400x.onnx",
        model_root / "wbc_5cls.onnx",
        model_root / "cell_detect_wbc_single_20260415.pt",
        model_root / "cell_detect_1000x_v2.pt",
        model_root / "wbc_single_smoke.pt",
        model_root / "yolov8n.pt",
    )


def resolve_default_detection_model_path(workspace_root: Path | None = None) -> str | None:
    for candidate in default_detection_model_candidates(workspace_root):
        resolved = resolve_detection_model_candidate(candidate)
        if resolved is not None:
            return str(resolved)
    return None


@dataclass(slots=True)
class StitchingConfig:
    """Runtime configuration shared by the CLI and the legacy Tkinter UI."""

    input_dir: str | Path
    output_dir: str | Path = Path("output")
    input_paths: list[str] | None = None
    image_extension: str = "auto"
    input_order: Literal["auto", "natural", "coordinates"] = "auto"
    coordinate_priority: Literal["row-major", "column-major"] = "row-major"
    alignment_method: str = "auto"
    blending_method: str = "auto"
    use_grayscale: bool = True
    use_denoise: bool = True
    use_clahe: bool = True
    use_flatfield: bool = True
    normalize: bool = False
    max_rotation: float = 3.0
    overlap_ratio: float = 0.40
    save_debug_images: bool = True
    use_yolo_guidance: bool = False
    yolo_model_path: str | None = None
    yolo_confidence: float = 0.25
    post_stitch_detection_enabled: bool = True
    post_stitch_detection_model_path: str | None = None
    post_stitch_detection_class_file: str | None = None
    post_stitch_detection_confidence: float = 0.35
    post_stitch_detection_iou_threshold: float = 0.45
    post_stitch_detection_imgsz: int = 512
    post_stitch_detection_output_dirname: str = "post_stitch_detection"
    output_format: str = "png"
    result_name: str = "stitched_result.png"
    overlay_name: str = "overlay_preview.png"
    shifts_json_name: str = "shifts.json"
    shifts_csv_name: str = "shifts.csv"
    log_name: str = "stitch_log.txt"
    debug_matches_dirname: str = "debug_matches"
    intermediate_dirname: str = "intermediate"
    multiband_levels: int = 4
    denoise_strength: int = 7
    clahe_clip_limit: float = 2.0
    clahe_tile_grid_size: int = 8
    flatfield_sigma_ratio: float = 0.08
    normalize_percentiles: tuple[float, float] = (1.0, 99.0)
    detector_expand_ratio: float = 0.08
    feature_max_keypoints: int = 4000
    feature_min_matches: int = 8
    candidate_min_pixels: int = 64
    max_relative_shift: float = 0.45
    max_images: int | None = None
    prefer_gpu: bool = True
    compute_device: Literal["auto", "cuda", "cpu"] = "auto"
    gpu_fallback_allowed: bool = True
    gpu_memory_budget_mb: int | None = None
    yolo_device: str | int = "auto"
    phase_score_floor: float = 0.01
    max_alignment_long_side: int | None = None
    performance_profile: Literal["quality", "balanced", "resource"] = "balanced"
    warnings: list[str] = field(default_factory=list)
    runtime: RuntimeInfo | None = None

    def __post_init__(self) -> None:
        self.input_dir = Path(self.input_dir)
        self.output_dir = Path(self.output_dir)
        self.image_extension = (self.image_extension or "auto").lower()
        self.input_order = str(self.input_order).lower()  # type: ignore[assignment]
        self.coordinate_priority = str(self.coordinate_priority).lower()  # type: ignore[assignment]
        self.alignment_method = self.alignment_method.lower()
        self.blending_method = self.blending_method.lower()
        self.output_format = self.output_format.lower()
        self.overlap_ratio = float(min(0.95, max(0.05, self.overlap_ratio)))
        self.max_rotation = float(max(0.0, self.max_rotation))
        self.yolo_confidence = float(min(1.0, max(0.01, self.yolo_confidence)))
        self.post_stitch_detection_confidence = float(min(1.0, max(0.01, self.post_stitch_detection_confidence)))
        self.post_stitch_detection_iou_threshold = float(min(1.0, max(0.01, self.post_stitch_detection_iou_threshold)))
        self.post_stitch_detection_imgsz = int(max(32, self.post_stitch_detection_imgsz))
        self.multiband_levels = int(max(1, self.multiband_levels))
        self.compute_device = str(self.compute_device).lower()  # type: ignore[assignment]
        self.performance_profile = str(self.performance_profile).lower()  # type: ignore[assignment]
        if self.performance_profile not in VALID_PERFORMANCE_PROFILES:
            raise ValueError(f"Unsupported performance profile: {self.performance_profile}")
        if self.input_order not in VALID_INPUT_ORDERS:
            raise ValueError(f"Unsupported input order: {self.input_order}")
        if self.coordinate_priority not in VALID_COORDINATE_PRIORITIES:
            raise ValueError(f"Unsupported coordinate priority: {self.coordinate_priority}")
        self._apply_performance_profile_defaults()
        self.gpu_memory_budget_mb = int(max(256, int(self.gpu_memory_budget_mb or 1536)))
        self.phase_score_floor = float(max(0.0, self.phase_score_floor))
        if self.max_alignment_long_side is not None:
            self.max_alignment_long_side = int(max(256, self.max_alignment_long_side))
        if self.alignment_method not in VALID_ALIGNMENT_METHODS:
            raise ValueError(f"Unsupported alignment method: {self.alignment_method}")
        if self.blending_method not in VALID_BLENDING_METHODS:
            raise ValueError(f"Unsupported blending method: {self.blending_method}")
        if self.compute_device not in {"auto", "cuda", "cpu"}:
            raise ValueError(f"Unsupported compute device: {self.compute_device}")
        if self.output_format not in {"png", "tif", "tiff"}:
            raise ValueError(f"Unsupported output format: {self.output_format}")
        expected_suffix = ".tiff" if self.output_format == "tiff" else f".{self.output_format}"
        result_path = Path(self.result_name)
        if result_path.suffix.lower() != expected_suffix:
            self.result_name = f"{result_path.stem or 'stitched_result'}{expected_suffix}"
        if self.max_images is not None:
            self.max_images = int(max(1, self.max_images))
        if self.input_paths:
            self.input_paths = [str(Path(p)) for p in self.input_paths]
        default_model_path = resolve_default_detection_model_path()
        if self.yolo_model_path is None and default_model_path is not None:
            self.yolo_model_path = default_model_path
        if self.post_stitch_detection_model_path is None and self.yolo_model_path is not None:
            self.post_stitch_detection_model_path = self.yolo_model_path

    def _apply_performance_profile_defaults(self) -> None:
        profile = PROFILE_DEFAULTS[self.performance_profile]
        if self.max_alignment_long_side is None:
            self.max_alignment_long_side = int(profile["max_alignment_long_side"])
        if self.gpu_memory_budget_mb is None:
            self.gpu_memory_budget_mb = int(profile["gpu_memory_budget_mb"])

    def with_warning(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)

    def record_fallback(self, stage: str, reason: str, requested_device: str, actual_device: str) -> None:
        if self.runtime is not None:
            self.runtime.record_fallback(stage, reason, requested_device, actual_device)
        self.with_warning(f"{stage}: {reason}")

    def describe(self) -> dict[str, object]:
        snapshot = {
            "input_dir": str(self.input_dir),
            "output_dir": str(self.output_dir),
            "input_paths": list(self.input_paths or []),
            "image_extension": self.image_extension,
            "input_order": self.input_order,
            "coordinate_priority": self.coordinate_priority,
            "alignment_method": self.alignment_method,
            "blending_method": self.blending_method,
            "use_grayscale": self.use_grayscale,
            "use_denoise": self.use_denoise,
            "use_clahe": self.use_clahe,
            "use_flatfield": self.use_flatfield,
            "normalize": self.normalize,
            "max_rotation": self.max_rotation,
            "overlap_ratio": self.overlap_ratio,
            "save_debug_images": self.save_debug_images,
            "use_yolo_guidance": self.use_yolo_guidance,
            "yolo_model_path": self.yolo_model_path,
            "yolo_confidence": self.yolo_confidence,
            "post_stitch_detection_enabled": self.post_stitch_detection_enabled,
            "post_stitch_detection_model_path": self.post_stitch_detection_model_path,
            "post_stitch_detection_class_file": self.post_stitch_detection_class_file,
            "post_stitch_detection_confidence": self.post_stitch_detection_confidence,
            "post_stitch_detection_iou_threshold": self.post_stitch_detection_iou_threshold,
            "post_stitch_detection_imgsz": self.post_stitch_detection_imgsz,
            "post_stitch_detection_output_dirname": self.post_stitch_detection_output_dirname,
            "output_format": self.output_format,
            "result_name": self.result_name,
            "overlay_name": self.overlay_name,
            "shifts_json_name": self.shifts_json_name,
            "shifts_csv_name": self.shifts_csv_name,
            "multiband_levels": self.multiband_levels,
            "max_images": self.max_images,
            "prefer_gpu": self.prefer_gpu,
            "compute_device": self.compute_device,
            "gpu_fallback_allowed": self.gpu_fallback_allowed,
            "gpu_memory_budget_mb": self.gpu_memory_budget_mb,
            "yolo_device": str(self.yolo_device),
            "phase_score_floor": self.phase_score_floor,
            "max_alignment_long_side": self.max_alignment_long_side,
            "performance_profile": self.performance_profile,
        }
        if self.runtime is not None:
            snapshot["runtime"] = self.runtime.as_dict()
        if self.warnings:
            snapshot["warnings"] = list(self.warnings)
        return snapshot


def make_config_from_args(namespace: object) -> StitchingConfig:
    source = vars(namespace)
    return StitchingConfig(
        input_dir=source["input_dir"],
        output_dir=source["output_dir"],
        image_extension=source["image_extension"],
        input_order=source.get("input_order", "auto"),
        coordinate_priority=source.get("coordinate_priority", "row-major"),
        alignment_method="auto",
        blending_method="auto",
        use_grayscale=True,
        use_denoise=True,
        use_clahe=True,
        use_flatfield=True,
        normalize=False,
        max_rotation=3.0,
        overlap_ratio=0.40,
        save_debug_images=True,
        use_yolo_guidance=True,
        yolo_model_path=None,
        yolo_confidence=0.25,
        post_stitch_detection_enabled=not source.get("disable_post_stitch_detection", False),
        post_stitch_detection_model_path=source.get("post_detection_model_path"),
        post_stitch_detection_class_file=source.get("post_detection_class_file"),
        post_stitch_detection_confidence=source.get("post_detection_confidence", 0.35),
        post_stitch_detection_iou_threshold=source.get("post_detection_iou_threshold", 0.45),
        post_stitch_detection_imgsz=source.get("post_detection_imgsz", 512),
        output_format=source["output_format"],
        max_images=source.get("max_images"),
        prefer_gpu=source.get("prefer_gpu", True),
        compute_device=source.get("compute_device", "auto"),
        gpu_fallback_allowed=not source.get("disable_gpu_fallback", False),
        gpu_memory_budget_mb=source.get("gpu_memory_budget_mb"),
        yolo_device=source.get("yolo_device", "auto"),
        max_alignment_long_side=source.get("max_alignment_long_side"),
        performance_profile=source.get("performance_profile", "balanced"),
    )

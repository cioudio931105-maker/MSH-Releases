from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class StitchConfig:
    input_dir: Path
    output_dir: Path
    coords_csv: Path | None = None
    excluded_filenames: tuple[str, ...] = ()
    overlap_ratio: float = 0.15
    work_scale: float = 0.35
    max_work_side: int = 1800
    feature_method: str = "orb"
    blend_mode: str = "feather"
    use_cuda: str = "auto"
    invert_x: bool = False
    invert_y: bool = False
    debug: bool = True
    export_format: str = "tif"
    feather_width: int = 96
    memmap_threshold_mb: int = 1400
    crop: bool = True
    min_overlap_px: int = 24
    ncc_search_radius: int = 90
    ncc_search_step: int = 6
    max_features: int = 6000
    min_feature_matches: int = 12
    feature_override_score: float = 0.45
    feature_override_inliers: int = 80
    feature_override_max_orthogonal_px: float = 70.0
    small_feature_weight: float = 0.0
    use_detection_features: bool = True
    detection_feature_min_matches: int = 3
    detection_feature_cluster_tolerance_px: float = 45.0
    ratio_test: float = 0.75
    ecc_iterations: int = 80
    ecc_eps: float = 1e-5
    stage_anchor_weight: float = 0.04
    preview_long_side: int = 2400
    min_edge_score: float = 0.10
    preserve_rejected_gaps: bool = True
    rejected_gap_px: int = 80
    placement_mode: str = "global"
    progressive_tolerance_px: float = 110.0
    progressive_min_anchor_count: int = 1
    drop_unconfirmed_tiles: bool = False
    progressive_anchor: str | None = None
    locked_placements_csv: Path | None = None

    def validate(self) -> None:
        if not self.input_dir.exists():
            raise FileNotFoundError(f"Input folder not found: {self.input_dir}")
        if not 0.0 <= self.overlap_ratio < 0.8:
            raise ValueError("overlap_ratio must be between 0.0 and 0.8")
        if not 0.05 <= self.work_scale <= 1.0:
            raise ValueError("work_scale must be between 0.05 and 1.0")
        if self.use_cuda not in {"auto", "on", "off"}:
            raise ValueError("use_cuda must be auto, on, or off")
        if self.blend_mode not in {"feather", "max_weight"}:
            raise ValueError("blend_mode must be feather or max_weight")
        if self.min_edge_score < 0.0:
            raise ValueError("min_edge_score must be non-negative")
        if self.rejected_gap_px < 0:
            raise ValueError("rejected_gap_px must be non-negative")
        if self.feature_override_score < 0.0:
            raise ValueError("feature_override_score must be non-negative")
        if self.feature_override_max_orthogonal_px < 0.0:
            raise ValueError("feature_override_max_orthogonal_px must be non-negative")
        if not 0.0 <= self.small_feature_weight <= 1.0:
            raise ValueError("small_feature_weight must be between 0.0 and 1.0")
        if self.detection_feature_min_matches < 1:
            raise ValueError("detection_feature_min_matches must be at least 1")
        if self.detection_feature_cluster_tolerance_px <= 0.0:
            raise ValueError("detection_feature_cluster_tolerance_px must be positive")
        if self.placement_mode not in {"global", "progressive"}:
            raise ValueError("placement_mode must be global or progressive")
        if self.progressive_tolerance_px <= 0.0:
            raise ValueError("progressive_tolerance_px must be positive")
        if self.progressive_min_anchor_count < 1:
            raise ValueError("progressive_min_anchor_count must be at least 1")

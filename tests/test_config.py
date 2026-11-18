from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cell_stitching_project.config import resolve_default_detection_model_path
from cell_stitching_project.model_presets import DEFAULT_LIVE_DETECTION_PRESET, resolve_detection_preset


class ConfigTests(unittest.TestCase):
    def test_resolve_default_detection_model_prefers_selected_project_model(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            refined_run = root / "staging" / "train" / "blood_cells_3cls_400x_refine_gpu_20260517"
            refined_weights = refined_run / "weights"
            refined_weights.mkdir(parents=True, exist_ok=True)
            refined_best = refined_weights / "best.pt"
            staging_run = root / "staging" / "train" / "blood_cells_3cls_yolov8n_20260429"
            staging_weights = staging_run / "weights"
            staging_weights.mkdir(parents=True, exist_ok=True)
            staging_best = staging_weights / "best.pt"
            model_root = root / "stitched_output" / "stitched_output" / "stitched_output" / "models"
            model_root.mkdir(parents=True, exist_ok=True)
            fallback = model_root / "yolov8n.pt"
            previous = model_root / "cell_detect_1000x_v2.pt"
            wbc_single = model_root / "cell_detect_wbc_single_20260415.pt"
            preferred = model_root / "blood_cells_3cls_yolov8n_20260429.pt"
            refined_export = model_root / "blood_cells_3cls_400x_refine_20260517.pt"
            refined_best.write_bytes(b"refined-preferred")
            staging_best.write_bytes(b"staging-preferred")
            fallback.write_bytes(b"fallback")
            previous.write_bytes(b"previous")
            wbc_single.write_bytes(b"wbc-single")
            preferred.write_bytes(b"preferred")
            refined_export.write_bytes(b"refined-export")

            resolved = resolve_default_detection_model_path(root)

            self.assertEqual(resolved, str(preferred.resolve()))

    def test_default_live_detection_preset_is_resolvable(self) -> None:
        preset = resolve_detection_preset(DEFAULT_LIVE_DETECTION_PRESET)

        self.assertEqual(preset.name, "blood_cells_3cls")
        self.assertEqual(preset.model_path.name, "blood_cells_3cls_yolov8n_20260429.pt")
        self.assertEqual(preset.class_file.name, "blood_cells_3cls_labels.txt")
        self.assertEqual(preset.stabilization_window, 5)
        self.assertEqual(preset.stabilization_threshold, 3)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
LEGACY_ROOT = REPO_ROOT / "msh_app"
HARDWARE_DIR = LEGACY_ROOT / "hardware"
CELL_ID_DIR = LEGACY_ROOT / "cell_identification"

for candidate in (HARDWARE_DIR, LEGACY_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))


def _load_module(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_object_detection = _load_module(
    "legacy_object_detection_test",
    CELL_ID_DIR / "object_detection.py",
)
_stepper_gui = _load_module(
    "legacy_stepper_drag_gui_test",
    HARDWARE_DIR / "stepper_drag_gui.py",
)


class SlideScanWorkflowTests(unittest.TestCase):
    def test_detection_coverage_ratio_uses_union_area(self) -> None:
        detection_a = _object_detection.Detection(0, 0, 10, 10, 0.9, 0, "cell")
        detection_b = _object_detection.Detection(5, 5, 15, 15, 0.8, 0, "cell")
        mask = _object_detection.build_detection_union_mask((20, 20, 3), [detection_a, detection_b])
        ratio = _object_detection.compute_detection_coverage_ratio((20, 20, 3), [detection_a, detection_b])

        self.assertEqual(int(np.count_nonzero(mask)), 175)
        self.assertAlmostEqual(ratio, 175 / 400)

    def test_compute_slide_scan_pitch_uses_thirty_five_percent_overlap(self) -> None:
        self.assertEqual(_stepper_gui.compute_slide_scan_pitch(100), 65)
        self.assertEqual(_stepper_gui.compute_slide_scan_pitch(1), 1)

    def test_serpentine_column_direction_starts_top_to_bottom(self) -> None:
        directions = [_stepper_gui.slide_scan_vertical_direction(index) for index in range(4)]
        self.assertEqual(directions, [-1, 1, -1, 1])

    def test_sparse_rules_trigger_column_advance_and_scan_stop(self) -> None:
        self.assertFalse(_stepper_gui.slide_scan_should_advance_column(had_tissue=True, consecutive_sparse=1))
        self.assertTrue(_stepper_gui.slide_scan_should_advance_column(had_tissue=False, consecutive_sparse=2))
        self.assertTrue(_stepper_gui.slide_scan_should_advance_column(had_tissue=True, consecutive_sparse=2))
        self.assertFalse(_stepper_gui.slide_scan_should_stop(1))
        self.assertTrue(_stepper_gui.slide_scan_should_stop(2))

    def test_column_entry_estimate_uses_previous_edge_and_margin(self) -> None:
        span = _stepper_gui.SlideScanColumnSpan(top_y=120, bottom_y=-220, tile_count=9)
        self.assertEqual(_stepper_gui.slide_scan_column_entry_y(span, vertical_dir=-1, y_pitch=10), 150)
        self.assertEqual(_stepper_gui.slide_scan_column_entry_y(span, vertical_dir=1, y_pitch=10), -250)

    def test_search_limit_expands_from_previous_column_height(self) -> None:
        span = _stepper_gui.SlideScanColumnSpan(top_y=120, bottom_y=-220, tile_count=9)
        self.assertEqual(_stepper_gui.slide_scan_search_limit(None), 48)
        self.assertEqual(_stepper_gui.slide_scan_search_limit(span), 15)

    def test_generate_serpentine_capture_coordinates_uses_user_steps(self) -> None:
        coords = _stepper_gui.generate_serpentine_capture_coordinates(
            start_x=100,
            start_y=50,
            end_x=80,
            end_y=30,
            step_x=10,
            step_y=10,
        )
        self.assertEqual(
            coords,
            [
                (100, 50),
                (90, 50),
                (80, 50),
                (80, 40),
                (90, 40),
                (100, 40),
                (100, 30),
                (90, 30),
                (80, 30),
            ],
        )

    def test_cell_detection_labels_are_mapped_to_output_classes(self) -> None:
        self.assertEqual(_stepper_gui.classify_cell_detection("WBC", 0), "white_blood_cell")
        self.assertEqual(_stepper_gui.classify_cell_detection("Red Blood Cell", 1), "red_blood_cell")
        self.assertEqual(_stepper_gui.classify_cell_detection("Platelets", 2), "platelet")
        self.assertEqual(_stepper_gui.classify_cell_detection("0", 0), "white_blood_cell")
        self.assertEqual(_stepper_gui.classify_cell_detection("1", 1), "red_blood_cell")
        self.assertEqual(_stepper_gui.classify_cell_detection("2", 2), "platelet")
        self.assertIsNone(_stepper_gui.classify_cell_detection("unknown", 99))

    def test_clip_detection_bbox_adds_margin_and_stays_inside_image(self) -> None:
        self.assertEqual(
            _stepper_gui.clip_detection_bbox((100, 120, 3), 0, 0, 10, 10),
            (0, 0, 12, 12),
        )
        self.assertEqual(
            _stepper_gui.clip_detection_bbox((100, 120, 3), 100, 80, 119, 99),
            (98, 78, 120, 100),
        )
        self.assertIsNone(_stepper_gui.clip_detection_bbox((100, 120, 3), 10, 10, 10, 12))

    def test_generate_spiral_search_offsets_starts_from_center(self) -> None:
        offsets = _stepper_gui.generate_spiral_search_offsets(radius_steps=8, step_steps=4)
        self.assertEqual(offsets[0], (0, 0))
        self.assertIn((4, 0), offsets)
        self.assertIn((-8, 8), offsets)
        self.assertEqual(len(offsets), len(set(offsets)))

    def test_white_blood_cell_detection_helpers_use_label_mapping(self) -> None:
        det = _object_detection.Detection(10, 20, 30, 60, 0.9, 0, "WBC")
        self.assertTrue(_stepper_gui.is_white_blood_cell_detection(det))
        self.assertEqual(_stepper_gui.detection_center(det), (20.0, 40.0))
        self.assertGreater(_stepper_gui.score_white_blood_cell_detection(det, (100, 100, 3)), 0.0)

    def test_wbc_subtype_display_only_changes_wbc_label(self) -> None:
        wbc = _object_detection.Detection(10, 20, 30, 60, 0.9, 0, "WBC", "neutrophil", 0.82)
        rbc = _object_detection.Detection(40, 20, 55, 50, 0.8, 1, "RBC", None, None)

        self.assertEqual(wbc.display_label, "WBC/neutrophil")
        self.assertEqual(rbc.display_label, "RBC")
        self.assertTrue(_object_detection.is_wbc_label(wbc.label, wbc.cls_id))
        self.assertFalse(_object_detection.is_wbc_label(rbc.label, rbc.cls_id))

    def test_wbc_collection_saves_only_unified_white_blood_cell_crops(self) -> None:
        frame = np.full((80, 100, 3), 180, dtype=np.uint8)
        wbc = _object_detection.Detection(10, 20, 30, 50, 0.91, 0, "WBC", "lymphocyte", 0.88)
        rbc = _object_detection.Detection(50, 20, 65, 40, 0.80, 1, "RBC", None, None)
        with tempfile.TemporaryDirectory() as tmp:
            collection_dir = Path(tmp) / "wbc_collection"
            records = _stepper_gui.save_wbc_collection_crops(
                collection_dir=collection_dir,
                frame=frame,
                detections=[wbc, rbc],
                source_image_path=Path(tmp) / "tile_001.jpg",
                tile_index=1,
                platform_x=100,
                platform_y=200,
            )

            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["wbc_subtype"], "")
            self.assertTrue(Path(records[0]["crop_path"]).exists())
            self.assertEqual(Path(records[0]["crop_path"]).parent.name, "White_Blood_Cell")
            self.assertTrue(Path(records[0]["crop_path"]).name.endswith("_White_Blood_Cell.png"))


if __name__ == "__main__":
    unittest.main()

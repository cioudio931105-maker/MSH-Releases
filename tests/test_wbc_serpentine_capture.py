from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

import numpy as np

from cell_stitching_project import wbc_serpentine_capture as wbc


class WBCSerpentineCaptureTests(unittest.TestCase):
    def test_generate_vertical_serpentine_path(self) -> None:
        path = wbc.generate_vertical_serpentine_path(
            start_x=0,
            start_y=0,
            columns=3,
            rows=3,
            step_x=1,
            step_y=1,
        )
        self.assertEqual(
            path,
            [
                {"x": 0, "y": 0},
                {"x": 0, "y": 1},
                {"x": 0, "y": 2},
                {"x": 1, "y": 2},
                {"x": 1, "y": 1},
                {"x": 1, "y": 0},
                {"x": 2, "y": 0},
                {"x": 2, "y": 1},
                {"x": 2, "y": 2},
            ],
        )

    def test_generate_vertical_serpentine_path_from_bounds_reaches_exact_endpoint(self) -> None:
        path = wbc.generate_vertical_serpentine_path_from_bounds(
            0,
            0,
            25,
            15,
            step_x=10,
            step_y=10,
        )
        self.assertEqual(
            path,
            [
                {"x": 0, "y": 0},
                {"x": 0, "y": 10},
                {"x": 0, "y": 15},
                {"x": 10, "y": 15},
                {"x": 10, "y": 10},
                {"x": 10, "y": 0},
                {"x": 20, "y": 0},
                {"x": 20, "y": 10},
                {"x": 20, "y": 15},
                {"x": 25, "y": 15},
                {"x": 25, "y": 10},
                {"x": 25, "y": 0},
            ],
        )

    def test_complete_white_blood_cell_detection_rules(self) -> None:
        frame_shape = (100, 100, 3)
        good = wbc.WBCDetection(wbc.WHITE_BLOOD_CELL_CLASS, 0.91, (20, 20, 60, 60))
        low_conf = wbc.WBCDetection(wbc.WHITE_BLOOD_CELL_CLASS, 0.20, (20, 20, 60, 60))
        touching_border = wbc.WBCDetection(wbc.WHITE_BLOOD_CELL_CLASS, 0.91, (0, 20, 60, 60))

        self.assertTrue(wbc.is_complete_white_blood_cell_detection(good, frame_shape))
        self.assertFalse(wbc.is_complete_white_blood_cell_detection(low_conf, frame_shape))
        self.assertFalse(wbc.is_complete_white_blood_cell_detection(touching_border, frame_shape))

    def test_scan_stop_accepts_wbc_box_in_range_without_full_crop_rules(self) -> None:
        original_config = dict(wbc.DEFAULT_CONFIG)
        try:
            wbc.DEFAULT_CONFIG.update({"scan_stop_min_confidence": 0.50, "min_bbox_area": 900})
            frame_shape = (100, 100, 3)
            small_in_range = wbc.WBCDetection(wbc.WHITE_BLOOD_CELL_CLASS, 0.80, (40, 40, 50, 50))
            low_conf = wbc.WBCDetection(wbc.WHITE_BLOOD_CELL_CLASS, 0.20, (40, 40, 50, 50))
            outside_range = wbc.WBCDetection(wbc.WHITE_BLOOD_CELL_CLASS, 0.80, (0, 0, 4, 4))

            self.assertFalse(wbc.is_complete_white_blood_cell_detection(small_in_range, frame_shape))
            self.assertTrue(wbc.is_scan_stop_white_blood_cell_detection(small_in_range, frame_shape))
            self.assertFalse(wbc.is_scan_stop_white_blood_cell_detection(low_conf, frame_shape))
            self.assertFalse(wbc.is_scan_stop_white_blood_cell_detection(outside_range, frame_shape))
        finally:
            wbc.DEFAULT_CONFIG.clear()
            wbc.DEFAULT_CONFIG.update(original_config)

    def test_yolo_detector_uses_lowest_preview_threshold_for_visible_boxes(self) -> None:
        original_config = dict(wbc.DEFAULT_CONFIG)
        try:
            wbc.DEFAULT_CONFIG.update(
                {
                    "preview_confidence": 0.20,
                    "scan_stop_min_confidence": 0.50,
                    "min_confidence": 0.50,
                    "iou": 0.45,
                    "imgsz": 640,
                    "device": "auto",
                }
            )

            calls: list[float] = []

            class FakeModel:
                def predict(self, **kwargs):
                    calls.append(float(kwargs["conf"]))
                    return []

            detector = wbc.YoloWhiteBloodCellDetector.__new__(wbc.YoloWhiteBloodCellDetector)
            detector.model_path = Path("dummy.pt")
            detector.model = FakeModel()
            self.assertEqual(detector.detect(np.zeros((20, 20, 3), dtype=np.uint8)), [])
            self.assertEqual(calls, [0.20])
        finally:
            wbc.DEFAULT_CONFIG.clear()
            wbc.DEFAULT_CONFIG.update(original_config)

    def test_crop_white_blood_cell_skips_ambiguous_overlap(self) -> None:
        image = np.zeros((100, 100, 3), dtype=np.uint8)
        target = (20, 20, 45, 45)
        nearby_separate = (56, 20, 80, 45)
        overlapping = (40, 20, 65, 45)

        crop = wbc.crop_white_blood_cell_by_bbox(image, target, [target, nearby_separate], padding=10)
        self.assertIsNotNone(crop)

        ambiguous_crop = wbc.crop_white_blood_cell_by_bbox(image, target, [target, overlapping], padding=10)
        self.assertIsNone(ambiguous_crop)

    def test_centering_steps_follow_microscope_motion_convention(self) -> None:
        original_config = dict(wbc.DEFAULT_CONFIG)
        try:
            wbc.DEFAULT_CONFIG.update(
                {
                    "center_tolerance_px": 10,
                    "center_x_image_px_per_step": -10.0,
                    "center_y_image_px_per_step": 5.0,
                    "center_max_step_per_axis": 12,
                }
            )
            frame_shape = (100, 100, 3)
            right_and_above = wbc.WBCDetection(wbc.WHITE_BLOOD_CELL_CLASS, 0.90, (60, 20, 80, 40))
            left_and_below = wbc.WBCDetection(wbc.WHITE_BLOOD_CELL_CLASS, 0.90, (20, 60, 40, 80))

            self.assertEqual(wbc.calculate_wbc_centering_steps(right_and_above, frame_shape), (2, 4))
            self.assertEqual(wbc.calculate_wbc_centering_steps(left_and_below, frame_shape), (-2, -4))
        finally:
            wbc.DEFAULT_CONFIG.clear()
            wbc.DEFAULT_CONFIG.update(original_config)

    def test_centering_steps_are_clamped_and_skip_centered_cell(self) -> None:
        original_config = dict(wbc.DEFAULT_CONFIG)
        try:
            wbc.DEFAULT_CONFIG.update(
                {
                    "center_tolerance_px": 8,
                    "center_x_image_px_per_step": -4.0,
                    "center_y_image_px_per_step": 4.0,
                    "center_max_step_per_axis": 5,
                }
            )
            frame_shape = (100, 100, 3)
            centered = wbc.WBCDetection(wbc.WHITE_BLOOD_CELL_CLASS, 0.90, (43, 43, 57, 57))
            far = wbc.WBCDetection(wbc.WHITE_BLOOD_CELL_CLASS, 0.90, (80, 0, 100, 20))

            self.assertTrue(wbc.is_wbc_centered(centered, frame_shape))
            self.assertEqual(wbc.calculate_wbc_centering_steps(centered, frame_shape), (0, 0))
            self.assertEqual(wbc.calculate_wbc_centering_steps(far, frame_shape), (5, 5))
        finally:
            wbc.DEFAULT_CONFIG.clear()
            wbc.DEFAULT_CONFIG.update(original_config)

    def test_centering_steps_skip_one_step_when_it_barely_improves_offset(self) -> None:
        original_config = dict(wbc.DEFAULT_CONFIG)
        try:
            wbc.DEFAULT_CONFIG.update(
                {
                    "center_tolerance_px": 32,
                    "center_min_step_improvement_px": 16,
                    "center_x_image_px_per_step": -160.0,
                    "center_y_image_px_per_step": -160.0,
                    "center_max_step_per_axis": 12,
                }
            )
            frame_shape = (2064, 3088, 3)
            small_y_gain = wbc.WBCDetection(wbc.WHITE_BLOOD_CELL_CLASS, 0.90, (1636, 870, 1836, 1030))
            useful_x_y_gain = wbc.WBCDetection(wbc.WHITE_BLOOD_CELL_CLASS, 0.90, (1622, 770, 1822, 945))

            self.assertEqual(wbc.calculate_wbc_centering_steps(small_y_gain, frame_shape), (1, 0))
            self.assertEqual(wbc.calculate_wbc_centering_steps(useful_x_y_gain, frame_shape), (1, -1))
        finally:
            wbc.DEFAULT_CONFIG.clear()
            wbc.DEFAULT_CONFIG.update(original_config)

    def test_centering_target_requires_high_confidence_scan_candidate(self) -> None:
        original_config = dict(wbc.DEFAULT_CONFIG)
        try:
            wbc.DEFAULT_CONFIG.update({"scan_stop_min_confidence": 0.50, "center_min_confidence": 0.70})
            frame_shape = (100, 100, 3)
            low = wbc.WBCDetection(wbc.WHITE_BLOOD_CELL_CLASS, 0.60, (30, 30, 60, 60))
            high = wbc.WBCDetection(wbc.WHITE_BLOOD_CELL_CLASS, 0.90, (35, 35, 65, 65))

            self.assertIsNone(wbc.select_wbc_centering_target([low], frame_shape))
            self.assertEqual(wbc.select_wbc_centering_target([low, high], frame_shape), high)
        finally:
            wbc.DEFAULT_CONFIG.clear()
            wbc.DEFAULT_CONFIG.update(original_config)

    def test_simulation_run_saves_original_crop_and_metadata(self) -> None:
        original_config = dict(wbc.DEFAULT_CONFIG)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                wbc.DEFAULT_CONFIG.update(
                    {
                        "simulation_mode": True,
                        "show_preview": False,
                        "output_root": Path(tmp),
                        "experiment_name": "unit_test",
                        "start_x": 0,
                        "start_y": 0,
                        "columns": 1,
                        "rows": 1,
                        "step_x": 10,
                        "step_y": 10,
                        "focus_wait_seconds": 0,
                        "countdown_seconds": 0,
                        "movement_pause_seconds": 0,
                        "center_after_detection": False,
                        "simulation_wbc_coordinates": {(0, 0): [(320, 280, 74)]},
                    }
                )
                output_dir = wbc.run_serpentine_white_blood_cell_capture()

                crops = list((output_dir / "cropped_cells").glob("*_White_Blood_Cell.png"))
                originals = list((output_dir / "original_frames").glob("*_original.png"))
                self.assertEqual(len(crops), 1)
                self.assertEqual(len(originals), 1)

                with (output_dir / "metadata.csv").open("r", encoding="utf-8", newline="") as handle:
                    rows = list(csv.DictReader(handle))
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["cell_class"], wbc.WHITE_BLOOD_CELL_CLASS)
                self.assertEqual(rows[0]["status"], "saved")
                self.assertEqual(rows[0]["captured_wbc_count"], "1")
        finally:
            wbc._release_runtime()
            wbc.DEFAULT_CONFIG.clear()
            wbc.DEFAULT_CONFIG.update(original_config)


if __name__ == "__main__":
    unittest.main()

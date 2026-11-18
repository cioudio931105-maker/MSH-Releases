from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from offline_cell_analysis.offline_pipeline.single_cell_crops import (
    CellDetection,
    classify_and_save_crop,
    crop_single_cell,
    export_csv,
    is_crop_ambiguous,
    remove_duplicate_cells,
)


class SingleCellCropTests(unittest.TestCase):
    def test_crop_single_cell_shrinks_padding_away_from_other_box(self) -> None:
        frame = np.zeros((100, 140, 3), dtype=np.uint8)
        target = (40.0, 30.0, 70.0, 60.0)
        other = (88.0, 30.0, 118.0, 60.0)

        crop = crop_single_cell(frame, target, [target, other], padding=30)

        self.assertIsNotNone(crop)
        assert crop is not None
        self.assertGreaterEqual(crop.shape[1], 30)
        self.assertLess(crop.shape[1], 90)

    def test_crop_single_cell_returns_none_when_cells_overlap(self) -> None:
        frame = np.zeros((100, 140, 3), dtype=np.uint8)
        target = (40.0, 30.0, 70.0, 60.0)
        overlapping = (55.0, 35.0, 85.0, 65.0)

        self.assertTrue(is_crop_ambiguous(target, [target, overlapping]))
        self.assertIsNone(crop_single_cell(frame, target, [target, overlapping], padding=10))

    def test_remove_duplicate_cells_keeps_highest_confidence(self) -> None:
        first = CellDetection(
            cell_id=1,
            cell_class="Red_Blood_Cell",
            bounding_box=(10.0, 10.0, 40.0, 40.0),
            confidence=0.70,
            frame_index=1,
            timestamp=0.1,
        )
        second = CellDetection(
            cell_id=2,
            cell_class="Red_Blood_Cell",
            bounding_box=(12.0, 11.0, 42.0, 41.0),
            confidence=0.92,
            frame_index=2,
            timestamp=0.2,
        )

        kept = remove_duplicate_cells([first, second], iou_threshold=0.2, centroid_threshold=20)

        self.assertEqual(kept, [second])
        self.assertEqual(first.status, "duplicate_skipped")

    def test_classify_and_export_csv(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "cells"
            crop_img = np.zeros((32, 32, 3), dtype=np.uint8)
            crop_path = classify_and_save_crop(
                crop_img,
                "Platelet",
                "sample_video",
                "2026-05-29_14-30-05",
                output_root=output_root,
                frame_index=123,
                cell_id=5,
                confidence=0.94,
            )
            self.assertTrue(crop_path.exists())
            self.assertIn("Platelet", crop_path.parts)
            self.assertIsNotNone(cv2.imread(str(crop_path)))

            det = CellDetection(
                cell_id=5,
                cell_class="Platelet",
                bounding_box=(1.0, 2.0, 10.0, 11.0),
                confidence=0.94,
                frame_index=123,
                timestamp=1.23,
                video_name="sample_video",
                status="saved",
                crop_path=str(crop_path),
            )
            csv_path = Path(temp_dir) / "results.csv"
            export_csv([det], csv_path)
            text = csv_path.read_text(encoding="utf-8")
            self.assertIn("cell_id,cell_class,video_name", text)
            self.assertIn("Platelet", text)
            self.assertIn("saved", text)


if __name__ == "__main__":
    unittest.main()


from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from offline_cell_analysis.offline_pipeline.pseudo_train import (
    THREE_CLASS_NAMES,
    build_three_class_yolo_dataset,
    normalize_three_class,
    read_pseudo_detections,
)


class PseudoTrainTests(unittest.TestCase):
    def test_normalize_three_class_aliases(self) -> None:
        self.assertEqual(normalize_three_class("White Blood Cell"), "WBC")
        self.assertEqual(normalize_three_class("Red_Blood_Cell"), "RBC")
        self.assertEqual(normalize_three_class("Platelet"), "Platelets")
        self.assertIsNone(normalize_three_class("Neutrophil"))

    def test_build_three_class_yolo_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            frames_dir = root / "frames"
            frames_dir.mkdir()
            frame_path = frames_dir / "frame_000001.jpg"
            frame = np.zeros((100, 200, 3), dtype=np.uint8)
            cv2.imwrite(str(frame_path), frame)

            csv_path = root / "detections_all.csv"
            with csv_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["frame_path", "class_name", "confidence", "x1", "y1", "x2", "y2"],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "frame_path": str(frame_path),
                        "class_name": "RBC",
                        "confidence": "0.91",
                        "x1": "20",
                        "y1": "10",
                        "x2": "80",
                        "y2": "50",
                    }
                )
                writer.writerow(
                    {
                        "frame_path": str(frame_path),
                        "class_name": "Platelets",
                        "confidence": "0.88",
                        "x1": "100",
                        "y1": "20",
                        "x2": "130",
                        "y2": "40",
                    }
                )
                writer.writerow(
                    {
                        "frame_path": str(frame_path),
                        "class_name": "WBC",
                        "confidence": "0.20",
                        "x1": "0",
                        "y1": "0",
                        "x2": "10",
                        "y2": "10",
                    }
                )

            detections = read_pseudo_detections([csv_path], min_confidence=0.65)
            self.assertEqual([det.class_name for det in detections], ["RBC", "Platelets"])

            output_root = root / "dataset"
            data_yaml = build_three_class_yolo_dataset([csv_path], output_root, min_confidence=0.65, val_ratio=0.0)

            self.assertTrue(data_yaml.exists())
            self.assertIn("names:", data_yaml.read_text(encoding="utf-8"))
            for class_name in THREE_CLASS_NAMES:
                self.assertIn(class_name, data_yaml.read_text(encoding="utf-8"))

            label_files = sorted((output_root / "labels" / "train").glob("*.txt"))
            self.assertEqual(len(label_files), 1)
            label_rows = label_files[0].read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(label_rows), 2)
            self.assertTrue(label_rows[0].startswith("1 "))
            self.assertTrue(label_rows[1].startswith("2 "))

    def test_build_dataset_rejects_empty_pseudo_labels(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            csv_path = root / "detections_all.csv"
            with csv_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["frame_path", "class_name", "confidence", "x1", "y1", "x2", "y2"],
                )
                writer.writeheader()

            with self.assertRaises(ValueError):
                build_three_class_yolo_dataset([csv_path], root / "dataset")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cell_stitching_project.prepare_manual_capture_yolo_dataset import (
    build_manual_capture_yolo_dataset,
    discover_manual_capture_samples,
)


class PrepareManualCaptureYoloDatasetTests(unittest.TestCase):
    def test_builds_split_dataset_from_manual_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            captured_root = root / "captured"
            for index in range(3):
                training_dir = captured_root / f"manual_session_20260608_00000{index}" / "training_dataset"
                images_dir = training_dir / "images"
                labels_dir = training_dir / "labels"
                images_dir.mkdir(parents=True)
                labels_dir.mkdir(parents=True)
                (images_dir / f"{index}_0.png").write_bytes(b"fake image bytes")
                (labels_dir / f"{index}_0.txt").write_text(
                    f"{index % 3} 0.50000000 0.50000000 0.10000000 0.10000000\n",
                    encoding="utf-8",
                )

            samples = discover_manual_capture_samples(captured_root)
            self.assertEqual(3, len(samples))

            output_root = root / "dataset"
            data_yaml = build_manual_capture_yolo_dataset(captured_root, output_root, val_ratio=0.34, seed=7)

            self.assertTrue(data_yaml.exists())
            self.assertIn("0: WBC", data_yaml.read_text(encoding="utf-8"))
            self.assertEqual(2, len(list((output_root / "images" / "train").glob("*.png"))))
            self.assertEqual(1, len(list((output_root / "images" / "val").glob("*.png"))))
            self.assertTrue((output_root / "manual_capture_manifest.csv").exists())

    def test_rejects_invalid_label_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            training_dir = Path(temp_dir) / "captured" / "manual_session_bad" / "training_dataset"
            (training_dir / "images").mkdir(parents=True)
            (training_dir / "labels").mkdir(parents=True)
            (training_dir / "images" / "bad.png").write_bytes(b"fake")
            (training_dir / "labels" / "bad.txt").write_text("9 0.5 0.5 0.1 0.1\n", encoding="utf-8")

            with self.assertRaises(ValueError):
                discover_manual_capture_samples(Path(temp_dir) / "captured")


if __name__ == "__main__":
    unittest.main()

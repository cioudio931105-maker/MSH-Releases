from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cell_stitching_project.train_yolo_wbc400 import _parser, read_yolo_names, validate_wbc_data_yaml, validate_wbc5_data_yaml


class TrainYoloWbc400Tests(unittest.TestCase):
    def test_validate_wbc5_data_yaml_accepts_expected_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_yaml = Path(tmp) / "data.yaml"
            data_yaml.write_text(
                "names: ['neutrophil', 'lymphocyte', 'monocyte', 'eosinophil', 'basophil']\n",
                encoding="utf-8",
            )

            self.assertEqual(
                validate_wbc5_data_yaml(data_yaml),
                ["neutrophil", "lymphocyte", "monocyte", "eosinophil", "basophil"],
            )

    def test_read_yolo_names_accepts_mapping_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_yaml = Path(tmp) / "data.yaml"
            data_yaml.write_text(
                "names: {0: neutrophil, 1: lymphocyte}\n",
                encoding="utf-8",
            )

            self.assertEqual(read_yolo_names(data_yaml), ["neutrophil", "lymphocyte"])

    def test_read_yolo_names_accepts_indented_mapping_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_yaml = Path(tmp) / "data.yaml"
            data_yaml.write_text(
                "names:\n  0: WBC\n",
                encoding="utf-8",
            )

            self.assertEqual(read_yolo_names(data_yaml), ["WBC"])

    def test_parser_defaults_to_high_confidence_400x_training(self) -> None:
        args = _parser().parse_args([])

        self.assertEqual(args.model, "yolov8s.pt")
        self.assertEqual(args.imgsz, 1280)
        self.assertEqual(args.epochs, 260)
        self.assertEqual(args.batch, 4)
        self.assertEqual(args.cls_loss_gain, 0.8)

    def test_validate_wbc_data_yaml_accepts_wbc_only_when_requested(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_yaml = Path(tmp) / "data.yaml"
            data_yaml.write_text(
                "names: {0: WBC}\n",
                encoding="utf-8",
            )

            self.assertEqual(validate_wbc_data_yaml(data_yaml, wbc_only=True), ["WBC"])


if __name__ == "__main__":
    unittest.main()

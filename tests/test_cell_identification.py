from __future__ import annotations

import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np

from cell_stitching_project.cell_identification import CellIdentificationDetector, load_class_names


class _FakeBoxScalar:
    def __init__(self, value):
        self._value = value

    def item(self):
        return self._value


class _FakeBoxArray:
    def __init__(self, values):
        self._values = values

    def __getitem__(self, _index):
        return self

    def tolist(self):
        return list(self._values)


class _FakeBox:
    def __init__(self):
        self.cls = _FakeBoxScalar(0)
        self.conf = _FakeBoxScalar(0.88)
        self.xyxy = _FakeBoxArray([10, 20, 30, 40])


class _FakeResult:
    def __init__(self):
        self.boxes = [_FakeBox()]
        self.names = {0: "embedded_class"}


class _FakeYOLOModel:
    def __init__(self, _path: str) -> None:
        self.names = {0: "embedded_class"}

    def predict(self, source, conf, iou, device, verbose):
        del source, conf, iou, device, verbose
        return [_FakeResult()]


class CellIdentificationDetectorTests(unittest.TestCase):
    def test_default_class_names_are_five_major_wbc_types(self) -> None:
        self.assertEqual(
            load_class_names(),
            ["neutrophil", "lymphocyte", "monocyte", "eosinophil", "basophil"],
        )

    def test_load_class_names_accepts_yolo_indexed_txt_and_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            indexed = root / "classes.txt"
            indexed.write_text("0 neutrophil\n1 lymphocyte\n", encoding="utf-8")
            yaml_file = root / "data.yaml"
            yaml_file.write_text("nc: 2\nnames: ['monocyte', 'eosinophil']\n", encoding="utf-8")

            self.assertEqual(load_class_names(indexed), ["neutrophil", "lymphocyte"])
            self.assertEqual(load_class_names(yaml_file), ["monocyte", "eosinophil"])

    def test_ultralytics_uses_embedded_class_names_when_file_missing(self) -> None:
        with patch("cell_stitching_project.cell_identification._import_ultralytics", return_value=_FakeYOLOModel):
            detector = CellIdentificationDetector(
                model_path="dummy.pt",
                backend="ultralytics",
                class_names=None,
            )
            detections = detector.predict(np.zeros((64, 64, 3), dtype=np.uint8))

        self.assertEqual(detector.class_names, ["embedded_class"])
        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0].label, "embedded_class")


if __name__ == "__main__":
    unittest.main()

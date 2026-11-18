from __future__ import annotations

import csv
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from xml.etree import ElementTree

import cv2
import numpy as np


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
HARDWARE_ROOT = WORKSPACE_ROOT / "stitched_output" / "stitched_output" / "stitched_output" / "hardware"
if str(HARDWARE_ROOT) not in sys.path:
    sys.path.insert(0, str(HARDWARE_ROOT))

import stepper_drag_gui as gui  # noqa: E402


class ManualCaptureTrainingExportTests(unittest.TestCase):
    def test_exports_three_class_crops_yolo_csv_and_xlsx_without_downscaling(self) -> None:
        frame = np.zeros((2064, 3088, 3), dtype=np.uint8)
        detections = [
            SimpleNamespace(x1=100, y1=120, x2=360, y2=390, cls_id=0, label="WBC", conf=0.91),
            SimpleNamespace(x1=500, y1=520, x2=730, y2=760, cls_id=1, label="RBC", conf=0.88),
            SimpleNamespace(x1=900, y1=400, x2=980, y2=490, cls_id=2, label="Platelets", conf=0.82),
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            session_dir = Path(temp_dir)
            source_path = session_dir / "0_0_test.png"
            self.assertTrue(gui.StepperDragGUI._write_capture_image(source_path, frame))

            records, csv_path, xlsx_path = gui.save_manual_three_class_training_data(
                session_dir,
                source_path,
                frame,
                detections,
                platform_x=0,
                platform_y=0,
            )

            loaded_source = cv2.imread(str(source_path), cv2.IMREAD_UNCHANGED)
            self.assertEqual((2064, 3088, 3), loaded_source.shape)
            self.assertEqual(3, len(records))

            second_source_path = session_dir / "8_0_test.png"
            self.assertTrue(gui.StepperDragGUI._write_capture_image(second_source_path, frame))
            gui.save_manual_three_class_training_data(
                session_dir,
                second_source_path,
                frame,
                detections,
                platform_x=8,
                platform_y=0,
            )

            crop_classes = sorted(
                path.parent.name for path in (session_dir / "training_dataset" / "crops").glob("*/*.png")
            )
            self.assertEqual(
                [
                    "platelet",
                    "platelet",
                    "red_blood_cell",
                    "red_blood_cell",
                    "white_blood_cell",
                    "white_blood_cell",
                ],
                crop_classes,
            )

            with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
                self.assertEqual(6, len(list(csv.DictReader(handle))))

            label_path = session_dir / "training_dataset" / "labels" / "0_0_test.txt"
            class_ids = [line.split()[0] for line in label_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(["0", "1", "2"], class_ids)

            with zipfile.ZipFile(xlsx_path) as archive:
                names = set(archive.namelist())
                self.assertIn("xl/workbook.xml", names)
                self.assertIn("xl/worksheets/sheet1.xml", names)
                self.assertIn("xl/worksheets/sheet2.xml", names)
                ElementTree.fromstring(archive.read("xl/workbook.xml"))
                ElementTree.fromstring(archive.read("xl/worksheets/sheet1.xml"))
                ElementTree.fromstring(archive.read("xl/worksheets/sheet2.xml"))

            self.assertTrue((session_dir / "training_dataset" / "images" / source_path.name).exists())
            self.assertTrue((session_dir / "training_dataset" / "data.yaml").exists())


if __name__ == "__main__":
    unittest.main()

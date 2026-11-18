from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from cell_stitching_project.prepare_wbc400_wbc_only_dataset import (
    anchor_target_size,
    build_wbc400_wbc_only_dataset,
    discover_mll23_crops,
    load_anchor_samples,
)


class PrepareWbc400WbcOnlyDatasetTests(unittest.TestCase):
    def test_builds_single_class_dataset_from_anchor_and_mll23_crop(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            session = root / "captured" / "manual_session_20260617_100926_956369"
            images = session / "training_dataset" / "images"
            labels = session / "training_dataset" / "labels"
            images.mkdir(parents=True)
            labels.mkdir(parents=True)

            background = np.full((120, 160, 3), 180, dtype=np.uint8)
            cv2.circle(background, (115, 60), 18, (120, 60, 180), -1)
            cv2.imwrite(str(images / "anchor.png"), background)
            labels.joinpath("anchor.txt").write_text("0 0.71875000 0.50000000 0.22500000 0.30000000\n", encoding="utf-8")

            mll23_root = root / "mll23"
            crop_dir = mll23_root / "lymphocyte_reactive"
            crop_dir.mkdir(parents=True)
            crop = np.full((48, 48, 3), 190, dtype=np.uint8)
            cv2.circle(crop, (24, 24), 14, (130, 70, 190), -1)
            cv2.imwrite(str(crop_dir / "lymphocyte_reactive_0001.png"), crop)

            samples = load_anchor_samples(session)
            self.assertEqual((36, 36), anchor_target_size(samples))
            self.assertEqual(1, len(discover_mll23_crops(mll23_root, ["lymphocyte_reactive"])))

            output_root = root / "dataset"
            data_yaml = build_wbc400_wbc_only_dataset(
                anchor_session=session,
                mll23_root=mll23_root,
                output_root=output_root,
                mll23_classes=["lymphocyte_reactive"],
                synthetic_count=4,
                val_ratio=0.25,
                seed=3,
                overwrite=True,
            )

            self.assertTrue(data_yaml.exists())
            self.assertIn("0: WBC", data_yaml.read_text(encoding="utf-8"))
            labels_written = list((output_root / "labels").rglob("*.txt"))
            self.assertGreaterEqual(len(labels_written), 5)
            for label_path in labels_written:
                for row in label_path.read_text(encoding="utf-8").splitlines():
                    self.assertTrue(row.startswith("0 "), row)
            self.assertTrue((output_root / "wbc400_wbc_only_manifest.csv").exists())
            self.assertTrue((output_root / "dataset_summary.json").exists())


if __name__ == "__main__":
    unittest.main()

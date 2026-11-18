from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from cell_stitching_project.prepare_wbc_boost_3cls_dataset import build_wbc_boost_dataset


class PrepareWbcBoost3clsDatasetTests(unittest.TestCase):
    def test_builds_dataset_from_txl_and_wbc_full_box_images(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            txl_root = root / "TXL-PBC"
            txl_images = txl_root / "images" / "train"
            txl_labels = txl_root / "labels" / "train"
            txl_images.mkdir(parents=True)
            txl_labels.mkdir(parents=True)
            for index in range(3):
                image = np.zeros((20, 30, 3), dtype=np.uint8)
                cv2.imwrite(str(txl_images / f"sample_{index}.jpg"), image)
                (txl_labels / f"sample_{index}.txt").write_text(
                    f"{index % 3} 0.50000000 0.50000000 0.20000000 0.20000000\n",
                    encoding="utf-8",
                )

            wbc_root = root / "wbc"
            wbc_root.mkdir()
            rgba = np.zeros((16, 16, 4), dtype=np.uint8)
            rgba[:, :, 3] = 255
            cv2.imwrite(str(wbc_root / "single_wbc.png"), rgba)

            output_root = root / "dataset"
            data_yaml = build_wbc_boost_dataset(txl_images, wbc_root, output_root, val_ratio=0.25, seed=1)

            self.assertTrue(data_yaml.exists())
            self.assertIn("0: WBC", data_yaml.read_text(encoding="utf-8"))
            self.assertTrue((output_root / "wbc_boost_manifest.csv").exists())
            all_labels = sorted((output_root / "labels").glob("*/*.txt"))
            self.assertEqual(4, len(all_labels))
            self.assertTrue(any(label.read_text(encoding="utf-8").startswith("0 0.50000000 0.50000000 1.00000000 1.00000000") for label in all_labels))


if __name__ == "__main__":
    unittest.main()

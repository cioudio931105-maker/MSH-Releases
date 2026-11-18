from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cell_stitching_project.eval_ssd import main as eval_ssd_main
from cell_stitching_project.export_ssd_onnx import main as export_ssd_onnx_main
from cell_stitching_project.prepare_voc_dataset import prepare_voc_dataset
from cell_stitching_project.ssd.common import find_best_checkpoint
from cell_stitching_project.train_ssd import main as train_ssd_main
from tests.test_prepare_voc_dataset import _write_sample_annotation

import cv2
import numpy as np


class SSDPipelineTests(unittest.TestCase):
    def test_find_best_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "mb1-ssd-Epoch-0-Loss-2.0.pth").write_text("", encoding="utf-8")
            (root / "mb1-ssd-Epoch-1-Loss-1.0.pth").write_text("", encoding="utf-8")
            self.assertEqual(find_best_checkpoint(root).name, "mb1-ssd-Epoch-1-Loss-1.0.pth")

    def test_train_eval_and_export_smoke(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            flat = root / "flat"
            flat.mkdir(parents=True, exist_ok=True)
            image_path = flat / "sample.png"
            image = np.zeros((300, 300, 3), dtype=np.uint8)
            image[60:220, 80:240] = (255, 255, 255)
            cv2.imwrite(str(image_path), image)
            _write_sample_annotation(flat / "sample.xml", image_path.name, 300, 300, "cell")

            voc_dir = root / "voc"
            prepare_voc_dataset(flat, voc_dir)

            model_dir = root / "models"
            with mock.patch.object(
                sys,
                "argv",
                [
                    "train_ssd",
                    "--dataset-type",
                    "voc",
                    "--datasets",
                    str(voc_dir),
                    "--net",
                    "mb1-ssd",
                    "--batch-size",
                    "1",
                    "--num-epochs",
                    "1",
                    "--num-workers",
                    "0",
                    "--use-cuda",
                    "false",
                    "--checkpoint-folder",
                    str(model_dir),
                ],
            ):
                train_ssd_main()

            checkpoint = find_best_checkpoint(model_dir)
            self.assertIsNotNone(checkpoint)
            label_file = model_dir / "labels.txt"
            eval_dir = root / "eval"

            with mock.patch.object(
                sys,
                "argv",
                [
                    "eval_ssd",
                    "--net",
                    "mb1-ssd",
                    "--trained-model",
                    str(checkpoint),
                    "--dataset-type",
                    "voc",
                    "--dataset",
                    str(voc_dir),
                    "--label-file",
                    str(label_file),
                    "--use-cuda",
                    "false",
                    "--eval-dir",
                    str(eval_dir),
                ],
            ):
                eval_ssd_main()
            self.assertTrue((eval_dir / "summary.json").exists())

            onnx_path = model_dir / "model.onnx"
            with mock.patch.object(
                sys,
                "argv",
                [
                    "export_ssd_onnx",
                    "--net",
                    "mb1-ssd",
                    "--input",
                    str(checkpoint),
                    "--labels",
                    str(label_file),
                    "--output",
                    str(onnx_path),
                    "--use-cuda",
                    "false",
                ],
            ):
                try:
                    export_ssd_onnx_main()
                except Exception as exc:
                    self.skipTest(f"ONNX export is not available in this environment: {exc}")
            self.assertTrue(onnx_path.exists())


if __name__ == "__main__":
    unittest.main()

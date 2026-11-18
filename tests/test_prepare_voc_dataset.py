from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from cell_stitching_project.prepare_voc_dataset import prepare_voc_dataset


def _write_sample_annotation(path: Path, image_name: str, width: int, height: int, label: str) -> None:
    path.write_text(
        f"""<annotation>
    <folder>dataset</folder>
    <filename>{image_name}</filename>
    <size><width>{width}</width><height>{height}</height><depth>3</depth></size>
    <object>
        <name>{label}</name>
        <pose>Unspecified</pose>
        <truncated>0</truncated>
        <difficult>0</difficult>
        <bndbox><xmin>40</xmin><ymin>50</ymin><xmax>180</xmax><ymax>190</ymax></bndbox>
    </object>
</annotation>
""",
        encoding="utf-8",
    )


class PrepareVocDatasetTests(unittest.TestCase):
    def test_prepare_voc_dataset_from_flat_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            output = root / "voc"
            source.mkdir(parents=True, exist_ok=True)

            image_path = source / "cell_001.png"
            image = np.zeros((256, 256, 3), dtype=np.uint8)
            image[50:190, 40:180] = (255, 255, 255)
            cv2.imwrite(str(image_path), image)
            _write_sample_annotation(source / "cell_001.xml", image_path.name, 256, 256, "cell")

            result = prepare_voc_dataset(source, output)

            self.assertEqual(result.images_count, 1)
            self.assertTrue((output / "JPEGImages" / "cell_001.png").exists())
            self.assertTrue((output / "Annotations" / "cell_001.xml").exists())
            self.assertEqual((output / "labels.txt").read_text(encoding="utf-8").strip(), "cell")
            for split_name in ("train", "val", "test", "trainval", "default"):
                self.assertEqual((output / "ImageSets" / "Main" / f"{split_name}.txt").read_text(encoding="utf-8").strip(), "cell_001")


if __name__ == "__main__":
    unittest.main()


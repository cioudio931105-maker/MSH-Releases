from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cell_stitching_project.io_utils import append_jsonl, list_image_paths, parse_image_coordinates, parse_xy_coordinates, save_text_lines


class IoUtilsTests(unittest.TestCase):
    def test_parse_image_coordinates_supports_plain_xy_tiles(self) -> None:
        self.assertEqual(parse_image_coordinates("D:/scan/-5000_-10.jpg"), (-10.0, -5000.0))
        self.assertEqual(parse_xy_coordinates("D:/scan/-5000_-10.jpg"), (-5000.0, -10.0))

    def test_list_image_paths_preserves_explicit_order(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = root / "10_0.jpg"
            second = root / "0_0.jpg"
            first.write_bytes(b"a")
            second.write_bytes(b"b")

            ordered = list_image_paths(
                input_dir=root,
                explicit_paths=[str(first), str(second)],
                input_order="coordinates",
            )

            self.assertEqual([path.name for path in ordered], ["10_0.jpg", "0_0.jpg"])

    def test_append_jsonl_and_save_text_lines(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            jsonl_path = root / "events.jsonl"
            labels_path = root / "labels.txt"

            append_jsonl(jsonl_path, {"label": "cell", "frame_index": 1})
            append_jsonl(jsonl_path, {"label": "cell", "frame_index": 2})
            save_text_lines(labels_path, ["a", "b"])

            self.assertEqual(len(jsonl_path.read_text(encoding="utf-8").strip().splitlines()), 2)
            self.assertEqual(labels_path.read_text(encoding="utf-8"), "a\nb\n")


if __name__ == "__main__":
    unittest.main()

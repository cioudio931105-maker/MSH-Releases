from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from cell_stitching_project.serpentine_stitch import discover_traversal_candidates, select_best_traversal_candidate


class SerpentineStitchTests(unittest.TestCase):
    def test_virtual_coordinate_capture_order_is_preferred_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            filenames = [
                "0_0.jpg",
                "-5_0.jpg",
                "-10_0.jpg",
                "-10_-10.jpg",
                "-5_-10.jpg",
                "0_-10.jpg",
            ]
            for name in filenames:
                (root / name).write_bytes(b"x")

            with (root / "virtual_coordinates.csv").open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["index", "x", "y", "filename"])
                writer.writeheader()
                rows = [
                    {"index": 1, "x": 0, "y": 0, "filename": "0_0.jpg"},
                    {"index": 2, "x": -5, "y": 0, "filename": "-5_0.jpg"},
                    {"index": 3, "x": -10, "y": 0, "filename": "-10_0.jpg"},
                    {"index": 4, "x": -10, "y": -10, "filename": "-10_-10.jpg"},
                    {"index": 5, "x": -5, "y": -10, "filename": "-5_-10.jpg"},
                    {"index": 6, "x": 0, "y": -10, "filename": "0_-10.jpg"},
                ]
                writer.writerows(rows)

            candidates = discover_traversal_candidates(root)
            selected = select_best_traversal_candidate(candidates)

            self.assertEqual(selected.name, "virtual_csv_capture_order")
            self.assertEqual(selected.source, "virtual_coordinates.csv")


if __name__ == "__main__":
    unittest.main()

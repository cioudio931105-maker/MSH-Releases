from __future__ import annotations

import csv
import json
from pathlib import Path
import tempfile

import cv2
import numpy as np
import unittest

from cell_stitching_project.coordinate_overlay_stitch import list_coordinate_tiles, parse_plain_coordinate_tile, stitch_by_coordinates


class CoordinateOverlayStitchTests(unittest.TestCase):
    def test_parse_plain_coordinate_tile_supports_negative_pairs(self) -> None:
        tile = parse_plain_coordinate_tile("D:/scan/-5000_-10.jpg")
        self.assertIsNotNone(tile)
        assert tile is not None
        self.assertEqual(tile.path.name, "-5000_-10.jpg")
        self.assertEqual(tile.x, -5000.0)
        self.assertEqual(tile.y, -10.0)

    def test_parse_plain_coordinate_tile_ignores_non_coordinate_names(self) -> None:
        self.assertIsNone(parse_plain_coordinate_tile("D:/scan/-5000_-10_detected.jpg"))
        self.assertIsNone(parse_plain_coordinate_tile("D:/scan/virtual_coordinates.csv"))

    def test_list_coordinate_tiles_skips_sidecar_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for name in ("0_0.jpg", "-5_0.jpg", "0_-10.jpg", "0_0_detected.jpg", "_preview_sheet.jpg"):
                (root / name).write_bytes(b"test")

            tiles = list_coordinate_tiles(root)
            self.assertEqual([tile.path.name for tile in tiles], ["-5_0.jpg", "0_-10.jpg", "0_0.jpg"])

    def test_stitch_by_coordinates_uses_virtual_coordinate_map_and_axis_scales(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image = np.full((4, 6, 3), 120, dtype=np.uint8)
            for name in ("0_0.jpg", "10_0.jpg", "0_-4.jpg", "10_-4.jpg"):
                self.assertTrue(cv2.imwrite(str(root / name), image), msg=name)

            with (root / "virtual_coordinates.csv").open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["index", "x", "y", "filename"])
                writer.writeheader()
                writer.writerows(
                    [
                        {"index": 1, "x": 0, "y": 0, "filename": "0_0.jpg"},
                        {"index": 2, "x": 10, "y": 0, "filename": "10_0.jpg"},
                        {"index": 3, "x": 0, "y": -4, "filename": "0_-4.jpg"},
                        {"index": 4, "x": 10, "y": -4, "filename": "10_-4.jpg"},
                    ]
                )

            result = stitch_by_coordinates(
                input_dir=root,
                output_dir=root / "out",
                overlap_ratio=0.5,
                blend_mode="ownership",
                result_name="result.png",
                preview_name="preview.jpg",
                metadata_name="placements.json",
            )

            self.assertEqual(result["coordinate_source"], "virtual_coordinates.csv")
            self.assertAlmostEqual(float(result["x_pixels_per_unit"]), 0.3, places=6)
            self.assertAlmostEqual(float(result["y_pixels_per_unit"]), 0.5, places=6)
            self.assertEqual(result["canvas_size"], [9, 6])
            self.assertTrue(Path(str(result["result_path"])).exists())
            self.assertTrue(Path(str(result["metadata_path"])).exists())

    def test_strip_ownership_builds_independent_coordinate_strips(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image = np.full((4, 6, 3), 180, dtype=np.uint8)
            for name in ("0_0.jpg", "0_-4.jpg", "10_0.jpg", "10_-4.jpg"):
                self.assertTrue(cv2.imwrite(str(root / name), image), msg=name)

            with (root / "virtual_coordinates.csv").open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["index", "x", "y", "filename"])
                writer.writeheader()
                writer.writerows(
                    [
                        {"index": 1, "x": 0, "y": 0, "filename": "0_0.jpg"},
                        {"index": 2, "x": 0, "y": -4, "filename": "0_-4.jpg"},
                        {"index": 3, "x": 10, "y": -4, "filename": "10_-4.jpg"},
                        {"index": 4, "x": 10, "y": 0, "filename": "10_0.jpg"},
                    ]
                )

            result = stitch_by_coordinates(
                input_dir=root,
                output_dir=root / "out",
                overlap_ratio=0.5,
                blend_mode="strip_ownership",
                result_name="result.png",
                preview_name="preview.jpg",
                metadata_name="placements.json",
            )

            self.assertEqual(result["strip_axis"], "x")
            self.assertEqual(len(result["strips"]), 2)
            for strip in result["strips"]:
                self.assertTrue(Path(str(strip["path"])).exists())
                self.assertEqual(strip["tile_count"], 2)

    def test_pairwise_strip_uses_capture_time_detection_features(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image = np.full((40, 40, 3), 120, dtype=np.uint8)
            for name in ("0_0.jpg", "0_10.jpg"):
                self.assertTrue(cv2.imwrite(str(root / name), image), msg=name)

            with (root / "virtual_coordinates.csv").open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["index", "x", "y", "filename"])
                writer.writeheader()
                writer.writerows(
                    [
                        {"index": 1, "x": 0, "y": 0, "filename": "0_0.jpg"},
                        {"index": 2, "x": 0, "y": 10, "filename": "0_10.jpg"},
                    ]
                )

            detected = root / "detected"
            detected.mkdir()
            feature_payloads = {
                "0_0_features.json": {"cx": 20.0, "cy": 30.0},
                "0_10_features.json": {"cx": 20.0, "cy": 50.0},
            }
            for filename, center in feature_payloads.items():
                with (detected / filename).open("w", encoding="utf-8") as handle:
                    json.dump(
                        {
                            "image": filename.replace("_features.json", ".jpg"),
                            "model_path": "capture-time-model.pt",
                            "feature_count": 1,
                            "features": [
                                {
                                    **center,
                                    "width": 8.0,
                                    "height": 8.0,
                                    "area": 64.0,
                                    "cls_id": 1,
                                    "label": "RBC",
                                    "conf": 0.9,
                                }
                            ],
                        },
                        handle,
                    )

            result = stitch_by_coordinates(
                input_dir=root,
                output_dir=root / "out",
                overlap_ratio=0.5,
                x_pixels_per_unit=1.0,
                blend_mode="pairwise_strip",
                strip_axis="x",
                use_detection_features=True,
                detection_feature_min_matches=1,
                result_name="result.png",
                preview_name="preview.jpg",
                metadata_name="metadata.json",
            )

            self.assertEqual(result["detection_feature_source"], "capture_time_existing")
            self.assertEqual(result["detection_model_path"], "capture-time-model.pt")
            self.assertEqual(result["pairwise_alignments"][0]["method"], "detection_feature_median")
            self.assertAlmostEqual(float(result["pairwise_alignments"][0]["increment"][0]), 0.0)
            self.assertAlmostEqual(float(result["pairwise_alignments"][0]["increment"][1]), -20.0)

    def test_content_phase_uses_image_alignment_beyond_stage_guess(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rng = np.random.default_rng(1234)
            base = rng.integers(0, 256, size=(120, 170), dtype=np.uint8)
            for _ in range(30):
                center = (int(rng.integers(10, 160)), int(rng.integers(10, 110)))
                radius = int(rng.integers(3, 10))
                color = int(rng.integers(40, 230))
                cv2.circle(base, center, radius, color, -1)
            base_bgr = cv2.cvtColor(base, cv2.COLOR_GRAY2BGR)
            first = base_bgr[:, 0:120]
            second = base_bgr[:, 50:170]
            self.assertTrue(cv2.imwrite(str(root / "0_0.png"), first))
            self.assertTrue(cv2.imwrite(str(root / "10_0.png"), second))

            with (root / "virtual_coordinates.csv").open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["index", "x", "y", "filename"])
                writer.writeheader()
                writer.writerows(
                    [
                        {"index": 1, "x": 0, "y": 0, "filename": "0_0.png"},
                        {"index": 2, "x": 10, "y": 0, "filename": "10_0.png"},
                    ]
                )

            result = stitch_by_coordinates(
                input_dir=root,
                output_dir=root / "out",
                x_pixels_per_unit=5.5,
                y_pixels_per_unit=1.0,
                blend_mode="content_phase",
                result_name="result.png",
                preview_name="preview.jpg",
                metadata_name="metadata.json",
            )

            self.assertIn(result["pairwise_alignments"][0]["method"], {"phase_overlap_subpixel", "phase_overlap_subpixel_refined", "phase_ecc_refined"})
            self.assertAlmostEqual(float(result["pairwise_alignments"][0]["expected_increment"][0]), 55.0)
            self.assertAlmostEqual(float(result["pairwise_alignments"][0]["increment"][0]), 50.0, delta=1.0)
            self.assertAlmostEqual(float(result["aligned_placements"][1]["x"]), 50.0, delta=1.0)

    def test_stage_motion_convention_matches_microscope_view_direction(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image = np.full((32, 32, 3), 128, dtype=np.uint8)
            for name in ("0_0.png", "10_0.png", "0_4.png", "10_4.png"):
                self.assertTrue(cv2.imwrite(str(root / name), image), msg=name)

            with (root / "virtual_coordinates.csv").open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["index", "x", "y", "filename"])
                writer.writeheader()
                writer.writerows(
                    [
                        {"index": 1, "x": 0, "y": 0, "filename": "0_0.png"},
                        {"index": 2, "x": 10, "y": 0, "filename": "10_0.png"},
                        {"index": 3, "x": 0, "y": 4, "filename": "0_4.png"},
                        {"index": 4, "x": 10, "y": 4, "filename": "10_4.png"},
                    ]
                )

            result = stitch_by_coordinates(
                input_dir=root,
                output_dir=root / "out",
                x_pixels_per_unit=2.0,
                y_pixels_per_unit=3.0,
                blend_mode="content_phase",
                result_name="result.png",
                preview_name="preview.jpg",
                metadata_name="metadata.json",
            )

            row_expected = [
                record["initial_guess_from_stage"]
                for record in result["pairwise_alignments"]
                if record.get("content_phase_scope") == "row"
            ]
            column_expected = [
                record["initial_guess_from_stage"]
                for record in result["pairwise_alignments"]
                if record.get("content_phase_scope") == "column"
            ]
            self.assertIn([20.0, 0.0], row_expected)
            self.assertIn([0.0, -12.0], column_expected)
            self.assertEqual(result["stage_motion_convention"]["x_positive_image_motion"], "left")
            self.assertEqual(result["stage_motion_convention"]["y_positive_image_motion"], "down")

    def test_content_phase_uses_rbc_constellation_features(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image = np.full((220, 220, 3), 128, dtype=np.uint8)
            for name in ("0_0.png", "10_0.png"):
                self.assertTrue(cv2.imwrite(str(root / name), image), msg=name)

            with (root / "virtual_coordinates.csv").open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["index", "x", "y", "filename"])
                writer.writeheader()
                writer.writerows(
                    [
                        {"index": 1, "x": 0, "y": 0, "filename": "0_0.png"},
                        {"index": 2, "x": 10, "y": 0, "filename": "10_0.png"},
                    ]
                )

            detected = root / "detected"
            detected.mkdir()
            ref_points = [(120, 40), (154, 70), (132, 108), (180, 126), (104, 150), (166, 170)]
            mov_points = [(x - 48, y + 7) for x, y in ref_points]
            for image_name, points in (("0_0.png", ref_points), ("10_0.png", mov_points)):
                with (detected / f"{Path(image_name).stem}_features.json").open("w", encoding="utf-8") as handle:
                    json.dump(
                        {
                            "image": image_name,
                            "model_path": "synthetic-rbc.pt",
                            "feature_count": len(points),
                            "features": [
                                {
                                    "cx": float(x),
                                    "cy": float(y),
                                    "width": 28.0,
                                    "height": 28.0,
                                    "area": 784.0,
                                    "cls_id": 1,
                                    "label": "RBC",
                                    "conf": 0.9,
                                }
                                for x, y in points
                            ],
                        },
                        handle,
                    )

            result = stitch_by_coordinates(
                input_dir=root,
                output_dir=root / "out",
                x_pixels_per_unit=5.5,
                y_pixels_per_unit=1.0,
                blend_mode="content_phase",
                use_detection_features=True,
                detection_feature_min_matches=3,
                result_name="result.png",
                preview_name="preview.jpg",
                metadata_name="metadata.json",
            )

            record = result["pairwise_alignments"][0]
            self.assertIn(record["method"], {"rbc_constellation", "rbc_constellation_phase", "rbc_constellation_ecc"})
            self.assertAlmostEqual(float(record["increment"][0]), 48.0, delta=2.0)
            self.assertAlmostEqual(float(record["increment"][1]), -7.0, delta=2.0)

    def test_content_phase_uses_rbc_density_map_when_constellation_is_sparse(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image = np.full((240, 240, 3), 128, dtype=np.uint8)
            for name in ("0_0.png", "10_0.png"):
                self.assertTrue(cv2.imwrite(str(root / name), image), msg=name)

            with (root / "virtual_coordinates.csv").open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["index", "x", "y", "filename"])
                writer.writeheader()
                writer.writerows(
                    [
                        {"index": 1, "x": 0, "y": 0, "filename": "0_0.png"},
                        {"index": 2, "x": 10, "y": 0, "filename": "10_0.png"},
                    ]
                )

            detected = root / "detected"
            detected.mkdir()
            ref_points = [(150, 42), (170, 91), (132, 133), (192, 180)]
            mov_points = [(x - 52, y + 5) for x, y in ref_points]
            for image_name, points in (("0_0.png", ref_points), ("10_0.png", mov_points)):
                with (detected / f"{Path(image_name).stem}_features.json").open("w", encoding="utf-8") as handle:
                    json.dump(
                        {
                            "image": image_name,
                            "model_path": "synthetic-rbc.pt",
                            "feature_count": len(points),
                            "features": [
                                {
                                    "cx": float(x),
                                    "cy": float(y),
                                    "width": 26.0,
                                    "height": 26.0,
                                    "area": 676.0,
                                    "cls_id": 1,
                                    "label": "RBC",
                                    "conf": 0.9,
                                }
                                for x, y in points
                            ],
                        },
                        handle,
                    )

            result = stitch_by_coordinates(
                input_dir=root,
                output_dir=root / "out",
                x_pixels_per_unit=5.5,
                y_pixels_per_unit=1.0,
                blend_mode="content_phase",
                use_detection_features=True,
                detection_feature_min_matches=5,
                result_name="result.png",
                preview_name="preview.jpg",
                metadata_name="metadata.json",
            )

            record = result["pairwise_alignments"][0]
            self.assertIn(record["method"], {"rbc_density_ncc", "rbc_density_phase", "rbc_density_ecc"})
            self.assertAlmostEqual(float(record["increment"][0]), 52.0, delta=4.0)
            self.assertAlmostEqual(float(record["increment"][1]), -5.0, delta=4.0)


if __name__ == "__main__":
    unittest.main()

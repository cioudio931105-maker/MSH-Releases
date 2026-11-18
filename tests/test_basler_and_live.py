from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from cell_stitching_project.camera.basler import BaslerCameraConfig, _configure_camera, _select_device_info
from cell_stitching_project.cell_identification import BoundingBox, CellDetection
from cell_stitching_project.detect_live import DetectionSessionPaths, DetectionStabilizer, StableDetectionDecision, StableEventDispatcher, _export_label_template, _parser, _reload_detector_class_names, _validate_args, count_labels, process_frame


class _FakeNode:
    def __init__(self) -> None:
        self.value = None

    def SetValue(self, value) -> None:
        self.value = value


class _FakeCamera:
    def __init__(self) -> None:
        self.Width = _FakeNode()
        self.Height = _FakeNode()
        self.ExposureTime = _FakeNode()
        self.Gain = _FakeNode()
        self.AcquisitionFrameRateEnable = _FakeNode()
        self.AcquisitionFrameRate = _FakeNode()
        self.PixelFormat = _FakeNode()


class _FakeDevice:
    def __init__(self, serial: str, model: str) -> None:
        self._serial = serial
        self._model = model

    def GetSerialNumber(self) -> str:
        return self._serial

    def GetModelName(self) -> str:
        return self._model


class _FakeDetector:
    def predict(self, frame):
        return [
            CellDetection(
                class_id=1,
                label="cell",
                confidence=0.9,
                bbox=BoundingBox(x1=10, y1=20, x2=40, y2=60),
            )
        ]


class _FakeNameDetector(_FakeDetector):
    def __init__(self) -> None:
        self.class_names = ["power", "soda"]


class BaslerAndLiveTests(unittest.TestCase):
    def test_select_device_by_serial(self) -> None:
        devices = [_FakeDevice("A", "cam-a"), _FakeDevice("B", "cam-b")]
        selected = _select_device_info(devices, camera_serial="B", camera_index=0)
        self.assertEqual(selected.GetSerialNumber(), "B")

    def test_configure_camera_sets_expected_fields(self) -> None:
        camera = _FakeCamera()
        _configure_camera(
            camera,
            BaslerCameraConfig(width=640, height=480, exposure_us=2500.0, gain=3.0, fps=12.0, pixel_format="Mono8"),
        )
        self.assertEqual(camera.Width.value, 640)
        self.assertEqual(camera.Height.value, 480)
        self.assertEqual(camera.ExposureTime.value, 2500.0)
        self.assertEqual(camera.Gain.value, 3.0)
        self.assertTrue(camera.AcquisitionFrameRateEnable.value)
        self.assertEqual(camera.AcquisitionFrameRate.value, 12.0)
        self.assertEqual(camera.PixelFormat.value, "Mono8")

    def test_process_frame_saves_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session_paths = DetectionSessionPaths(
                root=root,
                frames_dir=root / "frames",
                crops_dir=root / "crops",
                manual_dir=root / "manual",
                detections_json=root / "detections.json",
                summary_json=root / "summary.json",
                stable_events_jsonl=root / "stable_events.jsonl",
            )
            for path in (session_paths.frames_dir, session_paths.crops_dir, session_paths.manual_dir):
                path.mkdir(parents=True, exist_ok=True)
            frame = np.zeros((120, 120, 3), dtype=np.uint8)
            detections, counts, event = process_frame(
                frame=frame,
                detector=_FakeDetector(),
                session_paths=session_paths,
                frame_index=1,
                save_crops=True,
                save_frames=True,
            )
            self.assertEqual(len(detections), 1)
            self.assertEqual(counts, {"cell": 1})
            self.assertEqual(count_labels(_FakeDetector().predict(frame)), {"cell": 1})
            self.assertEqual(event["counts"], counts)
            self.assertEqual(len(event["crops"]), 1)
            frame_path = session_paths.frames_dir / "frame_000001.png"
            self.assertTrue(frame_path.exists())
            annotated = cv2.imread(str(frame_path))
            self.assertIsNotNone(annotated)
            self.assertEqual(annotated.shape, frame.shape)

    def test_process_frame_reports_stable_label(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session_paths = DetectionSessionPaths(
                root=root,
                frames_dir=root / "frames",
                crops_dir=root / "crops",
                manual_dir=root / "manual",
                detections_json=root / "detections.json",
                summary_json=root / "summary.json",
                stable_events_jsonl=root / "stable_events.jsonl",
            )
            for path in (session_paths.frames_dir, session_paths.crops_dir, session_paths.manual_dir):
                path.mkdir(parents=True, exist_ok=True)

            frame = np.zeros((64, 64, 3), dtype=np.uint8)
            stabilizer = DetectionStabilizer(window_size=3, trigger_threshold=2)

            _detections, _counts, first_event = process_frame(
                frame=frame,
                detector=_FakeDetector(),
                session_paths=session_paths,
                frame_index=1,
                save_crops=False,
                save_frames=False,
                stabilizer=stabilizer,
            )
            self.assertIsNone(first_event["stabilized_label"])

            _detections, _counts, second_event = process_frame(
                frame=frame,
                detector=_FakeDetector(),
                session_paths=session_paths,
                frame_index=2,
                save_crops=False,
                save_frames=False,
                stabilizer=stabilizer,
            )
            self.assertEqual(second_event["stabilized_label"], "cell")
            self.assertEqual(second_event["stabilized_votes"], 2)

    def test_live_parser_defaults_to_project_preset(self) -> None:
        args = _parser().parse_args(["--output-dir", "C:\\temp\\session"])
        _validate_args(args)
        self.assertEqual(args.preset, "blood_cells_3cls")
        self.assertEqual(args.backend, "ultralytics")
        self.assertTrue(str(args.model).endswith("blood_cells_3cls_yolov8n_20260429.pt"))
        self.assertTrue(str(args.labels).endswith("blood_cells_3cls_labels.txt"))
        self.assertEqual(args.stabilization_window, 5)
        self.assertEqual(args.stabilization_threshold, 3)
        self.assertEqual(args.stable_event_cooldown, 10)

    def test_stable_event_dispatcher_writes_jsonl_and_applies_cooldown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            event_log = Path(tmp) / "stable_events.jsonl"
            dispatcher = StableEventDispatcher(cooldown_frames=3, event_log_path=event_log, command_template="{label}:{frame_index}")

            first = dispatcher.handle(
                frame_index=5,
                decision=StableDetectionDecision(label="cell", votes=3, history=["cell", "cell", "cell"]),
                counts={"cell": 1},
            )
            second = dispatcher.handle(
                frame_index=6,
                decision=StableDetectionDecision(label="cell", votes=3, history=["cell", "cell", "cell"]),
                counts={"cell": 1},
            )
            third = dispatcher.handle(
                frame_index=8,
                decision=StableDetectionDecision(label="cell", votes=3, history=["cell", "cell", "cell"]),
                counts={"cell": 1},
            )

            self.assertIsNotNone(first)
            self.assertEqual(first["command"], "cell:5")
            self.assertEqual(first["command_status"], "rendered")
            self.assertIsNone(second)
            self.assertIsNotNone(third)
            self.assertEqual(dispatcher.event_count, 2)
            rows = event_log.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(rows), 2)

    def test_export_and_reload_label_template(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            labels_path = root / "labels.txt"
            detector = _FakeNameDetector()

            exported = _export_label_template(detector, labels_path)
            self.assertEqual(exported.read_text(encoding="utf-8"), "power\nsoda\n")

            labels_path.write_text("battery\ncan\n", encoding="utf-8")
            reloaded = _reload_detector_class_names(detector, str(labels_path))
            self.assertEqual(reloaded, ["battery", "can"])
            self.assertEqual(detector.class_names, ["battery", "can"])


if __name__ == "__main__":
    unittest.main()

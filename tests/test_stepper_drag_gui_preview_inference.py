from __future__ import annotations

import importlib.util
import queue
import sys
import threading
import time
from dataclasses import dataclass
from tempfile import TemporaryDirectory
import unittest
from pathlib import Path

import numpy as np


GUI_PATH = (
    Path(__file__).resolve().parents[1]
    / "stitched_output"
    / "stitched_output"
    / "stitched_output"
    / "hardware"
    / "stepper_drag_gui.py"
)
MODULE_NAME = "msh_stepper_drag_gui_preview_test"
sys.path.insert(0, str(GUI_PATH.parent))
SPEC = importlib.util.spec_from_file_location(MODULE_NAME, GUI_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load GUI module from {GUI_PATH}")
GUI_MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[MODULE_NAME] = GUI_MODULE
SPEC.loader.exec_module(GUI_MODULE)


@dataclass
class _PreviewDetection:
    x1: int
    y1: int
    x2: int
    y2: int
    conf: float
    cls_id: int
    label: str


class PreviewInferenceTests(unittest.TestCase):
    def _gui_without_tk(self):
        gui = GUI_MODULE.StepperDragGUI.__new__(GUI_MODULE.StepperDragGUI)
        gui._preview_inference_stop = threading.Event()
        gui._preview_inference_queue = queue.Queue(maxsize=1)
        gui._preview_detection_lock = threading.Lock()
        gui._preview_detections = []
        return gui

    def test_submit_keeps_only_latest_frame(self) -> None:
        gui = self._gui_without_tk()

        for value in (1, 2, 3):
            gui._submit_preview_inference(np.full((2, 2, 3), value, dtype=np.uint8))

        self.assertEqual(gui._preview_inference_queue.qsize(), 1)
        latest = gui._preview_inference_queue.get_nowait()
        self.assertEqual(int(latest[0, 0, 0]), 3)

    def test_worker_publishes_result_and_stops(self) -> None:
        gui = self._gui_without_tk()
        gui._detect_objects = lambda frame: [int(frame[0, 0, 0])]
        worker = threading.Thread(target=gui._preview_inference_loop)
        worker.start()

        try:
            gui._submit_preview_inference(np.full((2, 2, 3), 7, dtype=np.uint8))
            deadline = time.monotonic() + 1.0
            while time.monotonic() < deadline and gui._latest_preview_detections() != [7]:
                time.sleep(0.01)
            self.assertEqual(gui._latest_preview_detections(), [7])
        finally:
            gui._preview_inference_stop.set()
            worker.join(timeout=1.0)

        self.assertFalse(worker.is_alive())

    def test_detection_boxes_scale_from_inference_copy_to_raw_display(self) -> None:
        detection = _PreviewDetection(12, 20, 60, 100, 0.9, 0, "WBC")

        scaled = GUI_MODULE.StepperDragGUI._scale_preview_detections(
            [detection],
            source_shape=(513, 768, 3),
            display_shape=(640, 960, 3),
        )

        self.assertEqual((scaled[0].x1, scaled[0].y1, scaled[0].x2, scaled[0].y2), (15, 25, 75, 125))
        self.assertEqual((detection.x1, detection.y1, detection.x2, detection.y2), (12, 20, 60, 100))

    def test_preview_confidence_is_formatted_as_read_only_detection_output(self) -> None:
        detections = [
            _PreviewDetection(0, 0, 10, 10, 0.73, 0, "WBC"),
            _PreviewDetection(20, 20, 30, 30, 0.91, 0, "WBC"),
        ]

        self.assertEqual(
            GUI_MODULE.StepperDragGUI._format_preview_confidence(detections),
            "目前偵測信心值：最高 0.91（2 個目標）",
        )
        self.assertEqual(
            GUI_MODULE.StepperDragGUI._format_preview_confidence([]),
            "目前偵測信心值：尚無結果",
        )

    def test_preview_view_fit_preserves_aspect_ratio_with_letterboxing(self) -> None:
        frame = np.full((100, 200, 3), 37, dtype=np.uint8)

        rendered = GUI_MODULE.StepperDragGUI._render_preview_view(frame, 100, 100)

        self.assertEqual(rendered.shape, (100, 100, 3))
        self.assertTrue(np.all(rendered[:25] == 0))
        self.assertTrue(np.all(rendered[25:75] == 37))
        self.assertTrue(np.all(rendered[75:] == 0))

    def test_embedded_preview_is_large_and_preserves_basler_aspect_ratio(self) -> None:
        self.assertGreaterEqual(GUI_MODULE._EMBEDDED_PREVIEW_MAX_WIDTH, 480)
        self.assertGreaterEqual(GUI_MODULE._EMBEDDED_PREVIEW_MAX_HEIGHT, 320)
        self.assertEqual(
            GUI_MODULE._EMBEDDED_PREVIEW_MAX_WIDTH * 2,
            GUI_MODULE._EMBEDDED_PREVIEW_MAX_HEIGHT * 3,
        )

    def test_preview_overlay_uses_large_outlined_text_for_both_views(self) -> None:
        calls: list[tuple] = []
        original_put_text = GUI_MODULE.put_text
        GUI_MODULE.put_text = lambda *args: calls.append(args)
        try:
            GUI_MODULE.StepperDragGUI._draw_preview_status_overlay(
                np.zeros((2064, 3088, 3), dtype=np.uint8),
                [("Live preview", (0, 255, 0)), ("coord: 0,0", (0, 220, 255))],
            )
        finally:
            GUI_MODULE.put_text = original_put_text

        self.assertGreaterEqual(GUI_MODULE._PREVIEW_OVERLAY_FONT_SCALE, 2.5)
        self.assertGreaterEqual(GUI_MODULE._PREVIEW_OVERLAY_TEXT_THICKNESS, 6)
        self.assertEqual(len(calls), 4)
        self.assertEqual(calls[0][2], (GUI_MODULE._PREVIEW_OVERLAY_MARGIN, GUI_MODULE._PREVIEW_OVERLAY_LINE_HEIGHT))
        self.assertEqual(calls[0][4], (0, 0, 0))
        self.assertEqual(calls[1][4], (0, 255, 0))

    def test_preview_view_zoom_and_pan_select_source_region_without_mutating_frame(self) -> None:
        frame = np.zeros((100, 200, 3), dtype=np.uint8)
        frame[:, :100] = 20
        frame[:, 100:] = 200
        original = frame.copy()

        rendered = GUI_MODULE.StepperDragGUI._render_preview_view(
            frame,
            100,
            100,
            zoom=2.0,
            center=(0.75, 0.5),
        )

        self.assertEqual(rendered.shape, (100, 100, 3))
        self.assertGreater(float(rendered.mean()), 150.0)
        self.assertTrue(np.array_equal(frame, original))


class MotorConnectionUiTests(unittest.TestCase):
    class _Value:
        def __init__(self, value: str = "") -> None:
            self.value = value

        def get(self) -> str:
            return self.value

        def set(self, value: str) -> None:
            self.value = value

    class _Widget:
        def __init__(self) -> None:
            self.grids: list[dict] = []
            self.packs: list[dict] = []
            self.removed = False

        def grid(self, **kwargs) -> None:
            self.grids.append(kwargs)
            self.removed = False

        def grid_remove(self) -> None:
            self.removed = True

        def pack(self, **kwargs) -> None:
            self.packs.append(kwargs)
            self.removed = False

        def pack_forget(self) -> None:
            self.removed = True

    def _gui_without_tk(self):
        gui = GUI_MODULE.StepperDragGUI.__new__(GUI_MODULE.StepperDragGUI)
        gui.axis_names = {0: "X", 1: "Y"}
        gui.stepper_by_axis = {0: None, 1: None}
        gui.port_vars = {0: self._Value("COM3"), 1: self._Value("COM4")}
        gui._append_log = lambda _message: None
        return gui

    def test_connect_selected_axes_uses_existing_connect_for_both_axes(self) -> None:
        gui = self._gui_without_tk()
        connected_axes: list[int] = []
        gui._connect = connected_axes.append

        gui._connect_selected_axes()

        self.assertEqual(connected_axes, [0, 1])

    def test_output_folder_requires_generated_or_selected_directory(self) -> None:
        gui = self._gui_without_tk()
        gui.serpentine_video_output_var = self._Value()
        gui.stitch_output_dir_var = self._Value()
        gui.capture_output_dir_var = self._Value()
        gui._wbc_capture_latest_output_dir = None
        gui._latest_stitch_output_dir = None
        gui._latest_capture_session = None

        self.assertIsNone(gui._find_openable_output_folder())

        with TemporaryDirectory() as directory:
            selected_dir = Path(directory)
            gui.stitch_output_dir_var.set(str(selected_dir))
            self.assertEqual(gui._find_openable_output_folder(), selected_dir.resolve())

    def test_empty_output_path_hides_entry_and_aligns_folder_button(self) -> None:
        gui = self._gui_without_tk()
        gui.capture_output_dir_var = self._Value()
        gui.stitch_output_dir_var = self._Value()
        capture_entry = self._Widget()
        capture_button = self._Widget()
        gui._output_path_widgets = {"capture": (capture_entry, capture_button)}

        gui._update_output_path_row("capture")
        self.assertTrue(capture_entry.removed)
        self.assertEqual(capture_button.packs[-1]["padx"], (4, 0))

        gui.capture_output_dir_var.set("C:/selected-output")
        gui._update_output_path_row("capture")
        self.assertFalse(capture_entry.removed)
        self.assertEqual(capture_entry.packs[-1]["padx"], (4, 4))
        self.assertEqual(capture_button.packs[-1]["side"], GUI_MODULE.tk.LEFT)

    def test_styled_camera_frame_preserves_raw_camera_input(self) -> None:
        gui = self._gui_without_tk()
        frame = np.array([[[1, 2, 3], [253, 254, 255]]], dtype=np.uint8)

        styled = gui._styled_camera_frame(frame)

        np.testing.assert_array_equal(styled, frame)
        self.assertFalse(np.shares_memory(styled, frame))

    def test_wbc_output_button_uses_reserved_slot_until_output_exists(self) -> None:
        gui = self._gui_without_tk()
        gui._wbc_output_slot = self._Widget()
        gui._wbc_output_button = self._Widget()
        gui._wbc_capture_latest_output_dir = None

        gui._update_wbc_output_button()
        self.assertTrue(gui._wbc_output_button.removed)
        self.assertEqual(gui._wbc_output_slot.grids[-1]["column"], 2)

        with TemporaryDirectory() as directory:
            gui._wbc_capture_latest_output_dir = Path(directory)
            gui._update_wbc_output_button()
            self.assertTrue(gui._wbc_output_slot.removed)
            self.assertEqual(gui._wbc_output_button.grids[-1]["column"], 2)


if __name__ == "__main__":
    unittest.main()

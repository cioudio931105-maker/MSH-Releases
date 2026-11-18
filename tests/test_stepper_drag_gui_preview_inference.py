from __future__ import annotations

import importlib.util
import queue
import sys
import threading
import time
from tempfile import TemporaryDirectory
import unittest
from pathlib import Path
from unittest import mock

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


class PreviewCleanupTests(unittest.TestCase):
    class _Value:
        def __init__(self, value) -> None:
            self.value = value

        def get(self):
            return self.value

    def test_q_closes_preview_and_releases_camera(self) -> None:
        gui = GUI_MODULE.StepperDragGUI.__new__(GUI_MODULE.StepperDragGUI)
        gui._preview_stop = threading.Event()
        gui._preview_inference_stop = threading.Event()
        gui._preview_inference_thread = None
        gui._preview_thread = threading.current_thread()
        gui._preview_running = True
        gui._preview_detection_lock = threading.Lock()
        gui._preview_detections = []
        gui._camera_lock = threading.Lock()
        gui.cap = mock.Mock()
        camera = gui.cap
        frame = np.zeros((8, 8, 3), dtype=np.uint8)
        gui._ensure_camera_open = mock.Mock(return_value=camera)
        gui._read_latest_frame = mock.Mock(return_value=frame)
        gui._get_virtual_coord = mock.Mock(return_value=(0, 0))
        gui._prepare_preview_frame = mock.Mock(side_effect=lambda value: value)
        gui._styled_camera_frame = mock.Mock(side_effect=lambda value: value.copy())
        gui._resize_for_display_keep_aspect = mock.Mock(side_effect=lambda value, *_args: value)
        gui.object_detect_preview_var = self._Value(False)
        gui._append_log = mock.Mock()

        with (
            mock.patch.object(GUI_MODULE.cv2, "namedWindow"),
            mock.patch.object(GUI_MODULE.cv2, "moveWindow"),
            mock.patch.object(GUI_MODULE.cv2, "imshow"),
            mock.patch.object(GUI_MODULE.cv2, "waitKey", return_value=ord("q")),
            mock.patch.object(GUI_MODULE.cv2, "destroyWindow"),
        ):
            gui._preview_loop()

        camera.release.assert_called_once_with()
        self.assertIsNone(gui.cap)
        self.assertIsNone(gui._preview_thread)
        self.assertFalse(gui._preview_running)
        self.assertTrue(gui._preview_inference_stop.is_set())


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

    def test_pylon_profile_display_uses_filename_without_editable_path_field(self) -> None:
        gui = self._gui_without_tk()
        gui.pylon_profile_path_var = self._Value("C:/profiles/basler_400x.pfs")
        gui.pylon_profile_display_var = self._Value()

        gui._update_pylon_profile_display()

        self.assertEqual(gui.pylon_profile_display_var.get(), "已選擇：basler_400x.pfs")

    def test_pylon_path_entry_appears_only_after_a_profile_is_selected(self) -> None:
        gui = self._gui_without_tk()
        gui.pylon_profile_path_var = self._Value()
        gui.pylon_profile_display_var = self._Value()
        gui._pylon_profile_status_label = self._Widget()
        gui._pylon_profile_entry = self._Widget()
        gui._pylon_profile_select_button = self._Widget()

        gui._update_pylon_profile_display()
        self.assertFalse(gui._pylon_profile_status_label.removed)
        self.assertTrue(gui._pylon_profile_entry.removed)

        gui.pylon_profile_path_var.set("C:/profiles/basler_400x.pfs")
        gui._update_pylon_profile_display()
        self.assertTrue(gui._pylon_profile_status_label.removed)
        self.assertFalse(gui._pylon_profile_entry.removed)
        self.assertEqual(gui._pylon_profile_entry.packs[-1]["before"], gui._pylon_profile_select_button)

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

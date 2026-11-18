from __future__ import annotations

import importlib.util
import sys
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock


GUI_PATH = (
    Path(__file__).resolve().parents[1]
    / "stitched_output"
    / "stitched_output"
    / "stitched_output"
    / "hardware"
    / "stepper_drag_gui.py"
)
MODULE_NAME = "msh_stepper_drag_gui_position_validity_test"
sys.path.insert(0, str(GUI_PATH.parent))
SPEC = importlib.util.spec_from_file_location(MODULE_NAME, GUI_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load GUI module from {GUI_PATH}")
GUI_MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[MODULE_NAME] = GUI_MODULE
SPEC.loader.exec_module(GUI_MODULE)


class PositionValidityTests(unittest.TestCase):
    def _gui_without_tk(self):
        gui = GUI_MODULE.StepperDragGUI.__new__(GUI_MODULE.StepperDragGUI)
        gui._coord_lock = threading.Lock()
        gui._virtual_x = 12
        gui._virtual_y = -7
        gui._virtual_coord_known = True
        gui._virtual_coord_unknown_reason = ""
        gui._wbc_capture_running = False
        gui.axis_names = {0: "X", 1: "Y"}
        gui._append_log = mock.Mock()
        return gui

    def test_unknown_position_blocks_absolute_coordinate_move(self) -> None:
        gui = self._gui_without_tk()
        gui._mark_virtual_coord_unknown("校正只完成部分移動")

        with self.assertRaisesRegex(RuntimeError, "目前平台位置未知"):
            gui._move_to_coordinate(0, 0, label="測試目標")

    def test_reset_designates_current_position_as_new_virtual_origin(self) -> None:
        gui = self._gui_without_tk()
        gui._mark_virtual_coord_unknown("相機失敗")

        gui._reset_virtual_coord()

        self.assertTrue(gui._virtual_coord_is_known())
        self.assertEqual(gui._get_virtual_coord(), (0, 0))
        gui._append_log.assert_called_with("目前位置已指定為新的虛擬原點：(0,0)；這不是實體 homing。")

    def test_shift_does_not_make_unknown_position_trusted(self) -> None:
        gui = self._gui_without_tk()
        gui._mark_virtual_coord_unknown("動作結果不明")

        self.assertEqual(gui._shift_virtual_coord(3, 4), (15, -3))
        self.assertFalse(gui._virtual_coord_is_known())

    def test_numeric_coordinate_update_does_not_make_unknown_position_trusted(self) -> None:
        gui = self._gui_without_tk()
        gui._mark_virtual_coord_unknown("動作結果不明")

        gui._set_virtual_coord(20, 30)

        self.assertEqual(gui._get_virtual_coord(), (20, 30))
        self.assertFalse(gui._virtual_coord_is_known())

    def test_failure_before_motion_preserves_known_position(self) -> None:
        gui = self._gui_without_tk()
        gui._image_feedback_running = True
        gui._capture_job_stop = threading.Event()
        gui.steps_var = mock.Mock(get=mock.Mock(return_value=8))
        gui.y_steps_var = mock.Mock(get=mock.Mock(return_value=8))
        gui.settle_ms_var = mock.Mock(get=mock.Mock(return_value=0))
        gui._current_feedback_sample_count = mock.Mock(return_value=1)
        gui._ensure_camera_open = mock.Mock(side_effect=RuntimeError("相機無法開啟"))
        gui.root = mock.Mock()

        with mock.patch.object(GUI_MODULE.messagebox, "showerror"):
            gui._run_image_feedback_calibration(0, False)

        self.assertTrue(gui._virtual_coord_is_known())
        self.assertEqual(gui._get_virtual_coord(), (12, -7))

    def test_failure_after_motion_marks_position_unknown(self) -> None:
        gui = self._gui_without_tk()
        gui._image_feedback_running = True
        gui._capture_job_stop = threading.Event()
        gui.steps_var = mock.Mock(get=mock.Mock(return_value=8))
        gui.y_steps_var = mock.Mock(get=mock.Mock(return_value=8))
        gui.settle_ms_var = mock.Mock(get=mock.Mock(return_value=0))
        gui._current_feedback_sample_count = mock.Mock(return_value=1)
        gui._ensure_camera_open = mock.Mock()
        gui._warmup_axis = mock.Mock()
        gui._capture_motion_tracking_frame = mock.Mock(side_effect=[object(), RuntimeError("相機讀取失敗")])
        gui._frame_texture_score = mock.Mock(return_value=10.0)
        gui._move_axis_steps = mock.Mock()
        gui.root = mock.Mock()

        with TemporaryDirectory() as temp_dir:
            gui._resolve_stitch_output_dir = mock.Mock(return_value=Path(temp_dir))
            with mock.patch.object(GUI_MODULE.messagebox, "showerror"):
                gui._run_image_feedback_calibration(0, False)

        self.assertFalse(gui._virtual_coord_is_known())

    def test_cancel_after_first_move_marks_position_unknown(self) -> None:
        gui = self._gui_without_tk()
        gui._image_feedback_running = True
        gui._capture_job_stop = threading.Event()
        gui.steps_var = mock.Mock(get=mock.Mock(return_value=8))
        gui.y_steps_var = mock.Mock(get=mock.Mock(return_value=8))
        gui.settle_ms_var = mock.Mock(get=mock.Mock(return_value=0))
        gui._current_feedback_sample_count = mock.Mock(return_value=2)
        gui._ensure_camera_open = mock.Mock()
        gui._warmup_axis = mock.Mock()
        gui._capture_motion_tracking_frame = mock.Mock(return_value=object())
        gui._frame_texture_score = mock.Mock(return_value=10.0)
        gui._estimate_frame_shift = mock.Mock(return_value=(1.0, 0.0, 1.0))
        gui._estimate_frame_change = mock.Mock(return_value=0.1)
        gui.root = mock.Mock()

        def move_then_cancel(*_args, **_kwargs) -> None:
            gui._capture_job_stop.set()

        gui._move_axis_steps = mock.Mock(side_effect=move_then_cancel)

        with TemporaryDirectory() as temp_dir:
            gui._resolve_stitch_output_dir = mock.Mock(return_value=Path(temp_dir))
            with mock.patch.object(GUI_MODULE.messagebox, "showerror"):
                gui._run_image_feedback_calibration(0, False)

        self.assertFalse(gui._virtual_coord_is_known())
        self.assertEqual(gui._move_axis_steps.call_count, 1)

    def test_backlash_failure_after_preload_marks_position_unknown(self) -> None:
        gui = self._gui_without_tk()
        gui._backlash_calibration_running = True
        gui.settle_ms_var = mock.Mock(get=mock.Mock(return_value=0))
        stepper = mock.Mock()
        gui._get_stepper = mock.Mock(return_value=stepper)
        gui._current_backlash_steps = mock.Mock(return_value=6)
        gui._calibration_probe_settings = mock.Mock(return_value=(1, 1))
        gui._capture_motion_tracking_frame = mock.Mock(
            side_effect=[object(), object(), RuntimeError("預壓後相機讀取失敗")]
        )
        gui._frame_texture_score = mock.Mock(return_value=10.0)
        gui._estimate_frame_change = mock.Mock(return_value=0.0)
        gui._move_axis_steps = mock.Mock()
        gui.root = mock.Mock()

        with mock.patch.object(GUI_MODULE.messagebox, "showerror"):
            gui._run_backlash_calibration(0, False)

        self.assertEqual(gui._move_axis_steps.call_count, 1)
        self.assertFalse(gui._virtual_coord_is_known())
        stepper.set_backlash_steps.assert_any_call(6)


if __name__ == "__main__":
    unittest.main()

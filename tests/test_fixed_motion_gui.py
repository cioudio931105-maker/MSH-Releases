"""Execute GUI motion paths with fake serial I/O; never connect hardware."""

import threading
import unittest
from unittest import mock

from tests.test_stepper_drag_gui_preview_inference import GUI_MODULE


class Value:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class FixedMotionGuiTests(unittest.TestCase):
    def setUp(self):
        self.gui = GUI_MODULE.StepperDragGUI.__new__(GUI_MODULE.StepperDragGUI)
        self.gui.axis_names = {0: "X", 1: "Y"}
        self.gui._append_log = mock.Mock()
        self.gui.stepper_by_axis = {}
        self.commands = {0: [], 1: []}
        for axis in (0, 1):
            stepper = GUI_MODULE.ArduinoStepper(port="COM_TEST")
            stepper._write = lambda command, _retry=True, a=axis: self.commands[a].append(command)
            stepper._readline = lambda: "DONE 8"
            stepper._write_and_wait_ok = lambda command, timeout_s=None, a=axis: (
                self.commands[a].append(command) or "OK"
            )
            self.gui.stepper_by_axis[axis] = stepper
        # Old stored UI values must not reactivate isolated movement.
        self.gui.x_backlash_var = Value(60)
        self.gui.y_backlash_var = Value(60)
        self.gui.fixed_approach_var = Value(True)
        self.gui.motion_stabilize_var = Value(True)
        self.gui.warmup_steps_var = Value(80)
        self.gui.warmup_cycles_var = Value(3)
        self.gui.settle_ms_var = Value(0)

    def test_step_moves_have_no_backlash_or_fixed_approach_extra_steps(self):
        self.gui._move_axis_steps(0, 8)
        self.gui._move_axis_steps(0, -8)
        self.assertEqual(self.commands[0], ["MOVE 8", "MOVE -8"])

    def test_all_gui_preload_entry_points_are_inert(self):
        self.gui._warmup_axis(0)
        self.gui._warmup_axis_once(0)
        self.gui._warmup_connected_axes_for_capture()
        self.gui._move_serpentine_startup_extra_steps(0, 1)
        self.gui._run_backlash_calibration(0, False)
        self.assertEqual(self.commands, {0: [], 1: []})
        self.assertEqual(self.gui._current_backlash_steps(0), 0)
        self.assertFalse(self.gui._fixed_approach_enabled())

    def test_scan_entry_and_exit_keep_fixed_rpm_even_with_old_requested_speed(self):
        self.gui._set_serpentine_motor_speed(200)
        self.gui._restore_normal_motor_speed_after_serpentine()
        for commands in self.commands.values():
            self.assertEqual(commands, ["SPEED_RPM 0.020", "SPEED_RPM 0.020"])

    def test_wbc_axis_switch_and_resume_add_no_compensation(self):
        position = [0, 0]
        self.gui._get_virtual_coord = lambda: tuple(position)
        self.gui._set_virtual_coord = lambda x, y: position.__setitem__(slice(None), [x, y])
        self.gui._wbc_capture_last_move_axis = None
        self.gui._wbc_capture_resume_y_forward_compensation_pending = True
        started_axes = set()
        self.gui._move_wbc_capture_to_coordinate(8, 0, startup_extra_done=started_axes)
        self.gui._move_wbc_capture_to_coordinate(8, 8, startup_extra_done=started_axes)
        self.assertEqual(self.commands, {0: ["MOVE 8"], 1: ["MOVE 8"]})
        self.assertEqual(position, [8, 8])

    def test_manual_stop_does_not_send_fast_speed_or_release(self):
        self.gui._manual_motion_lock = threading.Lock()
        self.gui._manual_motion_generation = {0: 0, 1: 0}
        self.gui._manual_motion_direction = {0: 1, 1: None}
        self.gui._set_manual_motion_status = mock.Mock()

        def immediate_thread(*, target, daemon):
            return mock.Mock(start=target)

        with mock.patch.object(GUI_MODULE.threading, "Thread", side_effect=immediate_thread):
            self.gui._stop_manual_motion(0)
        self.assertEqual(self.commands[0], ["STOP"])

    def test_disconnect_explicitly_releases_held_coils(self):
        self.gui._manual_motion_lock = threading.Lock()
        self.gui._manual_motion_generation = {0: 0, 1: 0}
        self.gui._manual_motion_direction = {0: None, 1: None}
        self.gui._stop_and_release_stepper(0, self.gui.stepper_by_axis[0], reason="test")
        self.assertEqual(self.commands[0], ["STOP", "RELEASE"])


if __name__ == "__main__":
    unittest.main()

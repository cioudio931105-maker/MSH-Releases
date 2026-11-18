import ast
from pathlib import Path
import unittest
from msh_app.core.msh_motion_policy import FIXED_MOTOR_RPM, FIXED_STEP_INTERVAL_US


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIRMWARE_FILES = (
    PROJECT_ROOT / "msh_app"
    / "hardware"
    / "x_motor_controller_continuous"
    / "x_motor_controller_continuous.ino",
    PROJECT_ROOT / "msh_app"
    / "hardware"
    / "y_motor_controller_continuous"
    / "y_motor_controller_continuous.ino",
)
HARDWARE_DIR = (
    PROJECT_ROOT / "msh_app"
    / "hardware"
)
GUI_PATH = HARDWARE_DIR / "stepper_drag_gui.py"
DRIVER_PATH = HARDWARE_DIR / "arduino_stepper.py"


def _class_method(tree: ast.AST, class_name: str, method_name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == method_name:
                    return item
    raise AssertionError(f"Missing {class_name}.{method_name}")


def _attribute_call_lines(method: ast.FunctionDef, object_name: str, attribute: str) -> list[int]:
    lines = []
    for node in ast.walk(method):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != attribute:
            continue
        owner = node.func.value
        if isinstance(owner, ast.Name) and owner.id == object_name:
            lines.append(node.lineno)
    return sorted(lines)


class ContinuousFirmwareContractTests(unittest.TestCase):
    def test_board_identity_is_unique_and_read_only(self) -> None:
        for axis, firmware_path in zip(("X", "Y"), FIRMWARE_FILES):
            with self.subTest(axis=axis):
                source = firmware_path.read_text(encoding="utf-8")
                start = source.index('if (cmd.equalsIgnoreCase(F("FIRMWARE_ID")))')
                end = source.index('\n  }', start)
                identity_handler = source[start:end]
                expected = (
                    f"FIRMWARE_ID MSH_FIXED_002RPM_V1 AXIS={axis} "
                    f"BOARD=MSH-B-{axis}-01 BUILD=20260916-01 TOPOLOGY=DUAL_UNO"
                )
                self.assertIn(expected, identity_handler)
                self.assertNotIn("applyPhase", identity_handler)
                self.assertNotIn("applyStep", identity_handler)
                self.assertNotIn("handleMove", identity_handler)
                self.assertIn("return;", identity_handler)

    def test_stop_holds_and_release_deenergizes(self) -> None:
        for firmware_path in FIRMWARE_FILES:
            with self.subTest(firmware=firmware_path.name):
                source = firmware_path.read_text(encoding="utf-8")
                self.assertIn("static void handleStop(bool releaseCoils)", source)
                self.assertIn("handleStop(false);", source)
                self.assertIn("handleStop(true);", source)
                self.assertIn('Serial.println(F("OK STOPPED"));', source)
                self.assertIn('Serial.println(F("OK RELEASED"));', source)
                self.assertIn("if (releaseCoils) {\n    releaseMotor();\n  }", source)
                self.assertIn(
                    "if (!g_holdEnabled && !g_blockingMotionAbort) {\n    releaseMotor();\n  }",
                    source,
                )

    def test_all_motion_uses_an_immutable_interval_at_the_phase_output(self) -> None:
        for firmware_path in FIRMWARE_FILES:
            with self.subTest(firmware=firmware_path.name):
                source = firmware_path.read_text(encoding="utf-8")
                self.assertIn(f"constexpr float kFixedMotorRpm = {FIXED_MOTOR_RPM}F;", source)
                self.assertIn(f"kFixedStepIntervalUs == {FIXED_STEP_INTERVAL_US}UL", source)
                self.assertIn("const unsigned long g_stepDelayMs =", source)
                self.assertEqual(source.count("g_stepDelayMs ="), 1)
                self.assertIn("(unsigned long)(now - g_lastStepAtUs) < kFixedStepIntervalUs", source)
                self.assertEqual(source.count("if (!applyStep(g_moveDirection)) return;"), 2)
                self.assertIn('F("ERR FIXED_RPM 0.020")', source)
                self.assertIn("const bool kLegacyPreloadEnabled = false;", source)
                self.assertNotIn("g_autoWarmupEnabled = true", source)


class GuiFirmwareContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.gui_source = GUI_PATH.read_text(encoding="utf-8-sig")
        cls.gui_tree = ast.parse(cls.gui_source)
        cls.driver_source = DRIVER_PATH.read_text(encoding="utf-8-sig")
        cls.driver_tree = ast.parse(cls.driver_source)

    def test_manual_continuous_speed_is_fixed_at_point_zero_two_rpm(self) -> None:
        values = {}
        for node in self.gui_tree.body:
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            target = node.targets[0]
            if isinstance(target, ast.Name) and target.id == "_FIXED_MANUAL_MOTOR_RPM":
                values[target.id] = ast.unparse(node.value)
        self.assertEqual(values["_FIXED_MANUAL_MOTOR_RPM"], "FIXED_MOTOR_RPM")
        start = _class_method(self.gui_tree, "StepperDragGUI", "_start_manual_motion")
        run_lines = _attribute_call_lines(start, "stepper", "run_continuous")
        self.assertTrue(run_lines, "Manual control must issue RUN through run_continuous().")

    def test_manual_stop_never_rewrites_the_fixed_motion_speed(self) -> None:
        method = _class_method(self.gui_tree, "StepperDragGUI", "_stop_manual_motion")
        stop_lines = _attribute_call_lines(method, "stepper", "stop")
        self.assertTrue(stop_lines)
        self.assertFalse(_attribute_call_lines(method, "stepper", "set_speed_ms"))
        self.assertNotIn("_restore_step_speed_after_continuous_motion", self.gui_source)

    def test_disconnect_stops_then_releases_coils(self) -> None:
        method = _class_method(self.gui_tree, "StepperDragGUI", "_stop_and_release_stepper")
        stop_lines = _attribute_call_lines(method, "stepper", "stop")
        release_lines = _attribute_call_lines(method, "stepper", "release")
        self.assertTrue(stop_lines)
        self.assertTrue(release_lines)
        self.assertLess(stop_lines[0], release_lines[0])

    def test_direct_driver_close_releases_coils(self) -> None:
        close = _class_method(self.driver_tree, "ArduinoStepper", "close")
        commands = []
        for node in ast.walk(close):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr != "_write" or not node.args:
                continue
            try:
                commands.append(ast.literal_eval(node.args[0]))
            except (ValueError, TypeError):
                continue
        self.assertIn("RELEASE", commands)
        self.assertNotIn("STOP", commands)

    def test_every_gui_stepper_call_has_a_firmware_protocol_path(self) -> None:
        protocol_by_gui_method = {
            "close": {"RELEASE"},
            "connect": {"MOTION_POLICY"},
            "move": {"MOVE"},
            "move_stabilized": {"MOVE"},
            "move_with_fixed_approach": {"MOVE"},
            "release": {"RELEASE"},
            "request_stop": {"STOP"},
            "run_continuous": {"RUN"},
            "set_backlash_steps": set(),
            "set_hold": {"HOLD"},
            "set_fixed_speed": {"SPEED_RPM"},
            "stop": {"STOP"},
            "warmup": {"WARMUP", "MOVE"},
        }
        gui_stepper_methods = {
            node.func.attr
            for node in ast.walk(self.gui_tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "stepper"
        }
        self.assertSetEqual(gui_stepper_methods, set(protocol_by_gui_method))

        firmware_source = FIRMWARE_FILES[0].read_text(encoding="utf-8")
        required_commands = set().union(*protocol_by_gui_method.values())
        for command in sorted(required_commands):
            with self.subTest(command=command):
                self.assertIn(f'F("{command}")', firmware_source)


if __name__ == "__main__":
    unittest.main()

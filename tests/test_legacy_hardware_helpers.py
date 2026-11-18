from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
HARDWARE_DIR = REPO_ROOT / "stitched_output" / "stitched_output" / "stitched_output" / "hardware"

if str(HARDWARE_DIR) not in sys.path:
    sys.path.insert(0, str(HARDWARE_DIR))


def _load_module(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_arduino_stepper = _load_module(
    "legacy_arduino_stepper_test",
    HARDWARE_DIR / "arduino_stepper.py",
)


class LegacyHardwareHelperTests(unittest.TestCase):
    def test_list_serial_port_infos_merges_pyserial_and_registry_without_duplicates(self) -> None:
        pyserial_ports = [
            _arduino_stepper.SerialPortInfo(device="COM8", description="USB-SERIAL CH340", hwid="USB\\VID_1A86"),
            _arduino_stepper.SerialPortInfo(device="COM7", description="Arduino Uno", hwid="USB\\VID_2341"),
        ]
        registry_ports = [
            _arduino_stepper.SerialPortInfo(device="COM7"),
            _arduino_stepper.SerialPortInfo(device="COM10"),
        ]

        with (
            mock.patch.object(_arduino_stepper, "_list_serial_ports_pyserial", return_value=pyserial_ports),
            mock.patch.object(_arduino_stepper, "_list_serial_ports_windows_registry", return_value=registry_ports),
        ):
            infos = _arduino_stepper.list_serial_port_infos()

        self.assertEqual([info.device for info in infos], ["COM7", "COM8", "COM10"])
        self.assertEqual(infos[0].description, "Arduino Uno")
        self.assertEqual(infos[2].description, "")

    def test_list_serial_ports_returns_device_names_from_infos(self) -> None:
        infos = [
            _arduino_stepper.SerialPortInfo(device="COM3"),
            _arduino_stepper.SerialPortInfo(device="COM7"),
            _arduino_stepper.SerialPortInfo(device="COM12"),
        ]

        with mock.patch.object(_arduino_stepper, "list_serial_port_infos", return_value=infos):
            ports = _arduino_stepper.list_serial_ports()

        self.assertEqual(ports, ["COM3", "COM7", "COM12"])

    def test_port_sort_key_prefers_numeric_com_order(self) -> None:
        ordered = sorted(["COM12", "COM3", "COM7", "TTYUSB0"], key=_arduino_stepper._port_sort_key)
        self.assertEqual(ordered, ["COM3", "COM7", "COM12", "TTYUSB0"])

    def test_fixed_approach_overshoots_then_returns_from_requested_direction(self) -> None:
        stepper = _arduino_stepper.ArduinoStepper(port="COM_TEST")
        calls: list[tuple[int, bool]] = []

        def fake_move(steps: int, wait_done: bool = True, motor_id=None, apply_backlash: bool = True) -> str:
            calls.append((int(steps), bool(apply_backlash)))
            return f"DONE {steps}"

        stepper.move = fake_move  # type: ignore[method-assign]

        resp = stepper.move_with_fixed_approach(
            -8,
            approach_direction=1,
            preload_steps=6,
            settle_s=0.0,
        )

        self.assertEqual(calls, [(-14, False), (6, False)])
        self.assertEqual(resp, "DONE -14; DONE 6")

    def test_fixed_approach_moves_directly_when_already_approaching(self) -> None:
        stepper = _arduino_stepper.ArduinoStepper(port="COM_TEST")
        calls: list[tuple[int, bool]] = []

        def fake_move(steps: int, wait_done: bool = True, motor_id=None, apply_backlash: bool = True) -> str:
            calls.append((int(steps), bool(apply_backlash)))
            return f"DONE {steps}"

        stepper.move = fake_move  # type: ignore[method-assign]

        resp = stepper.move_with_fixed_approach(
            8,
            approach_direction=1,
            preload_steps=6,
            settle_s=0.0,
        )

        self.assertEqual(calls, [(8, False)])
        self.assertEqual(resp, "DONE 8")

    def test_continuous_motor_commands_are_clamped_and_formatted(self) -> None:
        stepper = _arduino_stepper.ArduinoStepper(port="COM_TEST")
        commands: list[str] = []

        def fake_write_and_wait(line: str, timeout_s=None) -> str:
            commands.append(line)
            return "OK"

        stepper._write_and_wait_ok = fake_write_and_wait  # type: ignore[method-assign]

        self.assertEqual(stepper.run_continuous(1, 99.0), "OK")
        self.assertEqual(stepper.run_continuous(-1, 0.01), "OK")
        self.assertEqual(stepper.release(), "OK")
        self.assertEqual(commands, ["RUN CW 15.000", "RUN CCW 0.010", "RELEASE"])


if __name__ == "__main__":
    unittest.main()

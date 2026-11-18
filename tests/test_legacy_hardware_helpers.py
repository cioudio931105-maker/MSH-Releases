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

    def test_isolated_fixed_approach_never_adds_reverse_preload(self) -> None:
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

        self.assertEqual(calls, [(-8, False)])
        self.assertEqual(resp, "DONE -8")

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

    def test_continuous_motor_commands_only_accept_fixed_rpm(self) -> None:
        stepper = _arduino_stepper.ArduinoStepper(port="COM_TEST")
        commands: list[str] = []

        def fake_write_and_wait(line: str, timeout_s=None) -> str:
            commands.append(line)
            return "OK"

        stepper._write_and_wait_ok = fake_write_and_wait  # type: ignore[method-assign]

        for rpm in (99.0, 0.01, 0.0, float("nan"), float("inf")):
            with self.subTest(rpm=rpm), self.assertRaises(ValueError):
                stepper.run_continuous(1, rpm)
        self.assertEqual(commands, [])
        self.assertEqual(stepper.run_continuous(1, 0.02), "OK")
        self.assertEqual(stepper.run_continuous(-1, 0.02), "OK")
        self.assertEqual(stepper.release(), "OK")
        self.assertEqual(commands, ["RUN CW 0.020", "RUN CCW 0.020", "RELEASE"])

    def test_speed_setters_reject_old_fast_values_before_serial_write(self) -> None:
        stepper = _arduino_stepper.ArduinoStepper(port="COM_TEST")
        stepper._write_and_wait_ok = mock.Mock(return_value="OK")
        for milliseconds in (1, 5, 8, 12, 250, 700):
            with self.subTest(ms=milliseconds), self.assertRaises(ValueError):
                stepper.set_speed_ms(milliseconds)
        with self.assertRaises(ValueError):
            stepper.set_speed_us(8000)
        stepper._write_and_wait_ok.assert_not_called()
        stepper.set_fixed_speed()
        stepper._write_and_wait_ok.assert_called_once_with("SPEED_RPM 0.020")

    def test_all_moves_ignore_legacy_backlash_even_after_direction_reversal(self) -> None:
        stepper = _arduino_stepper.ArduinoStepper(port="COM_TEST", backlash_steps=80)
        stepper._write = mock.Mock()
        stepper.move(8, wait_done=False)
        stepper.move(-8, wait_done=False)
        self.assertEqual(stepper._write.call_args_list, [mock.call("MOVE 8"), mock.call("MOVE -8")])

    def test_warmup_is_rejected_without_serial_or_fallback_movement(self) -> None:
        stepper = _arduino_stepper.ArduinoStepper(port="COM_TEST")
        stepper._write = mock.Mock()
        stepper.move = mock.Mock()
        with self.assertRaisesRegex(RuntimeError, "isolated"):
            stepper.warmup(steps=80, cycles=1)
        stepper._write.assert_not_called()
        stepper.move.assert_not_called()

    def test_move_timeout_covers_full_fixed_speed_travel_and_cali_return(self) -> None:
        stepper = _arduino_stepper.ArduinoStepper(port="COM_TEST")
        # A stale host-side cache must not shorten the fixed-speed timeout.
        stepper._speed_delay_s_by_motor[0] = 0.005
        self.assertGreater(stepper._move_timeout_s(4096), 3000)
        stepper._write = mock.Mock()
        stepper._wait_for_final_response = mock.Mock(return_value="OK CALIBRATED")
        stepper.calibrate_motion(80)
        timeout = stepper._wait_for_final_response.call_args.kwargs["timeout_s"]
        self.assertGreater(timeout, 160 * 0.732422)

    def test_stop_response_interrupts_slow_move_without_waiting_for_timeout(self) -> None:
        stepper = _arduino_stepper.ArduinoStepper(port="COM_TEST")
        stepper._write = mock.Mock()
        stepper._readline = mock.Mock(return_value="OK STOPPED")
        with self.assertRaisesRegex(RuntimeError, "interrupted"):
            stepper.move(4096)
        stepper._readline.assert_called_once()

    def test_connect_requires_policy_and_does_not_probe_by_changing_speed(self) -> None:
        for response, accepted in ((_arduino_stepper.MOTION_POLICY_REPLY, True), ("ERR unknown", False)):
            with self.subTest(response=response):
                stepper = _arduino_stepper.ArduinoStepper(port="COM_TEST", boot_wait_s=0)
                fake_serial = mock.Mock(is_open=False)
                stepper._open_serial = lambda: setattr(stepper, "_ser", fake_serial)
                stepper._write = mock.Mock()
                stepper._readline = mock.Mock(return_value=response)
                if accepted:
                    stepper.connect(initialize_speed=False, probe_capabilities=False)
                    self.assertIs(stepper._ser, fake_serial)
                    fake_serial.close.assert_not_called()
                else:
                    with self.assertRaises(RuntimeError):
                        stepper.connect()
                    self.assertIsNone(stepper._ser)
                    fake_serial.close.assert_called_once()
                stepper._write.assert_called_once_with("MOTION_POLICY", _retry=False)

    def test_close_releases_coils_before_closing_serial_link(self) -> None:
        class FakeSerial:
            is_open = True

            def __init__(self) -> None:
                self.closed = False
                self.flushed = False

            def close(self) -> None:
                self.closed = True

            def flush(self) -> None:
                self.flushed = True

        stepper = _arduino_stepper.ArduinoStepper(port="COM_TEST")
        fake_serial = FakeSerial()
        commands: list[tuple[str, bool]] = []
        stepper._ser = fake_serial  # type: ignore[assignment]
        stepper._write = lambda line, _retry=True: commands.append((line, _retry))  # type: ignore[method-assign]

        stepper.close()

        self.assertEqual(commands, [("RELEASE", False)])
        self.assertTrue(fake_serial.flushed)
        self.assertTrue(fake_serial.closed)
        self.assertIsNone(stepper._ser)


if __name__ == "__main__":
    unittest.main()

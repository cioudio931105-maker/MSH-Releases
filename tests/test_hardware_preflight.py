from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cell_stitching_project import hardware_preflight


class _FakeSerialConnection:
    def __init__(self, *args, **kwargs) -> None:
        self.closed = False
        self._reads = [b"PONG\n"]

    def close(self) -> None:
        self.closed = True

    def reset_input_buffer(self) -> None:
        return None

    def reset_output_buffer(self) -> None:
        return None

    def write(self, payload: bytes) -> None:
        self.last_write = payload

    def flush(self) -> None:
        return None

    def readline(self) -> bytes:
        if self._reads:
            return self._reads.pop(0)
        return b""


class _PermissionDeniedSerial:
    def __init__(self, *args, **kwargs) -> None:
        raise PermissionError(13, "存取被拒。")


class HardwarePreflightTests(unittest.TestCase):
    def test_check_output_directory_creates_and_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "captures"
            result = hardware_preflight._check_output_directory(target, create=True)

        self.assertTrue(result["ok"])
        self.assertIn("ready", result["summary"])

    def test_check_model_detects_label_count_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model_path = root / "model.pt"
            labels_path = root / "labels.txt"
            model_path.write_text("stub", encoding="utf-8")
            labels_path.write_text("cell\nwbc\n", encoding="utf-8")

            with mock.patch.object(
                hardware_preflight,
                "_load_ultralytics_model",
                return_value=(object(), ["cell"]),
            ):
                result = hardware_preflight._check_model(
                    "cell_model",
                    model_path=model_path,
                    class_file=labels_path,
                    load_model=True,
                )

        self.assertFalse(result["ok"])
        self.assertIn("does not match", result["summary"])

    def test_check_serial_port_ping_succeeds(self) -> None:
        fake_serial = mock.Mock()
        fake_serial.Serial = _FakeSerialConnection

        with (
            mock.patch.object(
                hardware_preflight,
                "_available_serial_ports",
                return_value=[{"device": "COM7", "description": "USB-SERIAL CH340", "hwid": "USB\\VID_1A86"}],
            ),
            mock.patch.object(hardware_preflight, "serial", fake_serial),
        ):
            result = hardware_preflight._check_serial_port("COM7", baud=115200, mode="ping")

        self.assertTrue(result["ok"])
        self.assertIn("responded to PING", result["summary"])

    def test_check_serial_port_reports_locked_port(self) -> None:
        fake_serial = mock.Mock()
        fake_serial.Serial = _PermissionDeniedSerial

        with (
            mock.patch.object(
                hardware_preflight,
                "_available_serial_ports",
                return_value=[{"device": "COM8", "description": "USB-SERIAL CH340", "hwid": "USB\\VID_1A86"}],
            ),
            mock.patch.object(hardware_preflight, "serial", fake_serial),
        ):
            result = hardware_preflight._check_serial_port("COM8", baud=115200, mode="open")

        self.assertFalse(result["ok"])
        self.assertIn("locked", result["summary"])

    def test_collect_preflight_report_treats_unspecified_serial_as_warning_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp)
            live_preset = hardware_preflight.resolve_detection_preset(hardware_preflight.DEFAULT_LIVE_DETECTION_PRESET)

            with (
                mock.patch.object(
                    hardware_preflight,
                    "_check_environment",
                    return_value={"ok": True, "summary": "env ok", "report": {"warnings": [], "errors": [], "runtime": {}, "python": {"executable": "python"}}},
                ),
                mock.patch.object(
                    hardware_preflight,
                    "_check_basler",
                    return_value={"ok": True, "summary": "camera ok"},
                ),
                mock.patch.object(
                    hardware_preflight,
                    "_check_model",
                    side_effect=[
                        {"ok": True, "summary": "legacy model ok"},
                        {"ok": True, "summary": "live model ok"},
                    ],
                ),
                mock.patch.object(
                    hardware_preflight,
                    "_check_output_directory",
                    side_effect=[
                        {"ok": True, "summary": "capture dir ok", "path": str(workspace_root / "captured")},
                        {"ok": True, "summary": "stitch dir ok", "path": str(workspace_root / "output")},
                        {"ok": True, "summary": "live dir ok", "path": str(workspace_root / "session_output")},
                    ],
                ),
                mock.patch.object(hardware_preflight, "_available_serial_ports", return_value=[]),
            ):
                report = hardware_preflight.collect_preflight_report(
                    workspace_root=workspace_root,
                    require_basler=True,
                    serial_ports=[],
                    load_models=False,
                )

        self.assertTrue(report["ok"])
        self.assertTrue(any("No serial ports detected" in item for item in report["warnings"]))
        self.assertEqual(live_preset.name, "blood_cells_3cls")


if __name__ == "__main__":
    unittest.main()

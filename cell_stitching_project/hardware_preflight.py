from __future__ import annotations

from msh_model_policy import require_local_model

import argparse
import importlib
import json
import time
from pathlib import Path
from typing import Any

from .camera.basler import list_basler_devices
from .config import default_detection_model_candidates, resolve_default_detection_model_path
from .model_presets import DEFAULT_LIVE_DETECTION_PRESET, resolve_detection_preset
from .verify_environment import collect_environment_report

try:
    import serial
    from serial.tools import list_ports
except Exception:  # pragma: no cover - optional dependency during tests
    serial = None  # type: ignore[assignment]
    list_ports = None  # type: ignore[assignment]


def _workspace_root(raw: str | None) -> Path:
    if raw:
        return Path(raw).resolve()
    return Path(__file__).resolve().parents[1]


def _legacy_project_root(workspace_root: Path) -> Path:
    return workspace_root / "stitched_output" / "stitched_output" / "stitched_output"


def _status(ok: bool, summary: str, **extra: Any) -> dict[str, Any]:
    payload = {"ok": bool(ok), "summary": str(summary)}
    payload.update(extra)
    return payload


def _check_environment(workspace_root: Path, require_cuda: bool) -> dict[str, Any]:
    report = collect_environment_report(
        workspace_root=workspace_root,
        require_cuda=require_cuda,
        require_basler=False,
        skip_basler_enumeration=True,
    )
    summary = "Environment verification passed." if report["ok"] else "Environment verification failed."
    return _status(report["ok"], summary, report=report)


def _check_basler(camera_serial: str | None, require_camera: bool) -> dict[str, Any]:
    try:
        devices = list_basler_devices()
    except Exception as exc:
        return _status(
            False,
            f"Basler enumeration failed: {exc}",
            devices=[],
            selected=None,
        )

    selected = None
    if camera_serial:
        for device in devices:
            if str(device.get("serial_number", "")) == str(camera_serial):
                selected = device
                break
        if selected is None:
            return _status(
                False,
                f"Basler camera `{camera_serial}` was not found.",
                devices=devices,
                selected=None,
            )
    elif devices:
        selected = devices[0]

    if require_camera and not devices:
        return _status(False, "No Basler camera detected.", devices=[], selected=None)
    if not devices:
        return _status(True, "No Basler camera detected, but camera is optional for this run.", devices=[], selected=None)

    summary = (
        f"Detected {len(devices)} Basler camera(s). Using {selected['model_name']} ({selected['serial_number']})."
        if selected is not None
        else f"Detected {len(devices)} Basler camera(s)."
    )
    return _status(True, summary, devices=devices, selected=selected)


def _read_label_names(label_path: Path) -> list[str]:
    return [line.strip() for line in label_path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _load_ultralytics_model(model_path: Path) -> tuple[Any, list[str]]:
    ultralytics = importlib.import_module("ultralytics")
    model = ultralytics.YOLO(require_local_model(str(model_path)))
    names = getattr(model, "names", {})
    if isinstance(names, dict):
        ordered_keys = sorted(names, key=lambda key: int(key) if str(key).isdigit() else str(key))
        return model, [str(names[key]) for key in ordered_keys]
    if isinstance(names, (list, tuple)):
        return model, [str(name) for name in names]
    return model, []


def _check_model(
    name: str,
    model_path: Path,
    class_file: Path | None = None,
    load_model: bool = True,
) -> dict[str, Any]:
    if not model_path.exists():
        return _status(False, f"{name}: model file is missing.", model_path=str(model_path), class_file=str(class_file) if class_file else None)

    label_names: list[str] = []
    if class_file is not None:
        if not class_file.exists():
            return _status(False, f"{name}: class file is missing.", model_path=str(model_path), class_file=str(class_file))
        label_names = _read_label_names(class_file)
        if not label_names:
            return _status(False, f"{name}: class file is empty.", model_path=str(model_path), class_file=str(class_file))

    model_names: list[str] = []
    load_error = None
    if load_model:
        try:
            _model, model_names = _load_ultralytics_model(model_path)
        except Exception as exc:
            load_error = str(exc)

    if load_error is not None:
        return _status(
            False,
            f"{name}: model exists but failed to load.",
            model_path=str(model_path),
            class_file=str(class_file) if class_file else None,
            load_error=load_error,
            model_names=model_names,
            label_names=label_names,
        )

    if label_names and model_names and len(label_names) != len(model_names):
        return _status(
            False,
            f"{name}: class-file count does not match model names.",
            model_path=str(model_path),
            class_file=str(class_file),
            model_names=model_names,
            label_names=label_names,
        )

    summary_parts = [f"{name}: model OK"]
    if model_names:
        summary_parts.append(f"{len(model_names)} class(es)")
    if class_file is not None:
        summary_parts.append(f"labels={class_file.name}")
    return _status(
        True,
        ", ".join(summary_parts),
        model_path=str(model_path),
        class_file=str(class_file) if class_file else None,
        model_names=model_names,
        label_names=label_names,
    )


def _check_output_directory(path: Path, create: bool = True) -> dict[str, Any]:
    try:
        if create:
            path.mkdir(parents=True, exist_ok=True)
        elif not path.exists():
            return _status(False, f"Output directory is missing: {path}", path=str(path))
        if not path.exists():
            return _status(False, f"Output directory is missing: {path}", path=str(path))
        if not path.is_dir():
            return _status(False, f"Output path is not a directory: {path}", path=str(path))
        probe = path / ".preflight_write_test"
        probe.write_text("ok\n", encoding="utf-8")
        probe.unlink()
    except Exception as exc:
        return _status(False, f"Output directory is not writable: {path}", path=str(path), error=str(exc))
    return _status(True, f"Output directory is ready: {path}", path=str(path))


def _available_serial_ports() -> list[dict[str, str]]:
    if list_ports is None:
        return []
    ports: list[dict[str, str]] = []
    for port in list_ports.comports():
        ports.append(
            {
                "device": str(getattr(port, "device", "") or ""),
                "description": str(getattr(port, "description", "") or ""),
                "hwid": str(getattr(port, "hwid", "") or ""),
            }
        )
    return ports


def _check_serial_port(port: str, baud: int, mode: str) -> dict[str, Any]:
    available = _available_serial_ports()
    available_map = {item["device"].upper(): item for item in available if item.get("device")}
    details = available_map.get(str(port).upper())
    if details is None:
        return _status(False, f"Serial port `{port}` was not detected.", port=str(port), mode=mode, detected_ports=available)
    if serial is None:
        return _status(False, f"pyserial is not installed; cannot probe `{port}`.", port=str(port), mode=mode, detected_ports=available)
    if mode == "detect":
        return _status(True, f"Serial port `{port}` detected.", port=str(port), mode=mode, detected_ports=available, port_info=details)

    connection = None
    try:
        connection = serial.Serial(str(port), int(baud), timeout=1.0, write_timeout=1.0)
        time.sleep(0.1)
        if mode == "ping":
            connection.reset_input_buffer()
            connection.reset_output_buffer()
            time.sleep(1.5)
            connection.write(b"PING\n")
            connection.flush()
            deadline = time.time() + 2.0
            while time.time() < deadline:
                response = connection.readline()
                if not response:
                    continue
                decoded = response.decode("utf-8", errors="replace").strip()
                if decoded == "PONG":
                    return _status(
                        True,
                        f"Serial port `{port}` opened and responded to PING.",
                        port=str(port),
                        mode=mode,
                        detected_ports=available,
                        port_info=details,
                    )
            return _status(
                False,
                f"Serial port `{port}` opened but did not answer PING.",
                port=str(port),
                mode=mode,
                detected_ports=available,
                port_info=details,
            )
    except Exception as exc:
        error_text = str(exc)
        summary = f"Serial port `{port}` could not be opened."
        if "PermissionError" in error_text or "Access is denied" in error_text or "存取被拒" in error_text:
            summary = f"Serial port `{port}` is present but currently locked by another application."
        return _status(
            False,
            summary,
            port=str(port),
            mode=mode,
            baud=int(baud),
            detected_ports=available,
            port_info=details,
            error=error_text,
        )
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass

    return _status(
        True,
        f"Serial port `{port}` opened successfully.",
        port=str(port),
        mode=mode,
        baud=int(baud),
        detected_ports=available,
        port_info=details,
    )


def collect_preflight_report(
    workspace_root: Path,
    require_cuda: bool = False,
    require_basler: bool = True,
    camera_serial: str | None = None,
    serial_ports: list[str] | None = None,
    serial_baud: int = 115200,
    serial_mode: str = "open",
    capture_output_dir: Path | None = None,
    stitch_output_dir: Path | None = None,
    live_output_dir: Path | None = None,
    create_output_dirs: bool = True,
    load_models: bool = True,
) -> dict[str, Any]:
    legacy_root = _legacy_project_root(workspace_root)
    capture_dir = (capture_output_dir or (legacy_root / "captured")).resolve()
    stitch_dir = (stitch_output_dir or (legacy_root / "output")).resolve()
    live_dir = (live_output_dir or (workspace_root / "session_output")).resolve()
    live_preset = resolve_detection_preset(DEFAULT_LIVE_DETECTION_PRESET)
    default_detect_model = resolve_default_detection_model_path(workspace_root)
    default_detect_path = Path(default_detect_model) if default_detect_model else default_detection_model_candidates(workspace_root)[0]

    serial_ports = [port.strip() for port in (serial_ports or []) if port and port.strip()]
    serial_checks: list[dict[str, Any]] = []
    if serial_ports:
        for port in serial_ports:
            serial_checks.append(_check_serial_port(port, baud=serial_baud, mode=serial_mode))
    else:
        available = _available_serial_ports()
        summary = (
            f"Detected {len(available)} serial port(s)."
            if available
            else "No serial ports detected."
        )
        serial_checks.append(_status(bool(available), summary, detected_ports=available, mode="list"))

    report = {
        "workspace_root": str(workspace_root),
        "checks": {
            "environment": _check_environment(workspace_root, require_cuda=require_cuda),
            "camera": _check_basler(camera_serial=camera_serial, require_camera=require_basler),
            "models": {
                "legacy_cell_preview": _check_model(
                    "legacy_cell_preview",
                    default_detect_path,
                    class_file=None,
                    load_model=load_models,
                ),
                "live_detection_preset": _check_model(
                    live_preset.name,
                    live_preset.model_path,
                    class_file=live_preset.class_file,
                    load_model=load_models,
                ),
            },
            "output_dirs": {
                "capture_output": _check_output_directory(capture_dir, create=create_output_dirs),
                "stitch_output": _check_output_directory(stitch_dir, create=create_output_dirs),
                "live_output": _check_output_directory(live_dir, create=create_output_dirs),
            },
            "serial": serial_checks,
        },
        "warnings": [],
        "errors": [],
    }

    environment_report = report["checks"]["environment"]["report"]
    report["warnings"].extend(environment_report.get("warnings", []))
    report["errors"].extend(environment_report.get("errors", []))

    camera_check = report["checks"]["camera"]
    if not camera_check["ok"]:
        report["errors"].append(camera_check["summary"])

    for model_check in report["checks"]["models"].values():
        if not model_check["ok"]:
            report["errors"].append(model_check["summary"])

    for output_check in report["checks"]["output_dirs"].values():
        if not output_check["ok"]:
            report["errors"].append(output_check["summary"])

    for serial_check in serial_checks:
        if serial_ports:
            if not serial_check["ok"]:
                report["errors"].append(serial_check["summary"])
        elif not serial_check["ok"]:
            report["warnings"].append(serial_check["summary"])

    report["ok"] = not report["errors"]
    return report


def _print_model_section(report: dict[str, Any]) -> None:
    print("models:")
    for name, status in report["checks"]["models"].items():
        prefix = "OK  " if status["ok"] else "FAIL"
        print(f"  {prefix} {name}: {status['summary']}")
        if status.get("model_names"):
            print(f"       classes: {', '.join(status['model_names'])}")


def _print_output_section(report: dict[str, Any]) -> None:
    print("output_dirs:")
    for name, status in report["checks"]["output_dirs"].items():
        prefix = "OK  " if status["ok"] else "FAIL"
        print(f"  {prefix} {name}: {status['path']}")


def _print_serial_section(report: dict[str, Any]) -> None:
    print("serial:")
    for status in report["checks"]["serial"]:
        prefix = "OK  " if status["ok"] else "FAIL"
        print(f"  {prefix} {status['summary']}")
        detected_ports = status.get("detected_ports", [])
        if detected_ports:
            labels = [
                (
                    f"{item.get('device', '')} [{item.get('description', '')}]"
                    if item.get("description")
                    else f"{item.get('device', '')}"
                )
                for item in detected_ports
            ]
            print(f"       detected: {', '.join(labels)}")
        if status.get("error"):
            print(f"       error: {status['error']}")


def _print_human(report: dict[str, Any]) -> None:
    print(f"workspace_root: {report['workspace_root']}")
    environment = report["checks"]["environment"]
    print(f"environment: {'PASS' if environment['ok'] else 'FAIL'}")
    runtime = environment["report"]["runtime"]
    print(
        "  python={executable} device={device} cuda_available={cuda_available} gpu={gpu_name}".format(
            executable=environment["report"]["python"]["executable"],
            device=runtime.get("device"),
            cuda_available=runtime.get("cuda_available"),
            gpu_name=runtime.get("gpu_name"),
        )
    )

    camera = report["checks"]["camera"]
    print(f"camera: {'PASS' if camera['ok'] else 'FAIL'}")
    print(f"  {camera['summary']}")

    _print_model_section(report)
    _print_output_section(report)
    _print_serial_section(report)

    if report["warnings"]:
        print("warnings:")
        for item in report["warnings"]:
            print(f"  - {item}")
    if report["errors"]:
        print("errors:")
        for item in report["errors"]:
            print(f"  - {item}")
    print(f"overall: {'PASS' if report['ok'] else 'FAIL'}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a deployment preflight for camera, models, outputs, and serial hardware.")
    parser.add_argument("--workspace-root", default=None, help="Workspace root. Defaults to the parent of this package.")
    parser.add_argument("--require-cuda", action="store_true", help="Fail if CUDA is unavailable.")
    parser.add_argument("--no-require-basler", action="store_true", help="Allow preflight to pass even when no Basler camera is connected.")
    parser.add_argument("--camera-serial", default=None, help="Expected Basler serial number.")
    parser.add_argument("--serial-port", action="append", default=[], help="Expected serial/PLC port. Repeat for multiple ports.")
    parser.add_argument("--serial-baud", type=int, default=115200, help="Baud rate used for serial open/ping checks.")
    parser.add_argument(
        "--serial-mode",
        choices=("detect", "open", "ping"),
        default="open",
        help="`detect` only enumerates. `open` opens/closes the port. `ping` expects an Arduino-style `PONG` reply.",
    )
    parser.add_argument("--capture-output-dir", default=None, help="Capture output directory to verify.")
    parser.add_argument("--stitch-output-dir", default=None, help="Stitch output directory to verify.")
    parser.add_argument("--live-output-dir", default=None, help="Live-detection output directory to verify.")
    parser.add_argument("--no-create-output-dirs", action="store_true", help="Do not create missing output directories.")
    parser.add_argument("--skip-model-load", action="store_true", help="Check model files only, without loading the weights.")
    parser.add_argument("--json", action="store_true", help="Print the report as JSON.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    workspace_root = _workspace_root(args.workspace_root)
    report = collect_preflight_report(
        workspace_root=workspace_root,
        require_cuda=bool(args.require_cuda),
        require_basler=not bool(args.no_require_basler),
        camera_serial=args.camera_serial,
        serial_ports=list(args.serial_port or []),
        serial_baud=int(args.serial_baud),
        serial_mode=str(args.serial_mode),
        capture_output_dir=Path(args.capture_output_dir).resolve() if args.capture_output_dir else None,
        stitch_output_dir=Path(args.stitch_output_dir).resolve() if args.stitch_output_dir else None,
        live_output_dir=Path(args.live_output_dir).resolve() if args.live_output_dir else None,
        create_output_dirs=not bool(args.no_create_output_dirs),
        load_models=not bool(args.skip_model_load),
    )

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_human(report)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

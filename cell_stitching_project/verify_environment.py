from __future__ import annotations

import argparse
import importlib
import json
import platform
import struct
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from cell_stitching_project.camera.basler import list_basler_devices
    from cell_stitching_project.config import default_detection_model_candidates, resolve_default_detection_model_path
    from cell_stitching_project.runtime import probe_runtime
else:
    from .camera.basler import list_basler_devices
    from .config import default_detection_model_candidates, resolve_default_detection_model_path
    from .runtime import probe_runtime


REQUIRED_MODULES = [
    "numpy",
    "cv2",
    "matplotlib",
    "scipy",
    "skimage",
    "tqdm",
    "tifffile",
    "imageio",
    "pandas",
    "serial",
    "ultralytics",
    "onnxruntime",
    "onnx",
    "onnxscript",
    "pypylon",
]

GPU_EXTRA_MODULES = [
    "torch",
    "kornia",
]

ENTRYPOINT_MODULES = [
    "cell_stitching_project.main",
    "cell_stitching_project.serpentine_stitch",
    "cell_stitching_project.cell_identification",
    "cell_stitching_project.capture_basler",
    "cell_stitching_project.detect_live",
    "cell_stitching_project.hardware_preflight",
    "cell_stitching_project.prepare_voc_dataset",
    "cell_stitching_project.train_ssd",
    "cell_stitching_project.eval_ssd",
    "cell_stitching_project.export_ssd_onnx",
]


def _workspace_root(raw: str | None) -> Path:
    if raw:
        return Path(raw).resolve()
    return Path(__file__).resolve().parents[1]


def _module_status(name: str) -> dict[str, Any]:
    try:
        module = importlib.import_module(name)
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
            "error_type": exc.__class__.__name__,
            "diagnosis": _diagnose_import_error(name, exc),
        }
    return {"ok": True, "version": getattr(module, "__version__", "n/a")}


def _entrypoint_status(name: str) -> dict[str, Any]:
    try:
        importlib.import_module(name)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True}


def _path_status(path: Path) -> dict[str, Any]:
    return {
        "exists": path.exists(),
        "path": str(path),
    }


def _diagnose_import_error(module_name: str, exc: Exception) -> list[str]:
    message = str(exc)
    diagnoses: list[str] = []
    if "WinError 193" in message:
        diagnoses.append(
            "Windows reported WinError 193 while loading a DLL. This usually means a 32/64-bit mismatch "
            "or an incompatible native dependency inside the active environment."
        )
    if module_name in {"torch", "ultralytics"} and ("DLL" in message or "WinError" in message):
        diagnoses.append(
            "PyTorch/Ultralytics failed during native library load. Reinstall the environment with a Python, "
            "PyTorch, and CUDA build that all match the same architecture."
        )
    if module_name == "pypylon" and ("DLL" in message or "No module named" in message):
        diagnoses.append("Check that Basler Pylon runtime/SDK is installed and matches the current Python architecture.")
    return diagnoses


def collect_environment_report(
    workspace_root: Path,
    require_cuda: bool = False,
    require_basler: bool = False,
    skip_basler_enumeration: bool = False,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "workspace_root": str(workspace_root),
        "python": {
            "executable": sys.executable,
            "version": sys.version.split()[0],
            "bits": struct.calcsize("P") * 8,
            "machine": platform.machine(),
            "platform": platform.platform(),
        },
        "modules": {},
        "entrypoints": {},
        "paths": {},
        "runtime": {},
        "basler": {},
        "warnings": [],
        "errors": [],
    }

    for module_name in REQUIRED_MODULES:
        status = _module_status(module_name)
        report["modules"][module_name] = status
        if not status["ok"]:
            report["errors"].append(f"Missing required module `{module_name}`: {status['error']}")
            for diagnosis in status.get("diagnosis", []):
                report["warnings"].append(f"{module_name}: {diagnosis}")

    for module_name in GPU_EXTRA_MODULES:
        status = _module_status(module_name)
        report["modules"][module_name] = status
        if not status["ok"]:
            report["warnings"].append(f"GPU extra module `{module_name}` is unavailable: {status['error']}")
            for diagnosis in status.get("diagnosis", []):
                report["warnings"].append(f"{module_name}: {diagnosis}")

    for module_name in ENTRYPOINT_MODULES:
        status = _entrypoint_status(module_name)
        report["entrypoints"][module_name] = status
        if not status["ok"]:
            report["errors"].append(f"Entrypoint import failed for `{module_name}`: {status['error']}")

    runtime = probe_runtime(
        compute_device="cuda" if require_cuda else "auto",
        prefer_gpu=True,
        gpu_fallback_allowed=True,
        gpu_memory_budget_mb=1024,
        yolo_device="0" if require_cuda else "auto",
    )
    report["runtime"] = runtime.as_dict()
    if require_cuda and runtime.device != "cuda":
        report["errors"].append("CUDA was required but the runtime did not activate `device=cuda`.")
    elif runtime.device != "cuda":
        report["warnings"].append("Runtime is not using CUDA. GPU features will fall back to CPU.")

    legacy_root = workspace_root / "stitched_output" / "stitched_output"
    legacy_project_root = legacy_root / "stitched_output"
    model_root = legacy_project_root / "models"
    practical_stitcher_root = workspace_root / "microscope_stitcher_project"
    practical_reference_root = practical_stitcher_root / "reference"
    practical_tools_root = practical_stitcher_root / "tools"
    default_detect_model = resolve_default_detection_model_path(workspace_root)
    default_detect_path = Path(default_detect_model) if default_detect_model else default_detection_model_candidates(workspace_root)[0]

    report["paths"] = {
        "root_readme": _path_status(workspace_root / "README.md"),
        "setup_gpu_env": _path_status(workspace_root / "setup_gpu_env.ps1"),
        "package_for_transfer": _path_status(workspace_root / "package_for_transfer.ps1"),
        "legacy_launcher": _path_status(legacy_root / "device_auto_launcher.bat"),
        "legacy_gui": _path_status(legacy_project_root / "hardware" / "stepper_drag_gui.py"),
        "default_detect_model": _path_status(default_detect_path),
        "practical_stitcher": _path_status(practical_stitcher_root / "run_practical_stitch.py"),
        "practical_stitcher_ps1": _path_status(practical_stitcher_root / "run_practical_stitch.ps1"),
        "practical_stitcher_readme": _path_status(practical_stitcher_root / "README.md"),
        "practical_golden_placements": _path_status(
            practical_reference_root / "session_20260521_181641_759929_golden_placements.csv"
        ),
        "practical_learning_json": _path_status(
            practical_reference_root / "session_20260521_181641_759929_learning.json"
        ),
        "practical_golden_compare": _path_status(practical_tools_root / "compare_against_golden.py"),
        "ssd_license": _path_status(workspace_root / "cell_stitching_project" / "ssd" / "THIRD_PARTY_LICENSE_pytorch_ssd.txt"),
        "tests_dir": _path_status(workspace_root / "tests"),
    }
    for key, value in report["paths"].items():
        if not value["exists"]:
            if key in {"default_detect_model", "practical_golden_placements", "practical_learning_json"}:
                report["warnings"].append(f"Optional user-supplied model/reference is absent: {key}")
            else:
                report["errors"].append(f"Required project path is missing: {key} -> {value['path']}")

    basler: dict[str, Any] = {"enumerated": False, "devices": []}
    if not skip_basler_enumeration:
        try:
            devices = list_basler_devices()
            basler["enumerated"] = True
            basler["devices"] = devices
            if require_basler and not devices:
                report["errors"].append("Basler camera was required but no device was detected.")
            elif not devices:
                report["warnings"].append("No Basler camera detected during verification.")
        except Exception as exc:
            basler["error"] = str(exc)
            if require_basler:
                report["errors"].append(f"Basler verification failed: {exc}")
            else:
                report["warnings"].append(f"Basler verification skipped or failed: {exc}")
    else:
        basler["skipped"] = True
    report["basler"] = basler

    report["ok"] = not report["errors"]
    return report


def _print_human(report: dict[str, Any]) -> None:
    print(f"workspace_root: {report['workspace_root']}")
    print(
        "python: {executable} ({version}, {bits}-bit, {machine})".format(
            **report["python"]
        )
    )
    print(f"platform: {report['python']['platform']}")
    runtime = report["runtime"]
    print(
        "runtime: device={device} requested={requested_device} cuda_available={cuda_available} "
        "gpu={gpu_name} yolo_device={yolo_device}".format(**runtime)
    )
    print("required modules:")
    for name in REQUIRED_MODULES + GPU_EXTRA_MODULES:
        status = report["modules"][name]
        if status["ok"]:
            print(f"  OK   {name} {status.get('version', 'n/a')}")
        else:
            print(f"  FAIL {name} {status['error']}")
            for diagnosis in status.get("diagnosis", []):
                print(f"       hint: {diagnosis}")
    print("entrypoints:")
    for name, status in report["entrypoints"].items():
        prefix = "OK  " if status["ok"] else "FAIL"
        suffix = "" if status["ok"] else f" {status['error']}"
        print(f"  {prefix} {name}{suffix}")
    print("paths:")
    for name, status in report["paths"].items():
        prefix = "OK  " if status["exists"] else "MISS"
        print(f"  {prefix} {name}: {status['path']}")
    basler = report["basler"]
    if basler.get("skipped"):
        print("basler: skipped")
    elif "error" in basler:
        print(f"basler: ERROR {basler['error']}")
    else:
        print(f"basler: devices={len(basler['devices'])}")
        for device in basler["devices"]:
            print(f"  - {device['model_name']} ({device['serial_number']})")
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
    parser = argparse.ArgumentParser(description="Verify that a machine can run the full Cell_Project workflow.")
    parser.add_argument("--workspace-root", default=None, help="Workspace root. Defaults to the parent of this package.")
    parser.add_argument("--json", action="store_true", help="Print the report as JSON.")
    parser.add_argument("--require-cuda", action="store_true", help="Fail if CUDA is not active.")
    parser.add_argument("--require-basler", action="store_true", help="Fail if no Basler camera is detected.")
    parser.add_argument("--skip-basler-enumeration", action="store_true", help="Skip Basler device enumeration.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    report = collect_environment_report(
        workspace_root=_workspace_root(args.workspace_root),
        require_cuda=args.require_cuda,
        require_basler=args.require_basler,
        skip_basler_enumeration=args.skip_basler_enumeration,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_human(report)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Read-only audit of a built MSH payload, including adjacent source-file hashes."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
from msh_app.core.msh_distribution import application_files, is_application_file


MODEL_SUFFIXES = {
    ".pt", ".pth", ".ckpt", ".onnx", ".engine", ".weights", ".omc",
    ".safetensors", ".tflite", ".h5", ".keras", ".pb", ".caffemodel", ".pfs",
}
EXCLUDED_PREFIXES = (
    "ultralytics/assets/", "matplotlib/mpl-data/sample_data/",
    "pypylon/pylondataprocessingplugins/", "pypylon/dataprocessingpluginsb/", "pypylon/docs/",
)
FIRST_PARTY_PREFIXES = ("cell_stitching_project/", "microscope_stitcher_project/", "msh_app/", "stitched_output/", "assets/", "licenses/", "installer/")
SOURCE_SUBTREES = (
    "licenses",
    "microscope_stitcher_project",
    "assets/branding/v1", "cell_stitching_project",
    "msh_app/hardware",
    "msh_app/cell_identification",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def forbidden(path: str) -> bool:
    normalized = path.replace("\\", "/").lower()
    return Path(normalized).suffix in MODEL_SUFFIXES or normalized.startswith(EXCLUDED_PREFIXES)


def audit(app_dir: Path, source_root: Path) -> dict:
    internal = app_dir / "_internal"
    if not internal.is_dir():
        raise ValueError(f"Missing onedir resource root: {internal}")
    manifest = json.loads((app_dir / "MSH-build-manifest.json").read_text(encoding="utf-8-sig"))
    issues = []
    for key, expected in (("model_distribution", "user-supplied"), ("bundled_models", []), ("bundled_research_data", False)):
        if manifest.get(key) != expected:
            issues.append(f"Unexpected build manifest field: {key}")
    if sha256(app_dir / "MSH.exe") != manifest.get("app_exe_sha256"):
        issues.append("Executable SHA-256 differs from build manifest")
    files = {}
    first_party = 0
    for path in sorted(app_dir.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(app_dir).as_posix()
        resource = path.relative_to(internal).as_posix() if path.is_relative_to(internal) else relative
        if forbidden(resource):
            issues.append(f"Forbidden model/data resource: {relative}")
        if manifest.get("runtime") == "cpu" and path.suffix.lower() == ".dll" and any(
            token in path.name.lower() for token in ("torch_cuda", "cudnn", "cublas", "cudart")
        ):
            issues.append(f"Unexpected CUDA DLL in CPU build: {relative}")
        if resource.startswith(FIRST_PARTY_PREFIXES) or resource in {"LICENSE", "THIRD_PARTY_NOTICES.md"}:
            if not is_application_file(resource):
                issues.append(f"First-party resource is outside application allowlist: {resource}")
            source = source_root / resource
            if not source.is_file() or sha256(source) != sha256(path):
                issues.append(f"First-party resource differs from source snapshot: {resource}")
            first_party += 1
        if path.suffix.lower() == ".zip":
            with zipfile.ZipFile(path) as archive:
                for member in archive.namelist():
                    if forbidden(member):
                        issues.append(f"Forbidden nested resource: {relative}!{member}")
        files[relative] = {"bytes": path.stat().st_size, "sha256": sha256(path)}
    expected_sources = []
    for subtree in SOURCE_SUBTREES:
        expected_sources.extend(application_files(source_root, subtree))
    for source_name, _destination in expected_sources:
        relative = Path(source_name).relative_to(source_root)
        if not (internal / relative).is_file():
            issues.append(f"Expected application source/asset absent: {relative.as_posix()}")
    if (source_root / 'installer/run_update.ps1').is_file() and not (internal / 'installer/run_update.ps1').is_file():
        issues.append('Expected update handoff helper absent: installer/run_update.ps1')
    # The legacy snapshot predates the license bundle; new source trees require it.
    if (source_root / "LICENSE").is_file():
        if manifest.get("source_license") != "AGPL-3.0-only":
            issues.append("New release manifest lacks the selected source license")
        for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
            if not (internal / name).is_file():
                issues.append(f"Required release notice absent: {name}")
        expected_notices = {Path(source).relative_to(source_root).as_posix(): sha256(Path(source))
                            for source, _ in application_files(source_root, "licenses")}
        if manifest.get("license_notice_sha256") != expected_notices:
            issues.append("Release notice hash inventory differs from source")
    return {
        "application": "MSH", "version": manifest.get("version"),
        "build_mode": manifest.get("build_mode"), "runtime": manifest.get("runtime"),
        "file_count": len(files), "first_party_file_count": first_party,
        "total_bytes": sum(value["bytes"] for value in files.values()),
        "issues": issues, "passed": not issues, "files": files,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-dir", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = audit(args.app_dir.resolve(), args.source_root.resolve())
    if args.report:
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{'PASS' if report['passed'] else 'FAIL'}: {report['file_count']} payload files; "
          f"{report['first_party_file_count']} first-party files checked; {len(report['issues'])} issues.")
    for issue in report["issues"]:
        print(issue)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

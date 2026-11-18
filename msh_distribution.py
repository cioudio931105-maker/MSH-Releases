"""Allowlist for MSH source handoff and first-party application payloads."""

from pathlib import Path, PurePosixPath


SOURCE_SUFFIXES = {".py", ".pyw", ".ps1", ".bat", ".ino", ".spec", ".iss", ".md", ".html"}
EXCLUDED_PARTS = {
    ".git", ".agents", ".codex", ".migration-local", "__pycache__", "node_modules", "venv", "env",
    "build", "dist", "tmp", "temp", "cache", "logs", "data", "datasets", "dataset",
    "models", "reference", "reports", "runs", "staging", "backups", "output",
    "outputs", "debug", "captured", "captured_steps", "experiments", "stitched_results",
    "extracted_frames", "detections", "training_datasets", "cropped_cells",
    "cropped_cells_single", "videos", "camera_profiles",
}


def is_application_file(relative_path: str | Path) -> bool:
    path = PurePosixPath(str(relative_path).replace("\\", "/"))
    parts = tuple(part.lower() for part in path.parts)
    if path.is_absolute() or ".." in parts:
        return False
    if path.name == ".gitkeep":
        return True
    if parts[0] == "models" and path.suffix.lower() == ".md":
        return True
    if parts[:4] == ("cell_stitching_project", "ssd", "vision", "datasets"):
        return path.suffix.lower() == ".py"
    if any(part in EXCLUDED_PARTS or part.startswith((".venv", ".conda")) for part in parts[:-1]):
        return False
    name = path.name.lower()
    if str(path) == "LICENSE":
        return True
    if parts[0] == "licenses" and name.startswith(("license", "copying", "notice", "authors")):
        return path.suffix.lower() in {"", ".txt", ".md", ".rst", ".apache", ".bsd", ".external"}
    if name.startswith(".") and name not in {".gitignore", ".gitattributes"}:
        return False
    if parts[0] == "assets":
        return path.suffix.lower() in {".png", ".ico", ".md"}
    if str(path) in {"latest.json", "release/latest.example.json", "release/acceptance.example.json", "release/acceptance.json",
                    ".github/workflows/release.yml"} or name in {".gitignore", ".gitattributes"}:
        return True
    if path.suffix.lower() == ".txt":
        return parts[0] == "docs" or name.startswith(("requirements", "third_party_license")) or name == "prerequisites.txt"
    return path.suffix.lower() in SOURCE_SUFFIXES or name == "makefile" or path.suffix.lower() == ".cjs"


def application_files(root: Path, subtree: str) -> list[tuple[str, str]]:
    """PyInstaller data entries; never copy a whole mixed source/data directory."""
    return [
        (str(path), path.parent.relative_to(root).as_posix())
        for path in sorted((root / subtree).rglob("*"))
        if path.is_file() and is_application_file(path.relative_to(root))
    ]

from __future__ import annotations

import re
from pathlib import Path


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def iter_image_paths(directory: Path) -> list[Path]:
    return sorted(path for path in directory.iterdir() if path.suffix.lower() in IMAGE_EXTENSIONS)


def safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return cleaned.strip("._") or "unknown"


def normalize_cell_class(name: str) -> str:
    compact = re.sub(r"[^a-z0-9]+", "", str(name).lower())
    if compact in {"rbc", "redbloodcell", "redbloodcells", "erythrocyte", "erythrocytes"}:
        return "RBC"
    if compact in {"wbc", "whitebloodcell", "whitebloodcells", "leukocyte", "leukocytes"}:
        return "WBC"
    if compact in {"platelet", "platelets", "plt", "thrombocyte", "thrombocytes"}:
        return "Platelet"
    return safe_name(str(name))


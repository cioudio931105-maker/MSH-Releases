from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from ultralytics import YOLO

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp"}


def _iter_weight_candidates(root: Path) -> Iterable[Path]:
    if not root.exists():
        return []

    candidates: list[Path] = []
    for sub in root.iterdir():
        weights = sub / "weights"
        if not weights.exists():
            continue
        for name in ("best.pt", "last.pt"):
            candidate = weights / name
            if candidate.exists():
                candidates.append(candidate)

    return sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)


def find_model(default_dirs: tuple[str, ...] = ("runs/classify",)) -> str:
    """Find latest available classification weight under runs/classify/*/weights."""
    for directory in default_dirs:
        candidates = _iter_weight_candidates(Path(directory))
        if candidates:
            return str(candidates[0])
    return ""


def resolve_model_path(model_path: str | None = None) -> str:
    if model_path:
        return model_path

    discovered = find_model()
    if discovered:
        return discovered

    return "yolov8n-cls.pt"


def load_model(model_path: str | None = None) -> YOLO:
    return YOLO(resolve_model_path(model_path))


def collect_images(source: str | Path) -> list[str]:
    src = Path(source)
    if src.is_file():
        if src.suffix.lower() not in IMAGE_SUFFIXES:
            return []
        return [str(src)]

    if src.is_dir():
        images = [
            str(path)
            for path in src.rglob("*")
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
        ]
        return sorted(images)

    return []


def infer(model_path: str | None, source: str, save_dir: str = "runs/classify/infer"):
    model = load_model(model_path)
    src = Path(source)

    if src.is_dir():
        images = collect_images(src)
        if not images:
            print("No image files found:", source)
            return None
        print(f"Found {len(images)} images under {source}, running inference...")
        results = model(images, save=True, save_dir=save_dir)
    elif src.is_file():
        print("Running inference on single image:", source)
        results = model(str(src), save=True, save_dir=save_dir)
    else:
        print("Source path does not exist:", source)
        return None

    print("Inference finished. Results saved to", save_dir)
    return results


def export_csv(results, model, csv_path: str):
    names = model.names
    rows = []
    for result in results:
        if not hasattr(result, "probs") or result.probs is None:
            continue
        top1 = int(result.probs.top1)
        top1_prob = float(result.probs.top1conf)
        label = names.get(top1, str(top1)) if isinstance(names, dict) else str(names[top1])
        rows.append(
            {
                "image": getattr(result, "path", ""),
                "top1": label,
                "top1_prob": round(top1_prob, 4),
            }
        )

    if not rows:
        print("No probabilities to export.")
        return

    with open(csv_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["image", "top1", "top1_prob"])
        writer.writeheader()
        writer.writerows(rows)
    print("CSV report saved to", csv_path)


def top1_label(model: YOLO, image_path: str) -> str:
    results = model(image_path, verbose=False)
    result = results[0]
    top1 = int(result.probs.top1)
    names = result.names
    if isinstance(names, dict):
        return str(names.get(top1, top1))
    return str(names[top1])


from __future__ import annotations

from msh_model_policy import require_local_model, local_training_options

import random
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from ultralytics import YOLO

from .classify import find_model

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}


@dataclass
class DatasetStats:
    train_count: int
    val_count: int
    classes: list[str]


def _class_image_map(root: Path) -> dict[str, list[Path]]:
    root = Path(root)
    if not root.exists():
        return {}

    classes: dict[str, list[Path]] = {}
    for class_dir in sorted([p for p in root.iterdir() if p.is_dir()], key=lambda p: p.name.lower()):
        images = [p for p in class_dir.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES]
        if images:
            classes[class_dir.name] = sorted(images, key=lambda p: p.name.lower())
    return classes


def _clean_dir(path: Path) -> None:
    if not path.exists():
        return
    for child in path.iterdir():
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        else:
            try:
                child.unlink()
            except Exception:
                pass


def _balanced_split(items: list[Path], val_ratio: float, rng: random.Random) -> tuple[list[Path], list[Path]]:
    if not items:
        return [], []
    if len(items) == 1:
        return [items[0]], []

    items = list(items)
    rng.shuffle(items)
    n_val = int(round(len(items) * val_ratio))
    n_val = max(1, min(len(items) - 1, n_val))
    n_train = len(items) - n_val
    return items[:n_train], items[n_train:]


def _copy_set(paths: Iterable[Path], dst_dir: Path) -> int:
    dst_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    used_names: set[str] = set()
    for idx, src in enumerate(paths, start=1):
        base_name = src.name
        if base_name in used_names:
            stem = src.stem
            suffix = src.suffix
            base_name = f"{stem}_{idx:06d}{suffix}"
        used_names.add(base_name)
        shutil.copy2(src, dst_dir / base_name)
        count += 1
    return count


def prepare_dataset(
    source_dirs: list[Path],
    output_dir: Path,
    val_ratio: float = 0.2,
    seed: int = 42,
    domain_focus_dir: Path | None = None,
    domain_focus_weight: int = 1,
    clean_output: bool = True,
) -> DatasetStats:
    """Build train/val dataset from class-subfolder sources.

    source_dirs:
      each source must be: source/class_name/*.jpg
    domain_focus_dir + domain_focus_weight:
      if set, this source is oversampled to emphasize the user's own images.
    """
    rng = random.Random(seed)
    output_dir = Path(output_dir)
    train_root = output_dir / "train"
    val_root = output_dir / "val"

    if clean_output:
        _clean_dir(train_root)
        _clean_dir(val_root)
    train_root.mkdir(parents=True, exist_ok=True)
    val_root.mkdir(parents=True, exist_ok=True)

    source_dirs = [Path(p) for p in source_dirs if Path(p).exists()]
    if not source_dirs:
        raise FileNotFoundError("No valid source_dirs found.")

    class_union: set[str] = set()
    source_maps: dict[Path, dict[str, list[Path]]] = {}
    for src in source_dirs:
        class_map = _class_image_map(src)
        source_maps[src] = class_map
        class_union.update(class_map.keys())

    if not class_union:
        raise RuntimeError("No class folders with images found under source_dirs.")

    all_classes = sorted(class_union, key=str.lower)
    total_train = 0
    total_val = 0

    focus = Path(domain_focus_dir).resolve() if domain_focus_dir else None
    focus_weight = max(1, int(domain_focus_weight))

    for class_name in all_classes:
        merged: list[Path] = []
        for src in source_dirs:
            items = source_maps[src].get(class_name, [])
            if not items:
                continue
            repeat = 1
            if focus is not None and src.resolve() == focus:
                repeat = focus_weight
            for _ in range(repeat):
                merged.extend(items)

        train_items, val_items = _balanced_split(merged, float(val_ratio), rng)
        total_train += _copy_set(train_items, train_root / class_name)
        total_val += _copy_set(val_items, val_root / class_name)

    return DatasetStats(
        train_count=total_train,
        val_count=total_val,
        classes=all_classes,
    )


def resolve_base_model(model_path: str | None = None) -> str:
    if model_path:
        return model_path
    latest = find_model()
    if latest:
        return latest
    return ""


def train_classification(
    data_dir: Path,
    model_path: str | None = None,
    epochs: int = 80,
    imgsz: int = 224,
    batch: int = 16,
    patience: int = 20,
    name: str = "domain_adapt",
    project: str = "runs/classify",
    workers: int = 4,
    device: str = "",
):
    """Train a YOLO classification model with microscope-friendly augmentation."""
    model = YOLO(require_local_model(resolve_base_model(model_path)))
    kwargs = {
        "data": str(data_dir),
        "epochs": int(epochs),
        "imgsz": int(imgsz),
        "batch": int(batch),
        "patience": int(patience),
        "name": str(name),
        "project": str(project),
        "workers": int(max(1, workers)),
        "save": True,
        "plots": True,
        # Augment settings for microscope domain shift robustness.
        "hsv_h": 0.015,
        "hsv_s": 0.70,
        "hsv_v": 0.40,
        "degrees": 12.0,
        "translate": 0.08,
        "scale": 0.40,
        "shear": 5.0,
        "fliplr": 0.5,
        "flipud": 0.0,
    }
    if device:
        kwargs["device"] = device

    return model.train(**(kwargs | local_training_options(resolve_base_model(model_path))))

from __future__ import annotations

import argparse
import random
import shutil
from collections import Counter
from pathlib import Path
from typing import Any

from .cell_classes import WBC_5_CLASS_NAMES


SOURCE_TO_TARGET_LABELS = {
    "basophil": "basophil",
    "eosinophil": "eosinophil",
    "lymphocyte": "lymphocyte",
    "monocyte": "monocyte",
    "neutrophil": "neutrophil",
    "neutrophil_segmented": "neutrophil",
    "segmented_neutrophil": "neutrophil",
    "segmented-form_neutrophil": "neutrophil",
    "sne": "neutrophil",
    "band_neutrophil": "neutrophil",
    "banded_neutrophil": "neutrophil",
    "banded-form_neutrophil": "neutrophil",
    "bne": "neutrophil",
}


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_output_dir() -> Path:
    return _workspace_root() / "datasets" / "wbc5_classification_1000x"


def normalize_label(label: Any) -> str:
    return str(label or "").strip().lower().replace(" ", "_").replace("-", "_")


def map_wbc5_label(label: Any) -> str | None:
    return SOURCE_TO_TARGET_LABELS.get(normalize_label(label))


def _ensure_empty_split_dirs(output_dir: Path) -> None:
    for split in ("train", "val", "test"):
        for class_name in WBC_5_CLASS_NAMES:
            target_dir = output_dir / split / class_name
            target_dir.mkdir(parents=True, exist_ok=True)
            for existing in target_dir.iterdir():
                if existing.is_file():
                    existing.unlink()


def _save_image(image: Any, path: Path) -> None:
    if hasattr(image, "save"):
        image.convert("RGB").save(path)
        return
    source = Path(str(image))
    if source.is_file():
        shutil.copy2(source, path)
        return
    raise TypeError(f"Unsupported image payload: {type(image)!r}")


def _item_label(item: dict[str, Any]) -> str | None:
    for key in ("label_name", "label", "class", "class_name", "cell_type"):
        if key in item:
            value = item[key]
            if isinstance(value, str):
                return value
    return None


def _iter_hf_items(dataset_name: str, split: str | None = None):
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise ImportError("The `datasets` package is required to download Hugging Face datasets.") from exc

    dataset = load_dataset(dataset_name, split=split) if split else load_dataset(dataset_name)
    if hasattr(dataset, "items"):
        for split_name, split_dataset in dataset.items():
            for item in split_dataset:
                yield split_name, item
    else:
        for item in dataset:
            yield split or "all", item


def prepare_from_huggingface(
    dataset_name: str,
    output_dir: Path,
    val_ratio: float,
    test_ratio: float,
    seed: int,
    limit_per_class: int | None,
) -> Counter[str]:
    random.seed(seed)
    _ensure_empty_split_dirs(output_dir)

    buckets: dict[str, list[tuple[str, dict[str, Any]]]] = {class_name: [] for class_name in WBC_5_CLASS_NAMES}
    for source_split, item in _iter_hf_items(dataset_name):
        label = map_wbc5_label(item.get("label_name") or _item_label(item))
        if label is None and "label" in item and hasattr(item["label"], "__int__"):
            label_names = getattr(item.get("label"), "names", None)
            if label_names:
                label = map_wbc5_label(label_names[int(item["label"])])
        if label is None:
            continue
        if "image" not in item:
            continue
        buckets[label].append((source_split, item))

    counts: Counter[str] = Counter()
    for class_name, rows in buckets.items():
        random.shuffle(rows)
        if limit_per_class is not None:
            rows = rows[: max(1, int(limit_per_class))]
        total = len(rows)
        test_count = int(round(total * test_ratio))
        val_count = int(round(total * val_ratio))
        for index, (_source_split, item) in enumerate(rows):
            if index < test_count:
                split = "test"
            elif index < test_count + val_count:
                split = "val"
            else:
                split = "train"
            target = output_dir / split / class_name / f"{class_name}_{index:06d}.png"
            _save_image(item["image"], target)
            counts[f"{split}/{class_name}"] += 1
    return counts


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare a five-class WBC classification dataset.")
    parser.add_argument("--source", default="nirschl-lab/acevedo_et_al_2020")
    parser.add_argument("--output-dir", default=str(default_output_dir()))
    parser.add_argument("--val-ratio", type=float, default=0.15)
    parser.add_argument("--test-ratio", type=float, default=0.10)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--limit-per-class", type=int, default=None)
    return parser


def main() -> int:
    args = _parser().parse_args()
    output_dir = Path(args.output_dir)
    counts = prepare_from_huggingface(
        dataset_name=args.source,
        output_dir=output_dir,
        val_ratio=max(0.0, min(0.4, float(args.val_ratio))),
        test_ratio=max(0.0, min(0.4, float(args.test_ratio))),
        seed=int(args.seed),
        limit_per_class=args.limit_per_class,
    )
    print(f"output_dir={output_dir.resolve()}")
    for key in sorted(counts):
        print(f"{key}={counts[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

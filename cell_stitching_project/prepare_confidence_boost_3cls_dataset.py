from __future__ import annotations

import argparse
import csv
import os
import random
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


CLASS_NAMES = ("WBC", "RBC", "Platelets")
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}


@dataclass(frozen=True)
class Sample:
    image: Path
    label: Path
    kind: str


def workspace_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_txl_root() -> Path:
    return workspace_root() / "datasets" / "TXL-PBC_Dataset" / "TXL-PBC"


def default_manual_augmented_root() -> Path:
    return workspace_root() / "staging" / "manual_annotation_augmented_3cls" / "latest"


def default_output_root() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return workspace_root() / "staging" / "confidence_boost_3cls" / stamp


def default_pseudo_root() -> Path:
    return Path("E:/Cell_Project_training_staging/pseudo_label_3cls/latest")


def parse_label(label_path: Path) -> tuple[int, ...]:
    classes: list[int] = []
    for line_number, line in enumerate(label_path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split()
        if len(parts) != 5:
            raise ValueError(f"Invalid YOLO row in {label_path}:{line_number}: {stripped}")
        class_id = int(parts[0])
        values = [float(value) for value in parts[1:]]
        if class_id < 0 or class_id >= len(CLASS_NAMES):
            raise ValueError(f"Class id out of range in {label_path}:{line_number}: {class_id}")
        if any(value < 0.0 or value > 1.0 for value in values):
            raise ValueError(f"Normalized value out of range in {label_path}:{line_number}: {stripped}")
        classes.append(class_id)
    return tuple(classes)


def discover_split(root: Path, split: str, kind: str) -> list[Sample]:
    image_dir = root / "images" / split
    label_dir = root / "labels" / split
    if not image_dir.is_dir() or not label_dir.is_dir():
        return []
    samples: list[Sample] = []
    for image_path in sorted(path for path in image_dir.iterdir() if path.suffix.lower() in IMAGE_EXTENSIONS):
        label_path = label_dir / f"{image_path.stem}.txt"
        if not label_path.is_file():
            continue
        if not parse_label(label_path):
            continue
        samples.append(Sample(image=image_path, label=label_path, kind=kind))
    return samples


def select_representative_samples(samples: list[Sample], limit: int, seed: int) -> list[Sample]:
    if limit <= 0 or len(samples) <= limit:
        return list(samples)
    rng = random.Random(seed)
    by_priority: dict[str, list[Sample]] = {"platelet": [], "wbc": [], "rbc": []}
    for sample in samples:
        classes = set(parse_label(sample.label))
        if 2 in classes:
            by_priority["platelet"].append(sample)
        elif 0 in classes:
            by_priority["wbc"].append(sample)
        else:
            by_priority["rbc"].append(sample)
    for group in by_priority.values():
        rng.shuffle(group)

    selected: list[Sample] = []
    seen: set[Path] = set()
    # Platelets and WBC are rarer and more useful for confidence repair.
    quotas = {
        "platelet": max(1, int(limit * 0.35)),
        "wbc": max(1, int(limit * 0.35)),
        "rbc": limit,
    }
    for key in ("platelet", "wbc", "rbc"):
        for sample in by_priority[key]:
            if len(selected) >= limit:
                break
            if sample.image in seen:
                continue
            if key != "rbc" and sum(1 for s in selected if s.kind == sample.kind and key in _sample_tags(s)) >= quotas[key]:
                continue
            selected.append(sample)
            seen.add(sample.image)
    remaining = [sample for sample in samples if sample.image not in seen]
    rng.shuffle(remaining)
    selected.extend(remaining[: max(0, limit - len(selected))])
    return selected[:limit]


def _sample_tags(sample: Sample) -> set[str]:
    classes = set(parse_label(sample.label))
    tags = set()
    if 0 in classes:
        tags.add("wbc")
    if 1 in classes:
        tags.add("rbc")
    if 2 in classes:
        tags.add("platelet")
    return tags


def repeat_training_samples(
    samples: list[Sample],
    *,
    manual_repeat: int = 1,
    pseudo_repeat: int = 1,
    wbc_repeat: int = 1,
    platelet_repeat: int = 1,
) -> list[Sample]:
    repeated: list[Sample] = []
    for sample in samples:
        tags = _sample_tags(sample)
        repeats = 1
        if sample.kind == "manual":
            repeats = max(repeats, int(manual_repeat))
        if sample.kind == "pseudo":
            repeats = max(repeats, int(pseudo_repeat))
        if "wbc" in tags:
            repeats = max(repeats, int(wbc_repeat))
        if "platelet" in tags:
            repeats = max(repeats, int(platelet_repeat))
        repeated.extend([sample] * max(1, repeats))
    return repeated


def reset_output(output_root: Path) -> None:
    if output_root.exists():
        shutil.rmtree(output_root)
    for split in ("train", "val"):
        (output_root / "images" / split).mkdir(parents=True, exist_ok=True)
        (output_root / "labels" / split).mkdir(parents=True, exist_ok=True)


def link_or_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()
    try:
        os.link(source, destination)
    except OSError:
        shutil.copy2(source, destination)


def safe_stem(sample: Sample, index: int) -> str:
    base = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in sample.image.stem)
    return f"{sample.kind}_{index:06d}_{base}"


def write_yaml(output_root: Path) -> Path:
    yaml_path = output_root / "data.yaml"
    yaml_path.write_text(
        "\n".join(
            [
                f"path: {output_root.resolve().as_posix()}",
                "train: images/train",
                "val: images/val",
                "names:",
                "  0: WBC",
                "  1: RBC",
                "  2: Platelets",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return yaml_path


def build_confidence_boost_dataset(
    txl_root: Path,
    manual_augmented_root: Path,
    output_root: Path,
    *,
    pseudo_root: Path | None = None,
    max_txl_train: int = 240,
    max_txl_val: int = 80,
    seed: int = 42,
    manual_repeat: int = 1,
    pseudo_repeat: int = 1,
    wbc_repeat: int = 1,
    platelet_repeat: int = 1,
) -> Path:
    txl_train = select_representative_samples(discover_split(txl_root, "train", "txl"), max_txl_train, seed)
    txl_val = select_representative_samples(discover_split(txl_root, "val", "txl"), max_txl_val, seed + 1)
    manual_train = discover_split(manual_augmented_root, "train", "manual")
    manual_val = discover_split(manual_augmented_root, "val", "manual")
    pseudo_train = discover_split(pseudo_root, "train", "pseudo") if pseudo_root and pseudo_root.exists() else []

    if not txl_train:
        raise ValueError(f"No TXL train samples found: {txl_root}")
    if not txl_val:
        raise ValueError(f"No TXL val samples found: {txl_root}")
    if not manual_train:
        raise ValueError(f"No manual augmented train samples found: {manual_augmented_root}")

    output_root = output_root.resolve()
    reset_output(output_root)

    train_samples = repeat_training_samples(
        manual_train + pseudo_train + txl_train,
        manual_repeat=manual_repeat,
        pseudo_repeat=pseudo_repeat,
        wbc_repeat=wbc_repeat,
        platelet_repeat=platelet_repeat,
    )

    rows: list[dict[str, str]] = []
    counts = {split: {name: 0 for name in CLASS_NAMES} for split in ("train", "val")}
    index = 0
    for split, samples in (("train", train_samples), ("val", manual_val + txl_val)):
        for sample in samples:
            stem = safe_stem(sample, index)
            index += 1
            image_out = output_root / "images" / split / f"{stem}{sample.image.suffix.lower()}"
            label_out = output_root / "labels" / split / f"{stem}.txt"
            link_or_copy(sample.image, image_out)
            shutil.copy2(sample.label, label_out)
            classes = parse_label(sample.label)
            for class_id in classes:
                counts[split][CLASS_NAMES[class_id]] += 1
            rows.append(
                {
                    "split": split,
                    "kind": sample.kind,
                    "source_image": str(sample.image.resolve()),
                    "source_label": str(sample.label.resolve()),
                    "output_image": str(image_out),
                    "output_label": str(label_out),
                    "boxes": str(len(classes)),
                }
            )

    yaml_path = write_yaml(output_root)
    manifest = output_root / "confidence_boost_manifest.csv"
    with manifest.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["split", "kind", "source_image", "source_label", "output_image", "output_label", "boxes"],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"data_yaml={yaml_path}")
    print(f"manifest={manifest}")
    for split in ("train", "val"):
        image_count = len(list((output_root / "images" / split).iterdir()))
        print(f"{split}_images={image_count}")
        for name in CLASS_NAMES:
            print(f"{split}_{name}_boxes={counts[split][name]}")
    return yaml_path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a confidence-boost YOLO dataset from manual annotations and TXL-PBC.")
    parser.add_argument("--txl-root", type=Path, default=default_txl_root())
    parser.add_argument("--manual-augmented-root", type=Path, default=default_manual_augmented_root())
    parser.add_argument("--pseudo-root", type=Path, default=default_pseudo_root())
    parser.add_argument("--output-root", type=Path, default=default_output_root())
    parser.add_argument("--max-txl-train", type=int, default=240)
    parser.add_argument("--max-txl-val", type=int, default=80)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--manual-repeat", type=int, default=1)
    parser.add_argument("--pseudo-repeat", type=int, default=1)
    parser.add_argument("--wbc-repeat", type=int, default=1)
    parser.add_argument("--platelet-repeat", type=int, default=1)
    return parser


def main() -> int:
    args = _parser().parse_args()
    build_confidence_boost_dataset(
        args.txl_root,
        args.manual_augmented_root,
        args.output_root,
        pseudo_root=args.pseudo_root,
        max_txl_train=args.max_txl_train,
        max_txl_val=args.max_txl_val,
        seed=args.seed,
        manual_repeat=args.manual_repeat,
        pseudo_repeat=args.pseudo_repeat,
        wbc_repeat=args.wbc_repeat,
        platelet_repeat=args.platelet_repeat,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

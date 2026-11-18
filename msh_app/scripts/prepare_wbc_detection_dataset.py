from __future__ import annotations

# Direct source entrypoints also resolve shared modules from the workspace.
import sys as _msh_sys
from pathlib import Path as _MshPath
if not getattr(_msh_sys, "frozen", False):
    _msh_sys.path.insert(0, str(_MshPath(__file__).resolve().parents[2]))


import argparse
import csv
import hashlib
import os
import random
import shutil
from dataclasses import dataclass
from pathlib import Path


IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff")


@dataclass(frozen=True)
class Sample:
    image_path: Path
    label_path: Path
    wbc_lines: tuple[str, ...]
    total_lines: int

    @property
    def is_positive(self) -> bool:
        return bool(self.wbc_lines)


def _find_dataset_root_and_relative_label(label_path: Path) -> tuple[Path, Path] | None:
    parts = label_path.parts
    label_indexes = [i for i, part in enumerate(parts) if part.lower() == "labels"]
    if not label_indexes:
        return None
    label_index = label_indexes[-1]
    label_root = Path(*parts[: label_index + 1])
    dataset_root = label_root.parent
    relative_label = label_path.relative_to(label_root)
    return dataset_root, relative_label


def _find_image_for_label(label_path: Path) -> Path | None:
    resolved = _find_dataset_root_and_relative_label(label_path)
    if resolved is None:
        return None
    dataset_root, relative_label = resolved
    relative_stem = relative_label.with_suffix("")
    for suffix in IMAGE_SUFFIXES:
        candidate = dataset_root / "images" / relative_stem.with_suffix(suffix)
        if candidate.is_file():
            return candidate
    return None


def _parse_wbc_lines(label_path: Path, source_class_id: int) -> tuple[tuple[str, ...], int]:
    wbc_lines: list[str] = []
    total_lines = 0
    with label_path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            total_lines += 1
            parts = line.split()
            if len(parts) < 5:
                continue
            try:
                class_id = int(float(parts[0]))
                coords = [float(value) for value in parts[1:5]]
            except ValueError:
                continue
            if class_id != source_class_id:
                continue
            x_center, y_center, width, height = coords
            if not (0.0 <= x_center <= 1.0 and 0.0 <= y_center <= 1.0):
                continue
            if not (0.0 < width <= 1.0 and 0.0 < height <= 1.0):
                continue
            wbc_lines.append(f"0 {x_center:.8f} {y_center:.8f} {width:.8f} {height:.8f}")
    return tuple(wbc_lines), total_lines


def collect_samples(captured_root: Path, source_class_id: int, include_negatives: bool) -> list[Sample]:
    samples: list[Sample] = []
    seen_images: set[Path] = set()
    for label_path in sorted(captured_root.rglob("*.txt")):
        normalized = str(label_path).replace("/", "\\").lower()
        if "\\training_dataset\\labels\\" not in normalized and "\\manual_annotation_dataset\\labels\\" not in normalized:
            continue
        image_path = _find_image_for_label(label_path)
        if image_path is None:
            continue
        resolved_image = image_path.resolve()
        if resolved_image in seen_images:
            continue
        wbc_lines, total_lines = _parse_wbc_lines(label_path, source_class_id)
        if not wbc_lines and not include_negatives:
            continue
        samples.append(
            Sample(
                image_path=image_path,
                label_path=label_path,
                wbc_lines=wbc_lines,
                total_lines=total_lines,
            )
        )
        seen_images.add(resolved_image)
    return samples


def split_samples(samples: list[Sample], val_ratio: float, seed: int) -> tuple[list[Sample], list[Sample]]:
    rng = random.Random(seed)
    positives = [sample for sample in samples if sample.is_positive]
    negatives = [sample for sample in samples if not sample.is_positive]
    rng.shuffle(positives)
    rng.shuffle(negatives)

    def split_group(group: list[Sample]) -> tuple[list[Sample], list[Sample]]:
        if len(group) <= 1:
            return group, []
        val_count = int(round(len(group) * val_ratio))
        val_count = max(1, min(len(group) - 1, val_count))
        return group[val_count:], group[:val_count]

    train_pos, val_pos = split_group(positives)
    train_neg, val_neg = split_group(negatives)
    train = train_pos + train_neg
    val = val_pos + val_neg
    rng.shuffle(train)
    rng.shuffle(val)
    return train, val


def _safe_name(sample: Sample, captured_root: Path) -> str:
    try:
        relative = sample.image_path.relative_to(captured_root)
    except ValueError:
        relative = sample.image_path
    digest = hashlib.sha1(str(relative).encode("utf-8")).hexdigest()[:10]
    return f"{digest}_{sample.image_path.name}"


def _place_image(src: Path, dst: Path, image_mode: str) -> None:
    if image_mode in {"hardlink", "auto"}:
        try:
            os.link(src, dst)
            return
        except OSError:
            if image_mode == "hardlink":
                raise
    shutil.copy2(src, dst)


def write_dataset(
    samples_by_split: dict[str, list[Sample]],
    output_dir: Path,
    captured_root: Path,
    image_mode: str,
) -> dict[str, int]:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    for split in ("train", "val"):
        (output_dir / "images" / split).mkdir(parents=True, exist_ok=True)
        (output_dir / "labels" / split).mkdir(parents=True, exist_ok=True)

    manifest_path = output_dir / "manifest.csv"
    counts = {
        "train_images": 0,
        "val_images": 0,
        "train_wbc_boxes": 0,
        "val_wbc_boxes": 0,
        "train_negative_images": 0,
        "val_negative_images": 0,
    }

    with manifest_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "split",
                "image",
                "label",
                "wbc_boxes",
                "source_total_boxes",
                "source_image",
                "source_label",
            ],
        )
        writer.writeheader()
        for split, samples in samples_by_split.items():
            for sample in samples:
                image_name = _safe_name(sample, captured_root)
                label_name = Path(image_name).with_suffix(".txt").name
                dst_image = output_dir / "images" / split / image_name
                dst_label = output_dir / "labels" / split / label_name
                _place_image(sample.image_path, dst_image, image_mode)
                dst_label.write_text("\n".join(sample.wbc_lines) + ("\n" if sample.wbc_lines else ""), encoding="utf-8")

                counts[f"{split}_images"] += 1
                counts[f"{split}_wbc_boxes"] += len(sample.wbc_lines)
                if not sample.wbc_lines:
                    counts[f"{split}_negative_images"] += 1

                writer.writerow(
                    {
                        "split": split,
                        "image": str(dst_image),
                        "label": str(dst_label),
                        "wbc_boxes": len(sample.wbc_lines),
                        "source_total_boxes": sample.total_lines,
                        "source_image": str(sample.image_path),
                        "source_label": str(sample.label_path),
                    }
                )

    yaml_text = "\n".join(
        [
            f"path: {output_dir.resolve().as_posix()}",
            "train: images/train",
            "val: images/val",
            "names:",
            "  0: WBC",
            "",
        ]
    )
    (output_dir / "data.yaml").write_text(yaml_text, encoding="utf-8")
    return counts


def main() -> int:
    from msh_app.research_paths import original_research_root
    project_root = original_research_root()
    parser = argparse.ArgumentParser(description="Prepare a WBC-only YOLO detection dataset from captured annotations.")
    parser.add_argument("--captured-root", type=Path, default=project_root / "captured")
    parser.add_argument("--output", type=Path, default=project_root / "data" / "wbc_detection_focus")
    parser.add_argument("--source-class-id", type=int, default=0)
    parser.add_argument("--val-ratio", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--exclude-negatives", action="store_true")
    parser.add_argument(
        "--image-mode",
        choices=("hardlink", "copy", "auto"),
        default="hardlink",
        help="Use hard links by default to avoid duplicating large microscope images.",
    )
    args = parser.parse_args()

    samples = collect_samples(
        captured_root=args.captured_root,
        source_class_id=args.source_class_id,
        include_negatives=not args.exclude_negatives,
    )
    if not samples:
        raise RuntimeError(f"No matching samples found under {args.captured_root}")

    train, val = split_samples(samples, val_ratio=args.val_ratio, seed=args.seed)
    counts = write_dataset({"train": train, "val": val}, args.output, args.captured_root, args.image_mode)
    total_wbc = counts["train_wbc_boxes"] + counts["val_wbc_boxes"]
    total_neg = counts["train_negative_images"] + counts["val_negative_images"]

    print(f"Dataset: {args.output.resolve()}")
    print(f"Images: train={counts['train_images']} val={counts['val_images']}")
    print(f"WBC boxes: train={counts['train_wbc_boxes']} val={counts['val_wbc_boxes']} total={total_wbc}")
    print(f"Negative images: total={total_neg}")
    print(f"YAML: {(args.output / 'data.yaml').resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

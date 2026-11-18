from __future__ import annotations

import argparse
import csv
import os
import random
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import cv2


CLASS_NAMES: tuple[str, ...] = ("WBC", "RBC", "Platelets")
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}


@dataclass(frozen=True)
class YoloSample:
    source_image: Path
    source_label: Path | None
    label_rows: tuple[str, ...]
    source_kind: str

    @property
    def stem(self) -> str:
        return self.source_image.stem


def workspace_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_txl_images_train() -> Path:
    return workspace_root() / "datasets" / "TXL-PBC_Dataset" / "TXL-PBC" / "images" / "train"


def default_wbc_root() -> Path:
    return Path("C:/wbc")


def default_output_root() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return workspace_root() / "staging" / "wbc_boost_3cls" / stamp


def _parse_yolo_label(label_path: Path) -> tuple[str, ...]:
    rows: list[str] = []
    for line_number, line in enumerate(label_path.read_text(encoding="utf-8").splitlines(), start=1):
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
            raise ValueError(f"YOLO coordinates must be normalized 0..1 in {label_path}:{line_number}: {stripped}")
        rows.append(f"{class_id} " + " ".join(f"{value:.8f}" for value in values))
    return tuple(rows)


def discover_txl_train_samples(txl_images_train: Path) -> list[YoloSample]:
    label_dir = txl_images_train.parents[1] / "labels" / txl_images_train.name
    samples: list[YoloSample] = []
    for image_path in sorted(path for path in txl_images_train.iterdir() if path.suffix.lower() in IMAGE_EXTENSIONS):
        label_path = label_dir / f"{image_path.stem}.txt"
        if not label_path.is_file():
            raise FileNotFoundError(f"Missing TXL label for {image_path}: {label_path}")
        samples.append(
            YoloSample(
                source_image=image_path,
                source_label=label_path,
                label_rows=_parse_yolo_label(label_path),
                source_kind="txl_train",
            )
        )
    return samples


def discover_wbc_full_box_samples(wbc_root: Path) -> list[YoloSample]:
    samples: list[YoloSample] = []
    for image_path in sorted(path for path in wbc_root.rglob("*") if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS):
        samples.append(
            YoloSample(
                source_image=image_path,
                source_label=None,
                label_rows=("0 0.50000000 0.50000000 1.00000000 1.00000000",),
                source_kind="wbc_full_box",
            )
        )
    return samples


def _reset_output_root(output_root: Path) -> None:
    if output_root.exists():
        shutil.rmtree(output_root)
    for split in ("train", "val"):
        (output_root / "images" / split).mkdir(parents=True, exist_ok=True)
        (output_root / "labels" / split).mkdir(parents=True, exist_ok=True)


def _link_or_copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()
    try:
        os.link(source, destination)
    except OSError:
        shutil.copy2(source, destination)


def _write_wbc_image_as_rgb(source: Path, destination: Path) -> None:
    image = cv2.imread(str(source), cv2.IMREAD_UNCHANGED)
    if image is None:
        raise ValueError(f"Failed to read WBC image: {source}")
    if image.ndim == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    elif image.shape[2] == 4:
        image = cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
    elif image.shape[2] != 3:
        raise ValueError(f"Unsupported WBC image shape {image.shape}: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(destination), image):
        raise OSError(f"Failed to write WBC image: {destination}")


def _split_samples(samples: list[YoloSample], val_ratio: float, seed: int) -> tuple[list[YoloSample], list[YoloSample]]:
    by_kind: dict[str, list[YoloSample]] = {}
    for sample in samples:
        by_kind.setdefault(sample.source_kind, []).append(sample)
    rng = random.Random(seed)
    train_samples: list[YoloSample] = []
    val_samples: list[YoloSample] = []
    for kind_samples in by_kind.values():
        shuffled = list(kind_samples)
        rng.shuffle(shuffled)
        if len(shuffled) <= 1 or val_ratio <= 0:
            train_samples.extend(shuffled)
            continue
        val_count = max(1, int(round(len(shuffled) * val_ratio)))
        val_count = min(val_count, len(shuffled) - 1)
        val_samples.extend(shuffled[:val_count])
        train_samples.extend(shuffled[val_count:])
    if not val_samples:
        val_samples = list(train_samples)
    return train_samples, val_samples


def _safe_output_stem(sample: YoloSample, index: int) -> str:
    safe_stem = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in sample.stem)
    return f"{sample.source_kind}_{index:06d}_{safe_stem}"


def _write_data_yaml(output_root: Path) -> Path:
    yaml_path = output_root / "data.yaml"
    names_text = "\n".join(f"  {index}: {name}" for index, name in enumerate(CLASS_NAMES))
    yaml_path.write_text(
        (
            f"path: {output_root.resolve().as_posix()}\n"
            "train: images/train\n"
            "val: images/val\n"
            "names:\n"
            f"{names_text}\n"
        ),
        encoding="utf-8",
    )
    return yaml_path


def _write_manifest(output_root: Path, rows: list[dict[str, str]]) -> Path:
    path = output_root / "wbc_boost_manifest.csv"
    fieldnames = ["split", "kind", "source_image", "source_label", "output_image", "output_label", "boxes"]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def build_wbc_boost_dataset(
    txl_images_train: Path,
    wbc_root: Path,
    output_root: Path,
    *,
    val_ratio: float = 0.1,
    seed: int = 42,
) -> Path:
    txl_samples = discover_txl_train_samples(txl_images_train.resolve())
    wbc_samples = discover_wbc_full_box_samples(wbc_root.resolve())
    if not txl_samples:
        raise ValueError(f"No TXL train samples found: {txl_images_train}")
    if not wbc_samples:
        raise ValueError(f"No WBC full-box samples found: {wbc_root}")

    output_root = output_root.resolve()
    _reset_output_root(output_root)
    train_samples, val_samples = _split_samples(txl_samples + wbc_samples, val_ratio=val_ratio, seed=seed)

    manifest_rows: list[dict[str, str]] = []
    running_index = 0
    for split, split_samples in (("train", train_samples), ("val", val_samples)):
        for sample in split_samples:
            output_stem = _safe_output_stem(sample, running_index)
            running_index += 1
            if sample.source_kind == "wbc_full_box":
                image_out = output_root / "images" / split / f"{output_stem}.png"
                _write_wbc_image_as_rgb(sample.source_image, image_out)
            else:
                image_out = output_root / "images" / split / f"{output_stem}{sample.source_image.suffix.lower()}"
                _link_or_copy_file(sample.source_image, image_out)
            label_out = output_root / "labels" / split / f"{output_stem}.txt"
            label_out.write_text("\n".join(sample.label_rows) + "\n", encoding="utf-8")
            manifest_rows.append(
                {
                    "split": split,
                    "kind": sample.source_kind,
                    "source_image": str(sample.source_image.resolve()),
                    "source_label": "" if sample.source_label is None else str(sample.source_label.resolve()),
                    "output_image": str(image_out),
                    "output_label": str(label_out),
                    "boxes": str(len(sample.label_rows)),
                }
            )

    data_yaml = _write_data_yaml(output_root)
    _write_manifest(output_root, manifest_rows)
    return data_yaml


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a WBC-boosted three-class YOLO dataset from TXL-PBC train and WBC-only images.")
    parser.add_argument("--txl-images-train", type=Path, default=default_txl_images_train())
    parser.add_argument("--wbc-root", type=Path, default=default_wbc_root())
    parser.add_argument("--output-root", type=Path, default=default_output_root())
    parser.add_argument("--val-ratio", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=42)
    return parser


def main() -> int:
    args = _parser().parse_args()
    data_yaml = build_wbc_boost_dataset(
        args.txl_images_train,
        args.wbc_root,
        args.output_root,
        val_ratio=args.val_ratio,
        seed=args.seed,
    )
    print(f"data_yaml={data_yaml}")
    print(f"manifest={data_yaml.parent / 'wbc_boost_manifest.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

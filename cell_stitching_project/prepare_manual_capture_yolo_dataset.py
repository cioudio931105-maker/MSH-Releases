from __future__ import annotations

import argparse
import csv
import os
import random
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


CLASS_NAMES: tuple[str, ...] = ("WBC", "RBC", "Platelets")
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}


@dataclass(frozen=True)
class ManualCaptureSample:
    session: str
    source_image: Path
    source_label: Path
    yolo_rows: tuple[str, ...]

    @property
    def class_counts(self) -> tuple[int, int, int]:
        counts = [0, 0, 0]
        for row in self.yolo_rows:
            class_id = int(row.split()[0])
            counts[class_id] += 1
        return tuple(counts)


def workspace_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_captured_root() -> Path:
    return (
        workspace_root()
        / "stitched_output"
        / "stitched_output"
        / "stitched_output"
        / "captured"
    )


def default_output_root() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return workspace_root() / "staging" / "manual_capture_3cls" / stamp


def _safe_dataset_name(sample: ManualCaptureSample) -> str:
    return f"{sample.session}__{sample.source_image.stem}"


def _parse_yolo_label(label_path: Path) -> tuple[str, ...]:
    rows: list[str] = []
    for line_number, line in enumerate(label_path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split()
        if len(parts) != 5:
            raise ValueError(f"Invalid YOLO row in {label_path}:{line_number}: {stripped}")
        try:
            class_id = int(parts[0])
            values = [float(value) for value in parts[1:]]
        except ValueError as exc:
            raise ValueError(f"Non-numeric YOLO row in {label_path}:{line_number}: {stripped}") from exc
        if class_id < 0 or class_id >= len(CLASS_NAMES):
            raise ValueError(f"Class id out of range in {label_path}:{line_number}: {class_id}")
        if any(value < 0.0 or value > 1.0 for value in values):
            raise ValueError(f"YOLO coordinates must be normalized 0..1 in {label_path}:{line_number}: {stripped}")
        rows.append(f"{class_id} " + " ".join(f"{value:.8f}" for value in values))
    return tuple(rows)


def discover_manual_capture_samples(captured_root: Path, *, include_empty: bool = False) -> list[ManualCaptureSample]:
    samples: list[ManualCaptureSample] = []
    for training_dir in sorted(captured_root.glob("manual_session_*/training_dataset")):
        images_dir = training_dir / "images"
        labels_dir = training_dir / "labels"
        if not images_dir.is_dir() or not labels_dir.is_dir():
            continue
        for image_path in sorted(path for path in images_dir.iterdir() if path.suffix.lower() in IMAGE_EXTENSIONS):
            label_path = labels_dir / f"{image_path.stem}.txt"
            if not label_path.is_file():
                continue
            rows = _parse_yolo_label(label_path)
            if not rows and not include_empty:
                continue
            samples.append(
                ManualCaptureSample(
                    session=training_dir.parent.name,
                    source_image=image_path,
                    source_label=label_path,
                    yolo_rows=rows,
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


def _split_samples(samples: list[ManualCaptureSample], val_ratio: float, seed: int) -> tuple[list[ManualCaptureSample], list[ManualCaptureSample]]:
    shuffled = list(samples)
    random.Random(seed).shuffle(shuffled)
    if len(shuffled) <= 1 or val_ratio <= 0:
        return shuffled, []
    val_count = max(1, int(round(len(shuffled) * val_ratio)))
    val_count = min(val_count, len(shuffled) - 1)
    return shuffled[val_count:], shuffled[:val_count]


def _write_data_yaml(output_root: Path) -> Path:
    yaml_path = output_root / "data.yaml"
    root_text = output_root.resolve().as_posix()
    names_text = "\n".join(f"  {index}: {name}" for index, name in enumerate(CLASS_NAMES))
    yaml_path.write_text(
        (
            f"path: {root_text}\n"
            "train: images/train\n"
            "val: images/val\n"
            "names:\n"
            f"{names_text}\n"
        ),
        encoding="utf-8",
    )
    return yaml_path


def _write_manifest(output_root: Path, rows: list[dict[str, str]]) -> Path:
    manifest_path = output_root / "manual_capture_manifest.csv"
    fieldnames = [
        "split",
        "session",
        "source_image",
        "source_label",
        "output_image",
        "output_label",
        "boxes",
        "wbc",
        "rbc",
        "platelets",
    ]
    with manifest_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return manifest_path


def build_manual_capture_yolo_dataset(
    captured_root: Path,
    output_root: Path,
    *,
    val_ratio: float = 0.2,
    seed: int = 42,
    include_empty: bool = False,
) -> Path:
    captured_root = captured_root.resolve()
    output_root = output_root.resolve()
    samples = discover_manual_capture_samples(captured_root, include_empty=include_empty)
    if not samples:
        raise ValueError(f"No manual capture YOLO samples found under: {captured_root}")

    train_samples, val_samples = _split_samples(samples, val_ratio=val_ratio, seed=seed)
    if not val_samples:
        val_samples = list(train_samples)

    _reset_output_root(output_root)
    manifest_rows: list[dict[str, str]] = []
    for split, split_samples in (("train", train_samples), ("val", val_samples)):
        for sample in split_samples:
            base_name = _safe_dataset_name(sample)
            image_out = output_root / "images" / split / f"{base_name}{sample.source_image.suffix.lower()}"
            label_out = output_root / "labels" / split / f"{base_name}.txt"
            _link_or_copy_file(sample.source_image, image_out)
            label_out.write_text("\n".join(sample.yolo_rows) + ("\n" if sample.yolo_rows else ""), encoding="utf-8")
            wbc, rbc, platelets = sample.class_counts
            manifest_rows.append(
                {
                    "split": split,
                    "session": sample.session,
                    "source_image": str(sample.source_image.resolve()),
                    "source_label": str(sample.source_label.resolve()),
                    "output_image": str(image_out),
                    "output_label": str(label_out),
                    "boxes": str(len(sample.yolo_rows)),
                    "wbc": str(wbc),
                    "rbc": str(rbc),
                    "platelets": str(platelets),
                }
            )

    data_yaml = _write_data_yaml(output_root)
    _write_manifest(output_root, manifest_rows)
    return data_yaml


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a YOLO dataset from manual capture training_dataset folders.")
    parser.add_argument("--captured-root", type=Path, default=default_captured_root())
    parser.add_argument("--output-root", type=Path, default=default_output_root())
    parser.add_argument("--val-ratio", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--include-empty", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    data_yaml = build_manual_capture_yolo_dataset(
        args.captured_root,
        args.output_root,
        val_ratio=args.val_ratio,
        seed=args.seed,
        include_empty=args.include_empty,
    )
    print(f"data_yaml={data_yaml}")
    print(f"manifest={data_yaml.parent / 'manual_capture_manifest.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

from msh_app.core.msh_model_policy import require_local_model

import argparse
import csv
import json
import random
import shutil
from pathlib import Path
from typing import Any

import cv2

from .blood_cell_unified_classes import (
    UNIFIED_BLOOD_CELL_CLASS_NAMES,
    UNIFIED_BLOOD_CELL_CLASS_TO_ID,
    WBC_SUBTYPE_TO_UNIFIED_ID,
)


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
THREE_CLASS_TO_UNIFIED = {
    1: UNIFIED_BLOOD_CELL_CLASS_TO_ID["RBC"],
    2: UNIFIED_BLOOD_CELL_CLASS_TO_ID["Platelets"],
}


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_three_class_root() -> Path:
    return _workspace_root() / "datasets" / "TXL-PBC_Dataset" / "TXL-PBC"


def default_wbc5_classification_root() -> Path:
    return Path("D:/Cell_Project_Datasets/wbc5_classification_1000x")


def default_wbc5_classifier() -> Path:
    return (
        _workspace_root()
        / "stitched_output"
        / "stitched_output"
        / "stitched_output"
        / "models"
        / "wbc_5cls_1000x_cls.pt"
    )


def default_output_root() -> Path:
    return Path("D:/Cell_Project_Datasets/blood_cells_unified_7cls")


def _read_yolo_rows(label_path: Path) -> list[list[float]]:
    rows: list[list[float]] = []
    if not label_path.is_file():
        return rows
    for line in label_path.read_text(encoding="utf-8").splitlines():
        parts = line.strip().split()
        if len(parts) < 5:
            continue
        rows.append([float(value) for value in parts[:5]])
    return rows


def _clip_xyxy(x1: int, y1: int, x2: int, y2: int, width: int, height: int) -> tuple[int, int, int, int] | None:
    x1 = max(0, min(width - 1, int(x1)))
    y1 = max(0, min(height - 1, int(y1)))
    x2 = max(0, min(width, int(x2)))
    y2 = max(0, min(height, int(y2)))
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2


def _xywhn_to_xyxy(row: list[float], width: int, height: int) -> tuple[int, int, int, int] | None:
    _cls_id, cx, cy, bw, bh = row
    x1 = round((cx - bw / 2.0) * width)
    y1 = round((cy - bh / 2.0) * height)
    x2 = round((cx + bw / 2.0) * width)
    y2 = round((cy + bh / 2.0) * height)
    return _clip_xyxy(x1, y1, x2, y2, width, height)


def _xyxy_to_yolo_row(class_id: int, x1: int, y1: int, x2: int, y2: int, width: int, height: int) -> str:
    cx = ((x1 + x2) / 2.0) / float(width)
    cy = ((y1 + y2) / 2.0) / float(height)
    bw = (x2 - x1) / float(width)
    bh = (y2 - y1) / float(height)
    return f"{int(class_id)} {cx:.8f} {cy:.8f} {bw:.8f} {bh:.8f}"


def _classify_wbc_crop(model: Any, crop_bgr, fallback_confidence: float) -> tuple[str, float] | None:
    results = model.predict(source=crop_bgr, verbose=False)
    if not results:
        return None
    probs = getattr(results[0], "probs", None)
    names = getattr(results[0], "names", {})
    if probs is None or getattr(probs, "top1", None) is None:
        return None
    class_id = int(probs.top1)
    confidence = float(probs.top1conf)
    if isinstance(names, dict):
        label = str(names.get(class_id, class_id))
    else:
        label = str(names[class_id]) if 0 <= class_id < len(names) else str(class_id)
    if label not in WBC_SUBTYPE_TO_UNIFIED_ID or confidence < float(fallback_confidence):
        return None
    return label, confidence


def _copy_three_class_split(
    source_root: Path,
    output_root: Path,
    split: str,
    wbc_model: Any,
    min_wbc_subtype_conf: float,
    pseudo_rows: list[dict[str, Any]],
) -> dict[str, int]:
    source_image_dir = source_root / "images" / split
    source_label_dir = source_root / "labels" / split
    target_image_dir = output_root / "images" / split
    target_label_dir = output_root / "labels" / split
    target_image_dir.mkdir(parents=True, exist_ok=True)
    target_label_dir.mkdir(parents=True, exist_ok=True)
    counts = {"images": 0, "rbc": 0, "platelets": 0, "wbc_pseudo": 0, "wbc_skipped": 0}

    for image_path in sorted(path for path in source_image_dir.iterdir() if path.suffix.lower() in IMAGE_SUFFIXES):
        frame = cv2.imread(str(image_path))
        if frame is None:
            continue
        height, width = frame.shape[:2]
        label_path = source_label_dir / f"{image_path.stem}.txt"
        rows = _read_yolo_rows(label_path)
        output_rows: list[str] = []
        for row in rows:
            source_class_id = int(row[0])
            xyxy = _xywhn_to_xyxy(row, width, height)
            if xyxy is None:
                continue
            x1, y1, x2, y2 = xyxy
            if source_class_id in THREE_CLASS_TO_UNIFIED:
                unified_id = THREE_CLASS_TO_UNIFIED[source_class_id]
                output_rows.append(_xyxy_to_yolo_row(unified_id, x1, y1, x2, y2, width, height))
                if unified_id == UNIFIED_BLOOD_CELL_CLASS_TO_ID["RBC"]:
                    counts["rbc"] += 1
                else:
                    counts["platelets"] += 1
                continue
            if source_class_id != 0:
                continue

            subtype = _classify_wbc_crop(wbc_model, frame[y1:y2, x1:x2], min_wbc_subtype_conf)
            if subtype is None:
                counts["wbc_skipped"] += 1
                continue
            subtype_name, subtype_conf = subtype
            output_rows.append(_xyxy_to_yolo_row(WBC_SUBTYPE_TO_UNIFIED_ID[subtype_name], x1, y1, x2, y2, width, height))
            counts["wbc_pseudo"] += 1
            pseudo_rows.append(
                {
                    "split": split,
                    "image": str(image_path),
                    "bbox_xyxy": [x1, y1, x2, y2],
                    "pseudo_subtype": subtype_name,
                    "pseudo_confidence": subtype_conf,
                }
            )

        if output_rows:
            shutil.copy2(image_path, target_image_dir / image_path.name)
            (target_label_dir / f"{image_path.stem}.txt").write_text("\n".join(output_rows) + "\n", encoding="utf-8")
            counts["images"] += 1
    return counts


def _copy_wbc5_classification_split(source_root: Path, output_root: Path, split: str, limit_per_class: int | None) -> dict[str, int]:
    target_image_dir = output_root / "images" / split
    target_label_dir = output_root / "labels" / split
    target_image_dir.mkdir(parents=True, exist_ok=True)
    target_label_dir.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    rng = random.Random(42)

    for subtype, class_id in WBC_SUBTYPE_TO_UNIFIED_ID.items():
        source_dir = source_root / split / subtype
        if not source_dir.is_dir():
            continue
        images = [path for path in sorted(source_dir.iterdir()) if path.suffix.lower() in IMAGE_SUFFIXES]
        rng.shuffle(images)
        if limit_per_class is not None:
            images = images[: max(0, int(limit_per_class))]
        counts[subtype] = len(images)
        for index, image_path in enumerate(images):
            target_name = f"wbc5_{split}_{subtype}_{index:06d}{image_path.suffix.lower()}"
            target_image = target_image_dir / target_name
            target_label = target_label_dir / f"{Path(target_name).stem}.txt"
            shutil.copy2(image_path, target_image)
            target_label.write_text(f"{class_id} 0.50000000 0.50000000 1.00000000 1.00000000\n", encoding="utf-8")
    return counts


def _write_data_yaml(output_root: Path) -> Path:
    names = "\n".join(f"  {index}: {name}" for index, name in enumerate(UNIFIED_BLOOD_CELL_CLASS_NAMES))
    data_yaml = output_root / "data.yaml"
    data_yaml.write_text(
        f"path: {output_root}\n"
        "train: images/train\n"
        "val: images/val\n"
        "test: images/test\n"
        "names:\n"
        f"{names}\n",
        encoding="utf-8",
    )
    return data_yaml


def prepare_unified_dataset(args: argparse.Namespace) -> Path:
    output_root = Path(args.output)
    if output_root.exists() and args.recreate:
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise ImportError("Ultralytics is required to pseudo-label WBC subtypes.") from exc

    wbc_model = YOLO(require_local_model(str(args.wbc_classifier)))
    pseudo_rows: list[dict[str, Any]] = []
    summary: dict[str, Any] = {
        "classes": list(UNIFIED_BLOOD_CELL_CLASS_NAMES),
        "three_class_root": str(Path(args.three_class_root).resolve()),
        "wbc5_classification_root": str(Path(args.wbc5_classification_root).resolve()),
        "min_wbc_subtype_conf": float(args.min_wbc_subtype_conf),
        "three_class": {},
        "wbc5_classification": {},
    }

    for split in ("train", "val", "test"):
        summary["three_class"][split] = _copy_three_class_split(
            source_root=Path(args.three_class_root),
            output_root=output_root,
            split=split,
            wbc_model=wbc_model,
            min_wbc_subtype_conf=float(args.min_wbc_subtype_conf),
            pseudo_rows=pseudo_rows,
        )
        summary["wbc5_classification"][split] = _copy_wbc5_classification_split(
            source_root=Path(args.wbc5_classification_root),
            output_root=output_root,
            split=split,
            limit_per_class=args.limit_wbc5_per_class,
        )

    data_yaml = _write_data_yaml(output_root)
    with (output_root / "pseudo_wbc_labels.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["split", "image", "bbox_xyxy", "pseudo_subtype", "pseudo_confidence"])
        writer.writeheader()
        writer.writerows(pseudo_rows)
    (output_root / "dataset_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"data_yaml={data_yaml.resolve()}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return data_yaml


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a unified 7-class blood-cell YOLO dataset.")
    parser.add_argument("--three-class-root", default=str(default_three_class_root()))
    parser.add_argument("--wbc5-classification-root", default=str(default_wbc5_classification_root()))
    parser.add_argument("--wbc-classifier", default=str(default_wbc5_classifier()))
    parser.add_argument("--output", default=str(default_output_root()))
    parser.add_argument("--min-wbc-subtype-conf", type=float, default=0.70)
    parser.add_argument("--limit-wbc5-per-class", type=int, default=None)
    parser.add_argument("--recreate", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    prepare_unified_dataset(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

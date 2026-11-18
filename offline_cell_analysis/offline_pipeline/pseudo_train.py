from __future__ import annotations

from .model_files import require_local_model, local_training_options

import csv
import json
import random
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

import cv2

from .utils import ensure_dir, safe_name


THREE_CLASS_NAMES = ("WBC", "RBC", "Platelets")
THREE_CLASS_TO_ID = {name: index for index, name in enumerate(THREE_CLASS_NAMES)}


@dataclass
class PseudoDetection:
    frame_path: Path
    class_name: str
    confidence: float
    x1: float
    y1: float
    x2: float
    y2: float
    source_csv: Path


def normalize_three_class(label: str) -> str | None:
    compact = "".join(ch for ch in str(label).lower() if ch.isalnum())
    if compact in {"wbc", "whitebloodcell", "whitebloodcells", "leukocyte", "leukocytes"}:
        return "WBC"
    if compact in {"rbc", "redbloodcell", "redbloodcells", "erythrocyte", "erythrocytes"}:
        return "RBC"
    if compact in {"platelet", "platelets", "plt", "thrombocyte", "thrombocytes"}:
        return "Platelets"
    return None


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_base_model() -> Path:
    return (
        _workspace_root()
        / "stitched_output"
        / "stitched_output"
        / "stitched_output"
        / "models"
        / "blood_cells_3cls_400x_refine_20260517.pt"
    )


def default_training_project() -> Path:
    return _workspace_root() / "staging" / "train"


def default_dataset_root() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return _workspace_root() / "offline_cell_analysis" / "training_datasets" / f"three_class_pseudo_{stamp}"


def latest_detection_csv(root: Path | None = None) -> Path:
    search_root = root or (_workspace_root() / "offline_cell_analysis" / "detections")
    candidates = sorted(
        search_root.glob("*/detections_all.csv"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError(f"No detections_all.csv found under {search_root}")
    return candidates[0]


def resolve_detection_csvs(paths: Iterable[Path] | None) -> list[Path]:
    if not paths:
        return [latest_detection_csv()]
    csvs: list[Path] = []
    for path in paths:
        path = Path(path)
        if path.is_file():
            csvs.append(path)
        elif path.is_dir():
            for name in ("detections_all.csv", "detections_tracked.csv", "unique_cells.csv"):
                candidate = path / name
                if candidate.exists():
                    csvs.append(candidate)
                    break
            else:
                csvs.extend(sorted(path.glob("*/detections_all.csv")))
        else:
            raise FileNotFoundError(f"Detection path not found: {path}")
    unique: list[Path] = []
    seen: set[Path] = set()
    for csv_path in csvs:
        resolved = csv_path.resolve()
        if resolved not in seen:
            unique.append(csv_path)
            seen.add(resolved)
    if not unique:
        raise FileNotFoundError("No detection CSV files were resolved.")
    return unique


def read_pseudo_detections(csv_paths: Iterable[Path], *, min_confidence: float = 0.65) -> list[PseudoDetection]:
    detections: list[PseudoDetection] = []
    for csv_path in csv_paths:
        csv_path = Path(csv_path)
        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                class_name = normalize_three_class(row.get("class_name") or row.get("cell_class") or "")
                if class_name is None:
                    continue
                try:
                    confidence = float(row.get("confidence", "0") or 0)
                except ValueError:
                    continue
                if confidence < float(min_confidence):
                    continue
                frame_path_text = row.get("frame_path") or ""
                if not frame_path_text:
                    continue
                frame_path = Path(frame_path_text)
                if not frame_path.exists():
                    continue
                try:
                    detections.append(
                        PseudoDetection(
                            frame_path=frame_path,
                            class_name=class_name,
                            confidence=confidence,
                            x1=float(row.get("x1") or row.get("bbox_x1") or 0),
                            y1=float(row.get("y1") or row.get("bbox_y1") or 0),
                            x2=float(row.get("x2") or row.get("bbox_x2") or 0),
                            y2=float(row.get("y2") or row.get("bbox_y2") or 0),
                            source_csv=csv_path,
                        )
                    )
                except ValueError:
                    continue
    return detections


def _clip_box(det: PseudoDetection, width: int, height: int) -> tuple[float, float, float, float] | None:
    x1 = max(0.0, min(float(width - 1), det.x1))
    y1 = max(0.0, min(float(height - 1), det.y1))
    x2 = max(0.0, min(float(width), det.x2))
    y2 = max(0.0, min(float(height), det.y2))
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2


def _xyxy_to_yolo(class_id: int, x1: float, y1: float, x2: float, y2: float, width: int, height: int) -> str:
    cx = ((x1 + x2) / 2.0) / float(width)
    cy = ((y1 + y2) / 2.0) / float(height)
    bw = (x2 - x1) / float(width)
    bh = (y2 - y1) / float(height)
    return f"{int(class_id)} {cx:.8f} {cy:.8f} {bw:.8f} {bh:.8f}"


def build_three_class_yolo_dataset(
    csv_paths: Iterable[Path],
    output_root: Path,
    *,
    min_confidence: float = 0.65,
    val_ratio: float = 0.15,
    seed: int = 42,
) -> Path:
    output_root = Path(output_root)
    if output_root.exists():
        shutil.rmtree(output_root)
    for split in ("train", "val"):
        ensure_dir(output_root / "images" / split)
        ensure_dir(output_root / "labels" / split)

    detections = read_pseudo_detections(csv_paths, min_confidence=min_confidence)
    by_frame: dict[Path, list[PseudoDetection]] = {}
    for det in detections:
        by_frame.setdefault(det.frame_path, []).append(det)

    frames = sorted(by_frame)
    rng = random.Random(int(seed))
    rng.shuffle(frames)
    val_count = max(1 if len(frames) > 1 else 0, int(round(len(frames) * float(val_ratio))))
    val_frames = set(frames[:val_count])

    manifest_rows: list[dict[str, str | int | float]] = []
    counts = {"images_train": 0, "images_val": 0, "labels": 0, "skipped_boxes": 0}

    for frame_path in frames:
        frame = cv2.imread(str(frame_path))
        if frame is None:
            continue
        height, width = frame.shape[:2]
        split = "val" if frame_path in val_frames else "train"
        stem = safe_name(f"{frame_path.parent.name}_{frame_path.stem}")
        image_name = f"{stem}{frame_path.suffix.lower()}"
        label_name = f"{stem}.txt"
        label_rows: list[str] = []

        for det in by_frame[frame_path]:
            clipped = _clip_box(det, width, height)
            if clipped is None:
                counts["skipped_boxes"] += 1
                continue
            x1, y1, x2, y2 = clipped
            class_id = THREE_CLASS_TO_ID[det.class_name]
            label_rows.append(_xyxy_to_yolo(class_id, x1, y1, x2, y2, width, height))
            manifest_rows.append(
                {
                    "split": split,
                    "image": image_name,
                    "class_name": det.class_name,
                    "confidence": f"{det.confidence:.6f}",
                    "x1": f"{x1:.2f}",
                    "y1": f"{y1:.2f}",
                    "x2": f"{x2:.2f}",
                    "y2": f"{y2:.2f}",
                    "source_frame": str(frame_path),
                    "source_csv": str(det.source_csv),
                }
            )
            counts["labels"] += 1

        if not label_rows:
            continue
        shutil.copy2(frame_path, output_root / "images" / split / image_name)
        (output_root / "labels" / split / label_name).write_text("\n".join(label_rows) + "\n", encoding="utf-8")
        counts[f"images_{split}"] += 1

    if counts["labels"] == 0:
        raise ValueError(
            "No usable pseudo labels were found. Run offline detection first, "
            "or lower --min-conf after manually checking label quality."
        )

    data_yaml = output_root / "data.yaml"
    names_block = "\n".join(f"  {index}: {name}" for index, name in enumerate(THREE_CLASS_NAMES))
    data_yaml.write_text(
        f"path: {output_root.resolve()}\n"
        "train: images/train\n"
        "val: images/val\n"
        "names:\n"
        f"{names_block}\n",
        encoding="utf-8",
    )

    manifest_path = output_root / "pseudo_labels_manifest.csv"
    with manifest_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["split", "image", "class_name", "confidence", "x1", "y1", "x2", "y2", "source_frame", "source_csv"],
        )
        writer.writeheader()
        writer.writerows(manifest_rows)

    summary = {
        "data_yaml": str(data_yaml.resolve()),
        "classes": list(THREE_CLASS_NAMES),
        "min_confidence": float(min_confidence),
        "val_ratio": float(val_ratio),
        "source_csvs": [str(Path(path).resolve()) for path in csv_paths],
        **counts,
    }
    (output_root / "dataset_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return data_yaml


def train_three_class_model(
    *,
    data_yaml: Path,
    base_model: Path,
    project: Path,
    name: str,
    epochs: int = 30,
    imgsz: int = 960,
    batch: int = 2,
    device: str | None = None,
    workers: int = 0,
    dry_run: bool = False,
) -> Path | None:
    data_yaml = Path(data_yaml)
    base_model = Path(base_model)
    if not data_yaml.exists():
        raise FileNotFoundError(f"data.yaml not found: {data_yaml}")
    if not base_model.exists():
        raise FileNotFoundError(f"Base model not found: {base_model}")

    train_kwargs = {
        "data": str(data_yaml),
        "epochs": int(epochs),
        "imgsz": int(imgsz),
        "batch": int(batch),
        "workers": int(workers),
        "project": str(project),
        "name": str(name),
        "exist_ok": True,
        "patience": 12,
        "optimizer": "AdamW",
        "lr0": 0.00025,
        "cos_lr": True,

        "cache": False,
        "mosaic": 0.05,
        "mixup": 0.0,
        "copy_paste": 0.0,
        "degrees": 90.0,
        "scale": 0.10,
        "translate": 0.03,
        "fliplr": 0.5,
        "flipud": 0.5,
        "close_mosaic": 5,
        "seed": 42,
        "cls": 0.75,
        "box": 8.0,
        "dfl": 1.6,
    }
    if device not in {None, "", "auto"}:
        train_kwargs["device"] = device

    if dry_run:
        print(f"base_model={base_model}")
        print(f"data_yaml={data_yaml}")
        print(f"train_kwargs={train_kwargs}")
        return None

    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise RuntimeError("ultralytics is required for training.") from exc

    model = YOLO(require_local_model(str(base_model)))
    result = model.train(**(train_kwargs | local_training_options(base_model)))
    save_dir = Path(getattr(result, "save_dir", Path(project) / name))
    return save_dir / "weights" / "best.pt"

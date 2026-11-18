from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
from ultralytics import YOLO


CLASS_NAMES = ("WBC", "RBC", "Platelets")
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}


@dataclass(frozen=True)
class Box:
    cls: int
    conf: float
    xyxy: tuple[float, float, float, float]


def workspace_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_model_path() -> Path:
    trained = Path("E:/Cell_Project_training_staging/train/blood_cells_3cls_manual_annotation_continue_20260609/weights/best.pt")
    if trained.is_file():
        return trained
    return (
        workspace_root()
        / "stitched_output"
        / "stitched_output"
        / "stitched_output"
        / "models"
        / "blood_cells_3cls_400x_refine_20260517.pt"
    )


def default_data_yaml() -> Path:
    preferred = Path("E:/Cell_Project_training_staging/manual_annotation_augmented_3cls_latest/data.yaml")
    if preferred.is_file():
        return preferred
    return workspace_root() / "staging" / "manual_annotation_augmented_3cls" / "latest" / "data.yaml"


def parse_simple_yaml(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {}
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    index = 0
    while index < len(lines):
        raw = lines[index]
        line = raw.strip()
        index += 1
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if key == "names" and not value:
            names: dict[int, str] = {}
            while index < len(lines):
                child = lines[index]
                stripped = child.strip()
                if not stripped:
                    index += 1
                    continue
                if not child.startswith((" ", "\t")):
                    break
                if ":" in stripped:
                    child_key, child_value = stripped.split(":", 1)
                    if child_key.strip().isdigit():
                        names[int(child_key.strip())] = child_value.strip().strip("'\"")
                index += 1
            result[key] = names
        else:
            result[key] = value.strip("'\"")
    return result


def resolve_split(data_yaml: Path, split: str) -> tuple[Path, Path]:
    payload = parse_simple_yaml(data_yaml)
    root = Path(str(payload.get("path", data_yaml.parent))).expanduser()
    if not root.is_absolute():
        root = (data_yaml.parent / root).resolve()
    image_dir = Path(str(payload.get(split, f"images/{split}")))
    if not image_dir.is_absolute():
        image_dir = root / image_dir
    label_dir = Path(str(image_dir).replace(f"{Path('images')}", f"{Path('labels')}", 1))
    if "images" in image_dir.parts:
        parts = list(image_dir.parts)
        parts[parts.index("images")] = "labels"
        label_dir = Path(*parts)
    return image_dir, label_dir


def yolo_row_to_xyxy(row: str, width: int, height: int) -> Box | None:
    parts = row.strip().split()
    if len(parts) != 5:
        return None
    cls = int(float(parts[0]))
    cx, cy, bw, bh = [float(value) for value in parts[1:]]
    x1 = (cx - bw / 2) * width
    y1 = (cy - bh / 2) * height
    x2 = (cx + bw / 2) * width
    y2 = (cy + bh / 2) * height
    return Box(cls=cls, conf=1.0, xyxy=(x1, y1, x2, y2))


def load_ground_truth(image_path: Path, label_dir: Path) -> list[Box]:
    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        return []
    height, width = image.shape[:2]
    label_path = label_dir / f"{image_path.stem}.txt"
    if not label_path.is_file():
        return []
    boxes: list[Box] = []
    for row in label_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        box = yolo_row_to_xyxy(row, width, height)
        if box is not None and 0 <= box.cls < len(CLASS_NAMES):
            boxes.append(box)
    return boxes


def discover_images(image_dir: Path, max_images: int) -> list[Path]:
    images = sorted(path for path in image_dir.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS)
    return images[:max_images] if max_images > 0 else images


def box_iou(a: Box, b: Box) -> float:
    ax1, ay1, ax2, ay2 = a.xyxy
    bx1, by1, bx2, by2 = b.xyxy
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    iw = max(0.0, ix2 - ix1)
    ih = max(0.0, iy2 - iy1)
    intersection = iw * ih
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - intersection
    return 0.0 if union <= 0 else intersection / union


def predictions_for_image(model: YOLO, image_path: Path, imgsz: int, conf_floor: float, iou_threshold: float) -> list[Box]:
    result = model.predict(str(image_path), imgsz=imgsz, conf=conf_floor, iou=iou_threshold, verbose=False)[0]
    boxes: list[Box] = []
    for pred in result.boxes:
        cls = int(pred.cls.item())
        if not 0 <= cls < len(CLASS_NAMES):
            continue
        xyxy = tuple(float(value) for value in pred.xyxy[0].tolist())
        boxes.append(Box(cls=cls, conf=float(pred.conf.item()), xyxy=xyxy))  # type: ignore[arg-type]
    return boxes


def score_class(
    truth: list[Box],
    predictions: list[Box],
    class_id: int,
    threshold: float,
    iou_match: float,
) -> tuple[int, int, int]:
    gt = [box for box in truth if box.cls == class_id]
    pred = sorted((box for box in predictions if box.cls == class_id and box.conf >= threshold), key=lambda box: box.conf, reverse=True)
    matched: set[int] = set()
    tp = 0
    fp = 0
    for candidate in pred:
        best_index = -1
        best_iou = 0.0
        for index, target in enumerate(gt):
            if index in matched:
                continue
            iou = box_iou(candidate, target)
            if iou > best_iou:
                best_index = index
                best_iou = iou
        if best_index >= 0 and best_iou >= iou_match:
            matched.add(best_index)
            tp += 1
        else:
            fp += 1
    fn = len(gt) - tp
    return tp, fp, fn


def safe_divide(numerator: float, denominator: float) -> float:
    return 0.0 if denominator <= 0 else numerator / denominator


def main() -> int:
    parser = argparse.ArgumentParser(description="Calibrate per-class confidence thresholds for the 3-class blood-cell YOLO model.")
    parser.add_argument("--data", type=Path, default=default_data_yaml())
    parser.add_argument("--model", type=Path, default=default_model_path())
    parser.add_argument("--split", default="val", choices=("train", "val"))
    parser.add_argument("--output-dir", type=Path, default=Path("E:/Cell_Project_training_staging/confidence_calibration/latest"))
    parser.add_argument("--imgsz", type=int, default=960)
    parser.add_argument("--conf-floor", type=float, default=0.05)
    parser.add_argument("--iou-threshold", type=float, default=0.45)
    parser.add_argument("--match-iou", type=float, default=0.5)
    parser.add_argument("--max-images", type=int, default=300)
    parser.add_argument("--thresholds", default="0.10,0.15,0.20,0.25,0.30,0.35,0.40,0.45,0.50,0.55,0.60,0.65,0.70,0.75,0.80,0.85,0.90")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    if not args.data.is_file():
        raise FileNotFoundError(f"data yaml not found: {args.data}")
    if not args.model.is_file():
        raise FileNotFoundError(f"model not found: {args.model}")
    if args.output_dir.exists() and args.overwrite:
        import shutil

        shutil.rmtree(args.output_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    image_dir, label_dir = resolve_split(args.data, args.split)
    images = discover_images(image_dir, args.max_images)
    if not images:
        raise FileNotFoundError(f"No images found: {image_dir}")

    model = YOLO(str(args.model))
    records: list[tuple[list[Box], list[Box]]] = []
    for image_path in images:
        truth = load_ground_truth(image_path, label_dir)
        if not truth:
            continue
        predictions = predictions_for_image(model, image_path, args.imgsz, args.conf_floor, args.iou_threshold)
        records.append((truth, predictions))

    thresholds = [float(value.strip()) for value in args.thresholds.split(",") if value.strip()]
    rows: list[dict[str, object]] = []
    recommendations: dict[str, dict[str, float | int]] = {}
    for class_id, class_name in enumerate(CLASS_NAMES):
        best_row: dict[str, object] | None = None
        for threshold in thresholds:
            tp = fp = fn = 0
            for truth, predictions in records:
                row_tp, row_fp, row_fn = score_class(truth, predictions, class_id, threshold, args.match_iou)
                tp += row_tp
                fp += row_fp
                fn += row_fn
            precision = safe_divide(tp, tp + fp)
            recall = safe_divide(tp, tp + fn)
            f1 = safe_divide(2 * precision * recall, precision + recall)
            row = {
                "class_id": class_id,
                "class_name": class_name,
                "threshold": round(threshold, 3),
                "tp": tp,
                "fp": fp,
                "fn": fn,
                "precision": round(precision, 6),
                "recall": round(recall, 6),
                "f1": round(f1, 6),
            }
            rows.append(row)
            if best_row is None or (float(row["f1"]), float(row["precision"]), float(row["recall"])) > (
                float(best_row["f1"]),
                float(best_row["precision"]),
                float(best_row["recall"]),
            ):
                best_row = row
        if best_row is not None:
            recommendations[class_name] = {
                "threshold": float(best_row["threshold"]),
                "precision": float(best_row["precision"]),
                "recall": float(best_row["recall"]),
                "f1": float(best_row["f1"]),
                "tp": int(best_row["tp"]),
                "fp": int(best_row["fp"]),
                "fn": int(best_row["fn"]),
            }

    csv_path = args.output_dir / "threshold_sweep.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["class_id", "class_name", "threshold", "tp", "fp", "fn", "precision", "recall", "f1"])
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "model": str(args.model.resolve()),
        "data": str(args.data.resolve()),
        "split": args.split,
        "images_used": len(records),
        "match_iou": args.match_iou,
        "recommendations": recommendations,
    }
    summary_path = args.output_dir / "recommended_thresholds.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"calibration_dir={args.output_dir.resolve()}")
    print(f"threshold_sweep={csv_path.resolve()}")
    print(f"recommended_thresholds={summary_path.resolve()}")
    print(f"images_used={len(records)}")
    for class_name in CLASS_NAMES:
        rec = recommendations.get(class_name, {})
        print(
            f"{class_name}: threshold={rec.get('threshold', 'n/a')} "
            f"precision={rec.get('precision', 'n/a')} recall={rec.get('recall', 'n/a')} f1={rec.get('f1', 'n/a')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import csv
import shutil
from datetime import datetime
from pathlib import Path

import cv2
from ultralytics import YOLO


CLASS_NAMES = ("WBC", "RBC", "Platelets")
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}


def workspace_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_source_root() -> Path:
    return (
        workspace_root()
        / "stitched_output"
        / "stitched_output"
        / "stitched_output"
        / "captured"
    )


def default_model_path() -> Path:
    latest_e = Path("E:/Cell_Project_training_staging/train/blood_cells_3cls_manual_annotation_continue_20260609/weights/best.pt")
    if latest_e.is_file():
        return latest_e
    return (
        workspace_root()
        / "stitched_output"
        / "stitched_output"
        / "stitched_output"
        / "models"
        / "blood_cells_3cls_400x_refine_20260517.pt"
    )


def default_output_root() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path("E:/Cell_Project_training_staging") / "pseudo_label_3cls" / stamp


def discover_images(source_root: Path) -> list[Path]:
    excluded_parts = {
        "manual_annotation_dataset",
        "training_dataset",
        "pseudo_label_3cls",
        "detected",
        "crops",
        "labels",
        "staging",
    }
    images: list[Path] = []
    for path in source_root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        if any(part in excluded_parts for part in path.parts):
            continue
        images.append(path)
    return sorted(images)


def write_data_yaml(output_root: Path) -> Path:
    path = output_root / "data.yaml"
    path.write_text(
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
    return path


def normalized_xywh(box_xyxy, width: int, height: int) -> tuple[float, float, float, float]:
    x1, y1, x2, y2 = [float(value) for value in box_xyxy]
    x1 = max(0.0, min(x1, width - 1))
    y1 = max(0.0, min(y1, height - 1))
    x2 = max(0.0, min(x2, width - 1))
    y2 = max(0.0, min(y2, height - 1))
    bw = max(0.0, x2 - x1)
    bh = max(0.0, y2 - y1)
    return ((x1 + x2) / 2 / width, (y1 + y2) / 2 / height, bw / width, bh / height)


def safe_stem(path: Path, index: int) -> str:
    raw = "_".join(path.with_suffix("").parts[-3:])
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in raw)
    return f"pseudo_{index:06d}_{safe}"


def draw_boxes(image, rows: list[tuple[int, float, tuple[float, float, float, float]]]):
    colors = {0: (0, 255, 0), 1: (0, 255, 255), 2: (0, 0, 255)}
    h, w = image.shape[:2]
    out = image.copy()
    for cls, conf, (cx, cy, bw, bh) in rows:
        x1 = int((cx - bw / 2) * w)
        y1 = int((cy - bh / 2) * h)
        x2 = int((cx + bw / 2) * w)
        y2 = int((cy + bh / 2) * h)
        color = colors.get(cls, (255, 255, 255))
        cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)
        cv2.putText(out, f"{CLASS_NAMES[cls]} {conf:.2f}", (x1, max(20, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)
    return out


def parse_thresholds(value: str) -> dict[int, float]:
    parts = [float(item.strip()) for item in value.split(",")]
    if len(parts) != len(CLASS_NAMES):
        raise ValueError("--high-conf must contain WBC,RBC,Platelets thresholds")
    return {index: threshold for index, threshold in enumerate(parts)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect high-confidence pseudo labels from captured microscope images.")
    parser.add_argument("--source-root", type=Path, default=default_source_root())
    parser.add_argument("--model", type=Path, default=default_model_path())
    parser.add_argument("--output-root", type=Path, default=default_output_root())
    parser.add_argument("--high-conf", default="0.75,0.90,0.70", help="WBC,RBC,Platelets auto-label thresholds.")
    parser.add_argument("--review-conf", type=float, default=0.45)
    parser.add_argument("--imgsz", type=int, default=960)
    parser.add_argument("--max-images", type=int, default=300)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    if not args.model.is_file():
        raise FileNotFoundError(f"model not found: {args.model}")
    if not args.source_root.is_dir():
        raise FileNotFoundError(f"source root not found: {args.source_root}")
    if args.output_root.exists():
        if not args.overwrite:
            raise FileExistsError(f"output exists, add --overwrite: {args.output_root}")
        shutil.rmtree(args.output_root)

    for path in (
        args.output_root / "images" / "train",
        args.output_root / "labels" / "train",
        args.output_root / "review",
        args.output_root / "hard_cases",
    ):
        path.mkdir(parents=True, exist_ok=True)

    thresholds = parse_thresholds(args.high_conf)
    images = discover_images(args.source_root)
    if args.max_images > 0:
        images = images[: args.max_images]
    model = YOLO(str(args.model))

    manifest_path = args.output_root / "pseudo_label_manifest.csv"
    counts = {0: 0, 1: 0, 2: 0}
    auto_images = 0
    review_images = 0
    hard_images = 0
    with manifest_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=["source", "status", "output_image", "output_label", "auto_boxes", "review_boxes"])
        writer.writeheader()
        for index, image_path in enumerate(images):
            image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
            if image is None:
                continue
            height, width = image.shape[:2]
            result = model.predict(str(image_path), imgsz=args.imgsz, conf=args.review_conf, verbose=False)[0]
            auto_rows: list[tuple[int, float, tuple[float, float, float, float]]] = []
            review_rows: list[tuple[int, float, tuple[float, float, float, float]]] = []
            for box in result.boxes:
                cls = int(box.cls.item())
                conf = float(box.conf.item())
                xywh = normalized_xywh(box.xyxy[0].tolist(), width, height)
                if cls in thresholds and conf >= thresholds[cls]:
                    auto_rows.append((cls, conf, xywh))
                else:
                    review_rows.append((cls, conf, xywh))

            stem = safe_stem(image_path, index)
            if auto_rows:
                out_image = args.output_root / "images" / "train" / f"{stem}{image_path.suffix.lower()}"
                out_label = args.output_root / "labels" / "train" / f"{stem}.txt"
                shutil.copy2(image_path, out_image)
                lines = []
                for cls, _conf, (cx, cy, bw, bh) in auto_rows:
                    counts[cls] += 1
                    lines.append(f"{cls} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")
                out_label.write_text("\n".join(lines) + "\n", encoding="utf-8")
                auto_images += 1
                writer.writerow(
                    {
                        "source": str(image_path),
                        "status": "auto",
                        "output_image": str(out_image),
                        "output_label": str(out_label),
                        "auto_boxes": len(auto_rows),
                        "review_boxes": len(review_rows),
                    }
                )
            elif review_rows:
                review_out = args.output_root / "review" / f"{stem}.jpg"
                cv2.imwrite(str(review_out), draw_boxes(image, review_rows), [cv2.IMWRITE_JPEG_QUALITY, 92])
                review_images += 1
                writer.writerow(
                    {
                        "source": str(image_path),
                        "status": "review",
                        "output_image": str(review_out),
                        "output_label": "",
                        "auto_boxes": 0,
                        "review_boxes": len(review_rows),
                    }
                )
            else:
                hard_out = args.output_root / "hard_cases" / image_path.name
                shutil.copy2(image_path, hard_out)
                hard_images += 1
                writer.writerow(
                    {
                        "source": str(image_path),
                        "status": "hard",
                        "output_image": str(hard_out),
                        "output_label": "",
                        "auto_boxes": 0,
                        "review_boxes": 0,
                    }
                )

    data_yaml = write_data_yaml(args.output_root)
    print(f"pseudo_dataset={args.output_root}")
    print(f"data_yaml={data_yaml}")
    print(f"manifest={manifest_path}")
    print(f"auto_images={auto_images}")
    print(f"review_images={review_images}")
    print(f"hard_images={hard_images}")
    for cls, name in enumerate(CLASS_NAMES):
        print(f"{name}_auto_boxes={counts[cls]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

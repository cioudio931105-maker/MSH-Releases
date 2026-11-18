from __future__ import annotations

import argparse
import csv
import random
import shutil
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = (
    PROJECT_ROOT
    / "stitched_output"
    / "stitched_output"
    / "stitched_output"
    / "captured"
    / "manual_annotation_dataset"
)
DEFAULT_OUTPUT = PROJECT_ROOT / "staging" / "manual_annotation_augmented_3cls" / "latest"

CLASS_NAMES = ["WBC", "RBC", "Platelets"]


@dataclass(frozen=True)
class YoloBox:
    cls: int
    x: float
    y: float
    w: float
    h: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate safe augmentations from manually annotated blood-cell YOLO data."
    )
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--copies", type=int, default=8, help="Augmented copies per source image.")
    parser.add_argument("--val-ratio", type=float, default=0.15)
    parser.add_argument("--seed", type=int, default=20260608)
    parser.add_argument("--min-box-size", type=float, default=3.0)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def image_paths(root: Path) -> list[Path]:
    image_dir = root / "images" / "train"
    suffixes = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
    return sorted(p for p in image_dir.glob("*") if p.suffix.lower() in suffixes)


def load_labels(label_path: Path) -> list[YoloBox]:
    if not label_path.exists():
        return []
    boxes: list[YoloBox] = []
    for row in label_path.read_text(encoding="utf-8").splitlines():
        parts = row.strip().split()
        if len(parts) != 5:
            continue
        cls, x, y, w, h = parts
        boxes.append(YoloBox(int(cls), float(x), float(y), float(w), float(h)))
    return boxes


def save_labels(label_path: Path, boxes: list[YoloBox]) -> None:
    lines = [f"{b.cls} {b.x:.6f} {b.y:.6f} {b.w:.6f} {b.h:.6f}" for b in boxes]
    label_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def yolo_to_corners(box: YoloBox, width: int, height: int) -> np.ndarray:
    cx = box.x * width
    cy = box.y * height
    bw = box.w * width
    bh = box.h * height
    x1 = cx - bw / 2
    y1 = cy - bh / 2
    x2 = cx + bw / 2
    y2 = cy + bh / 2
    return np.array([[x1, y1], [x2, y1], [x2, y2], [x1, y2]], dtype=np.float32)


def corners_to_yolo(cls: int, corners: np.ndarray, width: int, height: int, min_size: float) -> YoloBox | None:
    x1 = float(np.clip(corners[:, 0].min(), 0, width - 1))
    y1 = float(np.clip(corners[:, 1].min(), 0, height - 1))
    x2 = float(np.clip(corners[:, 0].max(), 0, width - 1))
    y2 = float(np.clip(corners[:, 1].max(), 0, height - 1))
    bw = x2 - x1
    bh = y2 - y1
    if bw < min_size or bh < min_size:
        return None
    return YoloBox(cls=cls, x=((x1 + x2) / 2) / width, y=((y1 + y2) / 2) / height, w=bw / width, h=bh / height)


def transform_boxes(
    boxes: list[YoloBox],
    matrix: np.ndarray,
    width: int,
    height: int,
    min_size: float,
) -> list[YoloBox]:
    output: list[YoloBox] = []
    for box in boxes:
        corners = yolo_to_corners(box, width, height)
        hom = np.concatenate([corners, np.ones((4, 1), dtype=np.float32)], axis=1)
        moved = (matrix @ hom.T).T
        moved = moved[:, :2] / moved[:, 2:3]
        converted = corners_to_yolo(box.cls, moved, width, height, min_size)
        if converted is not None:
            output.append(converted)
    return output


def random_affine(width: int, height: int) -> np.ndarray:
    angle = random.uniform(-6.0, 6.0)
    scale = random.uniform(0.94, 1.06)
    tx = random.uniform(-0.035, 0.035) * width
    ty = random.uniform(-0.035, 0.035) * height
    center = (width / 2, height / 2)
    affine = cv2.getRotationMatrix2D(center, angle, scale)
    affine[:, 2] += [tx, ty]
    return np.vstack([affine, [0.0, 0.0, 1.0]]).astype(np.float32)


def color_augment(image: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[:, :, 0] = (hsv[:, :, 0] + random.uniform(-4.0, 4.0)) % 180
    hsv[:, :, 1] *= random.uniform(0.86, 1.18)
    hsv[:, :, 2] *= random.uniform(0.82, 1.22)
    hsv = np.clip(hsv, 0, 255).astype(np.uint8)
    out = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
    if random.random() < 0.45:
        gamma = random.uniform(0.82, 1.18)
        lut = np.array([((i / 255.0) ** gamma) * 255 for i in range(256)], dtype=np.uint8)
        out = cv2.LUT(out, lut)
    if random.random() < 0.35:
        noise = np.random.normal(0, random.uniform(2.0, 8.0), out.shape).astype(np.float32)
        out = np.clip(out.astype(np.float32) + noise, 0, 255).astype(np.uint8)
    if random.random() < 0.25:
        out = cv2.GaussianBlur(out, (3, 3), random.uniform(0.15, 0.65))
    return out


def augment_one(image: np.ndarray, boxes: list[YoloBox], min_box_size: float) -> tuple[np.ndarray, list[YoloBox]]:
    height, width = image.shape[:2]
    matrix = random_affine(width, height)
    moved = cv2.warpPerspective(
        image,
        matrix,
        (width, height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REFLECT_101,
    )
    out_boxes = transform_boxes(boxes, matrix, width, height, min_box_size)
    return color_augment(moved), out_boxes


def write_data_yaml(root: Path) -> None:
    text = "\n".join(
        [
            f"path: {root.as_posix()}",
            "train: images/train",
            "val: images/val",
            "names:",
            "  0: WBC",
            "  1: RBC",
            "  2: Platelets",
            "",
        ]
    )
    (root / "data.yaml").write_text(text, encoding="utf-8")


def copy_sample(image_path: Path, label_path: Path, out_root: Path, split: str, stem: str) -> None:
    out_image = out_root / "images" / split / f"{stem}.png"
    out_label = out_root / "labels" / split / f"{stem}.txt"
    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f"Cannot read image: {image_path}")
    cv2.imwrite(str(out_image), image, [cv2.IMWRITE_PNG_COMPRESSION, 3])
    shutil.copy2(label_path, out_label)


def main() -> int:
    args = parse_args()
    random.seed(args.seed)
    np.random.seed(args.seed)

    if not (args.source / "images" / "train").exists():
        raise SystemExit(f"Source images folder not found: {args.source / 'images' / 'train'}")
    if not (args.source / "labels" / "train").exists():
        raise SystemExit(f"Source labels folder not found: {args.source / 'labels' / 'train'}")
    if args.output.exists():
        if not args.overwrite:
            raise SystemExit(f"Output already exists, add --overwrite to replace: {args.output}")
        shutil.rmtree(args.output)

    for split in ("train", "val"):
        (args.output / "images" / split).mkdir(parents=True, exist_ok=True)
        (args.output / "labels" / split).mkdir(parents=True, exist_ok=True)

    sources = image_paths(args.source)
    if not sources:
        raise SystemExit("No source images found.")
    random.shuffle(sources)
    val_count = max(1, int(round(len(sources) * args.val_ratio))) if len(sources) > 1 else 0
    val_set = set(sources[:val_count])

    manifest_path = args.output / "augmentation_manifest.csv"
    class_counts = {0: 0, 1: 0, 2: 0}
    image_count = 0
    with manifest_path.open("w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=["source", "output", "split", "kind", "box_count"])
        writer.writeheader()
        for src in sources:
            label_path = args.source / "labels" / "train" / f"{src.stem}.txt"
            boxes = load_labels(label_path)
            if not boxes:
                continue
            split = "val" if src in val_set else "train"
            base_stem = f"{src.stem}__orig"
            copy_sample(src, label_path, args.output, split, base_stem)
            for box in boxes:
                class_counts[box.cls] = class_counts.get(box.cls, 0) + 1
            image_count += 1
            writer.writerow({"source": str(src), "output": base_stem, "split": split, "kind": "original", "box_count": len(boxes)})

            if split == "val":
                continue

            image = cv2.imread(str(src), cv2.IMREAD_COLOR)
            if image is None:
                continue
            for index in range(args.copies):
                aug_image, aug_boxes = augment_one(image, boxes, args.min_box_size)
                if not aug_boxes:
                    continue
                stem = f"{src.stem}__aug_{index:02d}"
                out_image = args.output / "images" / "train" / f"{stem}.png"
                out_label = args.output / "labels" / "train" / f"{stem}.txt"
                cv2.imwrite(str(out_image), aug_image, [cv2.IMWRITE_PNG_COMPRESSION, 3])
                save_labels(out_label, aug_boxes)
                for box in aug_boxes:
                    class_counts[box.cls] = class_counts.get(box.cls, 0) + 1
                image_count += 1
                writer.writerow({"source": str(src), "output": stem, "split": "train", "kind": "augmented", "box_count": len(aug_boxes)})

    write_data_yaml(args.output)
    print(f"Augmented dataset: {args.output}")
    print(f"Images written: {image_count}")
    for cls, name in enumerate(CLASS_NAMES):
        print(f"{name}: {class_counts.get(cls, 0)} boxes")
    print(f"Data YAML: {args.output / 'data.yaml'}")
    print(f"Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

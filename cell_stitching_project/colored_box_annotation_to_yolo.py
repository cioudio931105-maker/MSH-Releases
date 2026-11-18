from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import cv2
import numpy as np


CLASS_NAMES = {
    0: "WBC",
    1: "RBC",
    2: "Platelets",
}

COLOR_TO_CLASS = {
    "green": 0,   # WBC
    "yellow": 1,  # RBC
    "red": 2,     # Platelets
}


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _mask_for_color(image_bgr: np.ndarray, color_name: str) -> np.ndarray:
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    if color_name == "yellow":
        mask = cv2.inRange(hsv, np.array([20, 80, 80]), np.array([42, 255, 255]))
    elif color_name == "red":
        mask1 = cv2.inRange(hsv, np.array([0, 80, 80]), np.array([10, 255, 255]))
        mask2 = cv2.inRange(hsv, np.array([170, 80, 80]), np.array([179, 255, 255]))
        mask = cv2.bitwise_or(mask1, mask2)
    elif color_name == "green":
        mask = cv2.inRange(hsv, np.array([45, 60, 60]), np.array([95, 255, 255]))
    else:
        raise ValueError(f"Unsupported color: {color_name}")

    kernel = np.ones((3, 3), dtype=np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask = cv2.dilate(mask, kernel, iterations=1)
    return mask


def _extract_boxes_from_mask(
    mask: np.ndarray,
    min_area: int,
    min_side: int,
) -> list[tuple[int, int, int, int]]:
    contours, _hierarchy = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes: list[tuple[int, int, int, int]] = []
    height, width = mask.shape[:2]
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if w < min_side or h < min_side:
            continue
        if w * h < min_area:
            continue
        x1 = max(0, x)
        y1 = max(0, y)
        x2 = min(width, x + w)
        y2 = min(height, y + h)
        if x2 <= x1 or y2 <= y1:
            continue
        boxes.append((x1, y1, x2, y2))
    return boxes


def _to_yolo_line(class_id: int, box: tuple[int, int, int, int], width: int, height: int) -> str:
    x1, y1, x2, y2 = box
    cx = ((x1 + x2) / 2.0) / float(width)
    cy = ((y1 + y2) / 2.0) / float(height)
    bw = (x2 - x1) / float(width)
    bh = (y2 - y1) / float(height)
    return f"{class_id} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}"


def _inpaint_annotation_boxes(image_bgr: np.ndarray) -> np.ndarray:
    masks = [_mask_for_color(image_bgr, color) for color in COLOR_TO_CLASS]
    mask = np.zeros(image_bgr.shape[:2], dtype=np.uint8)
    for item in masks:
        mask = cv2.bitwise_or(mask, item)
    return cv2.inpaint(image_bgr, mask, inpaintRadius=3, flags=cv2.INPAINT_TELEA)


def convert_colored_box_annotation(
    annotated_image: str | Path,
    output_root: str | Path,
    split: str = "train",
    raw_image: str | Path | None = None,
    min_area: int = 80,
    min_side: int = 6,
    write_preview: bool = True,
) -> tuple[Path, Path, int]:
    annotated_path = Path(annotated_image)
    if not annotated_path.is_file():
        raise FileNotFoundError(f"Annotated image not found: {annotated_path}")

    image = cv2.imread(str(annotated_path))
    if image is None:
        raise RuntimeError(f"Unable to read image: {annotated_path}")

    height, width = image.shape[:2]
    labels: list[str] = []
    preview = image.copy()
    for color_name, class_id in COLOR_TO_CLASS.items():
        mask = _mask_for_color(image, color_name)
        boxes = _extract_boxes_from_mask(mask, min_area=min_area, min_side=min_side)
        for box in boxes:
            labels.append(_to_yolo_line(class_id, box, width, height))
            x1, y1, x2, y2 = box
            cv2.rectangle(preview, (x1, y1), (x2, y2), (255, 255, 255), 1)

    output_root = Path(output_root)
    image_dir = output_root / "images" / split
    label_dir = output_root / "labels" / split
    image_dir.mkdir(parents=True, exist_ok=True)
    label_dir.mkdir(parents=True, exist_ok=True)

    target_image = image_dir / f"{annotated_path.stem}.jpg"
    if raw_image is not None:
        raw_path = Path(raw_image)
        if not raw_path.is_file():
            raise FileNotFoundError(f"Raw image not found: {raw_path}")
        shutil.copy2(raw_path, target_image)
    else:
        cleaned = _inpaint_annotation_boxes(image)
        cv2.imwrite(str(target_image), cleaned)

    label_path = label_dir / f"{annotated_path.stem}.txt"
    label_path.write_text("\n".join(labels) + ("\n" if labels else ""), encoding="utf-8")

    if write_preview:
        preview_dir = output_root / "annotation_preview"
        preview_dir.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(preview_dir / f"{annotated_path.stem}_boxes.jpg"), preview)

    data_yaml = output_root / "data.yaml"
    data_yaml.write_text(
        "\n".join(
            [
                f"path: {output_root.resolve()}",
                "train: images/train",
                "val: images/val",
                "test: images/test",
                "names:",
                "  0: WBC",
                "  1: RBC",
                "  2: Platelets",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return target_image.resolve(), label_path.resolve(), len(labels)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert microscope colored-box annotations to YOLO labels. yellow=RBC, red=Platelets, green=WBC.",
    )
    parser.add_argument("--annotated-image", required=True, help="Image containing colored annotation boxes.")
    parser.add_argument("--raw-image", default=None, help="Optional clean image without colored boxes.")
    parser.add_argument(
        "--output-root",
        default=str(_workspace_root() / "datasets" / "blood_cells_3cls_400x_templates"),
        help="YOLO dataset output root.",
    )
    parser.add_argument("--split", default="train", choices=("train", "val", "test"))
    parser.add_argument("--min-area", type=int, default=80)
    parser.add_argument("--min-side", type=int, default=6)
    parser.add_argument("--no-preview", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    image_path, label_path, count = convert_colored_box_annotation(
        annotated_image=args.annotated_image,
        output_root=args.output_root,
        split=args.split,
        raw_image=args.raw_image,
        min_area=args.min_area,
        min_side=args.min_side,
        write_preview=not args.no_preview,
    )
    print(f"image={image_path}")
    print(f"label={label_path}")
    print(f"boxes={count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

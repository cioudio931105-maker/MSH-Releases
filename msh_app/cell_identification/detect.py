from __future__ import annotations

from msh_app.core.msh_model_policy import require_local_model

import os
from pathlib import Path

import cv2
from ultralytics import YOLO

try:
    from cell_stitching_project.text_overlay import get_text_size, put_text
except Exception:
    def get_text_size(text: str, font_scale: float, thickness: int):
        (text_width, text_height), baseline = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness)
        return int(text_width), int(text_height), int(baseline)

    def put_text(image_bgr, text, origin, font_scale, color_bgr, thickness=1):
        cv2.putText(image_bgr, text, origin, cv2.FONT_HERSHEY_SIMPLEX, font_scale, color_bgr, thickness)

from .classify import load_model as load_classification_model
from .classify import resolve_model_path as resolve_classification_model_path


def detect_and_classify(
    image_path: str,
    detect_model_path: str | None = None,
    classify_model_path: str | None = None,
    conf_threshold: float = 0.25,
    save_dir: str = "runs/detect_classify",
):
    detect_model_path = require_local_model(detect_model_path)
    classify_model_path = resolve_classification_model_path(classify_model_path)

    print(f"Loading detect model: {detect_model_path}")
    detect_model = YOLO(require_local_model(detect_model_path))
    print(f"Loading classify model: {classify_model_path}")
    classify_model = load_classification_model(classify_model_path)

    image = cv2.imread(image_path)
    if image is None:
        print("Failed to load image:", image_path)
        return None

    detect_results = detect_model(image, conf=conf_threshold, verbose=False)
    if len(detect_results) == 0 or len(detect_results[0].boxes) == 0:
        print("No detections found.")
        return None

    boxes = detect_results[0].boxes
    annotated = image.copy()
    output_rows: list[dict[str, object]] = []

    for idx, box in enumerate(boxes):
        x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
        detect_conf = float(box.conf[0])

        x1 = max(0, x1)
        y1 = max(0, y1)
        x2 = min(image.shape[1], x2)
        y2 = min(image.shape[0], y2)
        roi = image[y1:y2, x1:x2]
        if roi.size == 0:
            continue

        classify_result = classify_model(roi, verbose=False)
        probs = classify_result[0].probs
        top1 = int(probs.top1)
        top1_conf = float(probs.top1conf)
        names = classify_result[0].names
        if isinstance(names, dict):
            class_name = str(names.get(top1, top1))
        else:
            class_name = str(names[top1])

        row = {
            "bbox": [x1, y1, x2, y2],
            "detect_conf": detect_conf,
            "class": class_name,
            "class_conf": top1_conf,
        }
        output_rows.append(row)

        label = f"{class_name} {top1_conf:.2f}"
        color = (0, 255, 0)
        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
        text_w, text_h, baseline = get_text_size(label, font_scale=0.6, thickness=2)
        cv2.rectangle(annotated, (x1, y1 - text_h - baseline - 10), (x1 + text_w, y1), color, -1)
        put_text(
            annotated,
            label,
            (x1, y1 - 5),
            0.6,
            (0, 0, 0),
            2,
        )

        print(
            f"[{idx + 1}] bbox=[{x1},{y1},{x2},{y2}] "
            f"det={detect_conf:.2f} class={class_name} cls={top1_conf:.2f}"
        )

    os.makedirs(save_dir, exist_ok=True)
    output_image = os.path.join(save_dir, os.path.basename(image_path))
    cv2.imwrite(output_image, annotated)

    output_txt = os.path.join(save_dir, Path(image_path).stem + "_results.txt")
    with open(output_txt, "w", encoding="utf-8") as handle:
        handle.write(f"image: {image_path}\n")
        handle.write(f"detections: {len(output_rows)}\n\n")
        for index, row in enumerate(output_rows, start=1):
            handle.write(f"detection {index}:\n")
            handle.write(f"  bbox: {row['bbox']}\n")
            handle.write(f"  detect_conf: {row['detect_conf']:.3f}\n")
            handle.write(f"  class: {row['class']}\n")
            handle.write(f"  class_conf: {row['class_conf']:.3f}\n\n")

    print("Annotated image saved to", output_image)
    print("Result text saved to", output_txt)
    return output_rows, annotated

from __future__ import annotations

from msh_app.core.msh_model_policy import require_local_model

import argparse
import shutil
from pathlib import Path

from .cell_identification import collect_image_paths, load_class_names
from .io_utils import save_json


def default_output_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "datasets" / "wbc_400x" / "hard_examples"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect low-confidence 400x WBC/RBC confusion examples for relabeling.",
    )
    parser.add_argument("--model", required=True, help="YOLO .pt model used to mine hard examples.")
    parser.add_argument("--source", required=True, help="400x image file or folder.")
    parser.add_argument("--output-dir", default=str(default_output_dir()))
    parser.add_argument("--class-file", default=None)
    parser.add_argument("--confidence", type=float, default=0.05, help="Low threshold to expose weak detections.")
    parser.add_argument("--review-below", type=float, default=0.65, help="Copy images with detections below this confidence.")
    parser.add_argument("--include-label", action="append", default=[], help="Only review these predicted labels; repeatable.")
    parser.add_argument("--device", default=None)
    return parser


def collect_hard_examples(args: argparse.Namespace) -> Path:
    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise ImportError("Ultralytics is required to collect hard examples.") from exc

    source_paths = collect_image_paths(args.source)
    output_dir = Path(args.output_dir)
    images_dir = output_dir / "images_to_relabel"
    images_dir.mkdir(parents=True, exist_ok=True)
    class_names = load_class_names(args.class_file) if args.class_file else []
    include_labels = {label.strip() for label in args.include_label if label.strip()}

    model = YOLO(require_local_model(str(args.model)))
    manifest: list[dict[str, object]] = []
    for image_path in source_paths:
        results = model.predict(
            source=str(image_path),
            conf=float(args.confidence),
            device=args.device,
            verbose=False,
        )
        review_rows: list[dict[str, object]] = []
        for box in results[0].boxes:
            class_id = int(box.cls.item())
            confidence = float(box.conf.item())
            label = (
                class_names[class_id]
                if 0 <= class_id < len(class_names)
                else str(results[0].names.get(class_id, class_id))
            )
            if include_labels and label not in include_labels:
                continue
            if confidence > float(args.review_below):
                continue
            review_rows.append(
                {
                    "class_id": class_id,
                    "label": label,
                    "confidence": round(confidence, 6),
                    "xyxy": [round(float(value), 2) for value in box.xyxy[0].tolist()],
                }
            )

        if not review_rows:
            continue

        target = images_dir / image_path.name
        if image_path.resolve() != target.resolve():
            shutil.copy2(image_path, target)
        manifest.append(
            {
                "source_image": str(image_path.resolve()),
                "review_image": str(target.resolve()),
                "detections": review_rows,
            }
        )

    manifest_path = output_dir / "hard_examples_manifest.json"
    save_json(manifest_path, {"count": len(manifest), "examples": manifest})
    print(f"hard_examples={len(manifest)}")
    print(f"manifest={manifest_path.resolve()}")
    print(f"images_to_relabel={images_dir.resolve()}")
    return manifest_path


def main() -> int:
    args = _parser().parse_args()
    collect_hard_examples(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from offline_pipeline.pseudo_train import (
    build_three_class_yolo_dataset,
    default_base_model,
    default_dataset_root,
    default_training_project,
    resolve_detection_csvs,
    train_three_class_model,
)


def parse_args() -> argparse.Namespace:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    parser = argparse.ArgumentParser(
        description="Build a three-class pseudo-labeled YOLO dataset from offline detections and continue training.",
    )
    parser.add_argument(
        "--detections",
        type=Path,
        nargs="*",
        default=None,
        help="detections_all.csv, a detections run directory, or omitted to use the latest detections_all.csv.",
    )
    parser.add_argument("--base-model", type=Path, default=default_base_model())
    parser.add_argument("--dataset-out", type=Path, default=default_dataset_root())
    parser.add_argument("--project", type=Path, default=default_training_project())
    parser.add_argument("--name", default=f"blood_cells_3cls_pseudo_refine_{stamp}")
    parser.add_argument("--min-conf", type=float, default=0.65)
    parser.add_argument("--val-ratio", type=float, default=0.15)
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--imgsz", type=int, default=960)
    parser.add_argument("--batch", type=int, default=2)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--prepare-only", action="store_true", help="Only build the YOLO dataset; do not train.")
    parser.add_argument("--dry-run", action="store_true", help="Print training settings without training.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    csv_paths = resolve_detection_csvs(args.detections)
    print("Using detection CSV files:")
    for csv_path in csv_paths:
        print(f"  {csv_path.resolve()}")

    data_yaml = build_three_class_yolo_dataset(
        csv_paths,
        args.dataset_out,
        min_confidence=args.min_conf,
        val_ratio=args.val_ratio,
    )
    print(f"data_yaml={data_yaml.resolve()}")

    if args.prepare_only:
        print("Dataset prepared. Training skipped because --prepare-only was set.")
        return 0

    best_model = train_three_class_model(
        data_yaml=data_yaml,
        base_model=args.base_model,
        project=args.project,
        name=args.name,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        workers=args.workers,
        dry_run=args.dry_run,
    )
    if best_model is not None:
        print(f"best_model={best_model.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


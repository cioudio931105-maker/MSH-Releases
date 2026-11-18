"""Backward-compatible wrapper for classification training."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cell_identification.training import train_classification


def main() -> int:
    p = argparse.ArgumentParser(description="Train YOLOv8 classification on an existing train/val dataset")
    p.add_argument("--data", required=True, help="Dataset root with train/ and val/ class folders")
    p.add_argument("--epochs", type=int, default=80)
    p.add_argument("--imgsz", type=int, default=224)
    p.add_argument("--batch", type=int, default=16)
    p.add_argument("--patience", type=int, default=20)
    p.add_argument("--model", default="", help="Base model path. Empty=auto latest")
    p.add_argument("--name", default="train")
    p.add_argument("--project", default="runs/classify")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--device", default="")
    args = p.parse_args()

    data_dir = Path(args.data)
    if not data_dir.exists():
        raise FileNotFoundError(f"Dataset path not found: {data_dir}")

    train_classification(
        data_dir=data_dir,
        model_path=(args.model or None),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        patience=args.patience,
        name=args.name,
        project=args.project,
        workers=args.workers,
        device=args.device,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

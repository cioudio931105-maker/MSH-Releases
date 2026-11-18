from __future__ import annotations

import argparse
import shutil
from datetime import datetime
from pathlib import Path

import torch
from ultralytics import YOLO

from cell_stitching_project.augment_manual_annotation_dataset import DEFAULT_OUTPUT


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = (
    PROJECT_ROOT
    / "stitched_output"
    / "stitched_output"
    / "stitched_output"
    / "models"
    / "blood_cells_3cls_400x_refine_20260517.pt"
)
DEFAULT_RUNS = PROJECT_ROOT / "staging" / "train"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train blood-cell detector on augmented manual annotations.")
    parser.add_argument("--data", type=Path, default=DEFAULT_OUTPUT / "data.yaml")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--imgsz", type=int, default=960)
    parser.add_argument("--batch", type=int, default=1)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--name", default="blood_cells_3cls_augmented_manual_refine_latest")
    parser.add_argument("--project", type=Path, default=DEFAULT_RUNS)
    parser.add_argument("--promote-to-default", action="store_true")
    return parser.parse_args()


def require_file(path: Path, label: str) -> None:
    if not path.exists():
        raise SystemExit(f"{label} not found: {path}")


def resolve_device(device: str) -> str:
    if device.lower() != "auto":
        return device
    return "0" if torch.cuda.is_available() else "cpu"


def main() -> int:
    args = parse_args()
    require_file(args.data, "Data YAML")
    require_file(args.model, "Base model")
    device = resolve_device(args.device)
    print(f"Training device: {device}")

    model = YOLO(str(args.model))
    result = model.train(
        data=str(args.data),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=device,
        workers=args.workers,
        project=str(args.project),
        name=args.name,
        exist_ok=True,
        pretrained=True,
        optimizer="AdamW",
        lr0=0.0008,
        lrf=0.01,
        patience=12,
        cos_lr=True,
        close_mosaic=8,
        hsv_h=0.015,
        hsv_s=0.35,
        hsv_v=0.25,
        translate=0.06,
        scale=0.12,
        degrees=4.0,
        fliplr=0.5,
        mosaic=0.15,
        mixup=0.0,
        copy_paste=0.0,
        val=True,
    )

    run_dir = Path(result.save_dir)
    best = run_dir / "weights" / "best.pt"
    print(f"Training run: {run_dir}")
    print(f"Best model: {best}")
    for artifact in ("results.png", "confusion_matrix.png", "labels.jpg", "args.yaml"):
        path = run_dir / artifact
        if path.exists():
            print(f"Artifact: {path}")

    if args.promote_to_default:
        require_file(best, "Best trained model")
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = args.model.with_name(f"{args.model.stem}.backup_before_augmented_{stamp}{args.model.suffix}")
        shutil.copy2(args.model, backup)
        shutil.copy2(best, args.model)
        print(f"Default model updated: {args.model}")
        print(f"Backup created: {backup}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

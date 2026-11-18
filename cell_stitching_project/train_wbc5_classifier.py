from __future__ import annotations

from msh_app.core.msh_model_policy import require_local_model, local_training_options

import argparse
from pathlib import Path

from .cell_classes import WBC_5_CLASS_NAMES


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_data_dir() -> Path:
    return _workspace_root() / "datasets" / "wbc5_classification_1000x"


def default_project_dir() -> Path:
    return _workspace_root() / "staging" / "train"


def validate_classification_dataset(data_dir: str | Path) -> dict[str, int]:
    root = Path(data_dir)
    if not root.exists():
        raise FileNotFoundError(f"Classification dataset not found: {root}")
    counts: dict[str, int] = {}
    for split in ("train", "val"):
        for class_name in WBC_5_CLASS_NAMES:
            class_dir = root / split / class_name
            if not class_dir.is_dir():
                raise FileNotFoundError(f"Missing class folder: {class_dir}")
            count = len([p for p in class_dir.iterdir() if p.is_file()])
            counts[f"{split}/{class_name}"] = count
            if count <= 0:
                raise ValueError(f"No images found in {class_dir}")
    return counts


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train a five-class WBC subtype classifier.")
    parser.add_argument("--data", default=str(default_data_dir()), help="Ultralytics classification dataset folder.")
    parser.add_argument("--model", default="yolov8s-cls.pt", help="YOLO classification base model.")
    parser.add_argument("--project", default=str(default_project_dir()))
    parser.add_argument("--name", default="wbc_5cls_1000x_cls_20260519")
    parser.add_argument("--epochs", type=int, default=120)
    parser.add_argument("--imgsz", type=int, default=224)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--patience", type=int, default=30)
    parser.add_argument("--device", default=None)
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--optimizer", default="AdamW")
    parser.add_argument("--lr0", type=float, default=0.0005)
    parser.add_argument("--cache", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def train_wbc5_classifier(args: argparse.Namespace) -> Path | None:
    counts = validate_classification_dataset(args.data)
    train_kwargs = {
        "data": str(Path(args.data)),
        "epochs": int(args.epochs),
        "imgsz": int(args.imgsz),
        "batch": int(args.batch),
        "workers": int(args.workers),
        "project": str(Path(args.project)),
        "name": str(args.name),
        "patience": int(args.patience),
        "optimizer": str(args.optimizer),
        "lr0": float(args.lr0),
        "seed": int(args.seed),
        "cache": bool(args.cache),
    }
    if args.device is not None:
        train_kwargs["device"] = args.device

    print("dataset_counts=")
    for key in sorted(counts):
        print(f"  {key}: {counts[key]}")
    print(f"classes={list(WBC_5_CLASS_NAMES)}")
    print(f"model={args.model}")
    print(f"train_kwargs={train_kwargs}")
    if args.dry_run:
        return None

    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise ImportError("Ultralytics is required for YOLO classification training.") from exc

    model = YOLO(require_local_model(str(args.model)))
    result = model.train(**(train_kwargs | local_training_options(args.model)))
    save_dir = Path(getattr(result, "save_dir", Path(args.project) / str(args.name)))
    best_path = save_dir / "weights" / "best.pt"
    print(f"best_model={best_path.resolve()}")
    return best_path


def main() -> int:
    args = _parser().parse_args()
    train_wbc5_classifier(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

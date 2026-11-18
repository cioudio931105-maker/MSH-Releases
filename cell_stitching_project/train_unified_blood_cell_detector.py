from __future__ import annotations

from msh_app.core.msh_model_policy import require_local_model, local_training_options

import argparse
from pathlib import Path

from .blood_cell_unified_classes import UNIFIED_BLOOD_CELL_CLASS_NAMES


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_data_yaml() -> Path:
    return Path("D:/Cell_Project_Datasets/blood_cells_unified_7cls/data.yaml")


def default_model_path() -> Path:
    return (
        _workspace_root()
        / "stitched_output"
        / "stitched_output"
        / "stitched_output"
        / "models"
        / "blood_cells_3cls_yolov8n_20260429.pt"
    )


def default_project_dir() -> Path:
    return _workspace_root() / "staging" / "train"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train one unified detector for RBC, Platelets, and five WBC subtypes.")
    parser.add_argument("--data", default=str(default_data_yaml()))
    parser.add_argument("--model", default=str(default_model_path()))
    parser.add_argument("--project", default=str(default_project_dir()))
    parser.add_argument("--name", default="blood_cells_unified_7cls_yolov8n")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--imgsz", type=int, default=960)
    parser.add_argument("--batch", type=int, default=2)
    parser.add_argument("--patience", type=int, default=30)
    parser.add_argument("--device", default=None)
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--lr0", type=float, default=0.00045)
    parser.add_argument("--close-mosaic", type=int, default=25)
    parser.add_argument("--mosaic", type=float, default=0.20)
    parser.add_argument("--mixup", type=float, default=0.01)
    parser.add_argument("--degrees", type=float, default=180.0)
    parser.add_argument("--scale", type=float, default=0.20)
    parser.add_argument("--translate", type=float, default=0.05)
    parser.add_argument("--cls-loss-gain", type=float, default=0.90)
    parser.add_argument("--box-loss-gain", type=float, default=8.0)
    parser.add_argument("--dfl-loss-gain", type=float, default=1.6)
    parser.add_argument("--cache", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def train_unified_detector(args: argparse.Namespace) -> Path | None:
    data_yaml = Path(args.data)
    model_path = Path(args.model)
    if not data_yaml.is_file():
        raise FileNotFoundError(f"Unified data yaml not found: {data_yaml}")
    if not model_path.is_file():
        raise FileNotFoundError(f"Base model not found: {model_path}")

    train_kwargs = {
        "data": str(data_yaml),
        "epochs": int(args.epochs),
        "imgsz": int(args.imgsz),
        "batch": int(args.batch),
        "workers": int(args.workers),
        "project": str(Path(args.project)),
        "name": str(args.name),
        "exist_ok": True,
        "patience": int(args.patience),
        "optimizer": "AdamW",
        "lr0": float(args.lr0),
        "cos_lr": True,
        "close_mosaic": int(args.close_mosaic),
        "seed": int(args.seed),
        "cache": bool(args.cache),
        "mosaic": float(args.mosaic),
        "mixup": float(args.mixup),
        "copy_paste": 0.0,
        "degrees": float(args.degrees),
        "scale": float(args.scale),
        "translate": float(args.translate),
        "fliplr": 0.5,
        "flipud": 0.5,
        "cls": float(args.cls_loss_gain),
        "box": float(args.box_loss_gain),
        "dfl": float(args.dfl_loss_gain),
    }
    if args.device is not None:
        train_kwargs["device"] = args.device

    print(f"classes={list(UNIFIED_BLOOD_CELL_CLASS_NAMES)}")
    print(f"model={model_path}")
    print(f"data={data_yaml}")
    print(f"train_kwargs={train_kwargs}")
    if args.dry_run:
        return None

    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise ImportError("Ultralytics is required for YOLO training.") from exc

    model = YOLO(require_local_model(str(model_path)))
    result = model.train(**(train_kwargs | local_training_options(model_path)))
    save_dir = Path(getattr(result, "save_dir", Path(args.project) / str(args.name)))
    best_path = save_dir / "weights" / "best.pt"
    print(f"best_model={best_path.resolve()}")
    return best_path


def main() -> int:
    args = _parser().parse_args()
    train_unified_detector(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

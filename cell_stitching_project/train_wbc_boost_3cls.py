from __future__ import annotations

from msh_app.core.msh_model_policy import require_local_model, local_training_options

import argparse
from datetime import datetime
from pathlib import Path

from .prepare_wbc_boost_3cls_dataset import (
    build_wbc_boost_dataset,
    default_output_root,
    default_txl_images_train,
    default_wbc_root,
    workspace_root,
)


def default_model_path() -> Path:
    return (
        workspace_root()
        / "stitched_output"
        / "stitched_output"
        / "stitched_output"
        / "models"
        / "blood_cells_3cls_400x_refine_20260517.pt"
    )


def default_project_dir() -> Path:
    return workspace_root() / "staging" / "train"


def print_training_artifacts(save_dir: Path) -> None:
    artifacts = {
        "results_png": save_dir / "results.png",
        "confusion_matrix": save_dir / "confusion_matrix.png",
        "labels_plot": save_dir / "labels.jpg",
        "best_model": save_dir / "weights" / "best.pt",
        "last_model": save_dir / "weights" / "last.pt",
    }
    for name, path in artifacts.items():
        if path.exists():
            print(f"{name}={path.resolve()}")


def _auto_device() -> str:
    try:
        import torch

        return "0" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


def _parser() -> argparse.ArgumentParser:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    parser = argparse.ArgumentParser(description="Fine-tune the three-class detector with TXL-PBC train plus WBC-only images.")
    parser.add_argument("--txl-images-train", type=Path, default=default_txl_images_train())
    parser.add_argument("--wbc-root", type=Path, default=default_wbc_root())
    parser.add_argument("--dataset-out", type=Path, default=default_output_root())
    parser.add_argument("--model", type=Path, default=default_model_path())
    parser.add_argument("--project", type=Path, default=default_project_dir())
    parser.add_argument("--name", default=f"blood_cells_3cls_wbc_boost_{stamp}")
    parser.add_argument("--val-ratio", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--epochs", type=int, default=12)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=2)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--lr0", type=float, default=0.00015)
    parser.add_argument("--patience", type=int, default=5)
    parser.add_argument("--fraction", type=float, default=1.0)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def train_wbc_boost_3cls(args: argparse.Namespace) -> Path | None:
    data_yaml = build_wbc_boost_dataset(
        args.txl_images_train,
        args.wbc_root,
        args.dataset_out,
        val_ratio=args.val_ratio,
        seed=args.seed,
    )
    print(f"data_yaml={data_yaml}")

    if args.prepare_only:
        print("Dataset prepared. Training skipped because --prepare-only was set.")
        return None

    model_path = Path(args.model)
    if not model_path.is_file():
        raise FileNotFoundError(f"Base model not found: {model_path}")

    device = _auto_device() if str(args.device).lower() == "auto" else str(args.device)
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
        "seed": int(args.seed),
        "device": device,
        "cache": False,
        "mosaic": 0.15,
        "mixup": 0.0,
        "copy_paste": 0.0,
        "degrees": 30.0,
        "scale": 0.12,
        "translate": 0.04,
        "fliplr": 0.5,
        "flipud": 0.5,
        "close_mosaic": 4,
        "fraction": float(args.fraction),
    }
    print(f"model={model_path}")
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
    print_training_artifacts(save_dir)
    print(f"best_model={best_path.resolve()}")
    return best_path


def main() -> int:
    args = _parser().parse_args()
    train_wbc_boost_3cls(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

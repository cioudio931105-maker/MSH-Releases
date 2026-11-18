from __future__ import annotations

from msh_model_policy import require_local_model, local_training_options

import argparse
import shutil
from datetime import datetime
from pathlib import Path

from .prepare_confidence_boost_3cls_dataset import (
    build_confidence_boost_dataset,
    default_manual_augmented_root,
    default_output_root,
    default_pseudo_root,
    default_txl_root,
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


def auto_device() -> str:
    try:
        import torch

        return "0" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


def print_training_artifacts(save_dir: Path) -> None:
    for artifact in ("results.png", "confusion_matrix.png", "labels.jpg", "args.yaml", "weights/best.pt", "weights/last.pt"):
        path = save_dir / artifact
        if path.exists():
            print(f"artifact={path.resolve()}")


def parser() -> argparse.ArgumentParser:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    p = argparse.ArgumentParser(description="Fine-tune blood-cell detector with manual annotations plus TXL-PBC public data.")
    p.add_argument("--txl-root", type=Path, default=default_txl_root())
    p.add_argument("--manual-augmented-root", type=Path, default=default_manual_augmented_root())
    p.add_argument("--pseudo-root", type=Path, default=default_pseudo_root())
    p.add_argument("--dataset-out", type=Path, default=default_output_root())
    p.add_argument("--max-txl-train", type=int, default=240)
    p.add_argument("--max-txl-val", type=int, default=80)
    p.add_argument("--manual-repeat", type=int, default=1)
    p.add_argument("--pseudo-repeat", type=int, default=1)
    p.add_argument("--wbc-repeat", type=int, default=1)
    p.add_argument("--platelet-repeat", type=int, default=1)
    p.add_argument("--model", type=Path, default=default_model_path())
    p.add_argument("--project", type=Path, default=default_project_dir())
    p.add_argument("--name", default=f"blood_cells_3cls_confidence_boost_{stamp}")
    p.add_argument("--epochs", type=int, default=6)
    p.add_argument("--imgsz", type=int, default=640)
    p.add_argument("--batch", type=int, default=2)
    p.add_argument("--device", default="auto")
    p.add_argument("--workers", type=int, default=0)
    p.add_argument("--lr0", type=float, default=0.00012)
    p.add_argument("--box-loss-gain", type=float, default=7.5)
    p.add_argument("--cls-loss-gain", type=float, default=0.5)
    p.add_argument("--dfl-loss-gain", type=float, default=1.5)
    p.add_argument("--patience", type=int, default=4)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--prepare-only", action="store_true")
    p.add_argument("--promote-to-default", action="store_true")
    return p


def main() -> int:
    args = parser().parse_args()
    data_yaml = build_confidence_boost_dataset(
        args.txl_root,
        args.manual_augmented_root,
        args.dataset_out,
        pseudo_root=args.pseudo_root,
        max_txl_train=args.max_txl_train,
        max_txl_val=args.max_txl_val,
        seed=args.seed,
        manual_repeat=args.manual_repeat,
        pseudo_repeat=args.pseudo_repeat,
        wbc_repeat=args.wbc_repeat,
        platelet_repeat=args.platelet_repeat,
    )
    if args.prepare_only:
        return 0
    if not args.model.is_file():
        raise FileNotFoundError(f"Base model not found: {args.model}")

    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise ImportError("Ultralytics is required for YOLO training.") from exc

    device = auto_device() if str(args.device).lower() == "auto" else str(args.device)
    print(f"model={args.model.resolve()}")
    print(f"device={device}")
    model = YOLO(require_local_model(str(args.model)))
    result = model.train(
        data=str(data_yaml),
        epochs=int(args.epochs),
        imgsz=int(args.imgsz),
        batch=int(args.batch),
        workers=int(args.workers),
        project=str(args.project),
        name=str(args.name),
        exist_ok=True,
        patience=int(args.patience),
        optimizer="AdamW",
        lr0=float(args.lr0),
        box=float(args.box_loss_gain),
        cls=float(args.cls_loss_gain),
        dfl=float(args.dfl_loss_gain),
        cos_lr=True,
        seed=int(args.seed),
        **local_training_options(args.model),
        device=device,
        cache=False,
        mosaic=0.10,
        mixup=0.0,
        copy_paste=0.0,
        degrees=10.0,
        scale=0.08,
        translate=0.03,
        fliplr=0.5,
        flipud=0.2,
        close_mosaic=3,
    )
    save_dir = Path(getattr(result, "save_dir", Path(args.project) / str(args.name)))
    best = save_dir / "weights" / "best.pt"
    print_training_artifacts(save_dir)
    print(f"best_model={best.resolve()}")

    if args.promote_to_default:
        if not best.is_file():
            raise FileNotFoundError(f"Best model not found: {best}")
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = args.model.with_name(f"{args.model.stem}.backup_before_confidence_boost_{stamp}{args.model.suffix}")
        shutil.copy2(args.model, backup)
        shutil.copy2(best, args.model)
        print(f"backup_model={backup.resolve()}")
        print(f"promoted_model={args.model.resolve()}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

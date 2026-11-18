"""Unified classification training entrypoint."""

from __future__ import annotations

# Direct source entrypoints also resolve shared modules from the workspace.
import sys as _msh_sys
from pathlib import Path as _MshPath
if not getattr(_msh_sys, "frozen", False):
    _msh_sys.path.insert(0, str(_MshPath(__file__).resolve().parents[2]))


import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cell_identification.training import prepare_dataset, train_classification


def main() -> int:
    p = argparse.ArgumentParser(description="Prepare dataset then train YOLO classification model")
    p.add_argument("--src", required=True, help="Source root with class subfolders")
    p.add_argument("--out", default="data/dataset_cls", help="Output dataset root containing train/val")
    p.add_argument("--val_ratio", type=float, default=0.2)
    p.add_argument("--seed", type=int, default=42)
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

    src = Path(args.src)
    out = Path(args.out)
    if not src.exists():
        raise FileNotFoundError(f"Source path not found: {src}")

    stats = prepare_dataset([src], out, val_ratio=args.val_ratio, seed=args.seed, clean_output=True)
    print(f"Dataset prepared: train={stats.train_count}, val={stats.val_count}, classes={stats.classes}")

    train_classification(
        data_dir=out,
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

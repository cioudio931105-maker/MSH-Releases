"""Domain-adaptation training pipeline for user-captured slide images."""

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
    p = argparse.ArgumentParser(description="Adapt classification model to user-captured slide images")
    p.add_argument("--new_data", required=True, help="Your newly captured data root (class subfolders)")
    p.add_argument("--legacy_data", default="", help="Optional legacy data root (class subfolders)")
    p.add_argument("--output_dataset", default="data/dataset_domain_adapt", help="Prepared train/val dataset output")
    p.add_argument("--new_weight", type=int, default=3, help="Oversampling weight for new_data")
    p.add_argument("--val_ratio", type=float, default=0.2)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--epochs", type=int, default=100)
    p.add_argument("--imgsz", type=int, default=224)
    p.add_argument("--batch", type=int, default=16)
    p.add_argument("--patience", type=int, default=25)
    p.add_argument("--model", default="", help="Base model path. Empty=auto latest")
    p.add_argument("--name", default="domain_adapt")
    p.add_argument("--project", default="runs/classify")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--device", default="")
    p.add_argument("--prepare_only", action="store_true", help="Only prepare dataset, skip training")
    args = p.parse_args()

    new_data = Path(args.new_data)
    if not new_data.exists():
        raise FileNotFoundError(f"new_data not found: {new_data}")

    source_dirs = [new_data]
    legacy_data = Path(args.legacy_data) if args.legacy_data else None
    if legacy_data is not None and legacy_data.exists():
        source_dirs.append(legacy_data)

    output_dataset = Path(args.output_dataset)
    stats = prepare_dataset(
        source_dirs=source_dirs,
        output_dir=output_dataset,
        val_ratio=args.val_ratio,
        seed=args.seed,
        domain_focus_dir=new_data,
        domain_focus_weight=max(1, int(args.new_weight)),
        clean_output=True,
    )
    print(f"Prepared dataset: {output_dataset.resolve()}")
    print(f"Classes: {stats.classes}")
    print(f"train={stats.train_count}, val={stats.val_count}")

    if args.prepare_only:
        return 0

    train_classification(
        data_dir=output_dataset,
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

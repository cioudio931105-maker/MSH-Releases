"""Prepare train/val dataset from class-subfolder images."""

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

from cell_identification.training import prepare_dataset


def main() -> int:
    p = argparse.ArgumentParser(description="Build train/val split from source class folders")
    p.add_argument("--source", required=True, help="Source root with class subfolders")
    p.add_argument("--output", default="data/dataset_cls", help="Output dataset root")
    p.add_argument("--val_ratio", type=float, default=0.2)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--keep_output", action="store_true", help="Do not clean output directory before writing")
    args = p.parse_args()

    source = Path(args.source)
    output = Path(args.output)
    if not source.exists():
        raise FileNotFoundError(f"Source path not found: {source}")

    stats = prepare_dataset(
        source_dirs=[source],
        output_dir=output,
        val_ratio=args.val_ratio,
        seed=args.seed,
        clean_output=(not args.keep_output),
    )
    print(f"Prepared dataset at: {output.resolve()}")
    print(f"Classes: {stats.classes}")
    print(f"train={stats.train_count}, val={stats.val_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

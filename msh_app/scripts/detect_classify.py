"""CLI wrapper for unified detect+classify pipeline."""

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

from cell_identification.detect import detect_and_classify


def main() -> None:
    parser = argparse.ArgumentParser(description="Run detection and classification on one image")
    parser.add_argument("--source", required=True, help="Input image path")
    parser.add_argument("--detect_model", default=None, help="YOLO detect model path")
    parser.add_argument("--classify_model", default=None, help="YOLO classify model path")
    parser.add_argument("--conf", type=float, default=0.25, help="Detection confidence threshold")
    parser.add_argument("--save_dir", default="runs/detect_classify", help="Output directory")
    args = parser.parse_args()

    detect_and_classify(
        image_path=args.source,
        detect_model_path=args.detect_model,
        classify_model_path=args.classify_model,
        conf_threshold=args.conf,
        save_dir=args.save_dir,
    )


if __name__ == "__main__":
    main()


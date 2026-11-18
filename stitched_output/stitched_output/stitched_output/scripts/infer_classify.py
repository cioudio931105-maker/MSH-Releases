"""CLI wrapper for unified cell identification classification."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cell_identification.classify import export_csv, find_model, infer, load_model


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="", help="Classification model path")
    parser.add_argument("--source", default="cell_images", help="Image path or folder")
    parser.add_argument("--save_dir", default="runs/classify/infer", help="Output directory")
    parser.add_argument("--report_csv", default="", help="Optional CSV report path")
    args = parser.parse_args()

    model_path = args.model or find_model()
    if not model_path:
        model_path = "yolov8n-cls.pt"
        print("No trained classify model found. Falling back to yolov8n-cls.pt")

    results = infer(model_path, args.source, save_dir=args.save_dir)
    if results is not None and args.report_csv:
        export_csv(results, model=load_model(model_path), csv_path=args.report_csv)


if __name__ == "__main__":
    main()


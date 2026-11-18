from __future__ import annotations

import argparse
from pathlib import Path

from microscope_stitcher.manual_align import export_manual_alignment


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export a stitched mosaic from manual_positions.csv.")
    parser.add_argument("--input", required=True, help="Input session folder containing tile images.")
    parser.add_argument("--positions", required=True, help="manual_positions.csv saved by manual_align_gui.py.")
    parser.add_argument("--output", required=True, help="Output folder.")
    parser.add_argument("--blend-mode", choices=("max_weight", "feather"), default="max_weight")
    parser.add_argument("--export-format", choices=("tif", "png", "jpg"), default="tif")
    parser.add_argument("--no-crop", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    result = export_manual_alignment(
        input_dir=Path(args.input),
        positions_csv=Path(args.positions),
        output_dir=Path(args.output),
        blend_mode=args.blend_mode,
        export_format=args.export_format,
        crop=not args.no_crop,
    )
    print(f"stitched: {result['stitched']}")
    print(f"preview:  {result['preview']}")
    print(f"summary:  {result['summary']}")


if __name__ == "__main__":
    main()

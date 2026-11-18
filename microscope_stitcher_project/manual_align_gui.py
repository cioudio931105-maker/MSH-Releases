from __future__ import annotations

import argparse
from pathlib import Path

from microscope_stitcher.manual_align import ManualAlignApp


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manual tile alignment GUI for microscope stitching.")
    parser.add_argument("--input", required=True, help="Input session folder containing tile images.")
    parser.add_argument("--placement", default=None, help="Optional placements.csv from a previous stitching output.")
    parser.add_argument("--output", required=True, help="Output folder for manual_positions.csv and exported mosaic.")
    parser.add_argument("--view-scale", type=float, default=0.18, help="Initial GUI tile display scale.")
    parser.add_argument("--blend-mode", choices=("max_weight", "feather"), default="max_weight")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    app = ManualAlignApp(
        input_dir=Path(args.input),
        output_dir=Path(args.output),
        placement_csv=Path(args.placement) if args.placement else None,
        view_scale=args.view_scale,
        blend_mode=args.blend_mode,
    )
    app.run()


if __name__ == "__main__":
    main()

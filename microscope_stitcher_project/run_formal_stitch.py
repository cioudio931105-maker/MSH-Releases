from __future__ import annotations

import argparse
from pathlib import Path

from microscope_stitcher.config import StitchConfig
from microscope_stitcher.pipeline import run_pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Formal microscope stitching preset learned from the confirmed 2026-05-21 mosaic."
    )
    parser.add_argument("--input", required=True, help="Input folder containing microscope tiles.")
    parser.add_argument("--output", required=True, help="Output folder.")
    parser.add_argument("--coords", default=None, help="Optional CSV with filename,x,y columns.")
    parser.add_argument("--exclude", action="append", default=[], help="Tile filename to exclude. Can be repeated.")
    parser.add_argument("--overlap", type=float, default=0.35, help="Expected overlap ratio. Default: 0.35.")
    parser.add_argument("--work-scale", type=float, default=0.35, help="Alignment scale. Default: 0.35.")
    parser.add_argument("--max-work-side", type=int, default=1800, help="Max long side for alignment images.")
    parser.add_argument("--use-cuda", choices=("auto", "on", "off"), default="auto", help="Use OpenCV CUDA if available.")
    parser.add_argument("--invert-x", action="store_true", help="Invert X stage coordinates.")
    parser.add_argument("--invert-y", action="store_true", help="Invert Y stage coordinates.")
    parser.add_argument("--anchor", default=None, help="Optional progressive anchor filename.")
    parser.add_argument("--lock-placements", default=None, help="Optional existing placements.csv to keep fixed.")
    parser.add_argument("--export-format", choices=("tif", "png", "jpg"), default="tif")
    parser.add_argument("--debug", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument(
        "--preset",
        choices=("formal", "explore"),
        default="formal",
        help="formal is conservative; explore lowers score tolerance for candidate review.",
    )
    parser.add_argument(
        "--cluster-tolerance-full-px",
        type=float,
        default=None,
        help="Full-resolution px tolerance for multi-anchor consensus. Defaults depend on preset.",
    )
    parser.add_argument(
        "--min-edge-score",
        type=float,
        default=None,
        help="Pair score threshold. Defaults depend on preset.",
    )
    parser.add_argument(
        "--keep-unconfirmed-tiles",
        action="store_true",
        help="Place fallback tiles by stage estimate. Not recommended for formal delivery.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    min_score = args.min_edge_score
    if min_score is None:
        min_score = 0.55 if args.preset == "formal" else 0.40

    tolerance_full = args.cluster_tolerance_full_px
    if tolerance_full is None:
        tolerance_full = 25.0 if args.preset == "formal" else 65.0
    tolerance_work = float(tolerance_full) * float(args.work_scale)

    config = StitchConfig(
        input_dir=Path(args.input),
        output_dir=Path(args.output),
        coords_csv=Path(args.coords) if args.coords else None,
        excluded_filenames=tuple(args.exclude),
        overlap_ratio=args.overlap,
        work_scale=args.work_scale,
        max_work_side=args.max_work_side,
        feature_method="orb",
        feature_override_score=0.45,
        feature_override_inliers=80,
        feature_override_max_orthogonal_px=70.0,
        small_feature_weight=0.20,
        use_detection_features=True,
        detection_feature_min_matches=3,
        detection_feature_cluster_tolerance_px=45.0,
        blend_mode="max_weight",
        use_cuda=args.use_cuda,
        invert_x=args.invert_x,
        invert_y=args.invert_y,
        debug=args.debug,
        export_format=args.export_format,
        feather_width=96,
        min_edge_score=float(min_score),
        placement_mode="progressive",
        progressive_tolerance_px=tolerance_work,
        progressive_min_anchor_count=2,
        drop_unconfirmed_tiles=not args.keep_unconfirmed_tiles,
        progressive_anchor=args.anchor,
        locked_placements_csv=Path(args.lock_placements) if args.lock_placements else None,
        preserve_rejected_gaps=True,
        rejected_gap_px=80,
        memmap_threshold_mb=1400,
        crop=True,
    )
    result = run_pipeline(config)
    print(f"stitched: {result.final_image}")
    print(f"preview:  {result.preview_image}")
    print(f"debug:    {result.debug_dir}")
    print(f"summary:  {result.summary_json}")
    print(f"preset:   {args.preset}")
    print(f"formal:   min_edge_score={min_score}, min_anchors=2, tolerance_full_px={tolerance_full}")
    print("note:     unconfirmed tiles are dropped unless --keep-unconfirmed-tiles is used")


if __name__ == "__main__":
    main()

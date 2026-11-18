from __future__ import annotations

import argparse
from pathlib import Path

from microscope_stitcher.config import StitchConfig
from microscope_stitcher.pipeline import run_pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Microscope cell image stitching pipeline with phase/ECC first alignment."
    )
    parser.add_argument("--input", required=True, help="Input folder containing tiles.")
    parser.add_argument("--output", required=True, help="Output folder.")
    parser.add_argument("--coords", default=None, help="Optional CSV with filename,x,y columns.")
    parser.add_argument("--exclude", action="append", default=[], help="Tile filename to exclude. Can be repeated.")
    parser.add_argument("--overlap", type=float, default=0.15, help="Expected tile overlap ratio, e.g. 0.15.")
    parser.add_argument("--work-scale", type=float, default=0.35, help="Scale used for alignment.")
    parser.add_argument("--max-work-side", type=int, default=1800, help="Max long side for alignment images.")
    parser.add_argument("--feature", choices=("orb", "sift"), default="orb", help="Feature fallback method.")
    parser.add_argument("--feature-override-score", type=float, default=0.45, help="High-confidence feature score allowed to override stage deviation.")
    parser.add_argument("--feature-override-inliers", type=int, default=80, help="Inlier count required to override stage deviation.")
    parser.add_argument("--feature-override-max-orthogonal-px", type=float, default=70.0, help="Max work-scale orthogonal drift allowed for feature override.")
    parser.add_argument(
        "--small-feature-weight",
        type=float,
        default=0.0,
        help="Weight of platelet-like small high-contrast features in alignment scoring.",
    )
    parser.add_argument("--no-detection-features", action="store_true", help="Do not use detected/*_features.json as landmark alignment hints.")
    parser.add_argument("--detection-feature-min-matches", type=int, default=3, help="Minimum same-class detection landmark matches.")
    parser.add_argument("--detection-feature-cluster-tolerance", type=float, default=45.0, help="Work-scale px tolerance for detection landmark shift clusters.")
    parser.add_argument(
        "--blend-mode",
        choices=("feather", "max_weight"),
        default="feather",
        help="Final blending mode. max_weight reduces ghosting by avoiding overlap averaging.",
    )
    parser.add_argument("--use-cuda", choices=("auto", "on", "off"), default="auto", help="Use OpenCV CUDA if available.")
    parser.add_argument("--invert-x", action="store_true", help="Invert X coordinates before stitching.")
    parser.add_argument("--invert-y", action="store_true", help="Invert Y coordinates before stitching.")
    parser.add_argument("--no-debug", action="store_true", help="Disable debug image/json output.")
    parser.add_argument("--export-format", choices=("tif", "png", "jpg"), default="tif", help="Final image format.")
    parser.add_argument("--feather", type=int, default=96, help="Feather width in final-resolution pixels.")
    parser.add_argument("--min-edge-score", type=float, default=0.10, help="Pair alignments below this score are not used for pose graph.")
    parser.add_argument(
        "--placement-mode",
        choices=("global", "progressive"),
        default="global",
        help="global uses pose graph optimization; progressive grows from left-bottom with multi-neighbor checks.",
    )
    parser.add_argument(
        "--progressive-tolerance",
        type=float,
        default=110.0,
        help="Work-scale pixel tolerance for progressive multi-neighbor consistency.",
    )
    parser.add_argument(
        "--progressive-min-anchors",
        type=int,
        default=1,
        help="Minimum independent placed anchors required before a progressive tile is accepted.",
    )
    parser.add_argument(
        "--drop-unconfirmed-tiles",
        action="store_true",
        help="Do not place progressive fallback tiles by stage estimate; leave unmatched areas black instead.",
    )
    parser.add_argument(
        "--progressive-anchor",
        default=None,
        help="Filename to use as the fixed starting tile for progressive placement.",
    )
    parser.add_argument(
        "--lock-placements",
        default=None,
        help="Existing debug/placements.csv to keep already stitched tile positions fixed.",
    )
    parser.add_argument("--rejected-gap", type=int, default=80, help="Black gap in final pixels inserted around rejected adjacent pairs.")
    parser.add_argument("--no-rejected-gap", action="store_true", help="Do not separate rejected adjacent pairs with black gaps.")
    parser.add_argument("--memmap-threshold-mb", type=int, default=1400, help="Use memmap above this accumulator size.")
    parser.add_argument("--no-crop", action="store_true", help="Disable final black-border crop.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    config = StitchConfig(
        input_dir=Path(args.input),
        output_dir=Path(args.output),
        coords_csv=Path(args.coords) if args.coords else None,
        excluded_filenames=tuple(args.exclude),
        overlap_ratio=args.overlap,
        work_scale=args.work_scale,
        max_work_side=args.max_work_side,
        feature_method=args.feature,
        feature_override_score=args.feature_override_score,
        feature_override_inliers=args.feature_override_inliers,
        feature_override_max_orthogonal_px=args.feature_override_max_orthogonal_px,
        small_feature_weight=args.small_feature_weight,
        use_detection_features=not args.no_detection_features,
        detection_feature_min_matches=args.detection_feature_min_matches,
        detection_feature_cluster_tolerance_px=args.detection_feature_cluster_tolerance,
        blend_mode=args.blend_mode,
        use_cuda=args.use_cuda,
        invert_x=args.invert_x,
        invert_y=args.invert_y,
        debug=not args.no_debug,
        export_format=args.export_format,
        feather_width=args.feather,
        min_edge_score=args.min_edge_score,
        placement_mode=args.placement_mode,
        progressive_tolerance_px=args.progressive_tolerance,
        progressive_min_anchor_count=args.progressive_min_anchors,
        drop_unconfirmed_tiles=args.drop_unconfirmed_tiles,
        progressive_anchor=args.progressive_anchor,
        locked_placements_csv=Path(args.lock_placements) if args.lock_placements else None,
        preserve_rejected_gaps=not args.no_rejected_gap,
        rejected_gap_px=args.rejected_gap,
        memmap_threshold_mb=args.memmap_threshold_mb,
        crop=not args.no_crop,
    )
    result = run_pipeline(config)
    print(f"stitched: {result.final_image}")
    print(f"preview:  {result.preview_image}")
    print(f"debug:    {result.debug_dir}")
    print(f"summary:  {result.summary_json}")


if __name__ == "__main__":
    main()

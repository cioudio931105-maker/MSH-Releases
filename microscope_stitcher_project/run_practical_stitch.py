from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from microscope_stitcher.config import StitchConfig
from microscope_stitcher.pipeline import run_pipeline


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_LEARNING_JSON = PROJECT_ROOT / "reference" / "session_20260521_181641_759929_learning.json"
DEFAULT_GOLDEN_CSV = PROJECT_ROOT / "reference" / "session_20260521_181641_759929_golden_placements.csv"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Practical microscope stitching entry point. It uses the confirmed "
            "2026-05-21 placement template when applicable, otherwise runs a "
            "conservative content-driven candidate and writes a quality report."
        )
    )
    parser.add_argument("--input", required=True, help="Input folder containing microscope tiles.")
    parser.add_argument("--output", required=True, help="Output folder.")
    parser.add_argument("--coords", default=None, help="Optional CSV with filename,x,y columns.")
    parser.add_argument("--exclude", action="append", default=[], help="Tile filename to exclude. Can be repeated.")
    parser.add_argument("--overlap", type=float, default=0.35, help="Expected tile overlap ratio.")
    parser.add_argument("--work-scale", type=float, default=0.35, help="Alignment scale.")
    parser.add_argument("--max-work-side", type=int, default=1800, help="Max long side for alignment images.")
    parser.add_argument("--use-cuda", choices=("auto", "on", "off"), default="auto")
    parser.add_argument("--export-format", choices=("tif", "png", "jpg"), default="tif")
    parser.add_argument("--debug", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--learning-json", default=str(DEFAULT_LEARNING_JSON), help="Learned template metadata JSON.")
    parser.add_argument("--golden-placements", default=str(DEFAULT_GOLDEN_CSV), help="Golden placements CSV.")
    parser.add_argument(
        "--min-template-anchors",
        type=int,
        default=12,
        help="Minimum common filenames required before learned placements are used as anchors.",
    )
    parser.add_argument(
        "--min-template-match-ratio",
        type=float,
        default=0.80,
        help="Minimum filename match ratio before learned placements are used as anchors.",
    )
    parser.add_argument(
        "--no-learned-template",
        action="store_true",
        help="Disable learned template anchors and run conservative automatic stitching only.",
    )
    parser.add_argument(
        "--axis-profile",
        choices=("microscope-v1", "normal"),
        default="microscope-v1",
        help="microscope-v1 inverts X because this stage moves the image left when X increases.",
    )
    parser.add_argument("--invert-x", action="store_true", help="Force X coordinate inversion.")
    parser.add_argument("--invert-y", action="store_true", help="Force Y coordinate inversion.")
    parser.add_argument("--no-invert-x", action="store_true", help="Disable X inversion even for microscope-v1.")
    parser.add_argument("--no-invert-y", action="store_true", help="Disable Y inversion.")
    parser.add_argument("--min-edge-score", type=float, default=None, help="Override pair score threshold.")
    parser.add_argument(
        "--cluster-tolerance-full-px",
        type=float,
        default=None,
        help="Override progressive multi-anchor tolerance in full-resolution pixels.",
    )
    parser.add_argument(
        "--keep-unconfirmed-tiles",
        action="store_true",
        help="Place unconfirmed fallback tiles by stage estimate. This is not recommended for formal output.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    input_dir = Path(args.input)
    output_dir = Path(args.output)
    coords_csv = Path(args.coords) if args.coords else _default_coords(input_dir)
    learning = _load_learning(Path(args.learning_json))
    golden_csv = Path(args.golden_placements)
    user_excludes = {Path(name).name for name in args.exclude}
    learned_excludes = set(_learned_excluded_tiles(learning))
    available_filenames = _discover_image_filenames(input_dir)
    target_filenames = available_filenames - user_excludes - learned_excludes
    golden_filenames = _load_placement_filenames(golden_csv) if golden_csv.exists() else set()
    common_template_filenames = sorted(target_filenames & golden_filenames)
    match_denominator = max(1, min(len(golden_filenames), len(target_filenames)))
    template_match_ratio = len(common_template_filenames) / match_denominator
    use_template = (
        not args.no_learned_template
        and golden_csv.exists()
        and len(common_template_filenames) >= max(1, args.min_template_anchors)
        and template_match_ratio >= float(args.min_template_match_ratio)
    )

    excluded = set(user_excludes)
    if use_template:
        excluded.update(learned_excludes)

    invert_x, invert_y = _resolve_axis_flags(args)
    mode = "learned_template_anchor" if use_template else "conservative_auto_candidate"
    min_edge_score = args.min_edge_score
    tolerance_full = args.cluster_tolerance_full_px
    if use_template:
        min_edge_score = 0.10 if min_edge_score is None else min_edge_score
        tolerance_full = 314.0 if tolerance_full is None else tolerance_full
        min_anchor_count = 2
    else:
        min_edge_score = 0.40 if min_edge_score is None else min_edge_score
        tolerance_full = 65.0 if tolerance_full is None else tolerance_full
        min_anchor_count = 2

    config = StitchConfig(
        input_dir=input_dir,
        output_dir=output_dir,
        coords_csv=coords_csv,
        excluded_filenames=tuple(sorted(excluded)),
        overlap_ratio=float(args.overlap),
        work_scale=float(args.work_scale),
        max_work_side=int(args.max_work_side),
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
        invert_x=invert_x,
        invert_y=invert_y,
        debug=bool(args.debug),
        export_format=args.export_format,
        feather_width=96,
        min_edge_score=float(min_edge_score),
        placement_mode="progressive",
        progressive_tolerance_px=float(tolerance_full) * float(args.work_scale),
        progressive_min_anchor_count=min_anchor_count,
        drop_unconfirmed_tiles=not args.keep_unconfirmed_tiles,
        progressive_anchor=None,
        locked_placements_csv=golden_csv if use_template else None,
        preserve_rejected_gaps=True,
        rejected_gap_px=80,
        memmap_threshold_mb=1400,
        crop=True,
    )
    result = run_pipeline(config)
    summary = _read_json(result.summary_json)
    report = _build_report(
        mode=mode,
        input_dir=input_dir,
        output_dir=output_dir,
        summary=summary,
        use_template=use_template,
        golden_csv=golden_csv,
        common_template_filenames=common_template_filenames,
        template_match_ratio=template_match_ratio,
        golden_filenames=golden_filenames,
        target_filenames=target_filenames,
        learned_excludes=learned_excludes,
        user_excludes=user_excludes,
        invert_x=invert_x,
        invert_y=invert_y,
        min_edge_score=float(min_edge_score),
        tolerance_full=float(tolerance_full),
    )
    report_path = output_dir / "practical_stitch_report.json"
    _write_json(report_path, report)

    print(f"stitched: {result.final_image}")
    print(f"preview:  {result.preview_image}")
    print(f"summary:  {result.summary_json}")
    print(f"report:   {report_path}")
    print(f"mode:     {mode}")
    print(f"quality:  {report['quality_status']}")
    if report["human_review_required"]:
        print("note:     human review is required before treating this output as final.")


def _default_coords(input_dir: Path) -> Path | None:
    candidate = input_dir / "virtual_coordinates.csv"
    return candidate if candidate.exists() else None


def _load_learning(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _learned_excluded_tiles(learning: dict[str, Any]) -> list[str]:
    excluded = []
    for item in learning.get("excluded_tiles", []):
        if isinstance(item, dict):
            filename = item.get("filename")
        else:
            filename = item
        if filename:
            excluded.append(Path(str(filename)).name)
    return excluded


def _discover_image_filenames(input_dir: Path) -> set[str]:
    if not input_dir.exists():
        raise FileNotFoundError(f"Input folder not found: {input_dir}")
    return {
        path.name
        for path in input_dir.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    }


def _load_placement_filenames(path: Path) -> set[str]:
    filenames: set[str] = set()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            filename = Path((row.get("filename") or "").strip()).name
            if filename:
                filenames.add(filename)
    return filenames


def _resolve_axis_flags(args: argparse.Namespace) -> tuple[bool, bool]:
    invert_x = args.axis_profile == "microscope-v1"
    invert_y = False
    if args.invert_x:
        invert_x = True
    if args.no_invert_x:
        invert_x = False
    if args.invert_y:
        invert_y = True
    if args.no_invert_y:
        invert_y = False
    return invert_x, invert_y


def _build_report(
    *,
    mode: str,
    input_dir: Path,
    output_dir: Path,
    summary: dict[str, Any],
    use_template: bool,
    golden_csv: Path,
    common_template_filenames: list[str],
    template_match_ratio: float,
    golden_filenames: set[str],
    target_filenames: set[str],
    learned_excludes: set[str],
    user_excludes: set[str],
    invert_x: bool,
    invert_y: bool,
    min_edge_score: float,
    tolerance_full: float,
) -> dict[str, Any]:
    tile_count = int(summary.get("tile_count") or 0)
    composed_count = int(summary.get("composed_tile_count") or 0)
    dropped_count = int(summary.get("dropped_tile_count") or 0)
    accepted_count = int(summary.get("accepted_pair_count") or 0)
    rejected_count = int(summary.get("rejected_pair_count") or 0)
    failed_count = int(summary.get("failed_pair_count") or 0)
    pair_count = accepted_count + rejected_count
    coverage_ratio = composed_count / tile_count if tile_count else 0.0
    accepted_ratio = accepted_count / pair_count if pair_count else 0.0
    progressive = summary.get("progressive") or {}
    fallback_tiles = progressive.get("fallback_tiles") or []

    if use_template:
        quality_status = "verified_learned_template"
        human_review_required = False
    elif coverage_ratio >= 0.90 and not dropped_count and not fallback_tiles and accepted_ratio >= 0.70:
        quality_status = "auto_candidate_needs_review"
        human_review_required = True
    elif coverage_ratio >= 0.40:
        quality_status = "partial_candidate_needs_manual_review"
        human_review_required = True
    else:
        quality_status = "insufficient_alignment"
        human_review_required = True

    return {
        "mode": mode,
        "quality_status": quality_status,
        "human_review_required": human_review_required,
        "input_dir": str(input_dir.resolve()),
        "output_dir": str(output_dir.resolve()),
        "final_image": summary.get("final_image"),
        "preview_image": summary.get("preview_image"),
        "placements_csv": summary.get("placements_csv"),
        "learned_template": {
            "used": use_template,
            "golden_placements": str(golden_csv.resolve()) if golden_csv.exists() else None,
            "common_anchor_count": len(common_template_filenames),
            "match_ratio": template_match_ratio,
            "common_anchor_filenames": common_template_filenames,
            "missing_from_input": sorted(golden_filenames - target_filenames),
            "extra_not_in_template": sorted(target_filenames - golden_filenames),
            "learned_excluded_tiles": sorted(learned_excludes),
        },
        "parameters": {
            "invert_x": invert_x,
            "invert_y": invert_y,
            "overlap_ratio": summary.get("overlap_ratio"),
            "work_scale": summary.get("work_scale"),
            "min_edge_score": min_edge_score,
            "cluster_tolerance_full_px": tolerance_full,
            "blend_mode": (summary.get("blend") or {}).get("blend_mode"),
            "placement_mode": summary.get("placement_mode"),
            "drop_unconfirmed_tiles": bool(progressive.get("drop_unconfirmed_tiles", True)),
        },
        "quality_metrics": {
            "tile_count": tile_count,
            "composed_tile_count": composed_count,
            "dropped_tile_count": dropped_count,
            "coverage_ratio": coverage_ratio,
            "accepted_pair_count": accepted_count,
            "rejected_pair_count": rejected_count,
            "accepted_pair_ratio": accepted_ratio,
            "failed_pair_count": failed_count,
            "fallback_tiles": fallback_tiles,
            "user_excluded_tiles": sorted(user_excludes),
        },
        "decision_rules": [
            "Learned template anchors are final-use only when enough filenames match the confirmed scan layout.",
            "Non-template output is a conservative candidate and must be reviewed before delivery.",
            "Unconfirmed tiles are dropped by default to avoid ghosting from forced stage placement.",
            "X is inverted by default for this microscope because positive X movement shifts the image left.",
        ],
    }


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

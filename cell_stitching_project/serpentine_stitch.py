from __future__ import annotations

import argparse
import csv
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .config import StitchingConfig
from .io_utils import SUPPORTED_EXTENSIONS, parse_xy_coordinates, save_json
from .main import StitchingResult, run_stitch_pipeline


@dataclass(slots=True)
class TraversalCandidate:
    name: str
    source: str
    description: str
    ordered_paths: list[Path]
    metrics: dict[str, Any]
    score: float


def _list_coordinate_paths(input_dir: str | Path) -> list[Path]:
    root = Path(input_dir)
    if not root.exists():
        raise FileNotFoundError(f"Input directory does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Input path is not a directory: {root}")

    paths = [
        path
        for path in sorted(root.iterdir(), key=lambda item: item.name)
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS and parse_xy_coordinates(path) is not None
    ]
    if not paths:
        raise ValueError(f"No coordinate tiles like 'x_y.jpg' were found in {root}")
    return paths


def _load_virtual_coordinate_order(input_dir: str | Path) -> list[Path] | None:
    root = Path(input_dir)
    csv_path = root / "virtual_coordinates.csv"
    if not csv_path.exists():
        return None

    ordered_paths: list[Path] = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            filename = (row.get("filename") or "").strip()
            if not filename:
                continue
            path = root / filename
            if path.exists() and path.is_file():
                ordered_paths.append(path)

    if not ordered_paths:
        return None
    return ordered_paths


def _build_serpentine_order(
    paths: Iterable[Path],
    primary_axis: str,
    major_direction: str,
    first_minor_direction: str,
) -> list[Path]:
    grouped: dict[float, list[tuple[float, Path]]] = {}
    for path in paths:
        coords = parse_xy_coordinates(path)
        if coords is None:
            continue
        x, y = coords
        major = y if primary_axis == "rows" else x
        minor = x if primary_axis == "rows" else y
        grouped.setdefault(major, []).append((minor, path))

    reverse_major = major_direction == "desc"
    reverse_minor = first_minor_direction == "desc"
    ordered_paths: list[Path] = []
    for index, major_key in enumerate(sorted(grouped.keys(), reverse=reverse_major)):
        reverse = reverse_minor if index % 2 == 0 else not reverse_minor
        row = sorted(grouped[major_key], key=lambda item: (item[0], item[1].name), reverse=reverse)
        ordered_paths.extend(path for _minor, path in row)
    return ordered_paths


def _dominant_step(values: list[float]) -> float | None:
    rounded = [round(abs(value), 6) for value in values if abs(value) > 1e-9]
    if not rounded:
        return None
    counts = Counter(rounded)
    return counts.most_common(1)[0][0]


def _is_close_multiple(value: float, step: float | None) -> bool:
    if step is None or step <= 0.0:
        return False
    ratio = abs(value) / step
    nearest = round(ratio)
    return nearest >= 1 and abs(ratio - nearest) <= 0.15


def evaluate_traversal_order(paths: Iterable[Path]) -> tuple[dict[str, Any], float]:
    ordered = list(paths)
    coords = [parse_xy_coordinates(path) for path in ordered]
    valid_coords = [coord for coord in coords if coord is not None]
    if len(valid_coords) < 2:
        return {
            "tile_count": len(ordered),
            "step_count": max(0, len(ordered) - 1),
            "error": "Need at least two coordinate tiles",
        }, float("-inf")

    steps: list[tuple[float, float]] = []
    for index in range(len(valid_coords) - 1):
        x0, y0 = valid_coords[index]
        x1, y1 = valid_coords[index + 1]
        steps.append((x1 - x0, y1 - y0))

    horizontal = [dx for dx, dy in steps if abs(dx) > 1e-9 and abs(dy) <= 1e-9]
    vertical = [dy for dx, dy in steps if abs(dy) > 1e-9 and abs(dx) <= 1e-9]
    dominant_x = _dominant_step(horizontal)
    dominant_y = _dominant_step(vertical)

    axis_aligned = 0
    exact_step_matches = 0
    jump_steps = 0
    diagonal_steps = 0
    stationary_steps = 0
    for dx, dy in steps:
        dx_nonzero = abs(dx) > 1e-9
        dy_nonzero = abs(dy) > 1e-9
        if dx_nonzero and dy_nonzero:
            diagonal_steps += 1
            continue
        if not dx_nonzero and not dy_nonzero:
            stationary_steps += 1
            continue

        axis_aligned += 1
        if dx_nonzero:
            if _is_close_multiple(dx, dominant_x):
                nearest = round(abs(dx) / float(dominant_x or 1.0))
                if nearest == 1:
                    exact_step_matches += 1
                elif nearest > 1:
                    jump_steps += 1
        else:
            if _is_close_multiple(dy, dominant_y):
                nearest = round(abs(dy) / float(dominant_y or 1.0))
                if nearest == 1:
                    exact_step_matches += 1
                elif nearest > 1:
                    jump_steps += 1

    step_count = len(steps)
    exact_ratio = exact_step_matches / float(max(1, step_count))
    axis_ratio = axis_aligned / float(max(1, step_count))
    diagonal_ratio = diagonal_steps / float(max(1, step_count))
    jump_ratio = jump_steps / float(max(1, step_count))
    stationary_ratio = stationary_steps / float(max(1, step_count))
    score = (3.0 * exact_ratio) + axis_ratio - (2.5 * diagonal_ratio) - jump_ratio - stationary_ratio

    metrics = {
        "tile_count": len(ordered),
        "step_count": step_count,
        "dominant_step_x": dominant_x,
        "dominant_step_y": dominant_y,
        "axis_aligned_steps": axis_aligned,
        "exact_step_matches": exact_step_matches,
        "jump_steps": jump_steps,
        "diagonal_steps": diagonal_steps,
        "stationary_steps": stationary_steps,
        "axis_aligned_ratio": round(axis_ratio, 6),
        "exact_step_ratio": round(exact_ratio, 6),
        "jump_ratio": round(jump_ratio, 6),
        "diagonal_ratio": round(diagonal_ratio, 6),
        "stationary_ratio": round(stationary_ratio, 6),
    }
    return metrics, score


def discover_traversal_candidates(input_dir: str | Path) -> list[TraversalCandidate]:
    base_paths = _list_coordinate_paths(input_dir)
    candidates: list[TraversalCandidate] = []

    csv_paths = _load_virtual_coordinate_order(input_dir)
    if csv_paths is not None:
        metrics, score = evaluate_traversal_order(csv_paths)
        score += 0.05
        candidates.append(
            TraversalCandidate(
                name="virtual_csv_capture_order",
                source="virtual_coordinates.csv",
                description="Use the capture order recorded in virtual_coordinates.csv",
                ordered_paths=csv_paths,
                metrics=metrics,
                score=score,
            )
        )

    for primary_axis in ("rows", "columns"):
        for major_direction in ("desc", "asc"):
            for first_minor_direction in ("desc", "asc"):
                ordered_paths = _build_serpentine_order(
                    base_paths,
                    primary_axis=primary_axis,
                    major_direction=major_direction,
                    first_minor_direction=first_minor_direction,
                )
                metrics, score = evaluate_traversal_order(ordered_paths)
                candidates.append(
                    TraversalCandidate(
                        name=f"{primary_axis}_{major_direction}_{first_minor_direction}",
                        source="inferred_serpentine",
                        description=(
                            f"{primary_axis} serpentine, major={major_direction}, "
                            f"first sweep={first_minor_direction}"
                        ),
                        ordered_paths=ordered_paths,
                        metrics=metrics,
                        score=score,
                    )
                )

    candidates.sort(key=lambda item: (item.score, item.metrics.get("exact_step_ratio", 0.0)), reverse=True)
    return candidates


def select_best_traversal_candidate(candidates: Iterable[TraversalCandidate]) -> TraversalCandidate:
    ordered = list(candidates)
    if not ordered:
        raise ValueError("No traversal candidates are available")
    return max(ordered, key=lambda item: (item.score, item.metrics.get("exact_step_ratio", 0.0)))


def build_strategy_report(candidates: Iterable[TraversalCandidate], selected: TraversalCandidate) -> dict[str, Any]:
    return {
        "selected_strategy": {
            "name": selected.name,
            "source": selected.source,
            "description": selected.description,
            "score": round(selected.score, 6),
            "metrics": selected.metrics,
            "ordered_paths": [str(path) for path in selected.ordered_paths],
        },
        "candidates": [
            {
                "name": candidate.name,
                "source": candidate.source,
                "description": candidate.description,
                "score": round(candidate.score, 6),
                "metrics": candidate.metrics,
            }
            for candidate in candidates
        ],
    }


def run_serpentine_stitch(
    input_dir: str | Path,
    output_dir: str | Path,
    strategy: str = "auto",
    output_format: str = "png",
    performance_profile: str = "balanced",
    compute_device: str = "auto",
    max_images: int | None = None,
    disable_yolo_guidance: bool = False,
    disable_post_stitch_detection: bool = False,
    evaluate_only: bool = False,
) -> dict[str, Any]:
    candidates = discover_traversal_candidates(input_dir)
    if strategy == "auto":
        selected = select_best_traversal_candidate(candidates)
    else:
        match = next((candidate for candidate in candidates if candidate.name == strategy), None)
        if match is None:
            available = ", ".join(candidate.name for candidate in candidates)
            raise ValueError(f"Unknown strategy '{strategy}'. Available: {available}")
        selected = match

    report = build_strategy_report(candidates, selected)
    strategy_path = Path(output_dir) / "serpentine_strategy.json"
    strategy_path.parent.mkdir(parents=True, exist_ok=True)
    save_json(strategy_path, report)
    report["strategy_report_path"] = str(strategy_path.resolve())

    if evaluate_only:
        return report

    config = StitchingConfig(
        input_dir=input_dir,
        output_dir=output_dir,
        input_paths=[str(path) for path in selected.ordered_paths[:max_images] if path.exists()],
        input_order="natural",
        coordinate_priority="row-major",
        output_format=output_format,
        max_images=max_images,
        use_yolo_guidance=not disable_yolo_guidance,
        post_stitch_detection_enabled=not disable_post_stitch_detection,
        performance_profile=performance_profile,
        compute_device=compute_device,
    )
    result = run_stitch_pipeline(config)
    report["stitch_result"] = {
        "success": result.success,
        "message": result.message,
        "stitched_image_path": result.stitched_image_path,
        "overlay_preview_path": result.overlay_preview_path,
        "shifts_json_path": result.shifts_json_path,
        "shifts_csv_path": result.shifts_csv_path,
        "post_detection": result.post_detection,
        "warnings": result.warnings,
        "runtime": result.runtime,
    }
    save_json(strategy_path, report)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate serpentine coordinate orders and run the best stitching strategy")
    parser.add_argument("--input_dir", required=True, help="Directory containing coordinate tiles like x_y.jpg")
    parser.add_argument("--output_dir", required=True, help="Directory where stitched outputs will be written")
    parser.add_argument("--strategy", default="auto", help="Traversal strategy name, or 'auto' to choose the best candidate")
    parser.add_argument("--output_format", choices=("png", "tif", "tiff"), default="png")
    parser.add_argument("--performance_profile", choices=("quality", "balanced", "resource"), default="balanced")
    parser.add_argument("--compute_device", choices=("auto", "cuda", "cpu"), default="auto")
    parser.add_argument("--max_images", type=int, default=None, help="Optional image limit for smoke testing")
    parser.add_argument("--disable_yolo_guidance", action="store_true", help="Disable YOLO-guided ROI weighting during alignment")
    parser.add_argument("--disable_post_stitch_detection", action="store_true", help="Disable post-stitch object detection")
    parser.add_argument("--evaluate_only", action="store_true", help="Only score traversal strategies without running the stitcher")
    return parser


def _print_summary(report: dict[str, Any]) -> None:
    selected = report["selected_strategy"]
    print(f"selected_strategy={selected['name']}")
    print(f"selected_source={selected['source']}")
    print(f"selected_score={selected['score']}")
    print(f"strategy_report_path={report['strategy_report_path']}")
    stitch_result = report.get("stitch_result")
    if stitch_result:
        print(f"stitch_success={stitch_result['success']}")
        print(f"stitched_image_path={stitch_result['stitched_image_path']}")
        print(f"overlay_preview_path={stitch_result['overlay_preview_path']}")
        if stitch_result["post_detection"]:
            print(f"post_detection_enabled={stitch_result['post_detection'].get('enabled')}")
            print(f"post_detection_success={stitch_result['post_detection'].get('success')}")


def main() -> int:
    args = build_parser().parse_args()
    report = run_serpentine_stitch(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        strategy=args.strategy,
        output_format=args.output_format,
        performance_profile=args.performance_profile,
        compute_device=args.compute_device,
        max_images=args.max_images,
        disable_yolo_guidance=args.disable_yolo_guidance,
        disable_post_stitch_detection=args.disable_post_stitch_detection,
        evaluate_only=args.evaluate_only,
    )
    _print_summary(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

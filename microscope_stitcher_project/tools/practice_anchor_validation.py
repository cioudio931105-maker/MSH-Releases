from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, median
from typing import Any


@dataclass(frozen=True)
class Point:
    x: float
    y: float


@dataclass(frozen=True)
class AnchorCandidate:
    target: str
    anchor: str
    method: str
    score: float
    x: float
    y: float
    edge_error_px: float


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Practice multi-anchor tile validation against a confirmed golden mosaic. "
            "This does not change images; it searches thresholds that make anchor "
            "consensus reproduce the accepted placements."
        )
    )
    parser.add_argument("--placements", required=True, help="Debug placements.csv from a stitch run.")
    parser.add_argument("--pair-edges", required=True, help="Debug pair_edges.json from the same stitch run.")
    parser.add_argument("--golden", required=True, help="Confirmed golden placements CSV.")
    parser.add_argument("--output-dir", required=True, help="Folder for practice reports.")
    parser.add_argument("--ok-error-px", type=float, default=25.0, help="Max full-resolution error counted as OK.")
    parser.add_argument("--score-grid", default="0.10,0.20,0.30,0.40,0.55", help="Comma-separated score thresholds.")
    parser.add_argument("--tolerance-grid", default="10,25,35,50,65,90,110,160", help="Comma-separated full-resolution cluster tolerances.")
    parser.add_argument("--anchor-grid", default="2,3,4", help="Comma-separated distinct anchor requirements.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    filenames_by_internal_index, work_to_full_scale = _load_index_filenames_and_scale(Path(args.placements))
    golden = _load_points(Path(args.golden))
    pair_edges = _load_pair_edges(Path(args.pair_edges))
    edge_rows, candidates_by_target = _build_candidates(
        pair_edges,
        filenames_by_internal_index,
        golden,
        work_to_full_scale,
        float(args.ok_error_px),
    )

    score_grid = _parse_float_grid(args.score_grid)
    tolerance_grid = _parse_float_grid(args.tolerance_grid)
    anchor_grid = _parse_int_grid(args.anchor_grid)
    sweep_rows = []
    detail_by_key: dict[str, list[dict[str, Any]]] = {}

    for min_score in score_grid:
        for tolerance_px in tolerance_grid:
            for min_anchors in anchor_grid:
                tile_rows = _evaluate_tiles(
                    candidates_by_target=candidates_by_target,
                    golden=golden,
                    min_score=min_score,
                    tolerance_px=tolerance_px,
                    min_anchors=min_anchors,
                    ok_error_px=float(args.ok_error_px),
                )
                summary = _summarize_tile_rows(tile_rows)
                key = _practice_key(min_score, tolerance_px, min_anchors)
                detail_by_key[key] = tile_rows
                sweep_rows.append(
                    {
                        "key": key,
                        "min_score": min_score,
                        "tolerance_px": tolerance_px,
                        "min_anchors": min_anchors,
                        **summary,
                    }
                )

    best = _pick_best(sweep_rows)
    method_stats = _method_stats(edge_rows, float(args.ok_error_px))
    best_tile_rows = detail_by_key[best["key"]]
    report = {
        "inputs": {
            "placements": str(Path(args.placements).resolve()),
            "pair_edges": str(Path(args.pair_edges).resolve()),
            "golden": str(Path(args.golden).resolve()),
            "work_to_full_scale": work_to_full_scale,
        },
        "ok_error_px": float(args.ok_error_px),
        "best_parameters": {
            "min_score": best["min_score"],
            "tolerance_px": best["tolerance_px"],
            "min_anchors": best["min_anchors"],
        },
        "best_summary": {key: value for key, value in best.items() if key != "key"},
        "method_stats": method_stats,
        "recommendations": _recommendations(best, method_stats),
    }

    _write_csv(output_dir / "anchor_practice_sweep.csv", sweep_rows)
    _write_csv(output_dir / "anchor_practice_best_tiles.csv", best_tile_rows)
    _write_csv(output_dir / "anchor_practice_edge_errors.csv", edge_rows)
    _write_json(output_dir / "anchor_practice_report.json", report)

    print(json.dumps(report["best_parameters"], ensure_ascii=False, indent=2))
    print(json.dumps(report["best_summary"], ensure_ascii=False, indent=2))
    print(f"report: {output_dir / 'anchor_practice_report.json'}")


def _load_index_filenames_and_scale(path: Path) -> tuple[dict[int, str], float]:
    filenames: dict[int, str] = {}
    scale_samples: list[float] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for internal_idx, row in enumerate(reader):
            filename = Path((row.get("filename") or "").strip()).name
            if filename:
                filenames[internal_idx] = filename

            work_x = _optional_float(row.get("aligned_work_x"))
            full_x = _optional_float(row.get("aligned_full_x"))
            work_y = _optional_float(row.get("aligned_work_y"))
            full_y = _optional_float(row.get("aligned_full_y"))
            if work_x is not None and full_x is not None and abs(work_x) > 1e-6:
                scale_samples.append(full_x / work_x)
            if work_y is not None and full_y is not None and abs(work_y) > 1e-6:
                scale_samples.append(full_y / work_y)

    work_to_full_scale = float(median(scale_samples)) if scale_samples else 1.0
    return filenames, work_to_full_scale


def _load_points(path: Path) -> dict[str, Point]:
    points: dict[str, Point] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            filename = Path((row.get("filename") or "").strip()).name
            if not filename:
                continue
            points[filename] = Point(float(row["aligned_full_x"]), float(row["aligned_full_y"]))
    return points


def _load_pair_edges(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    return list(data.get("pairs", []))


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _build_candidates(
    pair_edges: list[dict[str, Any]],
    filenames_by_internal_index: dict[int, str],
    golden: dict[str, Point],
    work_to_full_scale: float,
    ok_error_px: float,
) -> tuple[list[dict[str, Any]], dict[str, list[AnchorCandidate]]]:
    edge_rows = []
    candidates_by_target: dict[str, list[AnchorCandidate]] = {name: [] for name in golden}
    for edge in pair_edges:
        ref = filenames_by_internal_index.get(int(edge["ref"]))
        mov = filenames_by_internal_index.get(int(edge["mov"]))
        if ref not in golden or mov not in golden:
            continue
        score = float(edge.get("score", -1.0))
        method = str(edge.get("method", "unknown"))
        success = bool(edge.get("success", False))
        dx = float(edge["dx"]) * work_to_full_scale
        dy = float(edge["dy"]) * work_to_full_scale
        golden_dx = golden[mov].x - golden[ref].x
        golden_dy = golden[mov].y - golden[ref].y
        edge_error_px = _distance(dx, dy, golden_dx, golden_dy)
        detail = edge.get("details") or {}
        edge_rows.append(
            {
                "ref": ref,
                "mov": mov,
                "method": method,
                "score": score,
                "success": success,
                "neighbor_kind": detail.get("neighbor_kind"),
                "matches": edge.get("matches", 0),
                "cluster_matches": detail.get("cluster_matches", ""),
                "candidate_matches": detail.get("candidate_matches", ""),
                "edge_error_px": edge_error_px,
                "ok": edge_error_px <= ok_error_px,
            }
        )
        if not success:
            continue
        candidates_by_target[mov].append(
            AnchorCandidate(
                target=mov,
                anchor=ref,
                method=method,
                score=score,
                x=golden[ref].x + dx,
                y=golden[ref].y + dy,
                edge_error_px=edge_error_px,
            )
        )
        candidates_by_target[ref].append(
            AnchorCandidate(
                target=ref,
                anchor=mov,
                method=method,
                score=score,
                x=golden[mov].x - dx,
                y=golden[mov].y - dy,
                edge_error_px=edge_error_px,
            )
        )
    return edge_rows, candidates_by_target


def _evaluate_tiles(
    *,
    candidates_by_target: dict[str, list[AnchorCandidate]],
    golden: dict[str, Point],
    min_score: float,
    tolerance_px: float,
    min_anchors: int,
    ok_error_px: float,
) -> list[dict[str, Any]]:
    rows = []
    for target, all_candidates in sorted(candidates_by_target.items()):
        candidates = [candidate for candidate in all_candidates if candidate.score >= min_score]
        cluster = _best_cluster(candidates, tolerance_px)
        if len({candidate.anchor for candidate in cluster}) < min_anchors:
            rows.append(
                {
                    "filename": target,
                    "status": "rejected",
                    "candidate_count": len(candidates),
                    "anchor_count": len({candidate.anchor for candidate in cluster}),
                    "support": _support(cluster),
                    "error_px": "",
                    "ok": False,
                    "x": "",
                    "y": "",
                    "anchors": ",".join(candidate.anchor for candidate in cluster),
                    "methods": ",".join(candidate.method for candidate in cluster),
                }
            )
            continue
        x, y = _weighted_average(cluster)
        error_px = _distance(x, y, golden[target].x, golden[target].y)
        rows.append(
            {
                "filename": target,
                "status": "accepted",
                "candidate_count": len(candidates),
                "anchor_count": len({candidate.anchor for candidate in cluster}),
                "support": _support(cluster),
                "error_px": error_px,
                "ok": error_px <= ok_error_px,
                "x": x,
                "y": y,
                "anchors": ",".join(candidate.anchor for candidate in cluster),
                "methods": ",".join(candidate.method for candidate in cluster),
            }
        )
    return rows


def _best_cluster(candidates: list[AnchorCandidate], tolerance_px: float) -> list[AnchorCandidate]:
    best: list[AnchorCandidate] = []
    best_support = -1.0
    best_spread = float("inf")
    for center in candidates:
        cluster = [
            candidate
            for candidate in candidates
            if _distance(candidate.x, candidate.y, center.x, center.y) <= tolerance_px
        ]
        support = _support(cluster)
        spread = _spread(cluster)
        if (len({item.anchor for item in cluster}), support, -spread) > (
            len({item.anchor for item in best}),
            best_support,
            -best_spread,
        ):
            best = cluster
            best_support = support
            best_spread = spread
    return best


def _weighted_average(candidates: list[AnchorCandidate]) -> tuple[float, float]:
    weights = [max(0.01, candidate.score) for candidate in candidates]
    total = sum(weights)
    x = sum(candidate.x * weight for candidate, weight in zip(candidates, weights)) / total
    y = sum(candidate.y * weight for candidate, weight in zip(candidates, weights)) / total
    return x, y


def _support(candidates: list[AnchorCandidate]) -> float:
    return float(sum(max(0.01, candidate.score) for candidate in candidates))


def _spread(candidates: list[AnchorCandidate]) -> float:
    if len(candidates) <= 1:
        return 0.0
    return max(_distance(a.x, a.y, b.x, b.y) for a in candidates for b in candidates)


def _summarize_tile_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    accepted = [row for row in rows if row["status"] == "accepted"]
    ok = [row for row in accepted if row["ok"]]
    errors = [float(row["error_px"]) for row in accepted if row["error_px"] != ""]
    return {
        "tile_count": len(rows),
        "accepted_count": len(accepted),
        "rejected_count": len(rows) - len(accepted),
        "ok_count": len(ok),
        "bad_count": len(accepted) - len(ok),
        "ok_rate_of_all": len(ok) / len(rows) if rows else 0.0,
        "precision": len(ok) / len(accepted) if accepted else 0.0,
        "mean_error_px": mean(errors) if errors else "",
        "median_error_px": median(errors) if errors else "",
        "max_error_px": max(errors) if errors else "",
    }


def _pick_best(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return max(
        rows,
        key=lambda row: (
            float(row["precision"]),
            int(row["ok_count"]),
            -int(row["bad_count"]),
            -float(row["mean_error_px"] if row["mean_error_px"] != "" else 1e9),
            -float(row["tolerance_px"]),
        ),
    )


def _method_stats(rows: list[dict[str, Any]], ok_error_px: float) -> list[dict[str, Any]]:
    by_method: dict[str, list[float]] = {}
    for row in rows:
        if not row["success"]:
            continue
        by_method.setdefault(row["method"], []).append(float(row["edge_error_px"]))
    stats = []
    for method, errors in sorted(by_method.items()):
        ok = [error for error in errors if error <= ok_error_px]
        stats.append(
            {
                "method": method,
                "edge_count": len(errors),
                "ok_count": len(ok),
                "precision": len(ok) / len(errors) if errors else 0.0,
                "median_error_px": median(errors),
                "max_error_px": max(errors),
            }
        )
    return stats


def _recommendations(best: dict[str, Any], method_stats: list[dict[str, Any]]) -> list[str]:
    recommendations = [
        f"Use at least {best['min_anchors']} distinct anchors before accepting a tile.",
        f"Use approximately {best['tolerance_px']} px full-resolution anchor cluster tolerance for this learned dataset.",
        f"Use min edge score around {best['min_score']} for candidate generation, then reject if anchors do not converge.",
        "Single platelet matches are useful candidates, but should not be final unless confirmed by another independent anchor.",
    ]
    platelet_stats = [row for row in method_stats if row["method"] == "detection_feature_landmark"]
    if platelet_stats:
        stat = platelet_stats[0]
        recommendations.append(
            f"Detection landmark edges had precision {stat['precision']:.2f}; keep them as high-value anchors but require multi-anchor agreement."
        )
    return recommendations


def _parse_float_grid(raw: str) -> list[float]:
    return [float(item.strip()) for item in raw.split(",") if item.strip()]


def _parse_int_grid(raw: str) -> list[int]:
    return [int(item.strip()) for item in raw.split(",") if item.strip()]


def _practice_key(min_score: float, tolerance_px: float, min_anchors: int) -> str:
    return f"score{min_score:g}_tol{tolerance_px:g}_anchors{min_anchors}"


def _distance(ax: float, ay: float, bx: float, by: float) -> float:
    return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()

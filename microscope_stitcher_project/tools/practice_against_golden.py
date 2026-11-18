from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from statistics import median

import cv2
import numpy as np


@dataclass(frozen=True)
class GoldenTile:
    filename: str
    stage_x: float
    stage_y: float
    x: float
    y: float


@dataclass(frozen=True)
class Candidate:
    target: str
    anchor: str
    score: float
    rel_dx: float
    rel_dy: float
    global_x: float
    global_y: float
    overlap_w: float
    overlap_h: float


def load_golden(path: Path) -> list[GoldenTile]:
    tiles: list[GoldenTile] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            tiles.append(
                GoldenTile(
                    filename=Path(row["filename"]).name,
                    stage_x=float(row["stage_x"]),
                    stage_y=float(row["stage_y"]),
                    x=float(row["aligned_full_x"]),
                    y=float(row["aligned_full_y"]),
                )
            )
    return tiles


def build_feature(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    sx = cv2.Sobel(clahe, cv2.CV_32F, 1, 0, ksize=3)
    sy = cv2.Sobel(clahe, cv2.CV_32F, 0, 1, ksize=3)
    edge = cv2.magnitude(sx, sy)
    edge = cv2.normalize(edge, None, 0, 1, cv2.NORM_MINMAX)

    b, g, r = cv2.split(image)
    bi = b.astype(np.int16)
    gi = g.astype(np.int16)
    ri = r.astype(np.int16)
    platelet_like = (
        ((bi - gi) > 18)
        & ((ri - gi) > 8)
        & ((bi + ri) > 150)
        & (g < 190)
    ).astype(np.uint8) * 255
    platelet_like = cv2.morphologyEx(platelet_like, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    platelet_like = cv2.GaussianBlur(platelet_like, (5, 5), 0).astype(np.float32) / 255.0

    contrast = clahe.astype(np.float32) / 255.0
    return (edge * 0.52 + contrast * 0.28 + platelet_like * 0.20).astype(np.float32)


def load_features(input_dir: Path, tiles: list[GoldenTile], scale: float) -> dict[str, np.ndarray]:
    features: dict[str, np.ndarray] = {}
    for tile in tiles:
        image = cv2.imread(str(input_dir / tile.filename), cv2.IMREAD_COLOR)
        if image is None:
            raise FileNotFoundError(input_dir / tile.filename)
        feature = build_feature(image)
        features[tile.filename] = cv2.resize(feature, (0, 0), fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    return features


def estimate_stage_model(tiles: list[GoldenTile]) -> tuple[float, float]:
    x_slopes: list[float] = []
    y_slopes: list[float] = []
    for a in tiles:
        for b in tiles:
            if a.filename >= b.filename:
                continue
            dsx = b.stage_x - a.stage_x
            dsy = b.stage_y - a.stage_y
            if abs(dsy) < 1e-6 and 0.0 < abs(dsx) <= 16.0:
                x_slopes.append((b.x - a.x) / dsx)
            if abs(dsx) < 1e-6 and 0.0 < abs(dsy) <= 8.0:
                y_slopes.append((b.y - a.y) / dsy)
    x_ppu = median(x_slopes) if x_slopes else 150.0
    y_ppu = median(y_slopes) if y_slopes else 60.0
    return float(x_ppu), float(y_ppu)


def stage_distance(a: GoldenTile, b: GoldenTile) -> float:
    return abs(a.stage_x - b.stage_x) + abs(a.stage_y - b.stage_y) * 1.5


def choose_anchors(target: GoldenTile, anchors: list[GoldenTile], max_anchors: int) -> list[GoldenTile]:
    nearby = [
        anchor for anchor in anchors
        if anchor.filename != target.filename
        and abs(anchor.stage_x - target.stage_x) <= 16.0
        and abs(anchor.stage_y - target.stage_y) <= 8.0
    ]
    if not nearby:
        nearby = [anchor for anchor in anchors if anchor.filename != target.filename]
    return sorted(nearby, key=lambda anchor: stage_distance(target, anchor))[:max_anchors]


def score_at(anchor: np.ndarray, target: np.ndarray, dx: float, dy: float, scale: float) -> tuple[float, float, float]:
    dxs = int(round(dx * scale))
    dys = int(round(dy * scale))
    ha, wa = anchor.shape
    ht, wt = target.shape
    ax0 = max(0, dxs)
    ay0 = max(0, dys)
    tx0 = max(0, -dxs)
    ty0 = max(0, -dys)
    ow = min(wa - ax0, wt - tx0)
    oh = min(ha - ay0, ht - ty0)
    if ow < 40 or oh < 40:
        return -999.0, ow / scale, oh / scale

    a = anchor[ay0:ay0 + oh, ax0:ax0 + ow]
    t = target[ty0:ty0 + oh, tx0:tx0 + ow]
    av = a - float(a.mean())
    tv = t - float(t.mean())
    denom = float(np.sqrt((av * av).sum()) * np.sqrt((tv * tv).sum()) + 1e-6)
    return float((av * tv).sum() / denom), ow / scale, oh / scale


def search_pair(
    target: GoldenTile,
    anchor: GoldenTile,
    features: dict[str, np.ndarray],
    anchor_position: tuple[float, float],
    x_ppu: float,
    y_ppu: float,
    scale: float,
    step: int,
) -> list[Candidate]:
    expected_dx = (target.stage_x - anchor.stage_x) * x_ppu
    expected_dy = (target.stage_y - anchor.stage_y) * y_ppu

    # Broad enough for backlash and this microscope's non-linear top-row behavior,
    # but still constrained by stage direction so repeated red cells do not dominate.
    radius_x = max(700, min(1500, int(abs(expected_dx) * 0.45 + 550)))
    radius_y = max(550, min(1100, int(abs(expected_dy) * 0.65 + 500)))
    min_ow = 240
    min_oh = 180

    anchor_feature = features[anchor.filename]
    target_feature = features[target.filename]
    coarse: list[tuple[float, int, int, float, float]] = []
    for dy in range(int(expected_dy - radius_y), int(expected_dy + radius_y) + 1, step):
        for dx in range(int(expected_dx - radius_x), int(expected_dx + radius_x) + 1, step):
            score, ow, oh = score_at(anchor_feature, target_feature, dx, dy, scale)
            if ow >= min_ow and oh >= min_oh:
                coarse.append((score, dx, dy, ow, oh))

    refined: list[tuple[float, int, int, float, float]] = []
    for _, dx0, dy0, _, _ in sorted(coarse, reverse=True)[:6]:
        for dy in range(dy0 - 36, dy0 + 37, 2):
            for dx in range(dx0 - 36, dx0 + 37, 2):
                score, ow, oh = score_at(anchor_feature, target_feature, dx, dy, scale)
                if ow >= min_ow and oh >= min_oh:
                    refined.append((score, dx, dy, ow, oh))

    unique: list[tuple[float, int, int, float, float]] = []
    seen: set[tuple[int, int]] = set()
    for item in sorted(refined, reverse=True):
        key = (item[1] // 4, item[2] // 4)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
        if len(unique) >= 4:
            break

    ax, ay = anchor_position
    return [
        Candidate(
            target=target.filename,
            anchor=anchor.filename,
            score=score,
            rel_dx=dx,
            rel_dy=dy,
            global_x=ax + dx,
            global_y=ay + dy,
            overlap_w=ow,
            overlap_h=oh,
        )
        for score, dx, dy, ow, oh in unique
    ]


def robust_position(candidates: list[Candidate], tolerance_px: float, min_score: float):
    usable = [candidate for candidate in candidates if candidate.score >= min_score]
    if not usable:
        return None, []

    best_cluster: list[Candidate] = []
    best_anchor_count = -1
    best_support = -1.0
    for center in usable:
        cluster = [
            candidate for candidate in usable
            if ((candidate.global_x - center.global_x) ** 2 + (candidate.global_y - center.global_y) ** 2) ** 0.5 <= tolerance_px
        ]
        anchor_count = len({candidate.anchor for candidate in cluster})
        support = sum(max(0.01, candidate.score) for candidate in cluster)
        if (anchor_count, support) > (best_anchor_count, best_support):
            best_cluster = cluster
            best_anchor_count = anchor_count
            best_support = support

    weights = np.array([max(0.01, candidate.score) for candidate in best_cluster], dtype=np.float64)
    xs = np.array([candidate.global_x for candidate in best_cluster], dtype=np.float64)
    ys = np.array([candidate.global_y for candidate in best_cluster], dtype=np.float64)
    return (float(np.average(xs, weights=weights)), float(np.average(ys, weights=weights))), best_cluster


def practice_leave_one_out(args, tiles, by_name, features, x_ppu, y_ppu):
    rows = []
    for target in tiles:
        anchors = choose_anchors(target, [tile for tile in tiles if tile.filename != target.filename], args.max_anchors)
        candidates: list[Candidate] = []
        for anchor in anchors:
            candidates.extend(
                search_pair(
                    target,
                    anchor,
                    features,
                    (anchor.x, anchor.y),
                    x_ppu,
                    y_ppu,
                    args.scale,
                    args.step,
                )
            )
        position, cluster = robust_position(candidates, args.cluster_tolerance, args.min_score)
        rows.append(result_row("leave_one_out", target, position, cluster, len(candidates)))
    return rows


def practice_progressive(args, tiles, features, x_ppu, y_ppu):
    rows = []
    placed: dict[str, tuple[float, float]] = {}
    for idx, target in enumerate(tiles):
        if idx == 0:
            placed[target.filename] = (target.x, target.y)
            rows.append(result_row("progressive", target, (target.x, target.y), [], 0, note="seed"))
            continue

        anchor_tiles = [tile for tile in tiles[:idx] if tile.filename in placed]
        anchors = choose_anchors(target, anchor_tiles, args.max_anchors)
        candidates: list[Candidate] = []
        for anchor in anchors:
            candidates.extend(
                search_pair(
                    target,
                    anchor,
                    features,
                    placed[anchor.filename],
                    x_ppu,
                    y_ppu,
                    args.scale,
                    args.step,
                )
            )
        position, cluster = robust_position(candidates, args.cluster_tolerance, args.min_score)
        if position is not None:
            placed[target.filename] = position
        rows.append(result_row("progressive", target, position, cluster, len(candidates)))
    return rows


def result_row(scenario: str, target: GoldenTile, position, cluster: list[Candidate], candidate_count: int, note: str = ""):
    if position is None:
        return {
            "scenario": scenario,
            "filename": target.filename,
            "status": "failed",
            "predicted_x": "",
            "predicted_y": "",
            "golden_x": target.x,
            "golden_y": target.y,
            "error_px": "",
            "cluster_size": len(cluster),
            "distinct_anchor_count": len({candidate.anchor for candidate in cluster}),
            "candidate_count": candidate_count,
            "anchors": "",
            "note": note,
        }
    dx = float(position[0] - target.x)
    dy = float(position[1] - target.y)
    error = (dx * dx + dy * dy) ** 0.5
    anchors = ";".join(f"{candidate.anchor}:{candidate.score:.3f}" for candidate in cluster)
    distinct_anchor_count = len({candidate.anchor for candidate in cluster})
    return {
        "scenario": scenario,
        "filename": target.filename,
        "status": "ok",
        "predicted_x": float(position[0]),
        "predicted_y": float(position[1]),
        "golden_x": target.x,
        "golden_y": target.y,
        "error_px": error,
        "cluster_size": len(cluster),
        "distinct_anchor_count": distinct_anchor_count,
        "candidate_count": candidate_count,
        "anchors": anchors,
        "note": note,
    }


def summarize(rows: list[dict[str, object]]) -> dict[str, object]:
    ok_rows = [row for row in rows if row["status"] == "ok" and row["error_px"] != ""]
    errors = [float(row["error_px"]) for row in ok_rows]
    formal_ok = [row for row in ok_rows if int(row["distinct_anchor_count"]) >= 2 and float(row["error_px"]) <= 25.0]
    return {
        "row_count": len(rows),
        "ok_count": len(ok_rows),
        "formal_ok_count": len(formal_ok),
        "failed_count": len(rows) - len(ok_rows),
        "mean_error_px": float(sum(errors) / len(errors)) if errors else None,
        "max_error_px": float(max(errors)) if errors else None,
        "over_25px": [
            {"scenario": row["scenario"], "filename": row["filename"], "error_px": row["error_px"], "cluster_size": row["cluster_size"]}
            for row in ok_rows
            if float(row["error_px"]) > 25.0
        ],
        "single_anchor_only": [
            {"scenario": row["scenario"], "filename": row["filename"], "error_px": row["error_px"], "anchors": row["anchors"]}
            for row in ok_rows
            if int(row["distinct_anchor_count"]) < 2
        ],
    }


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Repeatedly practice tile placement against the confirmed golden mosaic.")
    parser.add_argument("--input", required=True, help="Input session folder containing tile images.")
    parser.add_argument(
        "--golden",
        default=str(Path(__file__).resolve().parents[1] / "reference" / "session_20260521_181641_759929_golden_placements.csv"),
        help="Golden placements CSV.",
    )
    parser.add_argument("--output", required=True, help="Output folder for practice reports.")
    parser.add_argument("--scale", type=float, default=0.20, help="Feature scale used for repeated practice.")
    parser.add_argument("--step", type=int, default=12, help="Full-resolution coarse search step.")
    parser.add_argument("--min-score", type=float, default=0.55, help="Minimum candidate score used for formal clusters.")
    parser.add_argument("--cluster-tolerance", type=float, default=35.0, help="Full-resolution px tolerance for multi-anchor consensus.")
    parser.add_argument("--max-anchors", type=int, default=6, help="Maximum neighboring anchors per target.")
    args = parser.parse_args()

    input_dir = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    tiles = load_golden(Path(args.golden))
    by_name = {tile.filename: tile for tile in tiles}
    features = load_features(input_dir, tiles, args.scale)
    x_ppu, y_ppu = estimate_stage_model(tiles)

    rows = []
    rows.extend(practice_leave_one_out(args, tiles, by_name, features, x_ppu, y_ppu))
    rows.extend(practice_progressive(args, tiles, features, x_ppu, y_ppu))

    write_csv(output_dir / "practice_results.csv", rows)
    summary = {
        "input_dir": str(input_dir),
        "golden": str(Path(args.golden)),
        "stage_model": {"x_pixels_per_unit": x_ppu, "y_pixels_per_unit": y_ppu},
        "settings": {
            "scale": args.scale,
            "step": args.step,
            "min_score": args.min_score,
            "cluster_tolerance": args.cluster_tolerance,
            "max_anchors": args.max_anchors,
        },
        "summary": summarize(rows),
    }
    (output_dir / "practice_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

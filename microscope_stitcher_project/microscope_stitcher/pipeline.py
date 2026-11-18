from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
from tqdm import tqdm

from .blending import compose_mosaic
from .config import StitchConfig
from .cuda_utils import resolve_cuda
from .debug import prepare_debug_dirs, write_json, write_placements_csv
from .detection_features import load_detection_features
from .geometry import build_neighbors, estimate_pixels_per_unit, initial_positions
from .io_utils import discover_tiles, read_image_bgr
from .pose_graph import solve_positions
from .preprocess import preprocess_for_alignment
from .progressive import solve_progressive_positions
from .registration import estimate_pair_transform
from .types import StitchResult, WorkTile


def run_pipeline(config: StitchConfig) -> StitchResult:
    config.validate()
    config.output_dir.mkdir(parents=True, exist_ok=True)
    debug_dir, pair_debug_dir = prepare_debug_dirs(config.output_dir, config.debug)
    cuda_enabled, cuda_reason = resolve_cuda(config.use_cuda)

    tiles = discover_tiles(config.input_dir, config.coords_csv, config.invert_x, config.invert_y)
    excluded_names = {Path(name).name for name in config.excluded_filenames}
    if excluded_names:
        tiles = [tile for tile in tiles if Path(tile.filename).name not in excluded_names]
        if not tiles:
            raise ValueError("All tiles were excluded; nothing to stitch.")
    work_tiles = _load_work_tiles(tiles, config)
    tile_shape = work_tiles[0].gray.shape[:2]
    work_scale = work_tiles[0].scale

    x_ppu, y_ppu = estimate_pixels_per_unit(tiles, tile_shape, config.overlap_ratio)
    initial = initial_positions(tiles, x_ppu, y_ppu)
    detection_features = load_detection_features(config.input_dir, tiles, work_scale) if config.use_detection_features else {}
    for idx, features in detection_features.items():
        work_tiles[idx].features = features
    neighbors = build_neighbors(tiles, initial, tile_shape, config.min_overlap_px)
    if not neighbors:
        raise ValueError("No adjacent tile pairs were found. Check coordinates or filenames.")

    edges = []
    for neighbor in tqdm(neighbors, desc="align pairs"):
        ref = work_tiles[neighbor.ref]
        mov = work_tiles[neighbor.mov]
        expected_dx = float(initial[neighbor.mov, 0] - initial[neighbor.ref, 0])
        expected_dy = float(initial[neighbor.mov, 1] - initial[neighbor.ref, 1])
        edge = estimate_pair_transform(
            ref.gray,
            mov.gray,
            ref.image_bgr,
            mov.image_bgr,
            ref.features,
            mov.features,
            expected_dx,
            expected_dy,
            ref.tile.filename,
            mov.tile.filename,
            neighbor.ref,
            neighbor.mov,
            config,
            pair_debug_dir,
        )
        edge.details["neighbor_kind"] = neighbor.kind
        edges.append(edge)

    accepted_edges = []
    rejected_edges = []
    for edge in edges:
        accepted = _edge_is_accepted(edge, config)
        edge.details["accepted_for_pose_graph"] = accepted
        edge.details["min_edge_score"] = config.min_edge_score
        if accepted:
            accepted_edges.append(edge)
        else:
            rejected_edges.append(edge)

    progressive_debug = None
    if config.placement_mode == "progressive":
        progressive_anchor_index = _find_progressive_anchor(tiles, config.progressive_anchor)
        locked_positions = _load_locked_positions(tiles, config.locked_placements_csv, work_scale)
        progressive_result = solve_progressive_positions(
            tiles=tiles,
            initial=initial,
            edges=edges,
            min_score=config.min_edge_score,
            tolerance_px=config.progressive_tolerance_px,
            min_anchor_count=config.progressive_min_anchor_count,
            anchor_index=progressive_anchor_index,
            locked_positions=locked_positions,
            place_fallback_tiles=not config.drop_unconfirmed_tiles,
        )
        solved_work = progressive_result.positions
        progressive_debug = {
            "tolerance_px": config.progressive_tolerance_px,
            "min_anchor_count": config.progressive_min_anchor_count,
            "drop_unconfirmed_tiles": config.drop_unconfirmed_tiles,
            "anchor": tiles[progressive_anchor_index].filename if progressive_anchor_index is not None else None,
            "locked_tiles": [tiles[idx].filename for idx in sorted(locked_positions)],
            "fallback_tiles": [tiles[idx].filename for idx in progressive_result.fallback_tiles],
            "steps": [
                {
                    "tile_index": step.tile_index,
                    "filename": step.filename,
                    "candidate_count": step.candidate_count,
                    "inlier_count": step.inlier_count,
                    "required_anchor_count": step.required_anchor_count,
                    "support": step.support,
                    "conflict_px": step.conflict_px,
                    "source_tiles": step.source_tiles,
                }
                for step in progressive_result.steps
            ],
        }
    else:
        solved_work = solve_positions(initial, accepted_edges, config.stage_anchor_weight)
    if config.placement_mode == "global" and config.preserve_rejected_gaps and rejected_edges:
        solved_work = _preserve_rejected_pair_gaps(
            tiles=tiles,
            positions=solved_work,
            accepted_edges=accepted_edges,
            rejected_edges=rejected_edges,
            tile_shape=tile_shape,
            work_scale=work_scale,
            rejected_gap_px=config.rejected_gap_px,
        )
    solved_full = solved_work / max(work_scale, 1e-6)
    compose_mask = np.all(np.isfinite(solved_full), axis=1)
    if not np.any(compose_mask):
        raise ValueError("No tiles have finite solved positions; cannot compose mosaic.")
    compose_tiles = [tile for idx, tile in enumerate(tiles) if bool(compose_mask[idx])]
    compose_positions = solved_full[compose_mask]

    final_path = config.output_dir / f"stitched.{config.export_format}"
    preview_path = config.output_dir / "stitched_preview.jpg"
    blend_info = compose_mosaic(compose_tiles, compose_positions, config, final_path, preview_path)

    placement_rows = []
    for idx, tile in enumerate(tiles):
        placement_rows.append(
            {
                "index": tile.index,
                "filename": tile.filename,
                "stage_x": tile.x,
                "stage_y": tile.y,
                "initial_work_x": float(initial[idx, 0]),
                "initial_work_y": float(initial[idx, 1]),
                "aligned_work_x": float(solved_work[idx, 0]),
                "aligned_work_y": float(solved_work[idx, 1]),
                "aligned_full_x": float(solved_full[idx, 0]),
                "aligned_full_y": float(solved_full[idx, 1]),
            }
        )

    if debug_dir is not None:
        write_placements_csv(debug_dir / "placements.csv", placement_rows)
        write_json(debug_dir / "pair_edges.json", {"pairs": edges})
        if progressive_debug is not None:
            write_json(debug_dir / "progressive_steps.json", progressive_debug)

    summary_path = config.output_dir / "stitch_summary.json"
    summary = {
        "input_dir": config.input_dir,
        "output_dir": config.output_dir,
        "tile_count": len(tiles),
        "excluded_filenames": sorted(excluded_names),
        "overlap_ratio": config.overlap_ratio,
        "work_scale": work_scale,
        "pixels_per_unit": {"x": x_ppu, "y": y_ppu},
        "cuda": {"enabled": cuda_enabled, "reason": cuda_reason},
        "alignment_methods": _method_counts(edges),
        "accepted_pair_count": len(accepted_edges),
        "rejected_pair_count": len(rejected_edges),
        "min_edge_score": config.min_edge_score,
        "small_feature_weight": config.small_feature_weight,
        "use_detection_features": config.use_detection_features,
        "detection_feature_min_matches": config.detection_feature_min_matches,
        "detection_feature_cluster_tolerance_px": config.detection_feature_cluster_tolerance_px,
        "detection_feature_tile_count": sum(1 for features in detection_features.values() if features),
        "placement_mode": config.placement_mode,
        "composed_tile_count": int(np.count_nonzero(compose_mask)),
        "dropped_tile_count": int(len(tiles) - np.count_nonzero(compose_mask)),
        "dropped_tiles": [tiles[idx].filename for idx, used in enumerate(compose_mask) if not bool(used)],
        "progressive": progressive_debug,
        "preserve_rejected_gaps": config.preserve_rejected_gaps,
        "rejected_gap_px": config.rejected_gap_px,
        "failed_pair_count": sum(1 for edge in edges if not edge.success),
        "blend": blend_info,
        "final_image": final_path,
        "preview_image": preview_path,
        "debug_dir": debug_dir,
        "placements_csv": None if debug_dir is None else debug_dir / "placements.csv",
    }
    write_json(summary_path, summary)

    return StitchResult(
        final_image=final_path,
        preview_image=preview_path,
        debug_dir=debug_dir or config.output_dir,
        summary_json=summary_path,
        tile_count=len(tiles),
    )


def _load_work_tiles(tiles, config: StitchConfig) -> list[WorkTile]:
    work_tiles: list[WorkTile] = []
    for tile in tqdm(tiles, desc="load/preprocess"):
        image, scale = read_image_bgr(tile.path, scale=config.work_scale, max_side=config.max_work_side)
        gray = preprocess_for_alignment(image)
        work_tiles.append(WorkTile(tile=tile, image_bgr=image, gray=gray, scale=scale))
    scales = {round(item.scale, 6) for item in work_tiles}
    if len(scales) != 1:
        raise ValueError("All tiles must use the same alignment scale. Check input image sizes.")
    return work_tiles


def _method_counts(edges) -> dict[str, int]:
    counts: dict[str, int] = {}
    for edge in edges:
        counts[edge.method] = counts.get(edge.method, 0) + 1
    return counts


def _edge_is_accepted(edge, config: StitchConfig) -> bool:
    return bool(edge.success) and float(edge.score) >= float(config.min_edge_score)


def _find_progressive_anchor(tiles, anchor: str | None) -> int | None:
    if not anchor:
        return None
    target = Path(anchor).name
    for idx, tile in enumerate(tiles):
        if tile.filename == target or Path(tile.filename).name == target:
            return idx
    available = ", ".join(tile.filename for tile in tiles)
    raise ValueError(f"Progressive anchor not found: {anchor}. Available tiles: {available}")


def _load_locked_positions(tiles, placements_csv: Path | None, work_scale: float) -> dict[int, np.ndarray]:
    if placements_csv is None:
        return {}
    if not placements_csv.exists():
        raise FileNotFoundError(f"Locked placements CSV not found: {placements_csv}")

    by_filename: dict[str, tuple[float, float]] = {}
    with placements_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            filename = Path((row.get("filename") or "").strip()).name
            if not filename:
                continue
            if row.get("aligned_work_x") not in (None, "") and row.get("aligned_work_y") not in (None, ""):
                x = float(row["aligned_work_x"])
                y = float(row["aligned_work_y"])
            elif row.get("aligned_full_x") not in (None, "") and row.get("aligned_full_y") not in (None, ""):
                x = float(row["aligned_full_x"]) * float(work_scale)
                y = float(row["aligned_full_y"]) * float(work_scale)
            else:
                continue
            by_filename[filename] = (x, y)

    locked: dict[int, np.ndarray] = {}
    for idx, tile in enumerate(tiles):
        key = Path(tile.filename).name
        if key in by_filename:
            locked[idx] = np.array(by_filename[key], dtype=np.float64)
    if not locked:
        raise ValueError(f"No current tiles matched locked placements CSV: {placements_csv}")
    return locked


def _preserve_rejected_pair_gaps(
    tiles,
    positions,
    accepted_edges,
    rejected_edges,
    tile_shape: tuple[int, int],
    work_scale: float,
    rejected_gap_px: int,
):
    adjusted = positions.copy()
    tile_h, tile_w = tile_shape
    gap_work = max(0.0, float(rejected_gap_px) * float(work_scale))

    for edge in sorted(rejected_edges, key=lambda item: max(abs(item.expected_dx), abs(item.expected_dy))):
        # Diagonal overlap pairs are useful pose constraints, but a rejected diagonal
        # should not push whole rows/columns apart and create artificial gaps.
        if abs(edge.expected_dx) > 1e-6 and abs(edge.expected_dy) > 1e-6:
            continue
        axis = 0 if abs(edge.expected_dx) >= abs(edge.expected_dy) else 1
        if _has_accepted_bridge_on_axis(edge, accepted_edges, tiles, axis):
            edge.details["rejected_gap_skipped"] = "accepted_overlap_bridge_exists"
            continue
        tile_size = tile_w if axis == 0 else tile_h
        desired_distance = float(tile_size) + gap_work
        current_delta = float(adjusted[edge.mov, axis] - adjusted[edge.ref, axis])
        direction = 1.0 if current_delta >= 0 else -1.0
        if abs(current_delta) >= desired_distance:
            continue

        shift = direction * desired_distance - current_delta
        coord_attr = "x" if axis == 0 else "y"
        ref_coord = float(getattr(tiles[edge.ref], coord_attr))
        mov_coord = float(getattr(tiles[edge.mov], coord_attr))
        coord_direction = 1.0 if mov_coord >= ref_coord else -1.0
        if abs(mov_coord - ref_coord) < 1e-9:
            pos_threshold = adjusted[edge.mov, axis]
            if direction >= 0:
                group = adjusted[:, axis] >= pos_threshold - 1e-6
            else:
                group = adjusted[:, axis] <= pos_threshold + 1e-6
        else:
            group = [
                (float(getattr(tile, coord_attr)) - mov_coord) * coord_direction >= -1e-9
                for tile in tiles
            ]

        adjusted[group, axis] += shift

    adjusted[:, 0] -= adjusted[:, 0].min()
    adjusted[:, 1] -= adjusted[:, 1].min()
    return adjusted


def _has_accepted_bridge_on_axis(rejected_edge, accepted_edges, tiles, axis: int) -> bool:
    coord_attr = "x" if axis == 0 else "y"
    rejected_pair = _coord_pair(tiles, rejected_edge, coord_attr)
    if abs(rejected_pair[1] - rejected_pair[0]) < 1e-9:
        return False

    for accepted_edge in accepted_edges:
        if abs(accepted_edge.expected_dx) < 1e-6 and abs(accepted_edge.expected_dy) < 1e-6:
            continue
        if _coord_pair(tiles, accepted_edge, coord_attr) == rejected_pair:
            return True
    return False


def _coord_pair(tiles, edge, coord_attr: str) -> tuple[float, float]:
    a = round(float(getattr(tiles[edge.ref], coord_attr)), 6)
    b = round(float(getattr(tiles[edge.mov], coord_attr)), 6)
    return (a, b) if a <= b else (b, a)

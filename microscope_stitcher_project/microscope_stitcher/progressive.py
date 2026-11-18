from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .types import PairEdge, Tile


@dataclass(frozen=True)
class ProgressiveStep:
    tile_index: int
    filename: str
    candidate_count: int
    inlier_count: int
    required_anchor_count: int
    support: float
    conflict_px: float
    source_tiles: list[int]


@dataclass(frozen=True)
class ProgressiveSolveResult:
    positions: np.ndarray
    steps: list[ProgressiveStep]
    fallback_tiles: list[int]


def solve_progressive_positions(
    tiles: list[Tile],
    initial: np.ndarray,
    edges: list[PairEdge],
    min_score: float,
    tolerance_px: float,
    min_anchor_count: int = 1,
    anchor_index: int | None = None,
    locked_positions: dict[int, np.ndarray] | None = None,
    place_fallback_tiles: bool = True,
) -> ProgressiveSolveResult:
    usable_edges = [
        edge for edge in edges
        if edge.success and float(edge.score) >= float(min_score)
    ]
    adjacency = _build_adjacency(usable_edges)
    order = _progressive_order(initial)
    if anchor_index is not None:
        order = [anchor_index] + [idx for idx in order if idx != anchor_index]
    anchor = order[0]
    locked_positions = locked_positions or {}

    positions = np.full_like(initial, np.nan, dtype=np.float64)
    placed = set()
    for idx, position in locked_positions.items():
        positions[idx] = np.asarray(position, dtype=np.float64)
        placed.add(idx)
    if not placed:
        positions[anchor] = np.array([0.0, 0.0], dtype=np.float64)
        placed.add(anchor)
    steps: list[ProgressiveStep] = []

    remaining = [idx for idx in order if idx not in placed]
    while remaining:
        progressed = False
        for idx in list(remaining):
            candidates = _candidate_positions(idx, placed, positions, adjacency)
            if not candidates:
                continue
            required_anchor_count = min_anchor_count if len(placed) >= min_anchor_count else 1
            pos, inliers, support, conflict_px = _robust_position(candidates, tolerance_px, required_anchor_count)
            if pos is None:
                continue
            positions[idx] = pos
            placed.add(idx)
            remaining.remove(idx)
            steps.append(
                ProgressiveStep(
                    tile_index=idx,
                    filename=tiles[idx].filename,
                    candidate_count=len(candidates),
                    inlier_count=len(inliers),
                    required_anchor_count=required_anchor_count,
                    support=support,
                    conflict_px=conflict_px,
                    source_tiles=[candidate[2] for candidate in inliers],
                )
            )
            progressed = True
        if not progressed:
            break

    fallback_tiles = []
    reference = anchor if anchor in placed else next(iter(placed))
    reference_initial = initial[reference].copy()
    reference_position = positions[reference].copy()
    for idx in remaining:
        fallback_tiles.append(idx)
        if place_fallback_tiles:
            # Keep disconnected tiles near their stage-estimated position instead of
            # forcing an unverified image match.
            positions[idx] = reference_position + (initial[idx] - reference_initial)

    if not locked_positions:
        finite = np.all(np.isfinite(positions), axis=1)
        if np.any(finite):
            positions[finite, 0] -= np.nanmin(positions[finite, 0])
            positions[finite, 1] -= np.nanmin(positions[finite, 1])
    return ProgressiveSolveResult(positions=positions, steps=steps, fallback_tiles=fallback_tiles)


def _progressive_order(initial: np.ndarray) -> list[int]:
    x_values = _unique_sorted(initial[:, 0])
    y_values = _unique_sorted(initial[:, 1], reverse=True)
    lookup = {
        (_nearest_key(float(pos[0]), x_values), _nearest_key(float(pos[1]), y_values)): idx
        for idx, pos in enumerate(initial)
    }

    order: list[int] = []
    if not x_values or not y_values:
        return list(range(len(initial)))

    bottom = y_values[0]
    top_rows = y_values[1:]
    first_col = x_values[0]
    anchor = lookup.get((first_col, bottom))
    if anchor is not None:
        order.append(anchor)

    if len(x_values) > 1:
        first_right = lookup.get((x_values[1], bottom))
        if first_right is not None:
            order.append(first_right)

    for y_value in top_rows:
        first_top = lookup.get((first_col, y_value))
        if first_top is not None:
            order.append(first_top)
        if len(x_values) > 1:
            first_top_right = lookup.get((x_values[1], y_value))
            if first_top_right is not None:
                order.append(first_top_right)

    for x_value in x_values[2:]:
        bottom_tile = lookup.get((x_value, bottom))
        if bottom_tile is not None:
            order.append(bottom_tile)
        for y_value in top_rows:
            tile = lookup.get((x_value, y_value))
            if tile is not None:
                order.append(tile)

    for idx in range(len(initial)):
        if idx not in order:
            order.append(idx)
    return order


def _unique_sorted(values, reverse: bool = False) -> list[float]:
    unique = sorted({round(float(value), 6) for value in values}, reverse=reverse)
    return unique


def _nearest_key(value: float, keys: list[float]) -> float:
    return min(keys, key=lambda key: abs(key - value))


def _build_adjacency(edges: list[PairEdge]):
    adjacency: dict[int, list[PairEdge]] = {}
    for edge in edges:
        adjacency.setdefault(edge.ref, []).append(edge)
        adjacency.setdefault(edge.mov, []).append(edge)
    return adjacency


def _candidate_positions(idx: int, placed: set[int], positions: np.ndarray, adjacency) -> list[tuple[np.ndarray, float, int]]:
    candidates: list[tuple[np.ndarray, float, int]] = []
    for edge in adjacency.get(idx, []):
        if edge.ref == idx and edge.mov in placed:
            candidates.append((positions[edge.mov] - np.array([edge.dx, edge.dy]), float(edge.score), edge.mov))
        elif edge.mov == idx and edge.ref in placed:
            candidates.append((positions[edge.ref] + np.array([edge.dx, edge.dy]), float(edge.score), edge.ref))
    return candidates


def _robust_position(candidates: list[tuple[np.ndarray, float, int]], tolerance_px: float, min_anchor_count: int):
    if len(candidates) < min_anchor_count:
        return None, candidates, 0.0, 0.0
    if len(candidates) == 1:
        return candidates[0][0], candidates, float(candidates[0][1]), 0.0

    best_inliers = []
    best_support = -1.0
    best_spread = float("inf")
    for center, _, _ in candidates:
        inliers = [
            candidate for candidate in candidates
            if float(np.linalg.norm(candidate[0] - center)) <= tolerance_px
        ]
        support = float(sum(candidate[1] for candidate in inliers))
        spread = _cluster_spread(inliers)
        if (len(inliers), support, -spread) > (len(best_inliers), best_support, -best_spread):
            best_inliers = inliers
            best_support = support
            best_spread = spread

    if not best_inliers:
        best_inliers = [max(candidates, key=lambda item: item[1])]
        best_support = float(best_inliers[0][1])
        best_spread = 0.0
    if len({candidate[2] for candidate in best_inliers}) < min_anchor_count:
        return None, best_inliers, best_support, max(best_spread, _cluster_spread(candidates))

    weights = np.array([max(0.01, candidate[1]) for candidate in best_inliers], dtype=np.float64)
    points = np.array([candidate[0] for candidate in best_inliers], dtype=np.float64)
    position = np.average(points, axis=0, weights=weights)
    conflict_px = _cluster_spread(candidates)
    return position, best_inliers, best_support, max(best_spread, conflict_px)


def _cluster_spread(candidates: list[tuple[np.ndarray, float, int]]) -> float:
    if len(candidates) <= 1:
        return 0.0
    points = [candidate[0] for candidate in candidates]
    return float(max(np.linalg.norm(a - b) for a in points for b in points))

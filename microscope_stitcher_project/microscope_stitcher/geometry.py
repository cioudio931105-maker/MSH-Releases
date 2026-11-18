from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import numpy as np

from .types import Tile


@dataclass(frozen=True)
class Neighbor:
    ref: int
    mov: int
    kind: str = "grid"


def estimate_pixels_per_unit(tiles: list[Tile], tile_shape: tuple[int, int], overlap_ratio: float) -> tuple[float, float]:
    height, width = tile_shape
    x_step = _dominant_step([tile.x for tile in tiles])
    y_step = _dominant_step([tile.y for tile in tiles])
    x_ppu = width * (1.0 - overlap_ratio) / x_step if x_step > 0 else width * (1.0 - overlap_ratio)
    y_ppu = height * (1.0 - overlap_ratio) / y_step if y_step > 0 else height * (1.0 - overlap_ratio)
    return float(x_ppu), float(y_ppu)


def initial_positions(tiles: list[Tile], x_ppu: float, y_ppu: float) -> np.ndarray:
    pos = np.array([[tile.x * x_ppu, tile.y * y_ppu] for tile in tiles], dtype=np.float64)
    pos[:, 0] -= np.min(pos[:, 0])
    pos[:, 1] -= np.min(pos[:, 1])
    return pos


def build_neighbors(
    tiles: list[Tile],
    positions: np.ndarray | None = None,
    tile_shape: tuple[int, int] | None = None,
    min_overlap_px: int = 24,
) -> list[Neighbor]:
    neighbors: list[Neighbor] = []
    by_y: dict[float, list[tuple[int, Tile]]] = defaultdict(list)
    by_x: dict[float, list[tuple[int, Tile]]] = defaultdict(list)
    for idx, tile in enumerate(tiles):
        by_y[_round_coord(tile.y)].append((idx, tile))
        by_x[_round_coord(tile.x)].append((idx, tile))

    for row in by_y.values():
        ordered = sorted(row, key=lambda item: item[1].x)
        neighbors.extend(Neighbor(a[0], b[0], "row") for a, b in zip(ordered, ordered[1:]))
    for col in by_x.values():
        ordered = sorted(col, key=lambda item: item[1].y)
        neighbors.extend(Neighbor(a[0], b[0], "column") for a, b in zip(ordered, ordered[1:]))

    if positions is not None and tile_shape is not None:
        neighbors.extend(_overlapping_neighbors(positions, tile_shape, min_overlap_px))

    seen: set[tuple[int, int]] = set()
    unique: list[Neighbor] = []
    for edge in neighbors:
        key = (min(edge.ref, edge.mov), max(edge.ref, edge.mov))
        if key not in seen:
            seen.add(key)
            unique.append(edge)
    return unique


def _overlapping_neighbors(
    positions: np.ndarray,
    tile_shape: tuple[int, int],
    min_overlap_px: int,
) -> list[Neighbor]:
    tile_h, tile_w = tile_shape
    min_overlap = max(1, int(min_overlap_px))
    neighbors: list[Neighbor] = []
    for ref in range(len(positions)):
        ref_x, ref_y = float(positions[ref, 0]), float(positions[ref, 1])
        for mov in range(ref + 1, len(positions)):
            mov_x, mov_y = float(positions[mov, 0]), float(positions[mov, 1])
            overlap_w = min(ref_x + tile_w, mov_x + tile_w) - max(ref_x, mov_x)
            overlap_h = min(ref_y + tile_h, mov_y + tile_h) - max(ref_y, mov_y)
            if overlap_w >= min_overlap and overlap_h >= min_overlap:
                neighbors.append(Neighbor(ref, mov, "overlap"))
    return neighbors


def _dominant_step(values: list[float]) -> float:
    unique = sorted(set(round(float(value), 6) for value in values))
    diffs = [abs(b - a) for a, b in zip(unique, unique[1:]) if abs(b - a) > 1e-9]
    return float(np.median(diffs)) if diffs else 0.0


def _round_coord(value: float) -> float:
    return round(float(value), 6)

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .alignment import AlignmentResult


@dataclass(slots=True)
class TilePlacement:
    index: int
    path: Path
    x: int
    y: int
    width: int
    height: int


@dataclass(slots=True)
class CanvasLayout:
    width: int
    height: int
    origin_shift_x: int
    origin_shift_y: int


def build_layout(image_paths: list[Path], image_shapes: list[tuple[int, int]], shifts: list[AlignmentResult]) -> tuple[list[TilePlacement], CanvasLayout]:
    """Convert adjacent pairwise shifts into absolute tile placements."""

    if not image_paths:
        return [], CanvasLayout(width=0, height=0, origin_shift_x=0, origin_shift_y=0)

    raw_positions: list[tuple[float, float]] = [(0.0, 0.0)]
    for shift in shifts:
        prev_x, prev_y = raw_positions[-1]
        raw_positions.append((prev_x + shift.dx, prev_y + shift.dy))

    min_x = min(position[0] for position in raw_positions)
    min_y = min(position[1] for position in raw_positions)
    offset_x = int(round(-min_x if min_x < 0 else 0.0))
    offset_y = int(round(-min_y if min_y < 0 else 0.0))

    placements: list[TilePlacement] = []
    max_x = 0
    max_y = 0
    for index, (path, shape, raw_position) in enumerate(zip(image_paths, image_shapes, raw_positions)):
        height, width = shape
        x = int(round(raw_position[0])) + offset_x
        y = int(round(raw_position[1])) + offset_y
        placements.append(TilePlacement(index=index, path=Path(path), x=x, y=y, width=width, height=height))
        max_x = max(max_x, x + width)
        max_y = max(max_y, y + height)

    return placements, CanvasLayout(width=max_x, height=max_y, origin_shift_x=offset_x, origin_shift_y=offset_y)

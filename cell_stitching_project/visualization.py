from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from .alignment import AlignmentResult
from .layout import CanvasLayout, TilePlacement
from .preprocess import PreprocessedImage
from .text_overlay import put_text


def _to_bgr(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return cv2.cvtColor(np.clip(image, 0, 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)
    return np.clip(image, 0, 255).astype(np.uint8)


def _aligned_overlay(ref_strip: np.ndarray, mov_strip: np.ndarray, dx: float, dy: float) -> np.ndarray:
    ref_bgr = _to_bgr(ref_strip)
    mov_bgr = _to_bgr(mov_strip)
    height = max(ref_bgr.shape[0], mov_bgr.shape[0] + abs(int(round(dy))))
    width = max(ref_bgr.shape[1], mov_bgr.shape[1] + abs(int(round(dx))))
    canvas_ref = np.zeros((height, width, 3), dtype=np.uint8)
    canvas_mov = np.zeros((height, width, 3), dtype=np.uint8)

    ref_y = max(0, -int(round(dy)))
    ref_x = max(0, -int(round(dx)))
    mov_y = max(0, int(round(dy)))
    mov_x = max(0, int(round(dx)))
    canvas_ref[ref_y : ref_y + ref_bgr.shape[0], ref_x : ref_x + ref_bgr.shape[1], 1] = ref_bgr[:, :, 1]
    canvas_mov[mov_y : mov_y + mov_bgr.shape[0], mov_x : mov_x + mov_bgr.shape[1], 2] = mov_bgr[:, :, 2]
    return cv2.addWeighted(canvas_ref, 0.7, canvas_mov, 0.7, 0.0)


def save_pair_debug(
    pair_index: int,
    ref_tile: PreprocessedImage,
    mov_tile: PreprocessedImage,
    result: AlignmentResult,
    debug_dir: str | Path,
) -> Path:
    """Save a compact debug board for one aligned pair."""

    output_dir = Path(debug_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    board_rows: list[np.ndarray] = []
    ref_strip = result.debug.get("ref_strip")
    mov_strip = result.debug.get("mov_strip")

    if ref_strip is not None and mov_strip is not None:
        before_overlay = _aligned_overlay(ref_strip, mov_strip, 0.0, 0.0)
        after_overlay = _aligned_overlay(ref_strip, mov_strip, float(result.debug.get("local_dx", 0.0)), float(result.debug.get("local_dy", 0.0)))
        max_height = max(before_overlay.shape[0], after_overlay.shape[0])
        if before_overlay.shape[0] != max_height:
            before_overlay = cv2.copyMakeBorder(before_overlay, 0, max_height - before_overlay.shape[0], 0, 0, cv2.BORDER_CONSTANT, value=(0, 0, 0))
        if after_overlay.shape[0] != max_height:
            after_overlay = cv2.copyMakeBorder(after_overlay, 0, max_height - after_overlay.shape[0], 0, 0, cv2.BORDER_CONSTANT, value=(0, 0, 0))
        board_rows.append(cv2.hconcat([before_overlay, after_overlay]))

    match_image = result.debug.get("matches_image")
    if isinstance(match_image, np.ndarray):
        board_rows.append(_to_bgr(match_image))

    ref_preview = ref_tile.detection_overlay if ref_tile.detection_overlay is not None else ref_tile.blend_bgr
    mov_preview = mov_tile.detection_overlay if mov_tile.detection_overlay is not None else mov_tile.blend_bgr
    board_rows.insert(
        0,
        cv2.hconcat(
            [
                cv2.resize(_to_bgr(ref_preview), (640, 360), interpolation=cv2.INTER_AREA),
                cv2.resize(_to_bgr(mov_preview), (640, 360), interpolation=cv2.INTER_AREA),
            ]
        ),
    )

    board = board_rows[0]
    for row in board_rows[1:]:
        width = max(board.shape[1], row.shape[1])
        if board.shape[1] != width:
            board = cv2.copyMakeBorder(board, 0, 0, 0, width - board.shape[1], cv2.BORDER_CONSTANT, value=(0, 0, 0))
        if row.shape[1] != width:
            row = cv2.copyMakeBorder(row, 0, 0, 0, width - row.shape[1], cv2.BORDER_CONSTANT, value=(0, 0, 0))
        board = cv2.vconcat([board, row])

    title = (
        f"pair={pair_index:03d} method={result.method} dir={result.direction} "
        f"dx={result.dx:.2f} dy={result.dy:.2f} angle={result.angle:.2f} score={result.score:.4f}"
    )
    put_text(board, title, (12, 28), 0.7, (255, 255, 255), 2)
    output_path = output_dir / f"pair_{pair_index:03d}_{result.method}_{result.direction}.png"
    cv2.imwrite(str(output_path), board)
    return output_path


def save_tile_placement_preview(placements: list[TilePlacement], canvas: CanvasLayout, output_path: str | Path) -> Path:
    """Visualize the placement of each tile on the final canvas."""

    scale = min(1.0, 1400.0 / max(1, max(canvas.width, canvas.height)))
    preview = np.full((max(1, int(round(canvas.height * scale))), max(1, int(round(canvas.width * scale))), 3), 20, dtype=np.uint8)
    for placement in placements:
        x0 = int(round(placement.x * scale))
        y0 = int(round(placement.y * scale))
        x1 = int(round((placement.x + placement.width) * scale))
        y1 = int(round((placement.y + placement.height) * scale))
        color = (
            int((53 * (placement.index + 1)) % 255),
            int((97 * (placement.index + 1)) % 255),
            int((173 * (placement.index + 1)) % 255),
        )
        cv2.rectangle(preview, (x0, y0), (x1, y1), color, 2)
        put_text(preview, str(placement.index), (x0 + 4, y0 + 24), 0.7, color, 2)

    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(target), preview)
    return target


def save_overlay_preview(stitched: np.ndarray, placements: list[TilePlacement], output_path: str | Path) -> Path:
    """Draw tile boundaries on top of the final stitched result."""

    preview = stitched.copy()
    for placement in placements:
        color = (
            int((53 * (placement.index + 1)) % 255),
            int((97 * (placement.index + 1)) % 255),
            int((173 * (placement.index + 1)) % 255),
        )
        cv2.rectangle(preview, (placement.x, placement.y), (placement.x + placement.width, placement.y + placement.height), color, 2)
        put_text(preview, str(placement.index), (placement.x + 6, placement.y + 24), 0.7, color, 2)

    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(target), preview)
    return target


def save_intermediate_mosaics(images: list[np.ndarray], placements: list[TilePlacement], canvas: CanvasLayout, output_dir: str | Path) -> None:
    """Save simple alpha-composited intermediate placement previews."""

    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    accumulator = np.zeros((canvas.height, canvas.width, 3), dtype=np.float32)
    weight_accumulator = np.zeros((canvas.height, canvas.width), dtype=np.float32)
    for index, (image, placement) in enumerate(zip(images, placements), start=1):
        alpha = np.ones((image.shape[0], image.shape[1]), dtype=np.float32)
        y0 = placement.y
        y1 = placement.y + image.shape[0]
        x0 = placement.x
        x1 = placement.x + image.shape[1]
        accumulator[y0:y1, x0:x1] += image.astype(np.float32) * alpha[:, :, None]
        weight_accumulator[y0:y1, x0:x1] += alpha
        composite = accumulator / np.maximum(weight_accumulator[:, :, None], 1e-6)
        cv2.imwrite(str(target_dir / f"mosaic_step_{index:03d}.png"), np.clip(composite, 0, 255).astype(np.uint8))

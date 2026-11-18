from __future__ import annotations

import argparse
import csv
from pathlib import Path

import cv2
import numpy as np


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic microscope-like tiles for smoke testing.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--rows", type=int, default=2)
    parser.add_argument("--cols", type=int, default=4)
    parser.add_argument("--tile-w", type=int, default=640)
    parser.add_argument("--tile-h", type=int, default=420)
    parser.add_argument("--overlap", type=float, default=0.15)
    args = parser.parse_args()

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    step_x = int(args.tile_w * (1.0 - args.overlap))
    step_y = int(args.tile_h * (1.0 - args.overlap))
    canvas = np.full((step_y * (args.rows - 1) + args.tile_h, step_x * (args.cols - 1) + args.tile_w, 3), 220, np.uint8)
    rng = np.random.default_rng(7)
    for _ in range(480):
        x = int(rng.integers(0, canvas.shape[1]))
        y = int(rng.integers(0, canvas.shape[0]))
        r = int(rng.integers(10, 24))
        color = (int(rng.integers(70, 120)), int(rng.integers(80, 130)), int(rng.integers(120, 190)))
        cv2.circle(canvas, (x, y), r, color, 2)
        cv2.circle(canvas, (x, y), max(2, r - 5), (180, 180, 210), -1)
    noise = rng.normal(0, 5, canvas.shape).astype(np.int16)
    canvas = np.clip(canvas.astype(np.int16) + noise, 0, 255).astype(np.uint8)

    rows = []
    index = 1
    for row in range(args.rows):
        col_range = range(args.cols) if row % 2 == 0 else range(args.cols - 1, -1, -1)
        for col in col_range:
            x0 = col * step_x
            y0 = row * step_y
            jitter_x = int(rng.integers(-5, 6))
            jitter_y = int(rng.integers(-5, 6))
            tile = canvas[max(0, y0 + jitter_y):max(0, y0 + jitter_y) + args.tile_h, max(0, x0 + jitter_x):max(0, x0 + jitter_x) + args.tile_w]
            tile = cv2.copyMakeBorder(tile, 0, args.tile_h - tile.shape[0], 0, args.tile_w - tile.shape[1], cv2.BORDER_REFLECT)
            filename = f"{col}_{row}.jpg"
            cv2.imwrite(str(out / filename), tile)
            rows.append({"index": index, "x": col, "y": row, "filename": filename})
            index += 1

    with (out / "virtual_coordinates.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["index", "x", "y", "filename"])
        writer.writeheader()
        writer.writerows(rows)
    print(out)


if __name__ == "__main__":
    main()

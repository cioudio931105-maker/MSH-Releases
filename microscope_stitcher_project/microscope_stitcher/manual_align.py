from __future__ import annotations

import base64
import csv
import json
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

import cv2
import numpy as np

from .blending import compose_mosaic
from .config import StitchConfig
from .io_utils import SUPPORTED_EXTENSIONS, discover_tiles, read_image_bgr
from .types import Tile


@dataclass
class ManualTile:
    tile: Tile
    x: float
    y: float
    width: int
    height: int
    photo: tk.PhotoImage | None = None
    image_item: int | None = None
    rect_item: int | None = None
    label_item: int | None = None


class ManualAlignApp:
    def __init__(
        self,
        input_dir: Path,
        output_dir: Path,
        placement_csv: Path | None,
        view_scale: float = 0.18,
        blend_mode: str = "max_weight",
    ) -> None:
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.placement_csv = placement_csv
        self.view_scale = view_scale
        self.blend_mode = blend_mode
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.root = tk.Tk()
        self.root.title("Microscope Manual Tile Alignment")
        self.root.geometry("1400x850")

        self.tiles = load_manual_tiles(input_dir, placement_csv)
        self.selected_index: int | None = None
        self.drag_start: tuple[int, int] | None = None
        self.padding = 80

        self.status = tk.StringVar(value="Ready")
        self._build_ui()
        self._draw_all_tiles()
        self._bind_keys()

    def run(self) -> None:
        self.root.mainloop()

    def _build_ui(self) -> None:
        toolbar = ttk.Frame(self.root)
        toolbar.pack(side=tk.TOP, fill=tk.X)

        ttk.Button(toolbar, text="Save 座標", command=self.save_positions).pack(side=tk.LEFT, padx=4, pady=4)
        ttk.Button(toolbar, text="Export 拼接圖", command=self.export_mosaic).pack(side=tk.LEFT, padx=4, pady=4)
        ttk.Button(toolbar, text="載入座標", command=self.load_positions_dialog).pack(side=tk.LEFT, padx=4, pady=4)
        ttk.Button(toolbar, text="放大 +", command=lambda: self.zoom(1.15)).pack(side=tk.LEFT, padx=4, pady=4)
        ttk.Button(toolbar, text="縮小 -", command=lambda: self.zoom(1 / 1.15)).pack(side=tk.LEFT, padx=4, pady=4)
        ttk.Button(toolbar, text="置中", command=self.center_view).pack(side=tk.LEFT, padx=4, pady=4)
        ttk.Label(
            toolbar,
            text="操作：左鍵拖拉 tile，方向鍵微調，Shift+方向鍵大步移動，PageUp/PageDown 調整圖層。",
        ).pack(side=tk.LEFT, padx=12)

        main = ttk.Frame(self.root)
        main.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(main, bg="#111111", highlightthickness=0)
        x_scroll = ttk.Scrollbar(main, orient=tk.HORIZONTAL, command=self.canvas.xview)
        y_scroll = ttk.Scrollbar(main, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=x_scroll.set, yscrollcommand=y_scroll.set)

        self.canvas.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        main.columnconfigure(0, weight=1)
        main.rowconfigure(0, weight=1)

        status_bar = ttk.Label(self.root, textvariable=self.status, anchor="w")
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        self.canvas.bind("<ButtonPress-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel)

    def _bind_keys(self) -> None:
        self.root.bind("<KeyPress-Up>", lambda event: self.nudge_selected(0, -_key_step(event)))
        self.root.bind("<KeyPress-Down>", lambda event: self.nudge_selected(0, _key_step(event)))
        self.root.bind("<KeyPress-Left>", lambda event: self.nudge_selected(-_key_step(event), 0))
        self.root.bind("<KeyPress-Right>", lambda event: self.nudge_selected(_key_step(event), 0))
        self.root.bind("<KeyPress-plus>", lambda event: self.zoom(1.15))
        self.root.bind("<KeyPress-minus>", lambda event: self.zoom(1 / 1.15))
        self.root.bind("<KeyPress-equal>", lambda event: self.zoom(1.15))
        self.root.bind("<Control-s>", lambda event: self.save_positions())
        self.root.bind("<KeyPress-Prior>", lambda event: self.raise_selected())
        self.root.bind("<KeyPress-Next>", lambda event: self.lower_selected())

    def _draw_all_tiles(self) -> None:
        self.canvas.delete("all")
        min_x = min(tile.x for tile in self.tiles)
        min_y = min(tile.y for tile in self.tiles)
        max_x = max(tile.x + tile.width for tile in self.tiles)
        max_y = max(tile.y + tile.height for tile in self.tiles)
        self.origin_x = min_x
        self.origin_y = min_y

        for index, tile in enumerate(self.tiles):
            self._draw_tile(index, tile)

        scaled_w = int((max_x - min_x) * self.view_scale + self.padding * 2)
        scaled_h = int((max_y - min_y) * self.view_scale + self.padding * 2)
        self.canvas.configure(scrollregion=(0, 0, max(scaled_w, 1000), max(scaled_h, 800)))
        self.status.set(f"Loaded {len(self.tiles)} tiles | view_scale={self.view_scale:.3f}")

    def _draw_tile(self, index: int, tile: ManualTile) -> None:
        image_bgr, _ = read_image_bgr(tile.tile.path)
        display_w = max(1, int(image_bgr.shape[1] * self.view_scale))
        display_h = max(1, int(image_bgr.shape[0] * self.view_scale))
        thumb = cv2.resize(image_bgr, (display_w, display_h), interpolation=cv2.INTER_AREA)
        tile.photo = _bgr_to_photo_image(thumb)
        sx, sy = self._full_to_canvas(tile.x, tile.y)
        tag = f"tile_{index}"
        tile.image_item = self.canvas.create_image(sx, sy, image=tile.photo, anchor="nw", tags=(tag, "tile"))
        tile.rect_item = self.canvas.create_rectangle(
            sx,
            sy,
            sx + display_w,
            sy + display_h,
            outline="#00ff88" if index == self.selected_index else "#dddddd",
            width=3 if index == self.selected_index else 1,
            tags=(tag, "tile"),
        )
        tile.label_item = self.canvas.create_text(
            sx + 6,
            sy + 6,
            text=tile.tile.filename,
            fill="#ffffff",
            anchor="nw",
            font=("Consolas", 10, "bold"),
            tags=(tag, "tile"),
        )

    def _full_to_canvas(self, x: float, y: float) -> tuple[float, float]:
        return (
            (x - self.origin_x) * self.view_scale + self.padding,
            (y - self.origin_y) * self.view_scale + self.padding,
        )

    def _tile_index_from_current(self) -> int | None:
        current = self.canvas.find_withtag("current")
        if not current:
            return None
        tags = self.canvas.gettags(current[0])
        for tag in tags:
            if tag.startswith("tile_"):
                return int(tag.split("_", 1)[1])
        return None

    def on_mouse_down(self, event: tk.Event) -> None:
        index = self._tile_index_from_current()
        if index is None:
            return
        self.select_tile(index)
        self.drag_start = (event.x, event.y)

    def on_mouse_drag(self, event: tk.Event) -> None:
        if self.selected_index is None or self.drag_start is None:
            return
        dx = event.x - self.drag_start[0]
        dy = event.y - self.drag_start[1]
        self.drag_start = (event.x, event.y)
        self._move_tile_display(self.selected_index, dx, dy)
        tile = self.tiles[self.selected_index]
        tile.x += dx / self.view_scale
        tile.y += dy / self.view_scale
        self.status.set(f"{tile.tile.filename}: x={tile.x:.1f}, y={tile.y:.1f}")

    def on_mouse_up(self, _event: tk.Event) -> None:
        self.drag_start = None

    def on_mouse_wheel(self, event: tk.Event) -> None:
        if event.state & 0x0004:
            self.zoom(1.08 if event.delta > 0 else 1 / 1.08)

    def select_tile(self, index: int) -> None:
        old = self.selected_index
        self.selected_index = index
        if old is not None:
            self._update_tile_outline(old)
        self._update_tile_outline(index)
        tile = self.tiles[index]
        self.status.set(f"Selected {tile.tile.filename}: x={tile.x:.1f}, y={tile.y:.1f}")

    def _update_tile_outline(self, index: int) -> None:
        tile = self.tiles[index]
        if tile.rect_item is None:
            return
        selected = index == self.selected_index
        self.canvas.itemconfigure(
            tile.rect_item,
            outline="#00ff88" if selected else "#dddddd",
            width=3 if selected else 1,
        )

    def _move_tile_display(self, index: int, dx: float, dy: float) -> None:
        tile = self.tiles[index]
        for item in (tile.image_item, tile.rect_item, tile.label_item):
            if item is not None:
                self.canvas.move(item, dx, dy)

    def nudge_selected(self, dx_full: float, dy_full: float) -> None:
        if self.selected_index is None:
            return
        tile = self.tiles[self.selected_index]
        tile.x += dx_full
        tile.y += dy_full
        self._move_tile_display(self.selected_index, dx_full * self.view_scale, dy_full * self.view_scale)
        self.status.set(f"{tile.tile.filename}: x={tile.x:.1f}, y={tile.y:.1f}")

    def raise_selected(self) -> None:
        if self.selected_index is None:
            return
        tile = self.tiles[self.selected_index]
        for item in (tile.image_item, tile.rect_item, tile.label_item):
            if item is not None:
                self.canvas.tag_raise(item)

    def lower_selected(self) -> None:
        if self.selected_index is None:
            return
        tile = self.tiles[self.selected_index]
        for item in (tile.image_item, tile.rect_item, tile.label_item):
            if item is not None:
                self.canvas.tag_lower(item)

    def zoom(self, factor: float) -> None:
        self.view_scale = min(0.75, max(0.04, self.view_scale * factor))
        self._draw_all_tiles()

    def center_view(self) -> None:
        self.canvas.xview_moveto(0.0)
        self.canvas.yview_moveto(0.0)

    def save_positions(self) -> Path:
        path = self.output_dir / "manual_positions.csv"
        write_manual_positions(path, self.tiles)
        self.status.set(f"Saved {path}")
        messagebox.showinfo("Saved", f"已儲存手動座標：\n{path}")
        return path

    def load_positions_dialog(self) -> None:
        filename = filedialog.askopenfilename(
            title="選擇 manual_positions.csv 或 placements.csv",
            filetypes=(("CSV", "*.csv"), ("All files", "*.*")),
        )
        if not filename:
            return
        positions = read_position_map(Path(filename))
        applied = 0
        for tile in self.tiles:
            if tile.tile.filename in positions:
                tile.x, tile.y = positions[tile.tile.filename]
                applied += 1
        self._draw_all_tiles()
        self.status.set(f"Loaded {applied} positions from {filename}")

    def export_mosaic(self) -> None:
        positions_path = self.save_positions()
        result = export_manual_alignment(
            input_dir=self.input_dir,
            positions_csv=positions_path,
            output_dir=self.output_dir / "manual_export",
            blend_mode=self.blend_mode,
            export_format="tif",
            crop=True,
        )
        self.status.set(f"Exported {result['preview']}")
        messagebox.showinfo(
            "Exported",
            f"已輸出人工拼接圖：\n{result['stitched']}\n\nPreview：\n{result['preview']}",
        )


def load_manual_tiles(input_dir: Path, placement_csv: Path | None) -> list[ManualTile]:
    tiles = discover_tiles(input_dir)
    position_map = read_position_map(placement_csv) if placement_csv and placement_csv.exists() else {}
    fallback_positions = _stage_fallback_positions(tiles)
    manual_tiles: list[ManualTile] = []
    for tile in tiles:
        image_bgr, _ = read_image_bgr(tile.path)
        x, y = position_map.get(tile.filename, fallback_positions[tile.filename])
        manual_tiles.append(
            ManualTile(
                tile=tile,
                x=float(x),
                y=float(y),
                width=int(image_bgr.shape[1]),
                height=int(image_bgr.shape[0]),
            )
        )
    _normalize_tile_positions(manual_tiles)
    return manual_tiles


def read_position_map(path: Path | None) -> dict[str, tuple[float, float]]:
    if path is None:
        return {}
    positions: dict[str, tuple[float, float]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            filename = (row.get("filename") or "").strip()
            if not filename:
                continue
            x_value = _first_existing(row, ("aligned_full_x", "manual_x", "x", "stage_x"))
            y_value = _first_existing(row, ("aligned_full_y", "manual_y", "y", "stage_y"))
            if x_value is None or y_value is None:
                continue
            positions[filename] = (float(x_value), float(y_value))
    return positions


def write_manual_positions(path: Path, tiles: list[ManualTile]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["index", "filename", "manual_x", "manual_y", "width", "height", "source_path"],
        )
        writer.writeheader()
        for index, tile in enumerate(tiles, start=1):
            writer.writerow(
                {
                    "index": index,
                    "filename": tile.tile.filename,
                    "manual_x": f"{tile.x:.6f}",
                    "manual_y": f"{tile.y:.6f}",
                    "width": tile.width,
                    "height": tile.height,
                    "source_path": str(tile.tile.path),
                }
            )


def export_manual_alignment(
    input_dir: Path,
    positions_csv: Path,
    output_dir: Path,
    blend_mode: str = "max_weight",
    export_format: str = "tif",
    crop: bool = True,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    tiles = discover_tiles(input_dir)
    positions = read_position_map(positions_csv)
    missing = [tile.filename for tile in tiles if tile.filename not in positions]
    if missing:
        raise ValueError(f"Positions missing for {len(missing)} tiles: {missing[:5]}")
    positions_full = np.array([positions[tile.filename] for tile in tiles], dtype=np.float64)
    config = StitchConfig(
        input_dir=input_dir,
        output_dir=output_dir,
        blend_mode=blend_mode,
        export_format=export_format,
        crop=crop,
    )
    final_path = output_dir / f"manual_stitched.{export_format}"
    preview_path = output_dir / "manual_stitched_preview.jpg"
    blend_info = compose_mosaic(tiles, positions_full, config, final_path, preview_path)
    summary_path = output_dir / "manual_stitch_summary.json"
    with summary_path.open("w", encoding="utf-8") as handle:
        json.dump(
            {
                "input_dir": str(input_dir),
                "positions_csv": str(positions_csv),
                "blend_mode": blend_mode,
                "export_format": export_format,
                "blend": blend_info,
                "stitched": str(final_path),
                "preview": str(preview_path),
            },
            handle,
            indent=2,
            ensure_ascii=False,
        )
    return {"stitched": final_path, "preview": preview_path, "summary": summary_path}


def _stage_fallback_positions(tiles: list[Tile]) -> dict[str, tuple[float, float]]:
    x_values = sorted(set(tile.x for tile in tiles))
    y_values = sorted(set(tile.y for tile in tiles))
    x_step = _median_step(x_values)
    y_step = _median_step(y_values)
    x_scale = 1000.0 / x_step if x_step else 1000.0
    y_scale = 700.0 / y_step if y_step else 700.0
    return {tile.filename: (tile.x * x_scale, tile.y * y_scale) for tile in tiles}


def _median_step(values: list[float]) -> float:
    diffs = [abs(b - a) for a, b in zip(values, values[1:]) if abs(b - a) > 1e-9]
    return float(np.median(diffs)) if diffs else 0.0


def _normalize_tile_positions(tiles: list[ManualTile]) -> None:
    min_x = min(tile.x for tile in tiles)
    min_y = min(tile.y for tile in tiles)
    for tile in tiles:
        tile.x -= min_x
        tile.y -= min_y


def _bgr_to_photo_image(image_bgr) -> tk.PhotoImage:
    ok, encoded = cv2.imencode(".png", image_bgr)
    if not ok:
        raise RuntimeError("Failed to encode tile thumbnail")
    data = base64.b64encode(encoded.tobytes()).decode("ascii")
    return tk.PhotoImage(data=data, format="PNG")


def _first_existing(row: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _key_step(event: tk.Event) -> int:
    return 10 if event.state & 0x0001 else 1

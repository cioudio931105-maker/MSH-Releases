from __future__ import annotations

import argparse
import csv
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .io_utils import create_output_paths, read_image, save_image, save_json
from .text_overlay import put_text


@dataclass(slots=True)
class CellAnalysisConfig:
    input_path: str | Path
    output_dir: str | Path = Path("output") / "cell_analysis"
    min_area_px: int = 700
    max_area_px: int = 250_000
    background_sigma_px: float = 14.0
    distance_ratio: float = 0.22
    morph_kernel_px: int = 3
    clahe_clip_limit: float = 2.0
    label_font_scale: float = 0.45

    def __post_init__(self) -> None:
        self.input_path = Path(self.input_path)
        self.output_dir = Path(self.output_dir)
        self.min_area_px = int(max(16, self.min_area_px))
        self.max_area_px = int(max(self.min_area_px, self.max_area_px))
        self.background_sigma_px = float(max(3.0, self.background_sigma_px))
        self.distance_ratio = float(min(0.80, max(0.05, self.distance_ratio)))
        self.morph_kernel_px = int(max(1, self.morph_kernel_px))
        self.clahe_clip_limit = float(max(0.1, self.clahe_clip_limit))
        self.label_font_scale = float(max(0.1, self.label_font_scale))


@dataclass(slots=True)
class CellMeasurement:
    cell_id: int
    area_px: int
    perimeter_px: float
    centroid_x: float
    centroid_y: float
    bbox_x: int
    bbox_y: int
    bbox_w: int
    bbox_h: int
    equivalent_diameter_px: float
    circularity: float
    mean_gray: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "cell_id": self.cell_id,
            "area_px": self.area_px,
            "perimeter_px": round(self.perimeter_px, 3),
            "centroid_x": round(self.centroid_x, 3),
            "centroid_y": round(self.centroid_y, 3),
            "bbox_x": self.bbox_x,
            "bbox_y": self.bbox_y,
            "bbox_w": self.bbox_w,
            "bbox_h": self.bbox_h,
            "equivalent_diameter_px": round(self.equivalent_diameter_px, 3),
            "circularity": round(self.circularity, 5),
            "mean_gray": round(self.mean_gray, 3),
        }


@dataclass(slots=True)
class CellAnalysisResult:
    success: bool
    input_path: str
    output_dir: str
    detected_cells: int
    overlay_path: str
    boxes_path: str
    mask_path: str
    labels_path: str
    summary_json_path: str
    measurements_csv_path: str
    message: str
    cells: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Single-image cell segmentation and measurement")
    parser.add_argument("--input_path", required=True, help="Path to the microscope image")
    parser.add_argument("--output_dir", default=str(Path("output") / "cell_analysis"), help="Directory for analysis outputs")
    parser.add_argument("--min_area_px", type=int, default=700, help="Minimum cell area in pixels before scale adjustment")
    parser.add_argument("--max_area_px", type=int, default=250000, help="Maximum cell area in pixels before scale adjustment")
    parser.add_argument("--background_sigma_px", type=float, default=14.0, help="Gaussian sigma used for background estimation before scale adjustment")
    parser.add_argument("--distance_ratio", type=float, default=0.22, help="Relative distance-transform threshold used to split touching cells")
    parser.add_argument("--morph_kernel_px", type=int, default=3, help="Morphology kernel size before scale adjustment")
    return parser


def _odd(value: int) -> int:
    value = int(max(1, value))
    return value if value % 2 == 1 else value + 1


def _scale_from_shape(shape: tuple[int, int]) -> float:
    min_dim = min(shape[:2])
    return max(0.5, min_dim / 640.0)


def _prepare_gray(image_bgr: np.ndarray, config: CellAnalysisConfig) -> tuple[np.ndarray, np.ndarray, float]:
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.medianBlur(gray, 5)
    scale = _scale_from_shape(gray.shape)
    sigma = max(3.0, config.background_sigma_px * scale)
    background = cv2.GaussianBlur(gray, (0, 0), sigmaX=sigma, sigmaY=sigma)
    cellness = cv2.subtract(background, gray)
    cellness = cv2.normalize(cellness, None, 0, 255, cv2.NORM_MINMAX)
    clahe = cv2.createCLAHE(clipLimit=config.clahe_clip_limit, tileGridSize=(8, 8))
    cellness = clahe.apply(cellness)
    return gray, cellness, scale


def _clean_binary_mask(binary_mask: np.ndarray, min_area_px: int, max_area_px: int) -> np.ndarray:
    component_count, labels, stats, _ = cv2.connectedComponentsWithStats(binary_mask, connectivity=8)
    cleaned = np.zeros_like(binary_mask)
    for label in range(1, component_count):
        area = int(stats[label, cv2.CC_STAT_AREA])
        if min_area_px <= area <= max_area_px:
            cleaned[labels == label] = 255
    return cleaned


def _segment_cell_labels(image_bgr: np.ndarray, config: CellAnalysisConfig) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    gray, cellness, scale = _prepare_gray(image_bgr, config)
    _, binary = cv2.threshold(cellness, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    kernel_size = _odd(round(config.morph_kernel_px * scale))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=1)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)

    min_area_px = int(round(config.min_area_px * scale * scale))
    max_area_px = int(round(config.max_area_px * scale * scale))
    cleaned = _clean_binary_mask(binary, min_area_px=min_area_px, max_area_px=max_area_px)

    distance = cv2.distanceTransform(cleaned, cv2.DIST_L2, 5)
    _, sure_fg = cv2.threshold(distance, config.distance_ratio * float(distance.max()), 255, cv2.THRESH_BINARY)
    sure_fg = sure_fg.astype(np.uint8)
    sure_bg = cv2.dilate(cleaned, kernel, iterations=2)
    unknown = cv2.subtract(sure_bg, sure_fg)

    _, markers = cv2.connectedComponents(sure_fg)
    markers = markers + 1
    markers[unknown == 255] = 0
    watershed_labels = cv2.watershed(image_bgr.copy(), markers)

    return gray, cleaned, watershed_labels, scale


def _contour_from_mask(mask: np.ndarray) -> np.ndarray | None:
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    return max(contours, key=cv2.contourArea)


def _measure_cells(gray: np.ndarray, labels: np.ndarray, scale: float, config: CellAnalysisConfig) -> tuple[list[CellMeasurement], np.ndarray]:
    min_area_px = int(round(config.min_area_px * scale * scale))
    max_area_px = int(round(config.max_area_px * scale * scale))

    cells: list[CellMeasurement] = []
    label_mask = np.zeros(labels.shape, dtype=np.int32)
    stable_id = 1

    for raw_label in sorted(int(value) for value in np.unique(labels) if value > 1):
        mask = np.uint8(labels == raw_label) * 255
        area = int(cv2.countNonZero(mask))
        if area < min_area_px or area > max_area_px:
            continue
        contour = _contour_from_mask(mask)
        if contour is None:
            continue
        perimeter = float(cv2.arcLength(contour, True))
        if perimeter <= 0.0:
            continue
        moments = cv2.moments(contour)
        if moments["m00"] <= 0.0:
            continue
        centroid_x = float(moments["m10"] / moments["m00"])
        centroid_y = float(moments["m01"] / moments["m00"])
        bbox_x, bbox_y, bbox_w, bbox_h = cv2.boundingRect(contour)
        circularity = float(4.0 * math.pi * area / max(perimeter * perimeter, 1.0))
        equivalent_diameter_px = float(math.sqrt(4.0 * area / math.pi))
        mean_gray = float(cv2.mean(gray, mask=mask)[0])

        cells.append(
            CellMeasurement(
                cell_id=stable_id,
                area_px=area,
                perimeter_px=perimeter,
                centroid_x=centroid_x,
                centroid_y=centroid_y,
                bbox_x=bbox_x,
                bbox_y=bbox_y,
                bbox_w=bbox_w,
                bbox_h=bbox_h,
                equivalent_diameter_px=equivalent_diameter_px,
                circularity=circularity,
                mean_gray=mean_gray,
            )
        )
        label_mask[mask > 0] = stable_id
        stable_id += 1

    cells.sort(key=lambda item: (item.centroid_y, item.centroid_x))
    remapped_label_mask = np.zeros_like(label_mask)
    ordered_cells: list[CellMeasurement] = []
    for new_id, cell in enumerate(cells, start=1):
        remapped_label_mask[label_mask == cell.cell_id] = new_id
        ordered_cells.append(
            CellMeasurement(
                cell_id=new_id,
                area_px=cell.area_px,
                perimeter_px=cell.perimeter_px,
                centroid_x=cell.centroid_x,
                centroid_y=cell.centroid_y,
                bbox_x=cell.bbox_x,
                bbox_y=cell.bbox_y,
                bbox_w=cell.bbox_w,
                bbox_h=cell.bbox_h,
                equivalent_diameter_px=cell.equivalent_diameter_px,
                circularity=cell.circularity,
                mean_gray=cell.mean_gray,
            )
        )
    return ordered_cells, remapped_label_mask


def _build_overlay(image_bgr: np.ndarray, label_mask: np.ndarray, cells: list[CellMeasurement], scale: float, config: CellAnalysisConfig) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    overlay = image_bgr.copy()
    box_overlay = image_bgr.copy()
    label_preview = np.zeros_like(image_bgr)
    rng = np.random.default_rng(42)
    color_table = {
        cell.cell_id: tuple(int(v) for v in rng.integers(80, 255, size=3))
        for cell in cells
    }

    line_thickness = max(1, int(round(scale * 1.5)))
    font_scale = config.label_font_scale * max(0.8, scale * 0.9)

    for cell in cells:
        mask = np.uint8(label_mask == cell.cell_id) * 255
        contour = _contour_from_mask(mask)
        if contour is None:
            continue
        color = color_table[cell.cell_id]
        cv2.drawContours(overlay, [contour], -1, (0, 255, 0), line_thickness)
        cv2.circle(overlay, (int(round(cell.centroid_x)), int(round(cell.centroid_y))), max(2, line_thickness + 1), (0, 0, 255), -1)
        put_text(
            overlay,
            str(cell.cell_id),
            (int(round(cell.centroid_x)) + 4, int(round(cell.centroid_y)) - 4),
            font_scale,
            (255, 255, 255),
            max(1, line_thickness),
        )
        cv2.rectangle(
            box_overlay,
            (cell.bbox_x, cell.bbox_y),
            (cell.bbox_x + cell.bbox_w, cell.bbox_y + cell.bbox_h),
            (0, 255, 255),
            line_thickness,
        )
        put_text(
            box_overlay,
            str(cell.cell_id),
            (cell.bbox_x + 4, max(18, cell.bbox_y - 6)),
            font_scale,
            (0, 255, 255),
            max(1, line_thickness),
        )
        label_preview[mask > 0] = color

    label_preview = cv2.addWeighted(image_bgr, 0.35, label_preview, 0.65, 0.0)
    summary_text = f"Detected cells: {len(cells)}"
    cv2.rectangle(overlay, (12, 12), (260, 48), (0, 0, 0), -1)
    put_text(overlay, summary_text, (18, 38), font_scale * 1.1, (255, 255, 255), max(1, line_thickness))
    cv2.rectangle(box_overlay, (12, 12), (260, 48), (0, 0, 0), -1)
    put_text(box_overlay, summary_text, (18, 38), font_scale * 1.1, (255, 255, 255), max(1, line_thickness))
    return overlay, box_overlay, label_preview


def _save_measurements_csv(path: Path, cells: list[CellMeasurement]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [cell.as_dict() for cell in cells]
    fieldnames = list(rows[0].keys()) if rows else [
        "cell_id",
        "area_px",
        "perimeter_px",
        "centroid_x",
        "centroid_y",
        "bbox_x",
        "bbox_y",
        "bbox_w",
        "bbox_h",
        "equivalent_diameter_px",
        "circularity",
        "mean_gray",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def analyze_cells(config: CellAnalysisConfig) -> CellAnalysisResult:
    image_bgr = read_image(config.input_path)
    gray, mask, labels, scale = _segment_cell_labels(image_bgr, config)
    cells, ordered_labels = _measure_cells(gray, labels, scale, config)
    overlay, box_overlay, label_preview = _build_overlay(image_bgr, ordered_labels, cells, scale, config)

    mask_image = np.uint8(ordered_labels > 0) * 255
    output_paths = create_output_paths(
        output_dir=config.output_dir,
        result_name="cell_overlay.png",
        shifts_json_name="cell_summary.json",
        shifts_csv_name="cell_measurements.csv",
        overlay_name="cell_labels.png",
        log_name="cell_analysis.log",
        debug_matches_dirname="debug_matches",
        intermediate_dirname="intermediate",
    )
    mask_path = output_paths.root / "cell_mask.png"
    boxes_path = output_paths.root / "cell_boxes.png"

    save_image(output_paths.result_path, overlay)
    save_image(boxes_path, box_overlay)
    save_image(output_paths.overlay_preview_path, label_preview)
    save_image(mask_path, mask_image)
    _save_measurements_csv(output_paths.shifts_csv_path, cells)

    areas = np.array([cell.area_px for cell in cells], dtype=np.float64)
    summary = {
        "input_path": str(Path(config.input_path).resolve()),
        "output_dir": str(output_paths.root.resolve()),
        "image_shape": list(image_bgr.shape),
        "detected_cells": len(cells),
        "total_mask_pixels": int(np.count_nonzero(mask_image)),
        "coverage_ratio": round(float(np.count_nonzero(mask_image) / mask_image.size), 6),
        "mean_area_px": round(float(areas.mean()), 3) if len(areas) else 0.0,
        "median_area_px": round(float(np.median(areas)), 3) if len(areas) else 0.0,
        "min_area_px": int(areas.min()) if len(areas) else 0,
        "max_area_px": int(areas.max()) if len(areas) else 0,
        "config": {
            "min_area_px": config.min_area_px,
            "max_area_px": config.max_area_px,
            "background_sigma_px": config.background_sigma_px,
            "distance_ratio": config.distance_ratio,
            "morph_kernel_px": config.morph_kernel_px,
        },
        "cells": [cell.as_dict() for cell in cells],
    }
    save_json(output_paths.shifts_json_path, summary)

    return CellAnalysisResult(
        success=True,
        input_path=str(Path(config.input_path).resolve()),
        output_dir=str(output_paths.root.resolve()),
        detected_cells=len(cells),
        overlay_path=str(output_paths.result_path.resolve()),
        boxes_path=str(boxes_path.resolve()),
        mask_path=str(mask_path.resolve()),
        labels_path=str(output_paths.overlay_preview_path.resolve()),
        summary_json_path=str(output_paths.shifts_json_path.resolve()),
        measurements_csv_path=str(output_paths.shifts_csv_path.resolve()),
        message="Cell analysis completed successfully",
        cells=[cell.as_dict() for cell in cells],
        summary=summary,
    )


def main() -> int:
    args = _parser().parse_args()
    config = CellAnalysisConfig(
        input_path=args.input_path,
        output_dir=args.output_dir,
        min_area_px=args.min_area_px,
        max_area_px=args.max_area_px,
        background_sigma_px=args.background_sigma_px,
        distance_ratio=args.distance_ratio,
        morph_kernel_px=args.morph_kernel_px,
    )
    result = analyze_cells(config)
    print(result.message)
    print(f"detected_cells={result.detected_cells}")
    print(f"overlay_path={result.overlay_path}")
    print(f"boxes_path={result.boxes_path}")
    print(f"mask_path={result.mask_path}")
    print(f"labels_path={result.labels_path}")
    print(f"summary_json_path={result.summary_json_path}")
    print(f"measurements_csv_path={result.measurements_csv_path}")
    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import threading
import time
import queue
import ctypes
import base64
import csv
import json
import math
import os
import shutil
import subprocess
import zipfile
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional
from xml.sax.saxutils import escape
import sys

import cv2
import numpy as np
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from arduino_stepper import ArduinoStepper, list_serial_ports

def _find_workspace_root(start: Path) -> Path:
    for candidate in [start.parent, *start.parents]:
        if (candidate / "cell_stitching_project").exists():
            return candidate
    return start.parents[4]


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = _find_workspace_root(Path(__file__).resolve())
for import_root in (PROJECT_ROOT, WORKSPACE_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from msh_runtime import default_output_dir


def _apply_windows_window_icon(window: tk.Tk, icon_path: Path) -> tuple[int, int] | None:
    if os.name != "nt" or not icon_path.is_file():
        return None
    try:
        image_icon = 1
        load_from_file = 0x0010
        icon_small = ctypes.windll.user32.LoadImageW(None, str(icon_path), image_icon, 16, 16, load_from_file)
        icon_large = ctypes.windll.user32.LoadImageW(None, str(icon_path), image_icon, 32, 32, load_from_file)
        window.update_idletasks()
        window_handle = window.winfo_id()
        message_set_icon = 0x0080
        ctypes.windll.user32.SendMessageW(window_handle, message_set_icon, 0, icon_small)
        ctypes.windll.user32.SendMessageW(window_handle, message_set_icon, 1, icon_large)
        return int(icon_small), int(icon_large)
    except Exception:
        return None


def _apply_windows_window_chrome(window: tk.Tk) -> bool:
    """Apply the MSH navy caption and thin cyan frame when Windows supports it."""
    if os.name != "nt":
        return False
    try:
        window.update_idletasks()
        dwmapi = ctypes.windll.dwmapi
        handle = ctypes.c_void_p(window.winfo_id())
        dark_mode = ctypes.c_int(1)
        border_cyan = ctypes.c_uint(0x00FFE81B)
        caption_navy = ctypes.c_uint(0x00271607)
        text_white = ctypes.c_uint(0x00F5F8FA)
        for attribute, value in ((20, dark_mode), (34, border_cyan), (35, caption_navy), (36, text_white)):
            dwmapi.DwmSetWindowAttribute(handle, attribute, ctypes.byref(value), ctypes.sizeof(value))
        return True
    except Exception:
        return False


try:
    from cell_stitching_project.text_overlay import install_cv2_unicode_puttext_patch, put_text

    install_cv2_unicode_puttext_patch()
except Exception:
    def put_text(
        image_bgr: np.ndarray,
        text: str,
        origin: tuple[int, int],
        font_scale: float,
        color_bgr: tuple[int, int, int],
        thickness: int = 1,
    ) -> None:
        cv2.putText(image_bgr, text, origin, cv2.FONT_HERSHEY_SIMPLEX, font_scale, color_bgr, thickness)

try:
    from cell_stitching_project.serpentine_recording import (
        path_total_distance,
        sample_path_at_distance,
        serpentine_path,
        serpentine_path_from_bounds,
    )
except Exception:
    path_total_distance = None  # type: ignore[assignment]
    sample_path_at_distance = None  # type: ignore[assignment]
    serpentine_path = None  # type: ignore[assignment]
    serpentine_path_from_bounds = None  # type: ignore[assignment]

try:
    from cell_stitching_project.wbc_serpentine_capture import (
        DEFAULT_CONFIG as WBC_CAPTURE_DEFAULT_CONFIG,
        METADATA_FIELDS as WBC_CAPTURE_METADATA_FIELDS,
        WHITE_BLOOD_CELL_CLASS,
        WBCDetection,
        calculate_wbc_centering_steps,
        crop_white_blood_cell_by_bbox,
        generate_vertical_serpentine_path,
        generate_vertical_serpentine_path_from_bounds,
        is_complete_white_blood_cell_detection,
        is_wbc_centered,
        select_wbc_centering_target,
        wbc_center_offset_px,
        wbc_detection_center,
        white_blood_cell_detection_status,
    )
except Exception:
    WBC_CAPTURE_DEFAULT_CONFIG = {}  # type: ignore[assignment]
    WBC_CAPTURE_METADATA_FIELDS = []  # type: ignore[assignment]
    WHITE_BLOOD_CELL_CLASS = "White_Blood_Cell"
    WBCDetection = None  # type: ignore[assignment]
    calculate_wbc_centering_steps = None  # type: ignore[assignment]
    crop_white_blood_cell_by_bbox = None  # type: ignore[assignment]
    generate_vertical_serpentine_path = None  # type: ignore[assignment]
    generate_vertical_serpentine_path_from_bounds = None  # type: ignore[assignment]
    is_complete_white_blood_cell_detection = None  # type: ignore[assignment]
    is_wbc_centered = None  # type: ignore[assignment]
    select_wbc_centering_target = None  # type: ignore[assignment]
    wbc_center_offset_px = None  # type: ignore[assignment]
    wbc_detection_center = None  # type: ignore[assignment]
    white_blood_cell_detection_status = None  # type: ignore[assignment]

try:
    from cell_identification.object_detection import (
        Detection,
        ObjectDetector,
        annotate_detections,
        build_detection_union_mask,
        compute_detection_coverage_ratio,
        resolve_detect_model_path,
        resolve_wbc_subtype_model_path,
    )
except Exception:
    Detection = None  # type: ignore[assignment]
    ObjectDetector = None  # type: ignore[assignment]
    annotate_detections = None  # type: ignore[assignment]
    build_detection_union_mask = None  # type: ignore[assignment]
    compute_detection_coverage_ratio = None  # type: ignore[assignment]
    resolve_detect_model_path = None  # type: ignore[assignment]
    resolve_wbc_subtype_model_path = None  # type: ignore[assignment]

_PREVIEW_WINDOW_NAME = "Basler Live Preview"
_PREVIEW_WINDOW_WIDTH = 960
_PREVIEW_WINDOW_HEIGHT = 540
_EMBEDDED_PREVIEW_MAX_WIDTH = 480
_EMBEDDED_PREVIEW_MAX_HEIGHT = 320
_EMBEDDED_PREVIEW_PLACEHOLDER_SIZE = 128
_PREVIEW_VIEW_ZOOM_STEP = 1.25
_PREVIEW_VIEW_MAX_ZOOM = 16.0
_PREVIEW_PROCESS_MAX_LONG_SIDE = 768
_PREVIEW_OVERLAY_FONT_SCALE = 2.8
_PREVIEW_OVERLAY_TEXT_THICKNESS = 7
_PREVIEW_OVERLAY_BOX_THICKNESS = 6
_PREVIEW_OVERLAY_MARGIN = 28
_PREVIEW_OVERLAY_LINE_HEIGHT = 86
_CAPTURE_SAVE_MAX_LONG_SIDE = 1536
_CAPTURE_PNG_COMPRESSION = 1
_BASLER_PREVIEW_FPS = 20.0
_BASLER_PREVIEW_EXPOSURE_UPPER_US = 50000.0
_BASLER_PREVIEW_EXPOSURE_LOWER_US = 100.0
_DEFAULT_X_BACKLASH_STEPS = 60
_DEFAULT_Y_BACKLASH_STEPS = 60
_NORMAL_MOTOR_SPEED_MS = 5
_FIXED_MANUAL_MOTOR_RPM = 0.02
_SERPENTINE_STARTUP_EXTRA_STEPS = 72
_SERPENTINE_VIDEO_TARGET_OVERLAP = 0.15
_SERPENTINE_VIDEO_OVERLAP_TOLERANCE = 0.04
_SERPENTINE_VIDEO_MIN_ADAPTIVE_STEPS = 1
_SERPENTINE_VIDEO_MAX_ADAPTIVE_STEPS = 24
_SERPENTINE_VIDEO_MIN_SHIFT_RESPONSE = 0.04
_DEFAULT_MOTOR_WARMUP_STEPS = 80
_DEFAULT_MOTOR_WARMUP_CYCLES = 1
_DEFAULT_APPROACH_PRELOAD_STEPS = 6
_SLIDE_SCAN_OVERLAP_RATIO = 0.35
_SLIDE_SCAN_PITCH_SCALE = 1.0 - _SLIDE_SCAN_OVERLAP_RATIO
_SLIDE_SCAN_TISSUE_THRESHOLD = 0.30
_SLIDE_SCAN_SPARSE_CONFIRMATION_TILES = 2
_SLIDE_SCAN_EMPTY_COLUMN_LIMIT = 2
_SLIDE_SCAN_MAX_TILES = 4000
_SLIDE_SCAN_INITIAL_SEARCH_TILES = 48
_SLIDE_SCAN_EDGE_MARGIN_TILES = 3
_WBC_COLLECTION_CROP_MARGIN_RATIO = 0.18
_WBC_COLLECTION_FOLDER = "White_Blood_Cell"
_MANUAL_TRAINING_CROP_MARGIN_RATIO = 0.12
_MANUAL_TRAINING_CLASSES = {
    "white_blood_cell": 0,
    "red_blood_cell": 1,
    "platelet": 2,
}
_MANUAL_TRAINING_FIELDS = (
    "created_at",
    "review_status",
    "source_image",
    "training_image",
    "crop_path",
    "yolo_label_path",
    "cell_class",
    "training_class_id",
    "model_class_id",
    "model_label",
    "confidence",
    "platform_x",
    "platform_y",
    "frame_width",
    "frame_height",
    "bbox_x1",
    "bbox_y1",
    "bbox_x2",
    "bbox_y2",
    "crop_x1",
    "crop_y1",
    "crop_x2",
    "crop_y2",
)
_FORMAL_STITCHER_ROOT = WORKSPACE_ROOT / "microscope_stitcher_project"
_FORMAL_STITCHER_SCRIPT = _FORMAL_STITCHER_ROOT / "run_formal_stitch.py"
_PRACTICAL_STITCHER_SCRIPT = _FORMAL_STITCHER_ROOT / "run_practical_stitch.py"
_FORMAL_GOLDEN_SESSION_NAME = "session_20260521_181641_759929"
_FORMAL_GOLDEN_PLACEMENTS = (
    _FORMAL_STITCHER_ROOT / "reference" / "session_20260521_181641_759929_golden_placements.csv"
)
_FORMAL_GOLDEN_COMPARE_SCRIPT = _FORMAL_STITCHER_ROOT / "tools" / "compare_against_golden.py"
_FORMAL_GOLDEN_EXCLUDED_FILENAMES = {"8_0.jpg"}


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


@dataclass(slots=True)
class SlideScanTileRecord:
    scan_index: int
    column_index: int
    row_index: int
    x: int
    y: int
    filename: str
    image_path: str
    frame_width: int
    frame_height: int
    detection_count: int
    coverage_ratio: float
    is_sparse: bool
    detections: list[dict[str, Any]]


@dataclass(slots=True)
class SlideScanColumnSpan:
    top_y: int
    bottom_y: int
    tile_count: int


def compute_slide_scan_pitch(base_steps: int, overlap_ratio: float = _SLIDE_SCAN_OVERLAP_RATIO) -> int:
    step_value = abs(int(base_steps))
    if step_value <= 0:
        raise ValueError("掃描步數必須大於 0。")
    return max(1, int(round(step_value * (1.0 - float(overlap_ratio)))))


def slide_scan_vertical_direction(column_index: int) -> int:
    return -1 if int(column_index) % 2 == 0 else 1


def slide_scan_should_advance_column(
    had_tissue: bool,
    consecutive_sparse: int,
    sparse_limit: int = _SLIDE_SCAN_SPARSE_CONFIRMATION_TILES,
) -> bool:
    return int(consecutive_sparse) >= max(1, int(sparse_limit))


def slide_scan_should_stop(
    empty_column_run: int,
    empty_column_limit: int = _SLIDE_SCAN_EMPTY_COLUMN_LIMIT,
) -> bool:
    return int(empty_column_run) >= max(1, int(empty_column_limit))


def slide_scan_column_entry_y(
    span: SlideScanColumnSpan,
    vertical_dir: int,
    y_pitch: int,
    margin_tiles: int = _SLIDE_SCAN_EDGE_MARGIN_TILES,
) -> int:
    edge_y = int(span.top_y if int(vertical_dir) < 0 else span.bottom_y)
    return edge_y - int(vertical_dir) * abs(int(y_pitch)) * max(0, int(margin_tiles))


def slide_scan_search_limit(
    previous_span: SlideScanColumnSpan | None,
    initial_search_tiles: int = _SLIDE_SCAN_INITIAL_SEARCH_TILES,
    edge_margin_tiles: int = _SLIDE_SCAN_EDGE_MARGIN_TILES,
) -> int:
    if previous_span is None:
        return max(4, int(initial_search_tiles))
    return max(4, int(previous_span.tile_count) + max(2, int(edge_margin_tiles) * 2))


def generate_serpentine_capture_coordinates(
    start_x: int,
    start_y: int,
    end_x: int,
    end_y: int,
    step_x: int,
    step_y: int,
) -> list[tuple[int, int]]:
    def _axis_positions(start_value: int, end_value: int, step_size: int) -> list[int]:
        start_value = int(start_value)
        end_value = int(end_value)
        if start_value == end_value:
            return [start_value]
        if int(step_size) <= 0:
            raise ValueError("蛇行拍攝步數必須大於 0。")

        positions = [start_value]
        current_value = start_value
        direction = 1 if end_value > start_value else -1
        stride = abs(int(step_size)) * direction
        while current_value != end_value:
            remaining = end_value - current_value
            if abs(remaining) <= abs(stride):
                current_value = end_value
            else:
                current_value += stride
            positions.append(int(current_value))
        return positions

    x_positions = [int(x) for x in _axis_positions(start_x, end_x, step_x)]
    y_positions = [int(y) for y in _axis_positions(start_y, end_y, step_y)]
    coordinates: list[tuple[int, int]] = []
    for row_index, y in enumerate(y_positions):
        current_row = x_positions if row_index % 2 == 0 else list(reversed(x_positions))
        for x in current_row:
            coordinates.append((int(x), int(y)))
    return coordinates


def classify_cell_detection(label: str, class_id: int | None = None) -> str | None:
    normalized = str(label or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "wbc": "white_blood_cell",
        "white_blood_cell": "white_blood_cell",
        "white_blood_cell_(wbc)": "white_blood_cell",
        "red_blood_cell": "red_blood_cell",
        "red_blood_cell_(rbc)": "red_blood_cell",
        "rbc": "red_blood_cell",
        "platelet": "platelet",
        "platelets": "platelet",
        "0": "white_blood_cell",
        "1": "red_blood_cell",
        "2": "platelet",
    }
    mapped = aliases.get(normalized)
    if mapped is not None:
        return mapped
    if class_id == 0:
        return "white_blood_cell"
    if class_id == 1:
        return "red_blood_cell"
    if class_id == 2:
        return "platelet"
    return None


def is_white_blood_cell_detection(detection: Any) -> bool:
    return classify_cell_detection(getattr(detection, "label", ""), getattr(detection, "cls_id", None)) == "white_blood_cell"


def detection_center(detection: Any) -> tuple[float, float]:
    return (
        (float(getattr(detection, "x1")) + float(getattr(detection, "x2"))) / 2.0,
        (float(getattr(detection, "y1")) + float(getattr(detection, "y2"))) / 2.0,
    )


def score_white_blood_cell_detection(detection: Any, image_shape: tuple[int, int] | tuple[int, int, int]) -> float:
    if not is_white_blood_cell_detection(detection):
        return 0.0
    height = max(1, int(image_shape[0]))
    width = max(1, int(image_shape[1]))
    cx, cy = detection_center(detection)
    center_distance = math.hypot((cx / width) - 0.5, (cy / height) - 0.5)
    center_bonus = max(0.0, 1.0 - center_distance * 2.0)
    box_area = max(0.0, float(getattr(detection, "x2")) - float(getattr(detection, "x1"))) * max(
        0.0,
        float(getattr(detection, "y2")) - float(getattr(detection, "y1")),
    )
    area_ratio = min(1.0, box_area / float(width * height))
    confidence = max(0.0, min(1.0, float(getattr(detection, "conf", 0.0))))
    return confidence * 2.0 + center_bonus + area_ratio * 4.0


def clip_detection_bbox(
    image_shape: tuple[int, int] | tuple[int, int, int],
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    margin_ratio: float = 0.10,
) -> tuple[int, int, int, int] | None:
    height = int(image_shape[0])
    width = int(image_shape[1])
    if int(x2) <= int(x1) or int(y2) <= int(y1):
        return None
    box_w = int(x2) - int(x1)
    box_h = int(y2) - int(y1)
    margin = max(2, int(round(min(box_w, box_h) * float(margin_ratio))))
    clipped = (
        max(0, int(x1) - margin),
        max(0, int(y1) - margin),
        min(width, int(x2) + margin),
        min(height, int(y2) + margin),
    )
    if clipped[2] <= clipped[0] or clipped[3] <= clipped[1]:
        return None
    return clipped


def wbc_collection_subfolder(detection: Any) -> str:
    return _WBC_COLLECTION_FOLDER


def save_wbc_collection_crops(
    collection_dir: Path,
    frame: np.ndarray,
    detections: list,
    source_image_path: Path,
    tile_index: int,
    platform_x: int,
    platform_y: int,
    margin_ratio: float = _WBC_COLLECTION_CROP_MARGIN_RATIO,
) -> list[dict[str, Any]]:
    crop_root = collection_dir / "crops"
    crop_root.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    frame_height, frame_width = frame.shape[:2]

    wbc_index = 0
    for detection in detections or []:
        if not is_white_blood_cell_detection(detection):
            continue
        clipped = clip_detection_bbox(
            frame.shape,
            int(getattr(detection, "x1", 0)),
            int(getattr(detection, "y1", 0)),
            int(getattr(detection, "x2", 0)),
            int(getattr(detection, "y2", 0)),
            margin_ratio=margin_ratio,
        )
        if clipped is None:
            continue

        wbc_index += 1
        crop_x1, crop_y1, crop_x2, crop_y2 = clipped
        crop = frame[crop_y1:crop_y2, crop_x1:crop_x2]
        if crop.size == 0:
            continue

        class_folder = wbc_collection_subfolder(detection)
        class_dir = crop_root / class_folder
        class_dir.mkdir(parents=True, exist_ok=True)
        crop_name = f"x{int(platform_x)}_y{int(platform_y)}_{wbc_index:03d}_{class_folder}.png"
        crop_path = class_dir / crop_name
        if not cv2.imwrite(str(crop_path), crop):
            continue

        center_x, center_y = detection_center(detection)
        records.append(
            {
                "tile_index": int(tile_index),
                "tile_wbc_index": int(wbc_index),
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "platform_x": int(platform_x),
                "platform_y": int(platform_y),
                "source_image": str(source_image_path.resolve()),
                "crop_path": str(crop_path.resolve()),
                "frame_width": int(frame_width),
                "frame_height": int(frame_height),
                "center_x": float(center_x),
                "center_y": float(center_y),
                "bbox_x1": int(getattr(detection, "x1", 0)),
                "bbox_y1": int(getattr(detection, "y1", 0)),
                "bbox_x2": int(getattr(detection, "x2", 0)),
                "bbox_y2": int(getattr(detection, "y2", 0)),
                "crop_x1": int(crop_x1),
                "crop_y1": int(crop_y1),
                "crop_x2": int(crop_x2),
                "crop_y2": int(crop_y2),
                "confidence": float(getattr(detection, "conf", 0.0)),
                "label": str(getattr(detection, "label", "")),
                "wbc_subtype": "",
                "wbc_subtype_confidence": None,
            }
        )
    return records


def _xlsx_column_name(index: int) -> str:
    name = ""
    value = int(index)
    while value > 0:
        value, remainder = divmod(value - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _xlsx_safe_text(value: Any) -> str:
    text = str(value if value is not None else "")
    return escape("".join(ch for ch in text if ch in "\t\n\r" or ord(ch) >= 32))


def _xlsx_cell(reference: str, value: Any, *, style: int = 0) -> str:
    style_attr = f' s="{style}"' if style else ""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f'<c r="{reference}"{style_attr}><v>{value}</v></c>'
    return f'<c r="{reference}" t="inlineStr"{style_attr}><is><t>{_xlsx_safe_text(value)}</t></is></c>'


def _xlsx_sheet_xml(rows: list[list[Any]], *, freeze_header: bool = True) -> str:
    max_columns = max((len(row) for row in rows), default=1)
    max_rows = max(1, len(rows))
    dimension = f"A1:{_xlsx_column_name(max_columns)}{max_rows}"
    sheet_rows: list[str] = []
    for row_index, row in enumerate(rows, start=1):
        cells = [
            _xlsx_cell(f"{_xlsx_column_name(column_index)}{row_index}", value, style=1 if row_index == 1 else 0)
            for column_index, value in enumerate(row, start=1)
        ]
        sheet_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    freeze_xml = (
        '<sheetViews><sheetView workbookViewId="0">'
        '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
        '</sheetView></sheetViews>'
        if freeze_header
        else '<sheetViews><sheetView workbookViewId="0"/></sheetViews>'
    )
    auto_filter = f'<autoFilter ref="{dimension}"/>' if rows else ""
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<dimension ref="{dimension}"/>{freeze_xml}'
        '<cols><col min="1" max="5" width="24" customWidth="1"/>'
        '<col min="6" max="22" width="16" customWidth="1"/></cols>'
        f'<sheetData>{"".join(sheet_rows)}</sheetData>{auto_filter}</worksheet>'
    )


def write_manual_training_xlsx(records: list[dict[str, Any]], xlsx_path: Path) -> Path:
    xlsx_path.parent.mkdir(parents=True, exist_ok=True)
    detail_rows = [list(_MANUAL_TRAINING_FIELDS)]
    detail_rows.extend([[record.get(field, "") for field in _MANUAL_TRAINING_FIELDS] for record in records])
    counts = {
        cell_class: sum(1 for record in records if record.get("cell_class") == cell_class)
        for cell_class in _MANUAL_TRAINING_CLASSES
    }
    summary_rows = [
        ["三分類拍照預標註資料集", ""],
        ["用途", "供人工確認後持續訓練辨識模型"],
        ["重要提醒", "這些資料由現有模型自動產生，續訓前必須人工檢查與修正。"],
        ["總裁圖數", len(records)],
        ["white_blood_cell", counts["white_blood_cell"]],
        ["red_blood_cell", counts["red_blood_cell"]],
        ["platelet", counts["platelet"]],
    ]
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>"""
    package_relationships = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""
    workbook_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="summary" sheetId="1" r:id="rId1"/>
    <sheet name="cells" sheetId="2" r:id="rId2"/>
  </sheets>
</workbook>"""
    workbook_relationships = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""
    styles_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts>
  <fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FFD9EAD3"/><bgColor indexed="64"/></patternFill></fill></fills>
  <borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/></cellXfs>
  <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>"""
    with zipfile.ZipFile(xlsx_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", package_relationships)
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_relationships)
        archive.writestr("xl/styles.xml", styles_xml)
        archive.writestr("xl/worksheets/sheet1.xml", _xlsx_sheet_xml(summary_rows, freeze_header=False))
        archive.writestr("xl/worksheets/sheet2.xml", _xlsx_sheet_xml(detail_rows))
    return xlsx_path.resolve()


def save_manual_three_class_training_data(
    session_dir: Path,
    source_image_path: Path,
    frame: np.ndarray,
    detections: list,
    platform_x: int,
    platform_y: int,
) -> tuple[list[dict[str, Any]], Path, Path]:
    training_dir = session_dir / "training_dataset"
    crop_root = training_dir / "crops"
    image_dir = training_dir / "images"
    label_dir = training_dir / "labels"
    for cell_class in _MANUAL_TRAINING_CLASSES:
        (crop_root / cell_class).mkdir(parents=True, exist_ok=True)
    image_dir.mkdir(parents=True, exist_ok=True)
    label_dir.mkdir(parents=True, exist_ok=True)

    training_image_path = image_dir / source_image_path.name
    if not training_image_path.exists():
        try:
            os.link(source_image_path, training_image_path)
        except OSError:
            shutil.copy2(source_image_path, training_image_path)
    yolo_label_path = label_dir / f"{source_image_path.stem}.txt"
    csv_path = training_dir / "training_manifest.csv"
    xlsx_path = training_dir / "training_manifest.xlsx"
    frame_height, frame_width = frame.shape[:2]
    records: list[dict[str, Any]] = []
    yolo_lines: list[str] = []
    class_counts = {cell_class: 0 for cell_class in _MANUAL_TRAINING_CLASSES}

    for detection in detections or []:
        cell_class = classify_cell_detection(
            str(getattr(detection, "label", "")),
            getattr(detection, "cls_id", None),
        )
        if cell_class not in _MANUAL_TRAINING_CLASSES:
            continue
        class_counts[cell_class] += 1
        clipped = clip_detection_bbox(
            frame.shape,
            int(getattr(detection, "x1", 0)),
            int(getattr(detection, "y1", 0)),
            int(getattr(detection, "x2", 0)),
            int(getattr(detection, "y2", 0)),
            margin_ratio=_MANUAL_TRAINING_CROP_MARGIN_RATIO,
        )
        if clipped is None:
            continue
        crop_x1, crop_y1, crop_x2, crop_y2 = clipped
        crop = frame[crop_y1:crop_y2, crop_x1:crop_x2]
        if crop.size == 0:
            continue
        crop_name = f"{source_image_path.stem}_{cell_class}_{class_counts[cell_class]:04d}.png"
        crop_path = crop_root / cell_class / crop_name
        if not cv2.imwrite(str(crop_path), crop, [cv2.IMWRITE_PNG_COMPRESSION, _CAPTURE_PNG_COMPRESSION]):
            continue

        x1 = max(0.0, min(float(frame_width), float(getattr(detection, "x1", 0))))
        y1 = max(0.0, min(float(frame_height), float(getattr(detection, "y1", 0))))
        x2 = max(0.0, min(float(frame_width), float(getattr(detection, "x2", 0))))
        y2 = max(0.0, min(float(frame_height), float(getattr(detection, "y2", 0))))
        box_width = max(0.0, x2 - x1)
        box_height = max(0.0, y2 - y1)
        center_x = (x1 + x2) / 2.0
        center_y = (y1 + y2) / 2.0
        training_class_id = _MANUAL_TRAINING_CLASSES[cell_class]
        yolo_lines.append(
            f"{training_class_id} {center_x / frame_width:.8f} {center_y / frame_height:.8f} "
            f"{box_width / frame_width:.8f} {box_height / frame_height:.8f}"
        )
        records.append(
            {
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "review_status": "待人工確認",
                "source_image": str(source_image_path.resolve()),
                "training_image": str(training_image_path.resolve()),
                "crop_path": str(crop_path.resolve()),
                "yolo_label_path": str(yolo_label_path.resolve()),
                "cell_class": cell_class,
                "training_class_id": int(training_class_id),
                "model_class_id": int(getattr(detection, "cls_id", -1)),
                "model_label": str(getattr(detection, "label", "")),
                "confidence": f"{float(getattr(detection, 'conf', 0.0)):.6f}",
                "platform_x": int(platform_x),
                "platform_y": int(platform_y),
                "frame_width": int(frame_width),
                "frame_height": int(frame_height),
                "bbox_x1": f"{x1:.3f}",
                "bbox_y1": f"{y1:.3f}",
                "bbox_x2": f"{x2:.3f}",
                "bbox_y2": f"{y2:.3f}",
                "crop_x1": int(crop_x1),
                "crop_y1": int(crop_y1),
                "crop_x2": int(crop_x2),
                "crop_y2": int(crop_y2),
            }
        )

    yolo_label_path.write_text("\n".join(yolo_lines) + ("\n" if yolo_lines else ""), encoding="utf-8")
    (training_dir / "data.yaml").write_text(
        "path: .\n"
        "train: images\n"
        "val: images  # 收集階段暫用；正式訓練前請拆分獨立 validation set\n"
        "names:\n"
        "  0: white_blood_cell\n"
        "  1: red_blood_cell\n"
        "  2: platelet\n",
        encoding="utf-8",
    )
    write_header = not csv_path.exists()
    with csv_path.open("a", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(_MANUAL_TRAINING_FIELDS))
        if write_header:
            writer.writeheader()
        writer.writerows(records)
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        all_records = list(csv.DictReader(handle))
    write_manual_training_xlsx(all_records, xlsx_path)
    return records, csv_path.resolve(), xlsx_path.resolve()


def generate_spiral_search_offsets(radius_steps: int, step_steps: int) -> list[tuple[int, int]]:
    radius = max(0, int(radius_steps))
    step = max(1, abs(int(step_steps)))
    offsets: list[tuple[int, int]] = [(0, 0)]
    seen = {(0, 0)}
    for ring in range(step, radius + step, step):
        ring = min(ring, radius)
        points: list[tuple[int, int]] = []
        for x in range(-ring, ring + 1, step):
            points.append((x, -ring))
            points.append((x, ring))
        for y in range(-ring + step, ring, step):
            points.append((-ring, y))
            points.append((ring, y))
        for point in sorted(points, key=lambda item: (math.atan2(item[1], item[0]), item[0], item[1])):
            if point not in seen:
                offsets.append(point)
                seen.add(point)
    return offsets


class _PylonVideoCapture:
    def __init__(self, camera: object, converter: object) -> None:
        self._camera = camera
        self._converter = converter

    def read(self):  # -> tuple[bool, object]
        from pypylon import pylon

        try:
            grab = self._camera.RetrieveResult(2000, pylon.TimeoutHandling_ThrowException)
        except Exception:
            return False, None
        try:
            if not grab.GrabSucceeded():
                return False, None
            image = self._converter.Convert(grab)
            frame = image.GetArray()
            return True, frame
        finally:
            try:
                grab.Release()
            except Exception:
                pass

    def warmup(self, frames: int = 8) -> None:
        for _ in range(max(1, frames)):
            ok, _frame = self.read()
            if not ok:
                time.sleep(0.05)

    def release(self) -> None:
        try:
            self._camera.StopGrabbing()
        except Exception:
            pass
        try:
            self._camera.Close()
        except Exception:
            pass


class StepperDragGUI:
    def __init__(self, root: Optional[tk.Tk] = None) -> None:
        self.root = root if root is not None else tk.Tk()
        self.root.title("MSH")
        icon_path = WORKSPACE_ROOT / "assets" / "msh-pixel-icon.ico"
        icon_png_path = WORKSPACE_ROOT / "assets" / "msh-pixel-icon.png"
        if icon_path.is_file():
            self.root.iconbitmap(str(icon_path))
        if icon_png_path.is_file():
            self._window_icon_image = tk.PhotoImage(file=str(icon_png_path))
            self.root.iconphoto(True, self._window_icon_image)
        self._window_icon_handles = _apply_windows_window_icon(self.root, icon_path)
        self._window_chrome_applied = _apply_windows_window_chrome(self.root)
        window_width, window_height = 1040, 780
        frame_width, frame_height = window_width, window_height
        if os.name == "nt":
            try:
                user32 = ctypes.windll.user32
                frame_width += user32.GetSystemMetrics(32) * 2 + 8
                frame_height += user32.GetSystemMetrics(33) * 2 + user32.GetSystemMetrics(4) + 7
            except Exception:
                pass
        screen_x = max(0, (self.root.winfo_screenwidth() - frame_width) // 2)
        screen_y = max(0, (self.root.winfo_screenheight() - frame_height) // 2)
        self.root.geometry(f"{window_width}x{window_height}+{screen_x}+{screen_y}")

        self.axis_names = {0: "X", 1: "Y"}
        self.port_vars = {
            0: tk.StringVar(),
            1: tk.StringVar(),
        }
        self.baud_var = tk.IntVar(value=115200)
        self.steps_var = tk.IntVar(value=8)
        self.y_steps_var = tk.IntVar(value=8)
        self.x_backlash_var = tk.IntVar(value=_DEFAULT_X_BACKLASH_STEPS)
        self.y_backlash_var = tk.IntVar(value=_DEFAULT_Y_BACKLASH_STEPS)
        self.motion_stabilize_var = tk.BooleanVar(value=True)
        self.fixed_approach_var = tk.BooleanVar(value=False)
        self.warmup_steps_var = tk.IntVar(value=_DEFAULT_MOTOR_WARMUP_STEPS)
        self.warmup_cycles_var = tk.IntVar(value=_DEFAULT_MOTOR_WARMUP_CYCLES)
        self.approach_preload_steps_var = tk.IntVar(value=_DEFAULT_APPROACH_PRELOAD_STEPS)
        self.feedback_sample_count_var = tk.IntVar(value=10)
        self.x_approach_direction_var = tk.IntVar(value=1)
        self.y_approach_direction_var = tk.IntVar(value=1)
        self.settle_ms_var = tk.IntVar(value=200)
        self.pingpong_var = tk.BooleanVar(value=False)
        self.continuous_test_rpm_var = tk.DoubleVar(value=4.0)
        self.continuous_test_status_var = tk.StringVar(value="持續旋轉測試：停止")
        self.manual_motion_status_var = tk.StringVar(value="手動低速移動：待命（固定 0.02 RPM）")
        self._manual_motion_lock = threading.Lock()
        self._manual_motion_generation: dict[int, int] = {0: 0, 1: 0}
        self._manual_motion_direction: dict[int, Optional[int]] = {0: None, 1: None}
        self.camera_index_var = tk.IntVar(value=-1)
        self.auto_cycles_var = tk.IntVar(value=0)
        self.auto_interval_ms_var = tk.IntVar(value=500)
        self.capture_count_var = tk.StringVar(value="500")
        self.capture_start_x_var = tk.StringVar(value="0")
        self.capture_start_y_var = tk.StringVar(value="0")
        self.capture_end_x_var = tk.StringVar(value="0")
        self.capture_end_y_var = tk.StringVar(value="0")
        self.capture_output_dir_var = tk.StringVar()
        self.stitch_output_dir_var = tk.StringVar()
        self.serpentine_video_start_x_var = tk.IntVar(value=0)
        self.serpentine_video_start_y_var = tk.IntVar(value=0)
        self.serpentine_video_end_x_var = tk.IntVar(value=5000)
        self.serpentine_video_end_y_var = tk.IntVar(value=2000)
        self.serpentine_video_rows_var = tk.IntVar(value=3)
        self.serpentine_video_cols_var = tk.IntVar(value=4)
        self.serpentine_video_step_x_var = tk.IntVar(value=200)
        self.serpentine_video_step_y_var = tk.IntVar(value=6)
        self.serpentine_video_speed_var = tk.DoubleVar(value=4.0)
        self.serpentine_video_fps_var = tk.DoubleVar(value=20.0)
        self.serpentine_video_output_var = tk.StringVar()
        self.serpentine_video_status_var = tk.StringVar(value="蛇形連續錄影：未開始")
        self.preferred_basler_model = "aca3088-57uc"
        self.object_detect_preview_var = tk.BooleanVar(value=True)
        self.object_detect_save_var = tk.BooleanVar(value=True)
        self.object_detect_conf_var = tk.DoubleVar(value=0.25)
        self.object_detect_confidence_display_var = tk.StringVar(value="目前偵測信心值：尚無結果")
        self.wbc_subtype_conf_var = tk.DoubleVar(value=0.0)
        default_detect_weight = PROJECT_ROOT / "models" / "wbc_focus_yolov8n_e_20260611.pt"
        default_detect_model = (
            str(default_detect_weight)
            if default_detect_weight.exists()
            else (
                resolve_detect_model_path(PROJECT_ROOT, None)
                if resolve_detect_model_path is not None
                else "yolov8n.pt"
            )
        )
        self.object_detect_model_var = tk.StringVar(value=str(default_detect_model))
        self.object_detect_model_status_var = tk.StringVar(
            value=f"目前模型: {Path(str(default_detect_model)).name}"
        )
        self.wbc_subtype_model_var = tk.StringVar(value="")
        self.wbc_subtype_model_status_var = tk.StringVar(value="WBC 統一分類：White_Blood_Cell")
        self.wbc_capture_experiment_var = tk.StringVar(
            value=str(WBC_CAPTURE_DEFAULT_CONFIG.get("experiment_name", "sample_01"))
        )
        self.wbc_capture_status_var = tk.StringVar(value="白血球蛇行捕捉：未開始")
        self.wbc_capture_count_var = tk.StringVar(value="已拍攝白血球數量：0")

        self.log_text: Optional[tk.Text] = None
        self.status_vars = {
            0: tk.StringVar(value="X-motor: 未連線"),
            1: tk.StringVar(value="Y-motor: 未連線"),
        }

        self.stepper_by_axis: dict[int, Optional[ArduinoStepper]] = {0: None, 1: None}
        self.port_combos: dict[int, ttk.Combobox] = {}
        self._output_path_widgets: dict[str, tuple[ttk.Entry, ttk.Button]] = {}
        self.cap: Optional[cv2.VideoCapture] = None
        self._camera_lock = threading.Lock()

        self._preview_running = False
        self._preview_stop = threading.Event()
        self._preview_thread: Optional[threading.Thread] = None
        self._preview_inference_stop = threading.Event()
        self._preview_inference_thread: Optional[threading.Thread] = None
        self._preview_inference_queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=1)
        self._preview_detection_lock = threading.Lock()
        self._preview_detections: list = []
        self._preview_display_lock = threading.Lock()
        self._preview_display_frame: Optional[np.ndarray] = None
        self._preview_display_message = "尚未開始預覽"
        self._preview_display_label: Optional[tk.Label] = None
        self._preview_display_frame_widget: Optional[tk.Frame] = None
        self._preview_placeholder_image: Optional[tk.PhotoImage] = None
        self._preview_photo_image: Optional[tk.PhotoImage] = None
        self._preview_view_window: Optional[tk.Toplevel] = None
        self._preview_view_canvas: Optional[tk.Canvas] = None
        self._preview_view_photo_image: Optional[tk.PhotoImage] = None
        self._preview_view_zoom = 1.0
        self._preview_view_center = (0.5, 0.5)
        self._preview_view_drag_start: Optional[tuple[int, int]] = None
        self.preview_display_status_var = tk.StringVar(value="尚未開始預覽")

        self._auto_running = False
        self._auto_stop = threading.Event()
        self._auto_thread: Optional[threading.Thread] = None
        self._backlash_calibration_running = False
        self._backlash_calibration_thread: Optional[threading.Thread] = None
        self._image_feedback_running = False
        self._image_feedback_thread: Optional[threading.Thread] = None
        self._motor_warmup_running = False
        self._motor_warmup_thread: Optional[threading.Thread] = None
        self._capture_job_running = False
        self._capture_job_thread: Optional[threading.Thread] = None
        self._capture_job_stop = threading.Event()
        self._serpentine_video_running = False
        self._serpentine_video_thread: Optional[threading.Thread] = None
        self._serpentine_video_stop = threading.Event()
        self._serpentine_video_pause = threading.Event()
        self._serpentine_video_restart = threading.Event()
        self._serpentine_video_display_lock = threading.Lock()
        self._serpentine_video_display_frame: Optional[np.ndarray] = None
        self._serpentine_video_display_active = False
        self._serpentine_video_display_window = "Serpentine Continuous Recording"
        self._serpentine_video_display_window_open = False
        self._wbc_capture_running = False
        self._wbc_capture_thread: Optional[threading.Thread] = None
        self._wbc_capture_stop = threading.Event()
        self._wbc_capture_manual_capture = threading.Event()
        self._wbc_capture_resume = threading.Event()
        self._wbc_capture_waiting_manual_capture = False
        self._wbc_capture_waiting_resume = False
        self._wbc_capture_count = 0
        self._wbc_capture_latest_output_dir: Optional[Path] = None
        self._wbc_capture_detector: Optional[ObjectDetector] = None
        self._wbc_capture_detector_key: Optional[tuple[str, float]] = None
        self._wbc_capture_display_window = "White Blood Cell Capture"
        self._wbc_capture_last_move_axis: Optional[int] = None
        self._wbc_capture_resume_y_forward_compensation_pending = False
        self._coord_lock = threading.Lock()
        self._virtual_x = 0
        self._virtual_y = 0
        self._manual_capture_session: Optional[Path] = None
        self._latest_capture_session: Optional[Path] = None
        self._latest_stitch_output_dir: Optional[Path] = None
        self._wbc_memory_session_dir: Optional[Path] = None
        self._wbc_memory_records: list[dict[str, Any]] = []
        self._wbc_memory_lock = threading.Lock()
        self._camera_backends = self._build_camera_backends()
        self._detector_lock = threading.Lock()
        self._detector_inference_lock = threading.Lock()
        self._object_detector: Optional[ObjectDetector] = None
        self._object_detector_key: Optional[tuple[str, float, str, float]] = None
        self._detector_unavailable_logged = False

        self._build_ui()
        self._bind_keyboard_shortcuts()
        self.root.after(100, self._refresh_ports_async)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_camera_backends(self) -> list[tuple[str, Optional[int]]]:
        backends: list[tuple[str, Optional[int]]] = []
        if hasattr(cv2, "CAP_DSHOW"):
            backends.append(("DSHOW", cv2.CAP_DSHOW))
        if hasattr(cv2, "CAP_MSMF"):
            backends.append(("MSMF", cv2.CAP_MSMF))
        if not backends:
            backends.append(("DEFAULT", None))
        return backends

    def _build_ui(self) -> None:
        scroll_container = ttk.Frame(self.root)
        scroll_container.pack(fill=tk.BOTH, expand=True)

        scroll_canvas = tk.Canvas(scroll_container, highlightthickness=0, borderwidth=0)
        yscroll_main = ttk.Scrollbar(scroll_container, orient=tk.VERTICAL, command=scroll_canvas.yview)
        xscroll_main = ttk.Scrollbar(scroll_container, orient=tk.HORIZONTAL, command=scroll_canvas.xview)
        scroll_canvas.configure(yscrollcommand=yscroll_main.set, xscrollcommand=xscroll_main.set)

        yscroll_main.pack(side=tk.RIGHT, fill=tk.Y)
        xscroll_main.pack(side=tk.BOTTOM, fill=tk.X)
        scroll_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        frame = ttk.Frame(scroll_canvas, padding=12)
        scroll_window = scroll_canvas.create_window((0, 0), window=frame, anchor=tk.NW)

        def _update_scroll_region(_event: tk.Event | None = None) -> None:
            scroll_canvas.configure(scrollregion=scroll_canvas.bbox("all"))

        def _keep_minimum_width(event: tk.Event) -> None:
            requested_width = max(frame.winfo_reqwidth(), int(event.width))
            scroll_canvas.itemconfigure(scroll_window, width=requested_width)
            _update_scroll_region()

        def _on_mouse_wheel(event: tk.Event) -> None:
            delta = int(getattr(event, "delta", 0))
            if delta == 0:
                return
            units = -1 * int(delta / 120) if abs(delta) >= 120 else (-1 if delta > 0 else 1)
            if int(getattr(event, "state", 0)) & 0x0001:
                scroll_canvas.xview_scroll(units, "units")
            else:
                scroll_canvas.yview_scroll(units, "units")

        def _on_shift_mouse_wheel(event: tk.Event) -> str:
            delta = int(getattr(event, "delta", 0))
            if delta:
                units = -1 * int(delta / 120) if abs(delta) >= 120 else (-1 if delta > 0 else 1)
                scroll_canvas.xview_scroll(units, "units")
            return "break"

        frame.bind("<Configure>", _update_scroll_region)
        scroll_canvas.bind("<Configure>", _keep_minimum_width)
        self.root.bind_all("<MouseWheel>", _on_mouse_wheel, add="+")
        self.root.bind_all("<Shift-MouseWheel>", _on_shift_mouse_wheel, add="+")
        self.root.bind_all("<Button-4>", lambda _event: scroll_canvas.yview_scroll(-1, "units"), add="+")
        self.root.bind_all("<Button-5>", lambda _event: scroll_canvas.yview_scroll(1, "units"), add="+")

        serial_group = ttk.LabelFrame(frame, text="步進馬達")
        serial_group.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(serial_group, text="X-motor COM 連接埠").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.port_combos[0] = ttk.Combobox(
            serial_group, textvariable=self.port_vars[0], state="readonly", width=14
        )
        self.port_combos[0].grid(row=0, column=1, sticky=tk.W, padx=(6, 4), pady=2)
        ttk.Button(serial_group, text="僅連接 X", command=lambda: self._connect(0)).grid(row=0, column=2, padx=(0, 4))
        ttk.Button(serial_group, text="X-motor 斷線", command=lambda: self._disconnect(0)).grid(row=0, column=3, padx=(0, 4))
        ttk.Button(serial_group, text="重新整理", command=self._refresh_ports_async).grid(row=0, column=4, padx=(0, 4))
        ttk.Button(serial_group, text="連接 X/Y 馬達", command=self._connect_selected_axes).grid(row=0, column=5, padx=(0, 4))
        ttk.Button(serial_group, text="全部斷線", command=self._disconnect).grid(row=0, column=6)
        ttk.Label(serial_group, textvariable=self.status_vars[0]).grid(row=1, column=0, columnspan=4, sticky=tk.W, padx=(6, 0))

        ttk.Label(serial_group, text="Y-motor COM 連接埠").grid(row=2, column=0, sticky=tk.W, pady=(10, 2))
        self.port_combos[1] = ttk.Combobox(
            serial_group, textvariable=self.port_vars[1], state="readonly", width=14
        )
        self.port_combos[1].grid(row=2, column=1, sticky=tk.W, padx=(6, 4), pady=(10, 2))
        ttk.Button(serial_group, text="僅連接 Y", command=lambda: self._connect(1)).grid(row=2, column=2, padx=(0, 4))
        ttk.Button(serial_group, text="Y-motor 斷線", command=lambda: self._disconnect(1)).grid(row=2, column=3)
        ttk.Label(serial_group, textvariable=self.status_vars[1]).grid(row=3, column=0, columnspan=4, sticky=tk.W, padx=(6, 0), pady=(0, 10))

        motor_controls = ttk.Frame(serial_group)
        motor_controls.grid(row=5, column=0, columnspan=6, sticky=tk.W)
        ttk.Label(motor_controls, text="固定低速移動（0.02 RPM）：按住移動，放開立即停止並保持通電。").grid(
            row=0, column=0, columnspan=6, sticky=tk.W, pady=(2, 4)
        )
        self._bind_hold_to_move(ttk.Button(motor_controls, text="X 前進"), 0, 1).grid(row=1, column=0, padx=(0, 6), pady=2)
        self._bind_hold_to_move(ttk.Button(motor_controls, text="X 後退"), 0, -1).grid(row=1, column=1, padx=(0, 14), pady=2)
        self._bind_hold_to_move(ttk.Button(motor_controls, text="Y 前進"), 1, 1).grid(row=1, column=2, padx=(0, 6), pady=2)
        self._bind_hold_to_move(ttk.Button(motor_controls, text="Y 後退"), 1, -1).grid(row=1, column=3, padx=(0, 14), pady=2)
        ttk.Button(motor_controls, text="釋放 X/Y 馬達", command=self._release_all_continuous_motors).grid(row=1, column=4, padx=(0, 6), pady=2)
        ttk.Label(motor_controls, textvariable=self.manual_motion_status_var).grid(row=2, column=0, columnspan=6, sticky=tk.W, pady=(2, 0))
        ttk.Label(motor_controls, text="方向鍵：左／右 = X、上／下 = Y；關閉或斷線時會停止並釋放線圈。").grid(
            row=3, column=0, columnspan=6, sticky=tk.W, pady=(2, 6)
        )

        # Preserve the independent continuous-test widgets and handlers without
        # showing this legacy test panel in the production GUI.
        continuous_group = ttk.LabelFrame(frame, text="28BYJ-48 持續旋轉測試（需使用 continuous 新版韌體）")
        ttk.Label(continuous_group, text="測試轉速 RPM").grid(row=0, column=0, sticky=tk.W, padx=(6, 2), pady=6)
        ttk.Spinbox(
            continuous_group,
            from_=0.01,
            to=15.0,
            increment=0.01,
            textvariable=self.continuous_test_rpm_var,
            width=8,
        ).grid(row=0, column=1, sticky=tk.W, padx=(4, 8), pady=6)
        ttk.Button(
            continuous_group,
            text="X 正轉",
            command=lambda: self._start_continuous_motor_test(0, 1),
        ).grid(row=0, column=2, padx=4, pady=(4, 2))
        ttk.Button(
            continuous_group,
            text="X 反轉",
            command=lambda: self._start_continuous_motor_test(0, -1),
        ).grid(row=0, column=3, padx=4, pady=(4, 2))
        ttk.Button(
            continuous_group,
            text="X 停止",
            command=lambda: self._stop_continuous_motor_test(0),
        ).grid(row=0, column=4, padx=4, pady=(4, 2))
        ttk.Button(
            continuous_group,
            text="Y 正轉",
            command=lambda: self._start_continuous_motor_test(1, 1),
        ).grid(row=1, column=2, padx=4, pady=(2, 4))
        ttk.Button(
            continuous_group,
            text="Y 反轉",
            command=lambda: self._start_continuous_motor_test(1, -1),
        ).grid(row=1, column=3, padx=4, pady=(2, 4))
        ttk.Button(
            continuous_group,
            text="Y 停止",
            command=lambda: self._stop_continuous_motor_test(1),
        ).grid(row=1, column=4, padx=4, pady=(2, 4))
        ttk.Button(
            continuous_group,
            text="全部停止",
            command=self._stop_all_continuous_motor_tests,
        ).grid(row=0, column=6, rowspan=2, padx=(8, 4), pady=4, sticky=tk.NS)
        ttk.Button(
            continuous_group,
            text="全部釋放線圈",
            command=self._release_all_continuous_motors,
        ).grid(row=0, column=5, rowspan=2, padx=(4, 4), pady=4, sticky=tk.NS)
        ttk.Label(
            continuous_group,
            textvariable=self.continuous_test_status_var,
        ).grid(row=2, column=0, columnspan=7, sticky=tk.W, padx=6, pady=(0, 6))
        ttk.Label(
            continuous_group,
            text="安全提示：先以 4 RPM、無負載測試；進行拍攝、蛇行、校正或預熱時禁止啟動。",
        ).grid(row=3, column=0, columnspan=7, sticky=tk.W, padx=6, pady=(0, 6))

        preview_workspace = ttk.LabelFrame(frame, text="即時預覽與辨識")
        preview_workspace.pack(fill=tk.X, pady=(0, 10))
        preview_workspace.columnconfigure(0, weight=3)
        preview_workspace.columnconfigure(1, weight=2)

        preview_frame = tk.Frame(
            preview_workspace,
            width=_EMBEDDED_PREVIEW_MAX_WIDTH,
            height=_EMBEDDED_PREVIEW_MAX_HEIGHT,
            bg="#071627",
            highlightthickness=1,
            highlightbackground="#00D7E8",
        )
        preview_frame.grid(row=0, column=0, sticky=tk.N, padx=(8, 6), pady=8)
        preview_frame.pack_propagate(False)
        self._preview_display_frame_widget = preview_frame
        self._preview_display_label = tk.Label(
            preview_frame,
            text="尚未開始預覽",
            bg="#071627",
            fg="#EAFBFF",
            justify=tk.CENTER,
            compound=tk.TOP,
        )
        self._preview_display_label.pack(fill=tk.BOTH, expand=True)
        preview_icon_path = WORKSPACE_ROOT / "assets" / "msh-pixel-icon.png"
        if preview_icon_path.is_file():
            self._preview_placeholder_image = tk.PhotoImage(file=str(preview_icon_path))
            icon_divisor = max(
                1,
                int(
                    round(
                        max(self._preview_placeholder_image.width(), self._preview_placeholder_image.height())
                        / _EMBEDDED_PREVIEW_PLACEHOLDER_SIZE
                    )
                ),
            )
            if icon_divisor > 1:
                self._preview_placeholder_image = self._preview_placeholder_image.subsample(icon_divisor, icon_divisor)
            self._preview_display_label.configure(image=self._preview_placeholder_image)
        ttk.Label(preview_workspace, textvariable=self.preview_display_status_var).grid(
            row=1, column=0, sticky=tk.W, padx=8, pady=(0, 8)
        )

        preview_controls = ttk.Frame(preview_workspace)
        preview_controls.grid(row=0, column=1, rowspan=2, sticky=tk.NSEW, padx=(6, 8), pady=8)
        preview_controls.columnconfigure(0, weight=1)
        ttk.Label(preview_controls, text="預覽控制").grid(row=0, column=0, columnspan=3, sticky=tk.W)
        ttk.Button(preview_controls, text="開始預覽", command=self._start_preview).grid(row=1, column=0, sticky=tk.W, pady=(4, 0))
        ttk.Button(preview_controls, text="停止預覽", command=self._stop_preview).grid(row=1, column=1, sticky=tk.W, padx=(6, 0), pady=(4, 0))
        ttk.Button(preview_controls, text="拍照", command=self._capture_frame).grid(row=1, column=2, sticky=tk.W, padx=(6, 0), pady=(4, 0))
        ttk.Button(preview_controls, text="開啟輸出資料夾", command=self._open_output_folder).grid(
            row=2, column=0, columnspan=3, sticky=tk.W, pady=(6, 0)
        )
        ttk.Button(preview_controls, text="放大檢視", command=self._open_preview_view).grid(
            row=3, column=0, columnspan=2, sticky=tk.W, pady=(6, 0)
        )
        ttk.Button(preview_controls, text="重設檢視", command=self._reset_preview_view).grid(
            row=3, column=2, sticky=tk.W, padx=(6, 0), pady=(6, 0)
        )

        detection_panel = ttk.LabelFrame(preview_controls, text="預覽物件辨識")
        detection_panel.grid(row=4, column=0, columnspan=3, sticky=tk.EW, pady=(10, 0))
        detection_panel.columnconfigure(0, weight=1)
        ttk.Checkbutton(detection_panel, text="顯示偵測框", variable=self.object_detect_preview_var).grid(
            row=0, column=0, columnspan=3, sticky=tk.W, padx=6, pady=(4, 2)
        )
        ttk.Label(detection_panel, textvariable=self.object_detect_confidence_display_var).grid(
            row=1, column=0, columnspan=3, sticky=tk.W, padx=6, pady=2
        )
        ttk.Label(detection_panel, text="最低辨識門檻（固定）").grid(
            row=2, column=0, sticky=tk.W, padx=6, pady=2
        )
        ttk.Label(detection_panel, textvariable=self.object_detect_conf_var).grid(
            row=2, column=1, columnspan=2, sticky=tk.W, padx=(8, 4), pady=2
        )
        ttk.Button(detection_panel, text="選擇模型", command=self._choose_detect_model).grid(
            row=3, column=0, sticky=tk.W, padx=6, pady=(4, 4)
        )
        ttk.Button(detection_panel, text="套用 WBC 模型", command=self._reset_detect_model_to_default).grid(
            row=3, column=1, columnspan=2, sticky=tk.W, padx=(8, 4), pady=(4, 4)
        )
        ttk.Label(detection_panel, textvariable=self.object_detect_model_status_var, wraplength=360).grid(
            row=4, column=0, columnspan=3, sticky=tk.W, padx=6, pady=(0, 4)
        )
        ttk.Checkbutton(detection_panel, text="輸出偵測覆蓋圖", variable=self.object_detect_save_var).grid(
            row=5, column=0, columnspan=3, sticky=tk.W, padx=6, pady=(2, 6)
        )

        cam_group = ttk.LabelFrame(frame, text="手動拍照與拼接")
        cam_group.pack(fill=tk.X, pady=(0, 10))

        capture_actions = ttk.Frame(cam_group)
        capture_actions.grid(row=0, column=0, columnspan=8, sticky=tk.W, pady=(2, 2))
        ttk.Button(capture_actions, text="拼接手動拍照", command=self._stitch_manual_capture_session).pack(side=tk.LEFT)
        ttk.Button(capture_actions, text="終止拍攝", command=self._stop_capture_and_stitch).pack(side=tk.LEFT, padx=(6, 0))

        coordinate_controls = ttk.Frame(cam_group)
        # Preserve step/coordinate scanning controls for recovery, but do not
        # display them while the GUI is in manual hold-to-move mode.
        ttk.Label(coordinate_controls, text="起始座標 X").grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(coordinate_controls, textvariable=self.capture_start_x_var, width=10).grid(row=0, column=1, sticky=tk.W, padx=(6, 6))
        ttk.Label(coordinate_controls, text="起始座標 Y").grid(row=0, column=2, sticky=tk.W)
        ttk.Entry(coordinate_controls, textvariable=self.capture_start_y_var, width=10).grid(row=0, column=3, sticky=tk.W, padx=(6, 6))
        ttk.Button(coordinate_controls, text="蛇行拍攝", command=self._start_full_slide_scan).grid(row=0, column=4, padx=(6, 0))
        ttk.Button(coordinate_controls, text="正式拼接最近蛇行", command=self._stitch_latest_capture_session).grid(row=0, column=5, padx=(6, 0))
        ttk.Label(coordinate_controls, text="終點座標 X").grid(row=1, column=0, sticky=tk.W, pady=(6, 0))
        ttk.Entry(coordinate_controls, textvariable=self.capture_end_x_var, width=10).grid(row=1, column=1, sticky=tk.W, padx=(6, 6), pady=(6, 0))
        ttk.Label(coordinate_controls, text="終點座標 Y").grid(row=1, column=2, sticky=tk.W, pady=(6, 0))
        ttk.Entry(coordinate_controls, textvariable=self.capture_end_y_var, width=10).grid(row=1, column=3, sticky=tk.W, padx=(6, 6), pady=(6, 0))
        ttk.Button(coordinate_controls, text="依步數走到終點並沿途拍攝", command=self._start_capture_between_inputs).grid(
            row=1, column=4, columnspan=2, sticky=tk.W, padx=(6, 0), pady=(6, 0)
        )
        capture_output_controls = ttk.Frame(cam_group)
        capture_output_controls.grid(row=4, column=0, columnspan=8, sticky=tk.W, pady=(8, 2))
        ttk.Label(capture_output_controls, text="拍攝圖片資料夾").pack(side=tk.LEFT)
        capture_output_entry = ttk.Entry(capture_output_controls, textvariable=self.capture_output_dir_var, width=44)
        capture_output_button = ttk.Button(capture_output_controls, text="📁", width=3, command=self._choose_capture_output_dir)
        self._output_path_widgets["capture"] = (capture_output_entry, capture_output_button)
        stitch_output_controls = ttk.Frame(cam_group)
        stitch_output_controls.grid(row=5, column=0, columnspan=8, sticky=tk.W, pady=(8, 2))
        ttk.Label(stitch_output_controls, text="拼接輸出資料夾").pack(side=tk.LEFT)
        stitch_output_entry = ttk.Entry(stitch_output_controls, textvariable=self.stitch_output_dir_var, width=44)
        stitch_output_button = ttk.Button(stitch_output_controls, text="📁", width=3, command=self._choose_stitch_output_dir)
        self._output_path_widgets["stitch"] = (stitch_output_entry, stitch_output_button)
        self.capture_output_dir_var.trace_add("write", lambda *_args: self._update_output_path_row("capture"))
        self.stitch_output_dir_var.trace_add("write", lambda *_args: self._update_output_path_row("stitch"))
        self._update_output_path_row("capture")
        self._update_output_path_row("stitch")
        ttk.Label(
            cam_group,
            text="拼接策略：GUI 拼接按鈕優先使用正式拼接版本；正式引擎失敗時才回退舊自動流程。",
        ).grid(row=10, column=0, columnspan=7, sticky=tk.W, pady=(6, 2))
        ttk.Label(
            cam_group,
            text="注意：若使用通用 yolov8n.pt，細胞畫面通常不會有框；請改成細胞 detection 權重。",
        ).grid(row=11, column=0, columnspan=7, sticky=tk.W, pady=(2, 2))

        wbc_capture_group = ttk.LabelFrame(
            frame,
            text="固定速率座標化蛇行掃描 + White_Blood_Cell 手動拍攝",
        )
        # This legacy step/coordinate scan panel is intentionally hidden.

        ttk.Label(wbc_capture_group, text="實驗名稱").grid(row=0, column=0, sticky=tk.W, pady=4)
        ttk.Entry(wbc_capture_group, textvariable=self.wbc_capture_experiment_var, width=24).grid(
            row=0, column=1, sticky=tk.W, padx=(6, 4), pady=4
        )
        self._wbc_output_slot = tk.Frame(wbc_capture_group, width=32, height=1)
        self._wbc_output_button = ttk.Button(wbc_capture_group, text="📁", width=3, command=self._open_output_folder)
        self._update_wbc_output_button()
        ttk.Button(
            wbc_capture_group,
            text="開始白血球蛇行捕捉",
            command=self._start_wbc_serpentine_capture,
        ).grid(row=0, column=3, sticky=tk.W, padx=(4, 0), pady=4)
        ttk.Button(
            wbc_capture_group,
            text="停止",
            command=self._stop_wbc_serpentine_capture,
        ).grid(row=0, column=4, sticky=tk.W, padx=(4, 0), pady=4)
        ttk.Button(
            wbc_capture_group,
            text="手動拍攝白血球",
            command=self._manual_capture_wbc_serpentine_capture,
        ).grid(row=0, column=5, sticky=tk.W, padx=(4, 0), pady=4)
        ttk.Button(
            wbc_capture_group,
            text="繼續掃描",
            command=self._resume_wbc_serpentine_capture,
        ).grid(row=0, column=6, sticky=tk.W, padx=(4, 0), pady=4)
        ttk.Label(
            wbc_capture_group,
            text="偵測白血球後平台暫停。請先手動調焦，再按「手動拍攝白血球」；完成後按「繼續掃描」。",
        ).grid(row=1, column=0, columnspan=8, sticky=tk.W, pady=(2, 2))
        ttk.Label(wbc_capture_group, textvariable=self.wbc_capture_status_var).grid(
            row=2, column=0, columnspan=6, sticky=tk.W, pady=(2, 4)
        )
        ttk.Label(wbc_capture_group, textvariable=self.wbc_capture_count_var).grid(
            row=2, column=6, columnspan=2, sticky=tk.W, padx=(8, 0), pady=(2, 4)
        )

        ttk.Label(
            frame,
            text="狀態：X-motor 與 Y-motor 由兩組獨立 COM 分別控制。按住方向鍵移動，放開即停止。",
        ).pack(anchor=tk.W, pady=(2, 8))

        log_box = tk.Frame(frame)
        log_box.pack(fill=tk.BOTH, expand=True)
        self.log_text = tk.Text(log_box, height=16, wrap=tk.NONE)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        yscroll = ttk.Scrollbar(log_box, orient=tk.VERTICAL, command=self.log_text.yview)
        yscroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.configure(yscrollcommand=yscroll.set)

        self._append_log("介面已就緒。相機預覽可獨立於馬達連線運作。")
        self._append_log("已啟用相機自動偵測：預覽固定使用 Basler（acA3088-57Uc）。")

    def _bind_keyboard_shortcuts(self) -> None:
        for key, direction, axis_id in (("Left", -1, 0), ("Right", 1, 0), ("Up", 1, 1), ("Down", -1, 1)):
            self.root.bind(f"<{key}>", lambda event, d=direction, a=axis_id: self._handle_arrow_key_press(event, d, a))
            self.root.bind(f"<KeyRelease-{key}>", lambda event, a=axis_id: self._handle_arrow_key_release(event, a))

    def _axis_name(self, axis_id: int) -> str:
        return self.axis_names.get(axis_id, f"軸{axis_id}")

    def _get_stepper(self, axis_id: int) -> Optional[ArduinoStepper]:
        return self.stepper_by_axis.get(axis_id)

    def _continuous_motor_test_blocked(self) -> bool:
        return bool(
            self._wbc_capture_running
            or self._serpentine_video_running
            or self._capture_job_running
            or self._auto_running
            or self._backlash_calibration_running
            or self._image_feedback_running
            or self._motor_warmup_running
        )

    def _start_continuous_motor_test(self, axis_id: int, direction: int) -> None:
        axis = self._axis_name(axis_id)
        stepper = self._get_stepper(axis_id)
        if stepper is None:
            messagebox.showwarning("持續旋轉測試", f"請先連線 {axis}-motor。")
            return
        if self._continuous_motor_test_blocked():
            messagebox.showwarning("持續旋轉測試", "其他移動、校正或拍攝任務正在執行，請先停止該任務。")
            return
        try:
            rpm = float(self.continuous_test_rpm_var.get())
        except Exception:
            messagebox.showerror("持續旋轉測試", "RPM 必須是數字。")
            return
        if not 0.01 <= rpm <= 15.0:
            messagebox.showerror("持續旋轉測試", "RPM 必須介於 0.01 到 15.0。")
            return

        direction_text = "正轉 CW" if int(direction) >= 0 else "反轉 CCW"
        self.continuous_test_status_var.set(f"持續旋轉測試：正在啟動 {axis} {direction_text}...")

        def worker() -> None:
            try:
                response = stepper.run_continuous(direction, rpm)
                self._append_log(f"{axis}-motor 持續旋轉：{direction_text}，{rpm:.2f} RPM，回應={response}")
                self.root.after(
                    0,
                    lambda: self.continuous_test_status_var.set(
                        f"持續旋轉測試：{axis} {direction_text} {rpm:.2f} RPM"
                    ),
                )
            except Exception as exc:
                self._append_log(
                    f"{axis}-motor 持續旋轉啟動失敗：{exc}。請確認已上傳 continuous 新版韌體。"
                )
                self.root.after(
                    0,
                    lambda error=str(exc): self.continuous_test_status_var.set(
                        f"持續旋轉測試：啟動失敗 {error}"
                    ),
                )

        threading.Thread(target=worker, daemon=True).start()

    def _stop_continuous_motor_test(self, axis_id: int) -> None:
        axis = self._axis_name(axis_id)
        stepper = self._get_stepper(axis_id)
        if stepper is None:
            self._append_log(f"{axis}-motor 停止略過：尚未連線。")
            return

        def worker() -> None:
            try:
                response = stepper.stop()
                self._append_log(f"{axis}-motor 已停止：{response}")
                self.root.after(
                    0,
                    lambda: self.continuous_test_status_var.set(f"持續旋轉測試：{axis} 已停止"),
                )
            except Exception as exc:
                self._append_log(f"{axis}-motor 停止失敗：{exc}")

        threading.Thread(target=worker, daemon=True).start()

    def _stop_all_continuous_motor_tests(self) -> None:
        for axis_id in (0, 1):
            self._stop_continuous_motor_test(axis_id)
        self.continuous_test_status_var.set("持續旋轉測試：全部停止中...")

    def _release_all_continuous_motors(self) -> None:
        connected = [
            (axis_id, self._get_stepper(axis_id))
            for axis_id in (0, 1)
            if self._get_stepper(axis_id) is not None
        ]
        if not connected:
            messagebox.showwarning("釋放線圈", "X/Y 馬達均未連線。")
            return

        def worker() -> None:
            for axis_id, stepper in connected:
                assert stepper is not None
                axis = self._axis_name(axis_id)
                try:
                    response = stepper.release()
                    self._append_log(f"{axis}-motor 已停止並釋放線圈：{response}")
                except Exception as exc:
                    self._append_log(f"{axis}-motor 釋放線圈失敗：{exc}")
            self.root.after(
                0,
                lambda: self.continuous_test_status_var.set("持續旋轉測試：全部停止且線圈已釋放"),
            )

        threading.Thread(target=worker, daemon=True).start()

    def _set_stepper(self, axis_id: int, stepper: Optional[ArduinoStepper]) -> None:
        self.stepper_by_axis[axis_id] = stepper
        axis = self._axis_name(axis_id)
        if stepper is None:
            self.status_vars[axis_id].set(f"{axis}-motor: 未連線")
        else:
            self.status_vars[axis_id].set(f"{axis}-motor: 已連線 {stepper.port}")

    def _bind_hold_to_move(self, button: ttk.Button, axis_id: int, direction: int) -> ttk.Button:
        button.bind("<ButtonPress-1>", lambda _event: self._start_manual_motion(axis_id, direction))
        button.bind("<ButtonRelease-1>", lambda _event: self._stop_manual_motion(axis_id))
        button.bind("<Leave>", lambda _event: self._stop_manual_motion(axis_id))
        return button

    def _handle_arrow_key_press(self, event: tk.Event, direction: int, axis_motor_id: int) -> str:
        widget = self.root.focus_get()
        if widget is not None:
            widget_class = widget.winfo_class()
            if widget_class in {"Entry", "TEntry", "Spinbox", "TSpinbox", "Combobox", "TCombobox", "Text", "ttk::entry"}:
                return "break"

        if not self._get_stepper(0) and not self._get_stepper(1):
            return "break"

        self._start_manual_motion(axis_motor_id, direction)
        return "break"

    def _handle_arrow_key_release(self, _event: tk.Event, axis_motor_id: int) -> str:
        # Always stop on key release, even if focus changed while the key was held.
        self._stop_manual_motion(axis_motor_id)
        return "break"

    def _set_manual_motion_status(self, message: str) -> None:
        try:
            self.root.after(0, lambda: self.manual_motion_status_var.set(message))
        except Exception:
            pass

    def _start_manual_motion(self, axis_id: int, direction: int) -> None:
        if self._continuous_motor_test_blocked():
            self._append_log("手動低速移動已略過：其他移動、校正或拍攝任務仍在執行。")
            return
        stepper = self._get_stepper(axis_id)
        axis = self._axis_name(axis_id)
        if stepper is None:
            self._append_log(f"{axis}-motor 手動低速移動略過：尚未連線。")
            return

        # One active axis prevents an accidental diagonal run from two held keys.
        for other_axis in (0, 1):
            if other_axis != axis_id:
                self._stop_manual_motion(other_axis)

        normalized_direction = 1 if int(direction) >= 0 else -1
        with self._manual_motion_lock:
            if self._manual_motion_direction[axis_id] == normalized_direction:
                return
            self._manual_motion_generation[axis_id] += 1
            generation = self._manual_motion_generation[axis_id]
            self._manual_motion_direction[axis_id] = normalized_direction

        direction_text = "正轉" if normalized_direction > 0 else "反轉"
        self._set_manual_motion_status(f"手動低速移動：{axis} {direction_text}（0.02 RPM）")

        def worker() -> None:
            try:
                response = stepper.run_continuous(normalized_direction, _FIXED_MANUAL_MOTOR_RPM)
                with self._manual_motion_lock:
                    still_active = (
                        self._manual_motion_generation[axis_id] == generation
                        and self._manual_motion_direction[axis_id] == normalized_direction
                    )
                if not still_active:
                    stepper.stop()
                    return
                self._append_log(f"{axis}-motor 手動低速{direction_text}：0.02 RPM，回應={response}")
            except Exception as exc:
                with self._manual_motion_lock:
                    if self._manual_motion_generation[axis_id] == generation:
                        self._manual_motion_direction[axis_id] = None
                self._append_log(f"{axis}-motor 手動低速移動啟動失敗：{exc}")
                self._set_manual_motion_status(f"手動低速移動：{axis} 啟動失敗")

        threading.Thread(target=worker, daemon=True).start()

    def _stop_manual_motion(self, axis_id: int) -> None:
        stepper = self._get_stepper(axis_id)
        axis = self._axis_name(axis_id)
        with self._manual_motion_lock:
            was_active = self._manual_motion_direction[axis_id] is not None
            self._manual_motion_generation[axis_id] += 1
            self._manual_motion_direction[axis_id] = None
        if not was_active or stepper is None:
            return

        self._set_manual_motion_status(f"手動低速移動：{axis} 停止並保持通電")

        def worker() -> None:
            try:
                response = stepper.stop()
                self._append_log(f"{axis}-motor 手動低速移動已停止（保持通電）：{response}")
            except Exception as exc:
                self._append_log(f"{axis}-motor 手動低速停止失敗：{exc}")
                self._set_manual_motion_status(f"手動低速移動：{axis} 停止指令失敗")

        threading.Thread(target=worker, daemon=True).start()

    def _append_log(self, msg: str) -> None:
        if threading.current_thread() is not threading.main_thread():
            try:
                self.root.after(0, lambda message=msg: self._append_log(message))
            except Exception:
                pass
            return
        if self.log_text is None:
            return
        self.log_text.insert(tk.END, f"{datetime.now():%Y-%m-%d %H:%M:%S}  {msg}\n")
        self.log_text.see(tk.END)

    def _set_virtual_coord(self, x: int, y: int) -> None:
        with self._coord_lock:
            self._virtual_x = int(x)
            self._virtual_y = int(y)

    def _shift_virtual_coord(self, dx: int, dy: int = 0) -> tuple[int, int]:
        with self._coord_lock:
            self._virtual_x += int(dx)
            self._virtual_y += int(dy)
            return self._virtual_x, self._virtual_y

    def _get_virtual_coord(self) -> tuple[int, int]:
        with self._coord_lock:
            return self._virtual_x, self._virtual_y

    def _reset_virtual_coord(self) -> None:
        self._set_virtual_coord(0, 0)
        self._append_log("虛擬座標已歸零：(0,0)")

    def _fill_capture_start_from_current_coord(self) -> None:
        x, y = self._get_virtual_coord()
        self.capture_start_x_var.set(str(x))
        self.capture_start_y_var.set(str(y))
        self._append_log(f"已帶入目前座標作為起點：({x},{y})")

    def _update_wbc_output_button(self) -> None:
        if self._wbc_capture_latest_output_dir is not None and self._wbc_capture_latest_output_dir.is_dir():
            self._wbc_output_slot.grid_remove()
            self._wbc_output_button.grid(row=0, column=2, sticky=tk.W, padx=(0, 4), pady=4)
        else:
            self._wbc_output_button.grid_remove()
            self._wbc_output_slot.grid(row=0, column=2, sticky=tk.W, padx=(0, 4), pady=4)

    def _update_output_path_row(self, kind: str) -> None:
        entry, button = self._output_path_widgets[kind]
        path_var = self.capture_output_dir_var if kind == "capture" else self.stitch_output_dir_var
        entry.pack_forget()
        button.pack_forget()
        if path_var.get().strip():
            entry.pack(side=tk.LEFT, padx=(4, 4))
            button.pack(side=tk.LEFT)
        else:
            button.pack(side=tk.LEFT, padx=(4, 0))

    def _resolve_capture_output_dir(self) -> Path:
        raw_value = self.capture_output_dir_var.get().strip()
        if not raw_value:
            target_dir = default_output_dir("captured")
        else:
            target_dir = Path(raw_value).expanduser()
            if not target_dir.is_absolute():
                target_dir = (Path.cwd() / target_dir).resolve()
        target_dir.mkdir(parents=True, exist_ok=True)
        self.capture_output_dir_var.set(str(target_dir))
        return target_dir

    def _choose_capture_output_dir(self) -> None:
        configured_dir = self.capture_output_dir_var.get().strip()
        initial_dir = str(Path(configured_dir).expanduser()) if configured_dir else str(PROJECT_ROOT)
        selected = filedialog.askdirectory(
            parent=self.root,
            title="選擇拍攝圖片資料夾",
            initialdir=initial_dir,
            mustexist=False,
        )
        if not selected:
            return
        target_dir = Path(selected).resolve()
        self.capture_output_dir_var.set(str(target_dir))
        self._manual_capture_session = None
        self._append_log(f"拍攝圖片資料夾已設定為：{target_dir}")

    def _resolve_stitch_output_dir(self) -> Path:
        raw_value = self.stitch_output_dir_var.get().strip()
        if not raw_value:
            target_dir = default_output_dir("stitched")
        else:
            target_dir = Path(raw_value).expanduser()
            if not target_dir.is_absolute():
                target_dir = (Path.cwd() / target_dir).resolve()
        target_dir.mkdir(parents=True, exist_ok=True)
        self.stitch_output_dir_var.set(str(target_dir))
        return target_dir

    def _choose_stitch_output_dir(self) -> None:
        configured_dir = self.stitch_output_dir_var.get().strip()
        initial_dir = str(Path(configured_dir).expanduser()) if configured_dir else str(PROJECT_ROOT)
        selected = filedialog.askdirectory(
            parent=self.root,
            title="選擇拼接輸出資料夾",
            initialdir=initial_dir,
            mustexist=False,
        )
        if not selected:
            return
        target_dir = Path(selected).resolve()
        self.stitch_output_dir_var.set(str(target_dir))
        self._append_log(f"拼接輸出資料夾已設定為：{target_dir}")

    def _parse_coordinate_value(self, value: str, field_name: str) -> int:
        try:
            return int(str(value).strip())
        except Exception as exc:
            raise ValueError(f"{field_name} 必須是整數。") from exc

    def _parse_capture_start_coordinate(self) -> tuple[int, int]:
        start_x = self._parse_coordinate_value(self.capture_start_x_var.get(), "起始座標 X")
        start_y = self._parse_coordinate_value(self.capture_start_y_var.get(), "起始座標 Y")
        return start_x, start_y

    def _parse_capture_end_coordinate(self) -> tuple[int, int]:
        end_x = self._parse_coordinate_value(self.capture_end_x_var.get(), "終點座標 X")
        end_y = self._parse_coordinate_value(self.capture_end_y_var.get(), "終點座標 Y")
        return end_x, end_y

    def _get_backlash_var(self, axis_id: int) -> tk.IntVar:
        return self.x_backlash_var if axis_id == 0 else self.y_backlash_var

    def _current_backlash_steps(self, axis_id: int) -> int:
        backlash_var = self._get_backlash_var(axis_id)
        try:
            return max(0, int(backlash_var.get()))
        except (tk.TclError, TypeError, ValueError):
            return 0

    def _current_positive_int(self, var: tk.Variable, default_value: int, minimum: int = 0) -> int:
        try:
            return max(int(minimum), int(var.get()))
        except (tk.TclError, TypeError, ValueError):
            return max(int(minimum), int(default_value))

    def _motion_stabilization_enabled(self) -> bool:
        try:
            return bool(self.motion_stabilize_var.get())
        except tk.TclError:
            return True

    def _fixed_approach_enabled(self) -> bool:
        if not self._motion_stabilization_enabled():
            return False
        try:
            return bool(self.fixed_approach_var.get())
        except tk.TclError:
            return True

    def _axis_approach_direction(self, axis_id: int) -> int:
        var = self.x_approach_direction_var if axis_id == 0 else self.y_approach_direction_var
        try:
            value = int(var.get())
        except (tk.TclError, TypeError, ValueError):
            value = 1
        return 1 if value >= 0 else -1

    def _current_warmup_steps(self) -> int:
        return self._current_positive_int(self.warmup_steps_var, _DEFAULT_MOTOR_WARMUP_STEPS, minimum=1)

    def _current_warmup_cycles(self) -> int:
        return self._current_positive_int(self.warmup_cycles_var, _DEFAULT_MOTOR_WARMUP_CYCLES, minimum=0)

    def _current_approach_preload_steps(self) -> int:
        return self._current_positive_int(
            self.approach_preload_steps_var,
            _DEFAULT_APPROACH_PRELOAD_STEPS,
            minimum=0,
        )

    def _sync_axis_motion_settings(self, axis_id: int) -> Optional[ArduinoStepper]:
        stepper = self._get_stepper(axis_id)
        if stepper is None:
            return None
        stepper.set_backlash_steps(self._current_backlash_steps(axis_id))
        stepper.default_settle_s = max(0.0, int(self.settle_ms_var.get()) / 1000.0)
        stepper.warmup_steps = self._current_warmup_steps()
        stepper.warmup_cycles = self._current_warmup_cycles()
        return stepper

    def _move_axis_steps(self, axis_id: int, steps: int, apply_backlash: bool = True) -> None:
        if int(steps) == 0:
            return
        stepper = self._sync_axis_motion_settings(axis_id)
        if stepper is None:
            raise RuntimeError(f"{self._axis_name(axis_id)}-motor 尚未連線。")
        if apply_backlash and self._fixed_approach_enabled():
            stepper.move_with_fixed_approach(
                int(steps),
                approach_direction=self._axis_approach_direction(axis_id),
                preload_steps=self._current_approach_preload_steps(),
                settle_s=0.03,
            )
        elif self._motion_stabilization_enabled():
            stepper.move_stabilized(
                int(steps),
                apply_backlash=apply_backlash,
                settle_s=0.0,
            )
        else:
            stepper.move(int(steps), apply_backlash=apply_backlash)

    def _warmup_axis(self, axis_id: int) -> bool:
        stepper = self._sync_axis_motion_settings(axis_id)
        if stepper is None:
            return False
        axis = self._axis_name(axis_id)
        steps = self._current_warmup_steps()
        cycles = self._current_warmup_cycles()
        if cycles <= 0:
            return True
        stepper.warmup(steps=steps, cycles=cycles, interval_s=0.04)
        self._append_log(f"{axis}-motor 預熱完成：{steps} 步 x {cycles} 次。")
        return True

    def _warmup_axis_once(self, axis_id: int) -> bool:
        stepper = self._sync_axis_motion_settings(axis_id)
        axis = self._axis_name(axis_id)
        if stepper is None:
            self._append_log(f"{axis}-motor 預熱略過：尚未連線。")
            return False
        steps = self._current_warmup_steps()
        stepper.warmup(steps=steps, cycles=1, interval_s=0.04)
        self._append_log(f"{axis}-motor 單次預熱完成：+{steps} / -{steps} steps。")
        return True

    def _warmup_connected_axes_for_capture(self) -> None:
        if not self._motion_stabilization_enabled():
            return
        warmed_axes: list[str] = []
        for axis_id in (0, 1):
            if self._get_stepper(axis_id) is None:
                continue
            if self._warmup_axis(axis_id):
                warmed_axes.append(self._axis_name(axis_id))
        if warmed_axes:
            self._append_log(f"拍攝前馬達預熱完成：{', '.join(warmed_axes)}。")

    def _warmup_connected_axes(self) -> None:
        if self._wbc_capture_running:
            messagebox.showwarning("馬達預熱", "白血球固定步數蛇行掃描進行中，請先停止掃描。")
            return
        if self._backlash_calibration_running:
            messagebox.showwarning("馬達預熱", "backlash 校正進行中，請稍後再試。")
            return
        if self._capture_job_running:
            messagebox.showwarning("馬達預熱", "拍攝任務進行中，請先停止拍攝。")
            return
        if self._image_feedback_running:
            messagebox.showwarning("馬達預熱", "影像回饋校正進行中，請稍後再試。")
            return
        if self._motor_warmup_running:
            self._append_log("馬達預熱已在進行中。")
            return

        def _worker() -> None:
            self._motor_warmup_running = True
            try:
                warmed = False
                for axis_id in (0, 1):
                    warmed = self._warmup_axis(axis_id) or warmed
                if not warmed:
                    self._append_log("馬達預熱略過：尚未連線 X/Y 馬達。")
            except Exception as exc:
                self._append_log(f"馬達預熱失敗: {exc}")
            finally:
                self._motor_warmup_running = False

        self._motor_warmup_thread = threading.Thread(target=_worker, daemon=True)
        self._motor_warmup_thread.start()

    def _warmup_connected_axes_once(self) -> None:
        if self._wbc_capture_running:
            messagebox.showwarning("X/Y 預熱一次", "白血球固定步數蛇行掃描進行中，請先停止掃描。")
            return
        if self._backlash_calibration_running:
            messagebox.showwarning("X/Y 預熱一次", "backlash 校正進行中，請稍後再試。")
            return
        if self._capture_job_running:
            messagebox.showwarning("X/Y 預熱一次", "拍攝任務進行中，請先停止拍攝。")
            return
        if self._image_feedback_running:
            messagebox.showwarning("X/Y 預熱一次", "影像回饋校正進行中，請稍後再試。")
            return
        if self._motor_warmup_running:
            self._append_log("馬達預熱已在進行中。")
            return

        def _worker() -> None:
            self._motor_warmup_running = True
            try:
                warmed_axes: list[str] = []
                for axis_id in (0, 1):
                    if self._warmup_axis_once(axis_id):
                        warmed_axes.append(self._axis_name(axis_id))
                if not warmed_axes:
                    self._append_log("X/Y 單次預熱未執行：尚未連線 X/Y 馬達。")
                else:
                    self._append_log(f"X/Y 單次預熱完成：{', '.join(warmed_axes)}。")
            except Exception as exc:
                self._append_log(f"X/Y 單次預熱失敗: {exc}")
            finally:
                self._motor_warmup_running = False

        self._motor_warmup_thread = threading.Thread(target=_worker, daemon=True)
        self._motor_warmup_thread.start()

    @staticmethod
    def _extract_motion_tracking_roi(frame: np.ndarray, max_width: int = 1600, max_height: int = 1600) -> np.ndarray:
        if frame is None:
            return frame
        height, width = frame.shape[:2]
        crop_width = min(width, max_width)
        crop_height = min(height, max_height)
        x0 = max(0, (width - crop_width) // 2)
        y0 = max(0, (height - crop_height) // 2)
        x1 = x0 + crop_width
        y1 = y0 + crop_height
        return frame[y0:y1, x0:x1]

    def _capture_motion_tracking_frame(self, discard_frames: int = 3) -> np.ndarray:
        frame = self._read_latest_frame(discard_frames=discard_frames)
        prepared = self._extract_motion_tracking_roi(frame)
        gray_u8 = cv2.cvtColor(prepared, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        gray_u8 = clahe.apply(gray_u8)
        gray_blur = cv2.GaussianBlur(gray_u8, (0, 0), 1.0)
        sobel_x = cv2.Sobel(gray_blur, cv2.CV_32F, 1, 0, ksize=3)
        sobel_y = cv2.Sobel(gray_blur, cv2.CV_32F, 0, 1, ksize=3)
        gradient_mag = cv2.magnitude(sobel_x, sobel_y)
        laplacian = cv2.Laplacian(gray_blur, cv2.CV_32F, ksize=3)
        combined = cv2.addWeighted(gradient_mag, 0.7, np.abs(laplacian), 0.3, 0.0)
        normalized = cv2.normalize(combined, None, alpha=0.0, beta=1.0, norm_type=cv2.NORM_MINMAX)
        return normalized

    @staticmethod
    def _frame_texture_score(frame: np.ndarray) -> float:
        frame_u8 = np.clip(frame * 255.0, 0, 255).astype(np.uint8)
        corners = cv2.goodFeaturesToTrack(frame_u8, maxCorners=200, qualityLevel=0.01, minDistance=8)
        corner_count = 0 if corners is None else int(len(corners))
        lap_var = float(cv2.Laplacian(frame_u8, cv2.CV_32F).var())
        return lap_var + corner_count * 2.5

    @staticmethod
    def _estimate_frame_change(reference: np.ndarray, current: np.ndarray) -> float:
        if reference.shape != current.shape:
            raise ValueError("影像尺寸不一致，無法估計畫面變化。")
        ref_u8 = np.clip(reference * 255.0, 0, 255).astype(np.uint8)
        cur_u8 = np.clip(current * 255.0, 0, 255).astype(np.uint8)
        abs_diff = cv2.absdiff(ref_u8, cur_u8)
        diff_mean = float(abs_diff.mean()) / 255.0
        ref_edges = cv2.Canny(ref_u8, 30, 120)
        cur_edges = cv2.Canny(cur_u8, 30, 120)
        edge_diff = float(cv2.absdiff(ref_edges, cur_edges).mean()) / 255.0
        return diff_mean * 0.6 + edge_diff * 0.4

    @staticmethod
    def _estimate_frame_shift(reference: np.ndarray, current: np.ndarray) -> tuple[float, float, float]:
        if reference.shape != current.shape:
            raise ValueError("影像尺寸不一致，無法估計位移。")
        height, width = reference.shape[:2]
        window = cv2.createHanningWindow((width, height), cv2.CV_32F)
        shift, response = cv2.phaseCorrelate(reference * window, current * window)
        best_shift_x = float(shift[0])
        best_shift_y = float(shift[1])
        best_response = float(response)

        ref_u8 = np.clip(reference * 255.0, 0, 255).astype(np.uint8)
        cur_u8 = np.clip(current * 255.0, 0, 255).astype(np.uint8)
        template_margin_y = max(12, height // 5)
        template_margin_x = max(12, width // 5)
        template = ref_u8[template_margin_y: height - template_margin_y, template_margin_x: width - template_margin_x]
        if template.size > 0 and template.shape[0] < height and template.shape[1] < width:
            match = cv2.matchTemplate(cur_u8, template, cv2.TM_CCOEFF_NORMED)
            _min_val, max_val, _min_loc, max_loc = cv2.minMaxLoc(match)
            template_shift_x = float(max_loc[0] - template_margin_x)
            template_shift_y = float(max_loc[1] - template_margin_y)
            template_response = float(max_val)
            if template_response > best_response + 0.08:
                best_shift_x = template_shift_x
                best_shift_y = template_shift_y
                best_response = template_response
        return best_shift_x, best_shift_y, best_response

    def estimate_frame_shift(self, previous_frame: np.ndarray, current_frame: np.ndarray) -> tuple[float, float, float]:
        return self._estimate_frame_shift(previous_frame, current_frame)

    @staticmethod
    def estimate_overlap_ratio(
        previous_frame: np.ndarray,
        current_frame: np.ndarray,
        dx: float,
        dy: float,
    ) -> float:
        if previous_frame.shape[:2] != current_frame.shape[:2]:
            raise ValueError("影像尺寸不一致，無法估計 overlap。")
        height, width = previous_frame.shape[:2]
        if width <= 0 or height <= 0:
            return 0.0
        overlap_width = max(0.0, float(width) - abs(float(dx)))
        overlap_height = max(0.0, float(height) - abs(float(dy)))
        return float(max(0.0, min(1.0, (overlap_width * overlap_height) / float(width * height))))

    @staticmethod
    def _shift_component(shift_x: float, shift_y: float, component: str) -> float:
        return float(shift_x if component == "x" else shift_y)

    def _current_feedback_sample_count(self) -> int:
        return self._current_positive_int(self.feedback_sample_count_var, 10, minimum=1)

    @staticmethod
    def _summarize_feedback_records(records: list[dict[str, Any]], component: str) -> dict[str, Any]:
        def _stats(subset: list[dict[str, Any]]) -> dict[str, Any]:
            if not subset:
                return {
                    "count": 0,
                    "mean_signed_px_per_step": 0.0,
                    "mean_abs_px_per_step": 0.0,
                    "std_abs_px_per_step": 0.0,
                    "mean_response": 0.0,
                    "mean_orthogonal_shift_px": 0.0,
                }
            signed_values = [float(row["signed_px_per_step"]) for row in subset]
            abs_values = [abs(float(row["px_per_step"])) for row in subset]
            responses = [float(row["response"]) for row in subset]
            orthogonal_values = [abs(float(row["orthogonal_shift_px"])) for row in subset]
            return {
                "count": len(subset),
                "mean_signed_px_per_step": float(np.mean(signed_values)),
                "mean_abs_px_per_step": float(np.mean(abs_values)),
                "std_abs_px_per_step": float(np.std(abs_values)),
                "mean_response": float(np.mean(responses)),
                "mean_orthogonal_shift_px": float(np.mean(orthogonal_values)),
            }

        positive = [row for row in records if int(row["direction"]) > 0]
        negative = [row for row in records if int(row["direction"]) < 0]
        all_steps = [row for row in records if int(row["commanded_steps"]) != 0]
        return {
            "dominant_component": component,
            "positive_direction": _stats(positive),
            "negative_direction": _stats(negative),
            "all": _stats(all_steps),
        }

    def _start_image_feedback_calibration(self, axis_id: int) -> None:
        axis = self._axis_name(axis_id)
        if self._wbc_capture_running:
            messagebox.showwarning("影像回饋校正", "白血球固定步數蛇行掃描進行中，請先停止掃描。")
            return
        if self._image_feedback_running:
            self._append_log("影像回饋校正已在進行中。")
            return
        if self._backlash_calibration_running:
            messagebox.showwarning("影像回饋校正", "backlash 校正進行中，請稍後再試。")
            return
        if self._capture_job_running:
            messagebox.showwarning("影像回饋校正", "拍攝任務進行中，請先停止拍攝。")
            return
        if self._get_stepper(axis_id) is None:
            messagebox.showwarning("影像回饋校正", f"請先連線 {axis}-motor。")
            return

        self._image_feedback_running = True
        resume_preview = bool(self._preview_running)
        if resume_preview:
            self._stop_preview()
        self._append_log(f"{axis} 影像回饋校正開始。")
        self._image_feedback_thread = threading.Thread(
            target=self._run_image_feedback_calibration,
            args=(axis_id, resume_preview),
            daemon=True,
        )
        self._image_feedback_thread.start()

    def _run_image_feedback_calibration(self, axis_id: int, resume_preview: bool) -> None:
        axis = self._axis_name(axis_id)
        component = "x" if axis_id == 0 else "y"
        orthogonal_component = "y" if axis_id == 0 else "x"
        step_size = abs(int(self.steps_var.get() if axis_id == 0 else self.y_steps_var.get()))
        sample_count = self._current_feedback_sample_count()
        settle_s = max(0.05, int(self.settle_ms_var.get()) / 1000.0)
        start_x, start_y = self._get_virtual_coord()
        records: list[dict[str, Any]] = []

        try:
            if step_size <= 0:
                raise RuntimeError(f"{axis} 每次移動步數必須大於 0。")
            self._ensure_camera_open()
            self._warmup_axis(axis_id)
            reference_frame = self._capture_motion_tracking_frame(discard_frames=4)
            texture_score = self._frame_texture_score(reference_frame)
            previous_frame = reference_frame
            output_dir = self._resolve_stitch_output_dir() / f"motion_feedback_{axis}_{_timestamp()}"
            output_dir.mkdir(parents=True, exist_ok=True)

            self._append_log(
                f"{axis} 影像回饋：step={step_size}，正反向各 {sample_count} 次，texture={texture_score:.1f}"
            )

            sequence: list[tuple[int, int]] = [(1, step_size) for _ in range(sample_count)]
            sequence.extend([(-1, -step_size) for _ in range(sample_count)])
            for sample_index, (direction, commanded_steps) in enumerate(sequence, start=1):
                if self._capture_job_stop.is_set():
                    break
                before_x, before_y = self._get_virtual_coord()
                self._move_axis_steps(axis_id, commanded_steps, apply_backlash=True)
                if settle_s > 0:
                    time.sleep(settle_s)
                current_frame = self._capture_motion_tracking_frame(discard_frames=3)
                shift_x, shift_y, response = self._estimate_frame_shift(previous_frame, current_frame)
                change_score = self._estimate_frame_change(previous_frame, current_frame)
                dominant_shift = self._shift_component(shift_x, shift_y, component)
                orthogonal_shift = self._shift_component(shift_x, shift_y, orthogonal_component)
                px_per_step = dominant_shift / float(commanded_steps)
                signed_px_per_step = dominant_shift / float(abs(commanded_steps))
                if axis_id == 0:
                    after_x, after_y = self._shift_virtual_coord(commanded_steps, 0)
                else:
                    after_x, after_y = self._shift_virtual_coord(0, commanded_steps)

                row = {
                    "sample_index": sample_index,
                    "axis": axis,
                    "direction": direction,
                    "commanded_steps": commanded_steps,
                    "before_x": before_x,
                    "before_y": before_y,
                    "after_x": after_x,
                    "after_y": after_y,
                    "shift_x_px": float(shift_x),
                    "shift_y_px": float(shift_y),
                    "dominant_shift_px": float(dominant_shift),
                    "orthogonal_shift_px": float(orthogonal_shift),
                    "px_per_step": float(px_per_step),
                    "signed_px_per_step": float(signed_px_per_step),
                    "response": float(response),
                    "change_score": float(change_score),
                }
                records.append(row)
                previous_frame = current_frame
                self._append_log(
                    f"{axis} feedback {sample_index}/{len(sequence)}: steps={commanded_steps}, "
                    f"shift=({shift_x:.2f},{shift_y:.2f}) px, px/step={px_per_step:.3f}, response={response:.3f}"
                )

            if not records:
                raise RuntimeError("未產生任何影像回饋資料。")

            csv_path = output_dir / "motion_feedback.csv"
            json_path = output_dir / "motion_feedback_summary.json"
            fieldnames = list(records[0].keys())
            with csv_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(records)

            summary = {
                "axis": axis,
                "step_size": step_size,
                "sample_count_per_direction": sample_count,
                "settle_s": settle_s,
                "texture_score": float(texture_score),
                "start_coord": {"x": start_x, "y": start_y},
                "end_coord": {"x": self._get_virtual_coord()[0], "y": self._get_virtual_coord()[1]},
                "settings": {
                    "motion_stabilize": self._motion_stabilization_enabled(),
                    "fixed_approach": self._fixed_approach_enabled(),
                    "approach_direction": self._axis_approach_direction(axis_id),
                    "approach_preload_steps": self._current_approach_preload_steps(),
                    "backlash_steps": self._current_backlash_steps(axis_id),
                },
                "summary": self._summarize_feedback_records(records, component),
                "csv_path": str(csv_path.resolve()),
            }
            json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
            self._latest_stitch_output_dir = output_dir
            stats = summary["summary"]["all"]
            self._append_log(
                f"{axis} 影像回饋完成：平均={stats['mean_abs_px_per_step']:.3f} px/step，"
                f"std={stats['std_abs_px_per_step']:.3f}，輸出={output_dir.resolve()}"
            )
        except Exception as exc:
            self._append_log(f"{axis} 影像回饋校正失敗: {exc}")
            messagebox.showerror("影像回饋校正失敗", str(exc))
        finally:
            self._image_feedback_running = False
            self._set_virtual_coord(start_x, start_y)
            if resume_preview:
                self.root.after(0, self._start_preview)

    def _calibration_probe_settings(self, axis_id: int, current_backlash: int) -> tuple[int, int]:
        base_steps = abs(int(self.steps_var.get() if axis_id == 0 else self.y_steps_var.get()))
        preload_steps = max(64, base_steps * 8, current_backlash * 4 + 24)
        search_limit = max(160, preload_steps * 2, current_backlash + 80)
        return preload_steps, search_limit

    def _start_backlash_calibration(self, axis_id: int) -> None:
        axis = self._axis_name(axis_id)
        current_steps = self._current_backlash_steps(axis_id)
        self._append_log(f"{axis} backlash 目前使用手動設定 {current_steps} 步。")

    def _run_backlash_calibration(self, axis_id: int, resume_preview: bool) -> None:
        axis = self._axis_name(axis_id)
        settle_s = max(0.05, int(self.settle_ms_var.get()) / 1000.0)
        stepper = self._get_stepper(axis_id)
        if stepper is None:
            self._append_log(f"{axis} backlash 校正失敗：馬達未連線。")
            self._backlash_calibration_running = False
            return

        original_backlash = self._current_backlash_steps(axis_id)
        preload_steps, search_limit = self._calibration_probe_settings(axis_id, original_backlash)
        start_x, start_y = self._get_virtual_coord()
        start_frame: Optional[np.ndarray] = None
        preload_frame: Optional[np.ndarray] = None

        try:
            start_frame = self._capture_motion_tracking_frame(discard_frames=4)
            texture_score = self._frame_texture_score(start_frame)
            self._append_log(f"{axis} 校正畫面紋理分數={texture_score:.1f}")
            idle_frame = self._capture_motion_tracking_frame(discard_frames=3)
            baseline_change = self._estimate_frame_change(start_frame, idle_frame)
            self._append_log(f"{axis} 靜止基線變化={baseline_change:.4f}")
            stepper.set_backlash_steps(0)
            preload_total_steps = 0
            preload_attempts = (preload_steps, preload_steps, preload_steps * 2, preload_steps * 4)
            preload_shift_x = 0.0
            preload_shift_y = 0.0
            preload_response = 0.0
            preload_magnitude = 0.0
            preload_change = 0.0
            dominant_component = "x"
            preload_component = 0.0
            preload_motion_detected = False
            for attempt_index, preload_increment in enumerate(preload_attempts, start=1):
                self._move_axis_steps(axis_id, preload_increment, apply_backlash=False)
                preload_total_steps += preload_increment
                time.sleep(settle_s)
                preload_frame = self._capture_motion_tracking_frame(discard_frames=3)
                preload_shift_x, preload_shift_y, preload_response = self._estimate_frame_shift(start_frame, preload_frame)
                preload_change = self._estimate_frame_change(start_frame, preload_frame)
                dominant_component = "x" if abs(preload_shift_x) >= abs(preload_shift_y) else "y"
                preload_component = self._shift_component(preload_shift_x, preload_shift_y, dominant_component)
                preload_magnitude = math.hypot(preload_shift_x, preload_shift_y)
                self._append_log(
                    f"{axis} 預壓嘗試 {attempt_index}: total={preload_total_steps} 步, shift=({preload_shift_x:.2f},{preload_shift_y:.2f}) px, response={preload_response:.3f}, change={preload_change:.4f}"
                )
                if (preload_response >= 0.02 and preload_magnitude >= 0.2) or preload_change >= max(0.012, baseline_change * 4.0):
                    preload_motion_detected = True
                    break

            if preload_frame is None or not preload_motion_detected:
                raise RuntimeError(
                    "在高解析 ROI 上仍看不到可用的預壓畫面變化。請確認目前軸向確實會影響視野，或先把單次步數調大後再重試。"
                )

            per_step_pixels = max(abs(preload_component) / max(preload_total_steps, 1), 1e-3)
            motion_threshold = max(0.08, min(0.7, per_step_pixels * 0.5))
            change_threshold = max(0.010, baseline_change * 3.0, preload_change * 0.15)
            self._append_log(
                f"{axis} 校正基準：img_shift=({preload_shift_x:.2f},{preload_shift_y:.2f}) px, response={preload_response:.3f}, shift_threshold={motion_threshold:.3f}, change_threshold={change_threshold:.4f}"
            )

            reverse_steps_taken = 0
            estimated_backlash: Optional[int] = None
            actual_reverse_motion_steps = 0
            for _ in range(search_limit):
                self._move_axis_steps(axis_id, -1, apply_backlash=False)
                reverse_steps_taken += 1
                time.sleep(settle_s)
                probe_frame = self._capture_motion_tracking_frame(discard_frames=2)
                shift_x, shift_y, response = self._estimate_frame_shift(preload_frame, probe_frame)
                change_score = self._estimate_frame_change(preload_frame, probe_frame)
                component_shift = abs(self._shift_component(shift_x, shift_y, dominant_component))
                if reverse_steps_taken in {1, 2, 4, 8, 16, 32, 64, 128, 192, 256}:
                    self._append_log(
                        f"{axis} reverse_probe={reverse_steps_taken} shift={component_shift:.3f}px change={change_score:.4f} response={response:.3f}"
                    )
                if (response >= 0.02 and component_shift >= motion_threshold) or change_score >= change_threshold:
                    estimated_backlash = max(0, reverse_steps_taken - 1)
                    actual_reverse_motion_steps = max(0, reverse_steps_taken - estimated_backlash)
                    self._append_log(
                        f"{axis} backlash 觸發：reverse={reverse_steps_taken} 步, visible_shift={component_shift:.3f} px, change={change_score:.4f}, estimated={estimated_backlash} 步"
                    )
                    break

            if estimated_backlash is None:
                raise RuntimeError(f"在 {search_limit} 步內未偵測到反轉後的實際位移，請增加步數或提高畫面紋理。")

            restore_steps = preload_total_steps - actual_reverse_motion_steps
            if restore_steps > 0:
                self._move_axis_steps(axis_id, -restore_steps, apply_backlash=False)
                time.sleep(settle_s)

            restored_frame = self._capture_motion_tracking_frame(discard_frames=3)
            restore_shift_x, restore_shift_y, restore_response = self._estimate_frame_shift(start_frame, restored_frame)
            residual_component = self._shift_component(restore_shift_x, restore_shift_y, dominant_component)
            correction_steps = 0
            if restore_response >= 0.02 and abs(residual_component) >= max(0.25, per_step_pixels * 0.75):
                estimated_steps = int(round(abs(residual_component) / per_step_pixels))
                correction_steps = max(0, min(20, estimated_steps))
                if correction_steps > 0:
                    correction_direction = -1 if residual_component * preload_component > 0 else 1
                    self._move_axis_steps(axis_id, correction_direction * correction_steps, apply_backlash=False)
                    time.sleep(settle_s)
                    self._append_log(
                        f"{axis} 校正回位微調：{correction_direction * correction_steps} 步，residual={residual_component:.3f} px"
                    )

            self._set_virtual_coord(start_x, start_y)
            self._get_backlash_var(axis_id).set(int(estimated_backlash))
            stepper.set_backlash_steps(int(estimated_backlash))
            self._append_log(f"{axis} backlash 自動校正完成：建議補償={estimated_backlash} 步。")
        except Exception as exc:
            try:
                self._set_virtual_coord(start_x, start_y)
                stepper.set_backlash_steps(original_backlash)
            except Exception:
                pass
            self._append_log(f"{axis} backlash 自動校正失敗: {exc}")
            messagebox.showerror("backlash 校正失敗", str(exc))
        finally:
            try:
                stepper.set_backlash_steps(self._current_backlash_steps(axis_id))
            except Exception:
                pass
            self._backlash_calibration_running = False
            if resume_preview:
                self.root.after(0, self._start_preview)

    def _move_to_end_and_capture(self) -> None:
        try:
            end_x, end_y = self._parse_capture_end_coordinate()
            self._ensure_camera_open()
            self._move_to_coordinate(end_x, end_y, label="終點座標")
            self._capture_frame()
            self._append_log(f"已移動到終點並完成拍照：({end_x},{end_y})")
        except Exception as exc:
            self._append_log(f"移動到終點並拍照失敗: {exc}")
            messagebox.showerror("終點拍照失敗", str(exc))

    def _move_by_configured_steps_and_capture(self) -> None:
        try:
            step_x = int(self.steps_var.get())
            step_y = int(self.y_steps_var.get())
        except Exception as exc:
            messagebox.showerror("步數設定", f"X/Y 步數必須是整數。\n{exc}")
            return

        if step_x == 0 and step_y == 0:
            messagebox.showwarning("步數設定", "X/Y 步數不能同時為 0。")
            return

        try:
            current_x, current_y = self._get_virtual_coord()
            target_x = current_x + step_x
            target_y = current_y + step_y
            self._ensure_camera_open()
            self._move_to_coordinate(target_x, target_y, label="依步數移動")
            self._capture_frame()
            self._append_log(
                f"已依設定步數移動並拍照：step=({step_x},{step_y}) -> 座標=({target_x},{target_y})"
            )
        except Exception as exc:
            self._append_log(f"依步數移動並拍照失敗: {exc}")
            messagebox.showerror("依步數移動並拍照失敗", str(exc))

    def _move_to_coordinate(self, target_x: int, target_y: int, label: str = "目標座標") -> None:
        if self._wbc_capture_running:
            raise RuntimeError("白血球固定步數蛇行掃描進行中，請使用停止或繼續掃描按鈕。")
        current_x, current_y = self._get_virtual_coord()
        dx = int(target_x) - current_x
        dy = int(target_y) - current_y
        if dx == 0 and dy == 0:
            self._set_virtual_coord(target_x, target_y)
            self._append_log(f"{label}已就緒：({target_x},{target_y})")
            return

        x_stepper = self._get_stepper(0)
        y_stepper = self._get_stepper(1)
        missing: list[str] = []
        if dx != 0 and x_stepper is None:
            missing.append("X-motor")
        if dy != 0 and y_stepper is None:
            missing.append("Y-motor")
        if missing:
            raise RuntimeError(f"{label}需要連線: {', '.join(missing)}")

        if dx != 0 and x_stepper is not None:
            self._move_axis_steps(0, dx)
        if dy != 0 and y_stepper is not None:
            self._move_axis_steps(1, dy)

        settle_ms = max(0, int(self.settle_ms_var.get()))
        if settle_ms > 0:
            time.sleep(settle_ms / 1000.0)

        self._set_virtual_coord(target_x, target_y)
        self._append_log(f"{label}已移動至 ({target_x},{target_y})，位移=({dx},{dy})")

    def _move_to_origin(self) -> None:
        if self._wbc_capture_running:
            messagebox.showwarning("回到原點", "白血球固定步數蛇行掃描進行中，請先停止掃描。")
            return
        x, y = self._get_virtual_coord()
        if x == 0 and y == 0:
            self._append_log("目前已在原點：(0,0)")
            return
        x_stepper = self._get_stepper(0)
        y_stepper = self._get_stepper(1)
        if x_stepper is None and y_stepper is None:
            messagebox.showwarning("回到原點", "請先連線至少一顆馬達。")
            return
        try:
            missing = []
            if x != 0 and x_stepper is None:
                missing.append("X-motor")
            if y != 0 and y_stepper is None:
                missing.append("Y-motor")
            if missing:
                raise RuntimeError(f"回原點時，缺少連線: {', '.join(missing)}")
            if x != 0:
                self._move_axis_steps(0, -x)
            if y != 0:
                self._move_axis_steps(1, -y)
            self._set_virtual_coord(0, 0)
            self._append_log(f"已回到原點：(0,0)，原座標=({x},{y})")
        except Exception as exc:
            self._append_log(f"回到原點失敗: {exc}")
            messagebox.showerror("回到原點失敗", str(exc))

    def _refresh_ports(self) -> None:
        ports = list_serial_ports()
        self._apply_refreshed_ports(ports)

    def _refresh_ports_async(self) -> None:
        self._append_log("正在重新整理 COM 連接埠...")

        def worker() -> None:
            try:
                ports = list_serial_ports()
                error_message = ""
            except Exception as exc:
                ports = []
                error_message = str(exc)

            def apply_result() -> None:
                self._apply_refreshed_ports(ports, error_message=error_message)

            try:
                self.root.after(0, apply_result)
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True).start()

    def _apply_refreshed_ports(self, ports: list[str], *, error_message: str = "") -> None:
        for axis_id in self.port_combos:
            self.port_combos[axis_id]["values"] = ports
            if ports and not self.port_vars[axis_id].get():
                self.port_vars[axis_id].set(ports[0])
        if error_message:
            self._append_log(f"COM 連接埠重新整理失敗: {error_message}")
        else:
            self._append_log(f"可用連接埠: {ports}")

    def _connect_selected_axes(self) -> None:
        missing_axes = [
            self._axis_name(axis_id)
            for axis_id in (0, 1)
            if not self.port_vars[axis_id].get().strip()
        ]
        if missing_axes:
            messagebox.showwarning(
                "連接馬達",
                f"請先選擇 {'、'.join(missing_axes)}-motor 的 COM 連接埠。",
            )
            return

        self._append_log("正在依已選擇的 COM 連接埠連接 X/Y 馬達...")
        for axis_id in (0, 1):
            self._connect(axis_id)

    def _connect(self, axis_id: int) -> None:
        axis = self._axis_name(axis_id)
        if self._get_stepper(axis_id) is not None:
            self._append_log(f"{axis}-motor 已連線。")
            return
        port = self.port_vars[axis_id].get().strip()
        if not port:
            messagebox.showwarning("連線", f"請先選擇 {axis}-motor 的 COM 連接埠。")
            return
        try:
            stepper = ArduinoStepper(port=port, baud=int(self.baud_var.get()))
            # Manual RUN mode must not probe by changing speed or initialize a
            # legacy step-delay setting when a controller is connected.
            stepper.connect(initialize_speed=False, probe_capabilities=False)
            try:
                stepper.set_hold(True)
            except Exception:
                pass
            self._set_stepper(axis_id, stepper)
            self._append_log(
                f"{axis}-motor 已連線: {port}，手動模式固定 0.02 RPM；按住控制移動。"
            )
        except Exception as exc:
            self._set_stepper(axis_id, None)
            self._append_log(f"{axis}-motor 連線失敗: {exc}")
            messagebox.showerror("連線失敗", str(exc))

    def _disconnect(self, axis_id: Optional[int] = None) -> None:
        # Keep camera preview alive even after stepper disconnect.
        if self._wbc_capture_running:
            messagebox.showwarning("斷線", "白血球固定步數蛇行掃描進行中，請先停止掃描。")
            return
        self._stop_auto()
        axis_ids = [axis_id] if axis_id is not None else [0, 1]
        for aid in axis_ids:
            stepper = self._get_stepper(aid)
            if stepper is None:
                self._set_stepper(aid, None)
                continue
            axis = self._axis_name(aid)
            try:
                self._stop_and_release_stepper(aid, stepper, reason="斷線")
                stepper.close()
                self._append_log(f"{axis}-motor 已斷線。")
            except Exception as exc:
                self._append_log(f"{axis}-motor 斷線警告: {exc}")
            finally:
                self._set_stepper(aid, None)

    def _move(self, axis_id: int, direction: int) -> None:
        if self._wbc_capture_running:
            self._append_log("白血球固定步數蛇行掃描進行中，已忽略手動移動。")
            return
        if self._backlash_calibration_running:
            self._append_log("backlash 校正進行中，暫停手動移動。")
            return
        if self._image_feedback_running:
            self._append_log("影像回饋校正進行中，暫停手動移動。")
            return
        if self._get_stepper(axis_id) is None:
            messagebox.showwarning("移動", f"請先連線 {self._axis_name(axis_id)}-motor。")
            return
        try:
            steps_var = self.steps_var if axis_id == 0 else self.y_steps_var
            steps = int(steps_var.get()) * int(direction)
            stepper = self._sync_axis_motion_settings(axis_id)
            if stepper is None:
                raise RuntimeError(f"{self._axis_name(axis_id)}-motor 尚未連線。")
            self._move_axis_steps(axis_id, steps, apply_backlash=True)
            if axis_id == 0:
                x, y = self._shift_virtual_coord(steps, 0)
                axis = "X"
            else:
                x, y = self._shift_virtual_coord(0, steps)
                axis = "Y"
            self._append_log(
                f"{axis} 移動: {steps} 步，反轉補償={self._current_backlash_steps(axis_id)}，座標=({x},{y})"
            )
        except Exception as exc:
            self._append_log(f"移動失敗: {exc}")
            messagebox.showerror("移動失敗", str(exc))

    def _stop_and_release_stepper(self, axis_id: int, stepper: ArduinoStepper, *, reason: str) -> None:
        """Best-effort hardware shutdown before a serial link is released."""
        axis = self._axis_name(axis_id)
        with self._manual_motion_lock:
            self._manual_motion_generation[axis_id] += 1
            self._manual_motion_direction[axis_id] = None
        try:
            stepper.stop()
        except Exception as exc:
            self._append_log(f"{axis}-motor {reason}前 STOP 失敗：{exc}")
        try:
            stepper.release()
            self._append_log(f"{axis}-motor {reason}保護：已停止並釋放線圈。")
        except Exception as exc:
            self._append_log(f"{axis}-motor {reason}前 RELEASE 失敗：{exc}")

    def _ensure_camera_open(self) -> Optional[cv2.VideoCapture]:
        if self.cap is not None:
            return self.cap

        with self._camera_lock:
            if self.cap is not None:
                return self.cap
            self.cap = self._auto_open_camera()
            if self.cap is None:
                raise RuntimeError("未偵測到可用攝影機。")
            return self.cap

    def _read_latest_frame(self, discard_frames: int = 3):
        cap = self._ensure_camera_open()
        if cap is None:
            raise RuntimeError("未偵測到可用攝影機。")

        last_ok_frame = None
        discard_frames = max(1, discard_frames)
        for _ in range(discard_frames):
            with self._camera_lock:
                ok, frame = cap.read()
            if ok and frame is not None:
                last_ok_frame = frame
        if last_ok_frame is None:
            raise RuntimeError("讀取相機畫面失敗。")
        return last_ok_frame

    @staticmethod
    def _downscale_frame_quality_first(
        frame: np.ndarray,
        max_long_side: int,
    ) -> np.ndarray:
        if frame is None:
            return frame

        height, width = frame.shape[:2]
        long_side = max(height, width)
        if long_side <= max_long_side:
            return frame

        reduced = frame
        while max(reduced.shape[:2]) >= max_long_side * 2:
            reduced = cv2.pyrDown(reduced)

        reduced_height, reduced_width = reduced.shape[:2]
        reduced_long_side = max(reduced_height, reduced_width)
        if reduced_long_side <= max_long_side:
            return reduced

        scale = max_long_side / float(reduced_long_side)
        out_width = max(1, int(round(reduced_width * scale)))
        out_height = max(1, int(round(reduced_height * scale)))
        return cv2.resize(reduced, (out_width, out_height), interpolation=cv2.INTER_AREA)

    @staticmethod
    def _prepare_preview_frame(frame: np.ndarray, max_long_side: int = _PREVIEW_PROCESS_MAX_LONG_SIDE) -> np.ndarray:
        """Prepare a compact copy for preview inference only, never for display."""
        return StepperDragGUI._downscale_frame_quality_first(frame, max_long_side=max_long_side)

    @staticmethod
    def _resize_for_display_keep_aspect(
        frame: np.ndarray,
        max_width: int = _PREVIEW_WINDOW_WIDTH,
        max_height: int = 720,
    ) -> np.ndarray:
        if frame is None:
            return frame
        height, width = frame.shape[:2]
        if width <= 0 or height <= 0:
            return frame
        target_width = max(1, int(max_width))
        target_height = max(1, int(max_height))
        scale = min(target_width / float(width), target_height / float(height), 1.0)
        if scale >= 1.0:
            return frame
        resized_width = max(1, int(round(width * scale)))
        resized_height = max(1, int(round(height * scale)))
        return cv2.resize(frame, (resized_width, resized_height), interpolation=cv2.INTER_AREA)

    def _set_preview_display_message(self, message: str) -> None:
        with self._preview_display_lock:
            self._preview_display_message = str(message)

    def _publish_preview_display_frame(self, frame: np.ndarray, message: str) -> None:
        with self._preview_display_lock:
            self._preview_display_frame = np.ascontiguousarray(frame.copy())
            self._preview_display_message = str(message)

    def _show_preview_placeholder(self, message: str) -> None:
        self.preview_display_status_var.set(message)
        if self._preview_display_frame_widget is not None:
            self._preview_display_frame_widget.configure(
                width=_EMBEDDED_PREVIEW_MAX_WIDTH,
                height=_EMBEDDED_PREVIEW_MAX_HEIGHT,
            )
        if self._preview_display_label is None:
            return
        self._preview_display_label.configure(image=self._preview_placeholder_image, text="")
        self._preview_photo_image = None

    @staticmethod
    def _render_preview_view(
        frame: np.ndarray,
        viewport_width: int,
        viewport_height: int,
        zoom: float = 1.0,
        center: tuple[float, float] = (0.5, 0.5),
    ) -> np.ndarray:
        """Render a fit/zoom/pan view without changing the source capture frame."""
        if frame is None or frame.ndim < 2:
            raise ValueError("預覽影像無效")
        source_height, source_width = frame.shape[:2]
        viewport_width = max(1, int(viewport_width))
        viewport_height = max(1, int(viewport_height))
        if source_width <= 0 or source_height <= 0:
            raise ValueError("預覽影像尺寸無效")

        fit_scale = min(viewport_width / float(source_width), viewport_height / float(source_height))
        scale = fit_scale * min(_PREVIEW_VIEW_MAX_ZOOM, max(1.0, float(zoom)))
        visible_width = min(source_width, max(1, int(round(viewport_width / scale))))
        visible_height = min(source_height, max(1, int(round(viewport_height / scale))))
        center_x = min(1.0, max(0.0, float(center[0]))) * source_width
        center_y = min(1.0, max(0.0, float(center[1]))) * source_height
        left = int(round(center_x - visible_width / 2.0))
        top = int(round(center_y - visible_height / 2.0))
        left = min(max(0, left), source_width - visible_width)
        top = min(max(0, top), source_height - visible_height)
        cropped = frame[top : top + visible_height, left : left + visible_width]

        rendered_width = max(1, int(round(visible_width * scale)))
        rendered_height = max(1, int(round(visible_height * scale)))
        interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR
        rendered = cv2.resize(cropped, (rendered_width, rendered_height), interpolation=interpolation)
        canvas = np.zeros((viewport_height, viewport_width, *frame.shape[2:]), dtype=frame.dtype)
        offset_x = max(0, (viewport_width - rendered_width) // 2)
        offset_y = max(0, (viewport_height - rendered_height) // 2)
        copy_width = min(viewport_width - offset_x, rendered_width)
        copy_height = min(viewport_height - offset_y, rendered_height)
        canvas[offset_y : offset_y + copy_height, offset_x : offset_x + copy_width] = rendered[:copy_height, :copy_width]
        return canvas

    def _reset_preview_view(self) -> None:
        self._preview_view_zoom = 1.0
        self._preview_view_center = (0.5, 0.5)

    def _open_preview_view(self) -> None:
        if self._preview_view_window is not None and self._preview_view_window.winfo_exists():
            self._preview_view_window.deiconify()
            self._preview_view_window.lift()
            return
        window = tk.Toplevel(self.root)
        window.title("MSH Basler 預覽檢視")
        window.geometry("1280x820")
        window.minsize(640, 480)
        window.configure(bg="#071627")
        window.protocol("WM_DELETE_WINDOW", self._close_preview_view)
        window.bind("<Escape>", lambda _event: self._set_preview_view_fullscreen(False))
        controls = ttk.Frame(window)
        controls.pack(fill=tk.X, padx=8, pady=(8, 4))
        ttk.Button(controls, text="−", command=lambda: self._change_preview_view_zoom(1 / _PREVIEW_VIEW_ZOOM_STEP)).pack(side=tk.LEFT)
        ttk.Button(controls, text="+", command=lambda: self._change_preview_view_zoom(_PREVIEW_VIEW_ZOOM_STEP)).pack(side=tk.LEFT, padx=(4, 0))
        ttk.Button(controls, text="重設為適合視窗", command=self._reset_preview_view).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(controls, text="1:1", command=self._set_preview_view_one_to_one).pack(side=tk.LEFT, padx=(4, 0))
        ttk.Button(controls, text="全螢幕", command=lambda: self._set_preview_view_fullscreen(True)).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Label(controls, text="滾輪縮放；拖曳平移；Esc 離開全螢幕").pack(side=tk.RIGHT)
        canvas = tk.Canvas(window, bg="#071627", highlightthickness=0, cursor="fleur")
        canvas.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
        canvas.bind("<MouseWheel>", self._on_preview_view_mousewheel)
        canvas.bind("<Button-4>", lambda _event: self._change_preview_view_zoom(_PREVIEW_VIEW_ZOOM_STEP))
        canvas.bind("<Button-5>", lambda _event: self._change_preview_view_zoom(1 / _PREVIEW_VIEW_ZOOM_STEP))
        canvas.bind("<ButtonPress-1>", self._on_preview_view_drag_start)
        canvas.bind("<B1-Motion>", self._on_preview_view_drag)
        self._preview_view_window = window
        self._preview_view_canvas = canvas
        self._reset_preview_view()

    def _close_preview_view(self) -> None:
        if self._preview_view_window is not None:
            self._preview_view_window.destroy()
        self._preview_view_window = None
        self._preview_view_canvas = None
        self._preview_view_photo_image = None

    def _set_preview_view_fullscreen(self, enabled: bool) -> None:
        if self._preview_view_window is not None and self._preview_view_window.winfo_exists():
            self._preview_view_window.attributes("-fullscreen", bool(enabled))

    def _change_preview_view_zoom(self, factor: float) -> None:
        self._preview_view_zoom = min(_PREVIEW_VIEW_MAX_ZOOM, max(1.0, self._preview_view_zoom * factor))

    def _set_preview_view_one_to_one(self) -> None:
        canvas = self._preview_view_canvas
        if canvas is None:
            return
        with self._preview_display_lock:
            frame = self._preview_display_frame
        if frame is None:
            return
        width = max(1, int(canvas.winfo_width()))
        height = max(1, int(canvas.winfo_height()))
        fit_scale = min(width / float(frame.shape[1]), height / float(frame.shape[0]))
        self._preview_view_zoom = min(_PREVIEW_VIEW_MAX_ZOOM, max(1.0, 1.0 / fit_scale))

    def _on_preview_view_mousewheel(self, event: tk.Event) -> None:
        self._change_preview_view_zoom(_PREVIEW_VIEW_ZOOM_STEP if event.delta > 0 else 1 / _PREVIEW_VIEW_ZOOM_STEP)

    def _on_preview_view_drag_start(self, event: tk.Event) -> None:
        self._preview_view_drag_start = (int(event.x), int(event.y))

    def _on_preview_view_drag(self, event: tk.Event) -> None:
        start = self._preview_view_drag_start
        canvas = self._preview_view_canvas
        if start is None or canvas is None:
            return
        with self._preview_display_lock:
            frame = self._preview_display_frame
        if frame is None:
            return
        width = max(1, int(canvas.winfo_width()))
        height = max(1, int(canvas.winfo_height()))
        fit_scale = min(width / float(frame.shape[1]), height / float(frame.shape[0]))
        scale = fit_scale * self._preview_view_zoom
        center_x, center_y = self._preview_view_center
        self._preview_view_center = (
            min(1.0, max(0.0, center_x - (int(event.x) - start[0]) / (frame.shape[1] * scale))),
            min(1.0, max(0.0, center_y - (int(event.y) - start[1]) / (frame.shape[0] * scale))),
        )
        self._preview_view_drag_start = (int(event.x), int(event.y))

    def _refresh_preview_view_window(self, frame: np.ndarray) -> None:
        canvas = self._preview_view_canvas
        if canvas is None or self._preview_view_window is None or not self._preview_view_window.winfo_exists():
            return
        width = max(1, int(canvas.winfo_width()))
        height = max(1, int(canvas.winfo_height()))
        rendered = self._render_preview_view(frame, width, height, self._preview_view_zoom, self._preview_view_center)
        photo_image = self._preview_photoimage_from_bgr(rendered)
        self._preview_view_photo_image = photo_image
        canvas.delete("preview")
        canvas.create_image(0, 0, anchor=tk.NW, image=photo_image, tags="preview")

    @staticmethod
    def _preview_photoimage_from_bgr(frame: np.ndarray) -> tk.PhotoImage:
        ok, encoded = cv2.imencode(".png", frame)
        if not ok:
            raise RuntimeError("無法轉換預覽畫面")
        return tk.PhotoImage(data=base64.b64encode(encoded.tobytes()), format="png")

    def _schedule_preview_display(self) -> None:
        try:
            self.root.after(33, self._preview_display_tick)
        except Exception:
            pass

    def _preview_display_tick(self) -> None:
        with self._preview_display_lock:
            frame = None if self._preview_display_frame is None else self._preview_display_frame.copy()
            message = self._preview_display_message
        self._update_preview_confidence_display()
        if not self._preview_running:
            self._show_preview_placeholder(message or "預覽已停止")
            return
        if frame is None:
            self._show_preview_placeholder(message or "等待 Basler 訊號…")
        elif self._preview_display_label is not None:
            try:
                embedded = self._render_preview_view(
                    frame,
                    _EMBEDDED_PREVIEW_MAX_WIDTH,
                    _EMBEDDED_PREVIEW_MAX_HEIGHT,
                )
                photo_image = self._preview_photoimage_from_bgr(embedded)
                self._preview_photo_image = photo_image
                self._preview_display_label.configure(image=photo_image, text="")
                self.preview_display_status_var.set(message)
                self._refresh_preview_view_window(frame)
            except Exception as exc:
                self._show_preview_placeholder(f"預覽顯示失敗：{exc}")
        self._schedule_preview_display()

    @staticmethod
    def _prepare_capture_save_frame(
        frame: np.ndarray,
        max_long_side: int = _CAPTURE_SAVE_MAX_LONG_SIDE,
    ) -> np.ndarray:
        return StepperDragGUI._downscale_frame_quality_first(frame, max_long_side=max_long_side)

    @staticmethod
    def _write_capture_image(path: Path, frame: np.ndarray) -> bool:
        params: list[int] = []
        if path.suffix.lower() == ".png":
            params = [cv2.IMWRITE_PNG_COMPRESSION, _CAPTURE_PNG_COMPRESSION]
        elif path.suffix.lower() in {".jpg", ".jpeg"}:
            params = [cv2.IMWRITE_JPEG_QUALITY, 100]
        return bool(cv2.imwrite(str(path), frame, params))

    def _matches_preferred_basler_model(self, model_name: str) -> bool:
        return self.preferred_basler_model in model_name.lower()

    @staticmethod
    def _set_pylon_enum_if_available(camera: object, attr_name: str, value: str) -> bool:
        try:
            node = getattr(camera, attr_name)
        except Exception:
            return False
        if node is None:
            return False
        try:
            if hasattr(node, "SetValue"):
                node.SetValue(value)
                return True
        except Exception:
            return False
        return False

    @staticmethod
    def _set_pylon_float_if_available(camera: object, attr_name: str, value: float) -> bool:
        try:
            node = getattr(camera, attr_name)
        except Exception:
            return False
        if node is None:
            return False
        try:
            if hasattr(node, "SetValue"):
                node.SetValue(value)
                return True
        except Exception:
            return False
        return False

    @staticmethod
    def _set_pylon_bool_if_available(camera: object, attr_name: str, value: bool) -> bool:
        try:
            node = getattr(camera, attr_name)
        except Exception:
            return False
        if node is None:
            return False
        try:
            if hasattr(node, "SetValue"):
                node.SetValue(value)
                return True
        except Exception:
            return False
        return False

    @staticmethod
    def _set_pylon_integer_min_if_available(camera: object, attr_name: str) -> Optional[int]:
        try:
            node = getattr(camera, attr_name)
        except Exception:
            return None
        if node is None or not hasattr(node, "SetValue"):
            return None
        try:
            value = int(node.GetMin()) if hasattr(node, "GetMin") else 0
            node.SetValue(value)
            return value
        except Exception:
            return None

    @staticmethod
    def _set_pylon_integer_max_if_available(camera: object, attr_name: str) -> Optional[int]:
        try:
            node = getattr(camera, attr_name)
        except Exception:
            return None
        if node is None or not hasattr(node, "SetValue"):
            return None
        try:
            if hasattr(node, "GetMax"):
                value = int(node.GetMax())
            elif hasattr(node, "Max"):
                value = int(node.Max)
            else:
                return None
            node.SetValue(value)
            return value
        except Exception:
            return None

    def _configure_basler_camera(self, camera: object) -> None:
        # Tune Basler for a smoother preview while keeping automatic exposure/gain enabled.
        applied_sensor_window: list[str] = []
        for attr_name in ("OffsetX", "OffsetY"):
            value = self._set_pylon_integer_min_if_available(camera, attr_name)
            if value is not None:
                applied_sensor_window.append(f"{attr_name}={value}")
        for attr_name in ("Width", "Height"):
            value = self._set_pylon_integer_max_if_available(camera, attr_name)
            if value is not None:
                applied_sensor_window.append(f"{attr_name}={value}")
        for attr_name in ("OffsetX", "OffsetY"):
            value = self._set_pylon_integer_min_if_available(camera, attr_name)
            if value is not None:
                applied_sensor_window.append(f"{attr_name}={value}")
        if applied_sensor_window:
            self._append_log("Basler full-frame ROI: " + ", ".join(applied_sensor_window))

        self._set_pylon_enum_if_available(camera, "TriggerSelector", "FrameStart")
        self._set_pylon_enum_if_available(camera, "TriggerMode", "Off")
        self._set_pylon_enum_if_available(camera, "AcquisitionMode", "Continuous")
        self._set_pylon_enum_if_available(camera, "ExposureMode", "Timed")
        self._set_pylon_enum_if_available(camera, "ExposureAuto", "Continuous")
        self._set_pylon_enum_if_available(camera, "GainAuto", "Continuous")
        self._set_pylon_enum_if_available(camera, "BalanceWhiteAuto", "Continuous")
        self._set_pylon_enum_if_available(camera, "LightSourcePreset", "Daylight5000K")
        self._set_pylon_float_if_available(camera, "Gamma", 1.0)
        self._set_pylon_float_if_available(camera, "AutoExposureTimeLowerLimit", _BASLER_PREVIEW_EXPOSURE_LOWER_US)
        self._set_pylon_float_if_available(camera, "AutoExposureTimeUpperLimit", _BASLER_PREVIEW_EXPOSURE_UPPER_US)
        self._set_pylon_bool_if_available(camera, "AcquisitionFrameRateEnable", True)
        self._set_pylon_float_if_available(camera, "AcquisitionFrameRate", _BASLER_PREVIEW_FPS)

    def _switch_basler_to_auto_exposure(self, camera: object) -> None:
        self._set_pylon_enum_if_available(camera, "ExposureMode", "Timed")
        self._set_pylon_enum_if_available(camera, "ExposureAuto", "Continuous")
        self._set_pylon_enum_if_available(camera, "GainAuto", "Continuous")
        self._set_pylon_enum_if_available(camera, "BalanceWhiteAuto", "Continuous")

    def _styled_camera_frame(self, frame: np.ndarray) -> np.ndarray:
        return np.ascontiguousarray(frame.copy())

    @staticmethod
    def _draw_preview_status_overlay(
        frame: np.ndarray,
        lines: list[tuple[str, tuple[int, int, int]]],
    ) -> None:
        for index, (text, color) in enumerate(lines, start=1):
            origin = (_PREVIEW_OVERLAY_MARGIN, index * _PREVIEW_OVERLAY_LINE_HEIGHT)
            put_text(
                frame,
                text,
                origin,
                _PREVIEW_OVERLAY_FONT_SCALE,
                (0, 0, 0),
                _PREVIEW_OVERLAY_TEXT_THICKNESS + 4,
            )
            put_text(
                frame,
                text,
                origin,
                _PREVIEW_OVERLAY_FONT_SCALE,
                color,
                _PREVIEW_OVERLAY_TEXT_THICKNESS,
            )

    def _get_detect_conf(self) -> float:
        try:
            conf = float(self.object_detect_conf_var.get())
        except Exception:
            conf = 0.25
        conf = max(0.01, min(1.0, conf))
        self.object_detect_conf_var.set(conf)
        return conf

    def _get_wbc_subtype_conf(self) -> float:
        try:
            conf = float(self.wbc_subtype_conf_var.get())
        except Exception:
            conf = 0.70
        conf = max(0.01, min(1.0, conf))
        self.wbc_subtype_conf_var.set(conf)
        return conf

    def _resolve_detect_model_for_gui(self) -> str:
        requested = self.object_detect_model_var.get().strip() or None
        if resolve_detect_model_path is None:
            return requested or "yolov8n.pt"
        return resolve_detect_model_path(PROJECT_ROOT, requested)

    def _resolve_wbc_subtype_model_for_gui(self) -> str | None:
        return None

    def _choose_detect_model(self) -> None:
        selected = filedialog.askopenfilename(
            title="選擇細胞偵測模型",
            filetypes=[("YOLO / ONNX 模型", "*.pt *.onnx"), ("所有檔案", "*.*")],
        )
        if not selected:
            return
        self.object_detect_model_var.set(selected)
        self.object_detect_model_status_var.set(f"目前模型: {Path(selected).name}（尚未載入）")
        with self._detector_lock:
            self._object_detector = None
            self._object_detector_key = None
        self._append_log(f"已選擇偵測模型：{selected}")

    def _reset_detect_model_to_default(self) -> None:
        if resolve_detect_model_path is None:
            self._append_log("無法解析預設偵測模型。")
            return
        model_path = resolve_detect_model_path(PROJECT_ROOT, None)
        self.object_detect_model_var.set(model_path)
        self.object_detect_model_status_var.set(f"目前模型: {Path(model_path).name}")
        with self._detector_lock:
            self._object_detector = None
            self._object_detector_key = None
        self._append_log(f"已套用預設 WBC 偵測模型：{model_path}")

    def _describe_detect_model_status(self, model_path: str) -> tuple[str, tuple[int, int, int]]:
        normalized = model_path.replace("\\", "/").lower()
        filename = Path(model_path).name.lower()
        if "-cls" in filename or "/classify/" in normalized:
            return "Warning: classification model cannot draw bbox", (0, 80, 255)
        if "wbc_focus" in filename:
            return "WBC-focused detection loaded", (0, 255, 0)
        if "blood_cells_3cls" in filename:
            return "3-class blood-cell detection loaded: WBC / RBC / Platelets", (0, 255, 0)
        generic_names = {"yolov8n.pt", "yolov8s.pt", "yolov8m.pt", "yolov8l.pt", "yolov8x.pt"}
        if filename in generic_names:
            return "Note: generic YOLO model may not detect cells", (0, 220, 255)
        if "/outputs/runs/detect/" in normalized or filename == "best.pt":
            return "cell detection model loaded", (0, 255, 0)
        if not Path(model_path).exists():
            return "Warning: detection model path not found", (0, 80, 255)
        return "custom detection model loaded", (0, 255, 0)

    def _get_object_detector(self) -> Optional[ObjectDetector]:
        if ObjectDetector is None or annotate_detections is None:
            if not self._detector_unavailable_logged:
                self._append_log("物件辨識模組不可用，將略過辨識。")
                self._detector_unavailable_logged = True
            return None

        conf = self._get_detect_conf()
        model_path = self._resolve_detect_model_for_gui()
        subtype_model_path = self._resolve_wbc_subtype_model_for_gui()
        subtype_conf = self._get_wbc_subtype_conf()
        key = (model_path, conf, subtype_model_path or "", subtype_conf)
        with self._detector_lock:
            if self._object_detector is not None and self._object_detector_key == key:
                return self._object_detector
            try:
                detector = ObjectDetector(
                    model_path=model_path,
                    conf_threshold=conf,
                    wbc_subtype_model_path=subtype_model_path,
                    wbc_subtype_min_conf=subtype_conf,
                )
                detector._ensure_model()
                if subtype_model_path:
                    detector._ensure_wbc_subtype_classifier()
            except Exception as exc:
                if not self._detector_unavailable_logged:
                    self._append_log(f"物件辨識初始化失敗: {exc}")
                    self._detector_unavailable_logged = True
                self._object_detector = None
                self._object_detector_key = None
                return None

            self._object_detector = detector
            self._object_detector_key = key
            self._detector_unavailable_logged = False
            self._append_log(f"物件辨識已載入：model={model_path} conf={conf:.2f}")
            if subtype_model_path:
                self._append_log(f"WBC 五分類已載入：model={subtype_model_path} min_conf={subtype_conf:.2f}")
            status_text, _status_color = self._describe_detect_model_status(model_path)
            self.object_detect_model_status_var.set(f"目前模型: {Path(model_path).name} | {status_text}")
            self.wbc_subtype_model_status_var.set("WBC 統一分類：White_Blood_Cell")
            self._append_log(status_text)
            return detector

    def _detect_objects(self, frame: np.ndarray, conf_threshold: Optional[float] = None) -> list:
        detector = self._get_object_detector()
        if detector is None:
            return []
        conf = self._get_detect_conf() if conf_threshold is None else float(conf_threshold)
        try:
            with self._detector_inference_lock:
                return detector.detect(frame, conf_threshold=conf)
        except Exception as exc:
            if not self._detector_unavailable_logged:
                self._append_log(f"物件辨識執行失敗：{exc}")
                self._detector_unavailable_logged = True
            return []

    def _render_detection_overlay(
        self,
        display_frame: np.ndarray,
        detection_frame: Optional[np.ndarray] = None,
    ) -> tuple[np.ndarray, list]:
        if display_frame is None:
            return display_frame, []
        if annotate_detections is None:
            return display_frame, []
        source_frame = detection_frame if detection_frame is not None else display_frame
        detections = self._detect_objects(source_frame)
        if not detections:
            return display_frame.copy(), []
        return annotate_detections(display_frame, detections), detections

    def _submit_preview_inference(self, frame: np.ndarray) -> None:
        inference_frame = np.ascontiguousarray(frame.copy())
        try:
            self._preview_inference_queue.put_nowait(inference_frame)
            return
        except queue.Full:
            pass
        try:
            self._preview_inference_queue.get_nowait()
        except queue.Empty:
            pass
        try:
            self._preview_inference_queue.put_nowait(inference_frame)
        except queue.Full:
            pass

    def _preview_inference_loop(self) -> None:
        while not self._preview_inference_stop.is_set():
            try:
                frame = self._preview_inference_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            detections = self._detect_objects(frame)
            with self._preview_detection_lock:
                self._preview_detections = detections

    def _latest_preview_detections(self) -> list:
        with self._preview_detection_lock:
            return list(self._preview_detections)

    @staticmethod
    def _format_preview_confidence(detections: list) -> str:
        confidence_values = [
            max(0.0, min(1.0, float(getattr(detection, "conf", 0.0))))
            for detection in detections
        ]
        if not confidence_values:
            return "目前偵測信心值：尚無結果"
        if len(confidence_values) == 1:
            return f"目前偵測信心值：{confidence_values[0]:.2f}"
        return f"目前偵測信心值：最高 {max(confidence_values):.2f}（{len(confidence_values)} 個目標）"

    def _update_preview_confidence_display(self) -> None:
        if not self._preview_running:
            text = "目前偵測信心值：預覽未啟動"
        elif not bool(self.object_detect_preview_var.get()):
            text = "目前偵測信心值：辨識已關閉"
        else:
            text = self._format_preview_confidence(self._latest_preview_detections())
        self.object_detect_confidence_display_var.set(text)

    @staticmethod
    def _scale_preview_detections(
        detections: list,
        source_shape: tuple[int, ...],
        display_shape: tuple[int, ...],
    ) -> list:
        """Map inference boxes from the compact frame onto the raw display frame."""
        if not detections:
            return list(detections)
        source_height, source_width = source_shape[:2]
        display_height, display_width = display_shape[:2]
        if source_width <= 0 or source_height <= 0:
            return list(detections)
        scale_x = display_width / float(source_width)
        scale_y = display_height / float(source_height)
        scaled: list = []
        for detection in detections:
            if not all(hasattr(detection, attribute) for attribute in ("x1", "y1", "x2", "y2")):
                scaled.append(detection)
                continue
            try:
                scaled.append(
                    replace(
                        detection,
                        x1=int(round(detection.x1 * scale_x)),
                        y1=int(round(detection.y1 * scale_y)),
                        x2=int(round(detection.x2 * scale_x)),
                        y2=int(round(detection.y2 * scale_y)),
                    )
                )
            except TypeError:
                scaled.append(detection)
        return scaled

    def _save_detection_artifacts(
        self,
        image_path: Path,
        frame: np.ndarray,
        detections: Optional[list] = None,
        force_features: bool = False,
    ) -> Optional[int]:
        save_visual_artifacts = bool(self.object_detect_save_var.get())
        if not save_visual_artifacts and not force_features:
            return None
        if frame is None:
            return None
        if annotate_detections is None and save_visual_artifacts:
            return None
        if image_path.stem.endswith("_detected"):
            return None

        if detections is None:
            detections = self._detect_objects(frame)

        if save_visual_artifacts and detections and annotate_detections is not None:
            detected_image = annotate_detections(frame, detections)
        else:
            detected_image = frame.copy()

        detected_dir = image_path.parent / "detected"
        detected_dir.mkdir(parents=True, exist_ok=True)
        detected_path = detected_dir / f"{image_path.stem}_detected{image_path.suffix or '.jpg'}"
        report_path = detected_dir / f"{image_path.stem}_detected.txt"
        features_path = detected_dir / f"{image_path.stem}_features.json"

        if save_visual_artifacts:
            cv2.imwrite(str(detected_path), detected_image)
        feature_records: list[dict[str, Any]] = []
        report_handle = report_path.open("w", encoding="utf-8") if save_visual_artifacts else None
        try:
            if report_handle is not None:
                report_handle.write(f"source: {image_path}\n")
                report_handle.write(f"detections: {len(detections)}\n")
            for idx, det in enumerate(detections, start=1):
                width = max(0.0, float(getattr(det, "x2", 0) - getattr(det, "x1", 0)))
                height = max(0.0, float(getattr(det, "y2", 0) - getattr(det, "y1", 0)))
                feature_records.append(
                    {
                        "cx": float(getattr(det, "x1", 0) + getattr(det, "x2", 0)) / 2.0,
                        "cy": float(getattr(det, "y1", 0) + getattr(det, "y2", 0)) / 2.0,
                        "width": width,
                        "height": height,
                        "area": width * height,
                        "cls_id": int(getattr(det, "cls_id", -1)),
                        "label": str(getattr(det, "label", "")),
                        "conf": float(getattr(det, "conf", 0.0)),
                        "wbc_subtype": getattr(det, "wbc_subtype", None),
                        "wbc_subtype_conf": getattr(det, "wbc_subtype_conf", None),
                    }
                )
                subtype_text = ""
                if getattr(det, "wbc_subtype", None):
                    subtype_text = (
                        f", wbc_subtype={getattr(det, 'wbc_subtype')}, "
                        f"wbc_subtype_conf={float(getattr(det, 'wbc_subtype_conf', 0.0)):.4f}"
                    )
                if report_handle is not None:
                    report_handle.write(
                        f"{idx}: bbox=[{det.x1},{det.y1},{det.x2},{det.y2}], "
                        f"label={det.label}, conf={det.conf:.4f}{subtype_text}\n"
                    )
        finally:
            if report_handle is not None:
                report_handle.close()
        feature_payload = {
            "image": image_path.name,
            "source": str(image_path.resolve()),
            "model_path": self._resolve_detect_model_for_gui(),
            "confidence": self._get_detect_conf(),
            "feature_count": len(feature_records),
            "features": feature_records,
            "annotated_path": str(detected_path.resolve()) if save_visual_artifacts else "",
        }
        with features_path.open("w", encoding="utf-8") as handle:
            json.dump(feature_payload, handle, ensure_ascii=False, indent=2)
        return len(detections)

    def _save_detection_artifacts_from_path(self, image_path: str) -> Optional[int]:
        path = Path(image_path)
        if path.stem.endswith("_detected"):
            return None
        frame = cv2.imread(str(path))
        if frame is None:
            return None
        return self._save_detection_artifacts(path, frame, detections=None)

    def _open_basler_camera(self) -> Optional[_PylonVideoCapture]:
        try:
            from pypylon import pylon
        except Exception as exc:
            self._append_log(f"pypylon 未安裝或無法載入：{exc}")
            return None

        try:
            tl_factory = pylon.TlFactory.GetInstance()
            devices = tl_factory.EnumerateDevices()
            if not devices:
                self._append_log("未偵測到 Basler 攝影機。")
                return None

            selected = None
            for device in devices:
                model_name = str(device.GetModelName())
                if self._matches_preferred_basler_model(model_name):
                    selected = device
                    self._append_log(f"已匹配指定 Basler 型號: {model_name}")
                    break
            if selected is None:
                selected = devices[0]
                self._append_log(f"未匹配指定型號，改用第一台 Basler: {selected.GetModelName()}")

            self._append_log(
                "Basler 列表: "
                + ", ".join([f"{d.GetModelName()}({d.GetSerialNumber()})" for d in devices])
            )

            pylon_camera = pylon.InstantCamera(tl_factory.CreateDevice(selected))
            pylon_camera.Open()
            self._configure_basler_camera(pylon_camera)
            converter = pylon.ImageFormatConverter()
            converter.OutputPixelFormat = pylon.PixelType_BGR8packed
            converter.OutputBitAlignment = pylon.OutputBitAlignment_MsbAligned
            pylon_camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
            cap = _PylonVideoCapture(pylon_camera, converter)
            cap.warmup()
            ok, probe_frame = cap.read()
            if ok and probe_frame is not None and float(probe_frame.mean()) < 20.0:
                self._append_log("Basler 固定曝光畫面過暗，切換為自動曝光/增益。")
                self._switch_basler_to_auto_exposure(pylon_camera)
                cap.warmup()
            self._append_log(
                "Basler 預覽模式: "
                f"{_BASLER_PREVIEW_FPS:.0f} fps, "
                f"auto-exposure <= {_BASLER_PREVIEW_EXPOSURE_UPPER_US / 1000.0:.0f} ms"
            )
            self._append_log(f"已開啟 Basler 攝影機: {selected.GetModelName()} (serial={selected.GetSerialNumber()})")
            return cap
        except Exception as exc:
            self._append_log(f"Basler 開啟失敗: {exc}")
            return None

    @staticmethod
    def _is_builtin_camera_index(camera_index: int) -> bool:
        return camera_index == 0

    def _candidate_camera_indices(self) -> list[int]:
        manual_index = int(self.camera_index_var.get())
        indices: list[int] = []
        if manual_index >= 0 and not self._is_builtin_camera_index(manual_index):
            indices.append(manual_index)

        for idx in range(1, 11):
            if idx not in indices:
                indices.append(idx)

        if 0 not in indices:
            indices.append(0)

        return indices

    def _try_open_camera(
        self,
        camera_index: int,
        backend_name: str,
        backend: Optional[int],
    ) -> Optional[cv2.VideoCapture]:
        cap = cv2.VideoCapture(camera_index, backend) if backend is not None else cv2.VideoCapture(camera_index)
        if not cap.isOpened():
            cap.release()
            return None

        ok = False
        for _ in range(2):
            ret, frame = cap.read()
            if ret and frame is not None:
                ok = True
                break
            time.sleep(0.05)

        if not ok:
            cap.release()
            return None

        self._append_log(f"已開啟攝影機: index={camera_index}, backend={backend_name}")
        return cap

    def _auto_open_camera(self) -> Optional[cv2.VideoCapture]:
        basler_camera = self._open_basler_camera()
        if basler_camera is not None:
            return basler_camera

        raise RuntimeError(
            "未偵測到可用 Basler。預覽已固定為 Basler，請確認相機已連線、未被 Pylon Viewer 佔用，且 pypylon 可正常載入。"
        )

    def _preview_loop(self) -> None:
        fail_count = 0
        last_shape_info: Optional[tuple[tuple[int, int], tuple[int, int], tuple[int, int]]] = None
        while not self._preview_stop.is_set():
            try:
                frame_cap = self._ensure_camera_open()
                if frame_cap is None:
                    break
                frame = self._read_latest_frame(discard_frames=1)
                if frame is None:
                    fail_count += 1
                    if fail_count == 1:
                        self._append_log("預覽警告：尚未拿到畫面幀，將持續重試。")
                        self._set_preview_display_message("等待 Basler 訊號…")
                    if fail_count >= 60:
                        raise RuntimeError("長時間無法抓到畫面幀，請檢查相機供電/授權/USB。")
                    continue
                fail_count = 0
                x, y = self._get_virtual_coord()
                # Display the original Basler frame.  Only the inference worker gets
                # a compact copy, so the UI does not silently alter camera color,
                # contrast, sharpness, or source resolution before rendering.
                preview_source = self._prepare_preview_frame(frame)
                display_preview = np.ascontiguousarray(frame.copy())
                if bool(self.object_detect_preview_var.get()):
                    model_path = self._resolve_detect_model_for_gui()
                    status_text, status_color = self._describe_detect_model_status(model_path)
                    self._submit_preview_inference(preview_source)
                    detections = self._scale_preview_detections(
                        self._latest_preview_detections(),
                        preview_source.shape,
                        display_preview.shape,
                    )
                    if detections and annotate_detections is not None:
                        display_preview = annotate_detections(
                            display_preview,
                            detections,
                            font_scale=_PREVIEW_OVERLAY_FONT_SCALE,
                            box_thickness=_PREVIEW_OVERLAY_BOX_THICKNESS,
                            text_thickness=_PREVIEW_OVERLAY_TEXT_THICKNESS,
                        )
                    detection_lines = [
                        (f"detections: {len(detections)}", (255, 220, 0)),
                        (f"model: {Path(model_path).name}", (255, 255, 255)),
                        (status_text, status_color),
                    ]
                else:
                    detection_lines = []
                    with self._preview_detection_lock:
                        self._preview_detections = []
                self._draw_preview_status_overlay(
                    display_preview,
                    [
                        ("Live preview", (0, 255, 0)),
                        (f"coord: {x},{y}", (0, 220, 255)),
                        *detection_lines,
                    ],
                )
                self._publish_preview_display_frame(
                    display_preview,
                    f"Basler 原始畫面：{frame.shape[1]}×{frame.shape[0]} | 顯示：{display_preview.shape[1]}×{display_preview.shape[0]}",
                )
                shape_info = (
                    (int(frame.shape[1]), int(frame.shape[0])),
                    (int(display_preview.shape[1]), int(display_preview.shape[0])),
                )
                if shape_info != last_shape_info:
                    last_shape_info = shape_info
                    self._append_log(
                        "預覽尺寸: "
                        f"raw={shape_info[0][0]}x{shape_info[0][1]}, "
                        f"display-buffer={shape_info[1][0]}x{shape_info[1][1]}"
                    )
            except Exception as exc:
                self._append_log(f"預覽錯誤: {exc}")
                self._set_preview_display_message(f"預覽錯誤：{exc}")
                break

        self._append_log("預覽已停止。")
        self._set_preview_display_message("預覽已停止；尚無相機訊號時會顯示 MSH 圖標。")
        self._preview_inference_stop.set()
        self._preview_running = False

    def _start_preview(self) -> None:
        if self._preview_running:
            self._append_log("預覽已在執行中。")
            return
        try:
            try:
                cv2.destroyAllWindows()
            except Exception:
                pass
            self._ensure_camera_open()
            with self._preview_display_lock:
                self._preview_display_frame = None
            self._append_log(
                "預覽模式: 顯示 Basler 原始畫面；僅依視窗等比例縮放。"
                f"辨識工作者使用 long_side={_PREVIEW_PROCESS_MAX_LONG_SIDE}px 的獨立縮圖。"
            )
            if bool(self.object_detect_preview_var.get()):
                model_path = self._resolve_detect_model_for_gui()
                self._append_log(f"預覽物件辨識已啟用：model={model_path} conf={self._get_detect_conf():.2f}")
                status_text, _status_color = self._describe_detect_model_status(model_path)
                self._append_log(status_text)
            else:
                self._append_log("預覽物件辨識目前為關閉狀態。")
        except Exception as exc:
            self._append_log(f"啟動預覽失敗: {exc}")
            messagebox.showerror("預覽錯誤", str(exc))
            return

        self._preview_stop.clear()
        self._preview_inference_stop.clear()
        self._preview_inference_queue = queue.Queue(maxsize=1)
        with self._preview_detection_lock:
            self._preview_detections = []
        self._preview_inference_thread = threading.Thread(target=self._preview_inference_loop, daemon=True)
        self._preview_inference_thread.start()
        self._preview_running = True
        self._set_preview_display_message("正在等待 Basler 訊號…")
        self._show_preview_placeholder("正在等待 Basler 訊號…")
        self._schedule_preview_display()
        self._preview_thread = threading.Thread(target=self._preview_loop, daemon=True)
        self._preview_thread.start()
        self._append_log("預覽已開始。")


    def _stop_preview(self) -> None:
        if not self._preview_running and self._preview_thread is None and self._preview_inference_thread is None:
            return
        self._preview_stop.set()
        self._preview_inference_stop.set()
        thread = self._preview_thread
        if thread is not None:
            thread.join(timeout=1.0)
        inference_thread = self._preview_inference_thread
        if inference_thread is not None:
            inference_thread.join(timeout=1.0)
        self._preview_thread = None
        self._preview_inference_thread = None
        with self._preview_display_lock:
            self._preview_display_frame = None
        self._show_preview_placeholder("預覽已停止；尚無相機訊號時會顯示 MSH 圖標。")
        with self._camera_lock:
            if self.cap is not None:
                self.cap.release()
                self.cap = None

    def _capture_frame(self) -> None:
        try:
            frame = self._read_latest_frame(discard_frames=5)
            out_dir = self._ensure_manual_capture_session()
            x, y = self._get_virtual_coord()
            path = out_dir / f"{x}_{y}_{_timestamp()}.png"
            saved_frame = np.ascontiguousarray(frame.copy())
            if not self._write_capture_image(path, saved_frame):
                raise RuntimeError(f"無法寫入拍照檔案: {path}")
            detections = self._detect_objects(saved_frame)
            det_count = self._save_detection_artifacts(path, saved_frame, detections=detections, force_features=True)
            training_records, training_csv, training_xlsx = save_manual_three_class_training_data(
                session_dir=out_dir,
                source_image_path=path,
                frame=saved_frame,
                detections=detections,
                platform_x=x,
                platform_y=y,
            )
            if det_count is None:
                self._append_log(f"已儲存: {path}，座標=({x},{y})")
            else:
                self._append_log(f"已儲存: {path}，座標=({x},{y})，detections={det_count}")
            self._append_log(
                f"三分類訓練預標註已更新：本次裁圖={len(training_records)}，CSV={training_csv}，Excel={training_xlsx}"
            )
        except Exception as exc:
            self._append_log(f"拍照失敗: {exc}")
            messagebox.showerror("拍照錯誤", str(exc))

    def _ensure_manual_capture_session(self) -> Path:
        root_dir = self._resolve_capture_output_dir()
        if (
            self._manual_capture_session is not None
            and self._manual_capture_session.exists()
            and self._manual_capture_session.parent.resolve() == root_dir.resolve()
        ):
            return self._manual_capture_session

        root_dir.mkdir(parents=True, exist_ok=True)
        self._manual_capture_session = root_dir / f"manual_session_{_timestamp()}"
        self._manual_capture_session.mkdir(parents=True, exist_ok=True)
        self._latest_capture_session = self._manual_capture_session
        self._append_log(f"已建立手動拍照資料夾：{self._manual_capture_session.resolve()}")
        self._append_log("手動拍照按鈕: 原始解析度 PNG（不降階、無有損壓縮）")
        return self._manual_capture_session

    def _ensure_wbc_memory_session(self) -> Path:
        root_dir = self._resolve_capture_output_dir()
        if (
            self._wbc_memory_session_dir is not None
            and self._wbc_memory_session_dir.exists()
            and self._wbc_memory_session_dir.parent.resolve() == root_dir.resolve()
        ):
            return self._wbc_memory_session_dir

        root_dir.mkdir(parents=True, exist_ok=True)
        self._wbc_memory_session_dir = root_dir / f"wbc_memory_session_{_timestamp()}"
        self._wbc_memory_session_dir.mkdir(parents=True, exist_ok=True)
        self._latest_capture_session = self._wbc_memory_session_dir
        self._append_log(f"已建立 400X WBC 記憶資料夾：{self._wbc_memory_session_dir.resolve()}")
        return self._wbc_memory_session_dir

    def _write_wbc_memory_manifest(self) -> tuple[Path, Path]:
        session_dir = self._ensure_wbc_memory_session()
        csv_path = session_dir / "wbc_memory.csv"
        json_path = session_dir / "wbc_memory.json"
        with self._wbc_memory_lock:
            records = list(self._wbc_memory_records)

        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                [
                    "memory_id",
                    "created_at",
                    "platform_x",
                    "platform_y",
                    "center_x",
                    "center_y",
                    "frame_width",
                    "frame_height",
                    "bbox_x1",
                    "bbox_y1",
                    "bbox_x2",
                    "bbox_y2",
                    "confidence",
                    "label",
                    "wbc_subtype",
                    "wbc_subtype_confidence",
                    "source_image",
                ]
            )
            for record in records:
                writer.writerow(
                    [
                        record["memory_id"],
                        record["created_at"],
                        record["platform_x"],
                        record["platform_y"],
                        f"{record['center_x']:.2f}",
                        f"{record['center_y']:.2f}",
                        record["frame_width"],
                        record["frame_height"],
                        record["bbox_x1"],
                        record["bbox_y1"],
                        record["bbox_x2"],
                        record["bbox_y2"],
                        f"{record['confidence']:.6f}",
                        record["label"],
                        record.get("wbc_subtype", ""),
                        (
                            f"{float(record['wbc_subtype_confidence']):.6f}"
                            if record.get("wbc_subtype_confidence") is not None
                            else ""
                        ),
                        record["source_image"],
                    ]
                )
        json_path.write_text(
            json.dumps({"wbc_memories": records}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return csv_path.resolve(), json_path.resolve()

    def _memorize_400x_wbc_positions(self) -> None:
        if self._capture_job_running:
            messagebox.showwarning("400X記憶白血球", "拍攝流程進行中，請先終止或等待完成。")
            return

        try:
            frame = self._read_latest_frame(discard_frames=5)
            styled_frame = self._styled_camera_frame(frame)
            saved_frame = self._prepare_capture_save_frame(styled_frame)
            detections = self._detect_objects(saved_frame)
            wbc_detections = [det for det in detections if is_white_blood_cell_detection(det)]
            if not wbc_detections:
                raise RuntimeError("目前畫面沒有偵測到白血球。請確認模型、焦距與 400X 視野。")

            session_dir = self._ensure_wbc_memory_session()
            platform_x, platform_y = self._get_virtual_coord()
            image_path = session_dir / f"400x_wbc_memory_{len(self._wbc_memory_records) + 1:04d}_x{platform_x}_y{platform_y}.jpg"
            if not cv2.imwrite(str(image_path), saved_frame):
                raise RuntimeError(f"無法寫入 400X 記憶影像：{image_path}")
            if annotate_detections is not None:
                overlay = annotate_detections(saved_frame, wbc_detections)
                cv2.imwrite(str(session_dir / f"{image_path.stem}_overlay.jpg"), overlay)

            frame_height, frame_width = saved_frame.shape[:2]
            with self._wbc_memory_lock:
                next_id = len(self._wbc_memory_records) + 1
                for det in sorted(
                    wbc_detections,
                    key=lambda item: score_white_blood_cell_detection(item, saved_frame.shape),
                    reverse=True,
                ):
                    center_x, center_y = detection_center(det)
                    self._wbc_memory_records.append(
                        {
                            "memory_id": next_id,
                            "created_at": datetime.now().isoformat(timespec="seconds"),
                            "platform_x": int(platform_x),
                            "platform_y": int(platform_y),
                            "center_x": float(center_x),
                            "center_y": float(center_y),
                            "frame_width": int(frame_width),
                            "frame_height": int(frame_height),
                            "bbox_x1": int(getattr(det, "x1", 0)),
                            "bbox_y1": int(getattr(det, "y1", 0)),
                            "bbox_x2": int(getattr(det, "x2", 0)),
                            "bbox_y2": int(getattr(det, "y2", 0)),
                            "confidence": float(getattr(det, "conf", 0.0)),
                            "label": str(getattr(det, "label", "")),
                            "wbc_subtype": getattr(det, "wbc_subtype", None),
                            "wbc_subtype_confidence": getattr(det, "wbc_subtype_conf", None),
                            "source_image": str(image_path.resolve()),
                        }
                    )
                    next_id += 1

            csv_path, json_path = self._write_wbc_memory_manifest()
            self._append_log(
                f"400X 已記憶 {len(wbc_detections)} 個白血球；累計={len(self._wbc_memory_records)}，JSON={json_path}"
            )
            messagebox.showinfo(
                "400X記憶白血球",
                f"已記憶 {len(wbc_detections)} 個白血球。\n\nCSV:\n{csv_path}\n\nJSON:\n{json_path}",
            )
        except Exception as exc:
            self._append_log(f"400X記憶白血球失敗: {exc}")
            messagebox.showerror("400X記憶白血球失敗", str(exc))

    @staticmethod
    def _serialize_detections(detections: list) -> list[dict[str, Any]]:
        serialized: list[dict[str, Any]] = []
        for det in detections or []:
            serialized.append(
                {
                    "x1": int(getattr(det, "x1", 0)),
                    "y1": int(getattr(det, "y1", 0)),
                    "x2": int(getattr(det, "x2", 0)),
                    "y2": int(getattr(det, "y2", 0)),
                    "conf": float(getattr(det, "conf", 0.0)),
                    "cls_id": int(getattr(det, "cls_id", -1)),
                    "label": str(getattr(det, "label", "")),
                    "wbc_subtype": getattr(det, "wbc_subtype", None),
                    "wbc_subtype_conf": getattr(det, "wbc_subtype_conf", None),
                }
            )
        return serialized

    def _parse_slide_scan_pitches(self) -> tuple[int, int]:
        try:
            x_pitch = abs(int(self.steps_var.get()))
            y_pitch = abs(int(self.y_steps_var.get()))
            if x_pitch <= 0 or y_pitch <= 0:
                raise ValueError("X/Y 步數必須大於 0。")
        except Exception as exc:
            raise ValueError(f"掃描步距設定無效：{exc}") from exc
        return x_pitch, y_pitch

    def _start_wbc_collection_scan(self) -> None:
        self._start_full_slide_scan(collect_wbc=True)

    def _choose_serpentine_video_output_path(self) -> None:
        current = Path(self.serpentine_video_output_var.get() or "serpentine_continuous_recording.mp4")
        filename = filedialog.asksaveasfilename(
            title="選擇蛇形連續錄影輸出影片",
            initialdir=str(current.parent if current.parent.exists() else PROJECT_ROOT),
            initialfile=current.name,
            defaultextension=".mp4",
            filetypes=[("MP4 video", "*.mp4"), ("AVI video", "*.avi"), ("All files", "*.*")],
        )
        if filename:
            self.serpentine_video_output_var.set(str(Path(filename).resolve()))

    def _set_serpentine_video_status(self, text: str) -> None:
        try:
            self.root.after(0, lambda: self.serpentine_video_status_var.set(text))
        except Exception:
            self.serpentine_video_status_var.set(text)

    def _set_serpentine_start_to_current(self) -> None:
        x, y = self._get_virtual_coord()
        self.serpentine_video_start_x_var.set(int(x))
        self.serpentine_video_start_y_var.set(int(y))
        self._append_log(f"蛇形錄影起點已設為目前座標：({x},{y})")

    def _apply_serpentine_detection_preset(self) -> None:
        self.serpentine_video_speed_var.set(4.0)
        self.serpentine_video_fps_var.set(20.0)
        self._append_log(
            "已套用蛇形錄影辨識穩定參數：Speed=4 steps/s, FPS=20；"
            "每幀約移動 0.20 step，適合產生較穩定的辨識影片。"
        )

    def _parse_serpentine_video_config(self) -> tuple[list[tuple[float, float]], int, int, int, int, float, float, Path]:
        start_x = int(self.serpentine_video_start_x_var.get())
        start_y = int(self.serpentine_video_start_y_var.get())
        end_x = int(self.serpentine_video_end_x_var.get())
        end_y = int(self.serpentine_video_end_y_var.get())
        step_x = int(self.serpentine_video_step_x_var.get())
        step_y = int(self.serpentine_video_step_y_var.get())
        speed = float(self.serpentine_video_speed_var.get())
        fps = float(self.serpentine_video_fps_var.get())
        raw_output_path = self.serpentine_video_output_var.get().strip()
        output_path = (
            Path(raw_output_path).expanduser()
            if raw_output_path
            else Path("output") / "serpentine_continuous_recording.mp4"
        )
        if step_x <= 0 or step_y <= 0:
            raise ValueError("Step X / Step Y 必須大於 0。")
        if speed <= 0:
            raise ValueError("Speed 必須大於 0。")
        if fps <= 0:
            raise ValueError("FPS 必須大於 0。")
        if start_x == end_x and start_y == end_y:
            raise ValueError("起點與終點不能完全相同。")
        path = [(float(start_x), float(start_y)), (float(end_x), float(end_y))]
        cols = int(math.ceil(abs(end_x - start_x) / float(step_x))) + 1
        rows = int(math.ceil(abs(end_y - start_y) / float(step_y))) + 1
        self.serpentine_video_cols_var.set(cols)
        self.serpentine_video_rows_var.set(rows)
        if output_path.suffix.lower() not in {".mp4", ".avi"}:
            output_path = output_path.with_suffix(".mp4")
        if not output_path.is_absolute():
            output_path = (Path.cwd() / output_path).resolve()
        self.serpentine_video_output_var.set(str(output_path))
        frame_motion = speed / fps
        if frame_motion > 0.5:
            self._append_log(
                f"蛇形連續錄影提醒：目前每幀約移動 {frame_motion:.2f} step，"
                "辨識影片建議 <= 0.50 step/frame；可降低 Speed 或提高 FPS。"
            )
        self._append_log(
            "蛇形錄影路線：adaptive 15% overlap 模式；"
            f"起點=({start_x},{start_y}) 終點=({end_x},{end_y}) "
            f"rows={rows}, cols={cols} 為顯示估算，step=({step_x},{step_y}) 不作為實際移動距離。"
        )
        return path, rows, cols, step_x, step_y, speed, fps, output_path

    def _start_serpentine_video_recording(self) -> None:
        if self._serpentine_video_running:
            self._append_log("蛇形連續錄影已在執行中。")
            return
        if self._wbc_capture_running:
            messagebox.showwarning("蛇形連續錄影", "請先停止白血球固定步數蛇行掃描。")
            return
        if self._capture_job_running:
            messagebox.showwarning("蛇形連續錄影", "請先停止既有拍攝任務。")
            return
        if self._auto_running:
            messagebox.showwarning("蛇形連續錄影", "請先停止自動移動。")
            return
        if self._backlash_calibration_running or self._image_feedback_running:
            messagebox.showwarning("蛇形連續錄影", "校正流程進行中，請稍後再試。")
            return
        if self._get_stepper(0) is None or self._get_stepper(1) is None:
            messagebox.showwarning("蛇形連續錄影", "請先連線 X-motor 與 Y-motor。")
            return

        if self._preview_running:
            self._append_log("蛇形連續錄影啟動前先停止一般 Live Preview，避免相機與 OpenCV 視窗互搶資源。")
            self._stop_preview()

        try:
            config = self._parse_serpentine_video_config()
            self._ensure_camera_open()
        except Exception as exc:
            messagebox.showerror("蛇形連續錄影設定", str(exc))
            return

        self._serpentine_video_stop.clear()
        self._serpentine_video_pause.clear()
        self._serpentine_video_restart.clear()
        with self._serpentine_video_display_lock:
            self._serpentine_video_display_frame = None
            self._serpentine_video_display_active = True
            self._serpentine_video_display_window_open = False
        self._schedule_serpentine_video_display()
        self._serpentine_video_running = True
        self._serpentine_video_thread = threading.Thread(
            target=self._serpentine_video_worker,
            args=config,
            daemon=True,
        )
        self._serpentine_video_thread.start()

    def _toggle_serpentine_video_pause(self) -> None:
        if not self._serpentine_video_running:
            self._append_log("蛇形連續錄影尚未開始。")
            return
        if self._serpentine_video_pause.is_set():
            self._serpentine_video_pause.clear()
            self._append_log("蛇形連續錄影繼續。")
        else:
            self._serpentine_video_pause.set()
            self._append_log("蛇形連續錄影已暫停。")

    def _restart_serpentine_video_recording(self) -> None:
        if not self._serpentine_video_running:
            self._append_log("蛇形連續錄影尚未開始。")
            return
        self._serpentine_video_restart.set()
        self._serpentine_video_pause.clear()
        self._append_log("蛇形連續錄影將重新從第一列第一欄開始。")

    def _stop_serpentine_video_recording(self) -> None:
        if not self._serpentine_video_running:
            return
        self._serpentine_video_stop.set()
        self._serpentine_video_pause.clear()
        with self._serpentine_video_display_lock:
            self._serpentine_video_display_active = False
        thread = self._serpentine_video_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.5)
        self._append_log("已送出蛇形連續錄影停止要求。")

    def _schedule_serpentine_video_display(self) -> None:
        try:
            self.root.after(33, self._serpentine_video_display_tick)
        except Exception:
            pass

    def _serpentine_video_display_tick(self) -> None:
        window_name = self._serpentine_video_display_window
        with self._serpentine_video_display_lock:
            active = bool(self._serpentine_video_display_active)
            frame = None if self._serpentine_video_display_frame is None else self._serpentine_video_display_frame.copy()

        if not active:
            try:
                cv2.destroyWindow(window_name)
            except Exception:
                pass
            with self._serpentine_video_display_lock:
                self._serpentine_video_display_window_open = False
            return

        if frame is not None:
            try:
                with self._serpentine_video_display_lock:
                    window_open = self._serpentine_video_display_window_open
                if not window_open:
                    cv2.namedWindow(window_name, cv2.WINDOW_AUTOSIZE)
                    with self._serpentine_video_display_lock:
                        self._serpentine_video_display_window_open = True
                cv2.imshow(window_name, frame)
                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), 27):
                    self._serpentine_video_stop.set()
                elif key == ord("p"):
                    if self._serpentine_video_pause.is_set():
                        self._serpentine_video_pause.clear()
                    else:
                        self._serpentine_video_pause.set()
                elif key == ord("r"):
                    self._serpentine_video_restart.set()
            except Exception as exc:
                self._append_log(f"蛇形連續錄影預覽顯示失敗，已關閉預覽視窗：{exc}")
                with self._serpentine_video_display_lock:
                    self._serpentine_video_display_active = False
                    self._serpentine_video_display_window_open = False
                return

        self._schedule_serpentine_video_display()

    def _move_serpentine_video_to(self, target_x: float, target_y: float) -> tuple[int, int]:
        current_x, current_y = self._get_virtual_coord()
        next_x = int(round(float(target_x)))
        next_y = int(round(float(target_y)))
        dx = next_x - current_x
        dy = next_y - current_y
        if dx != 0:
            self._move_axis_steps(0, dx, apply_backlash=False)
        if dy != 0:
            self._move_axis_steps(1, dy, apply_backlash=False)
        if dx != 0 or dy != 0:
            self._set_virtual_coord(next_x, next_y)
        return next_x, next_y

    @staticmethod
    def _open_serpentine_video_writer(output_path: Path, fps: float, frame_size: tuple[int, int]) -> cv2.VideoWriter:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_path.exists():
            output_path.unlink()
        width, height = frame_size
        codecs = ("mp4v", "avc1", "H264") if output_path.suffix.lower() == ".mp4" else ("MJPG", "XVID", "mp4v")
        for codec in codecs:
            writer = cv2.VideoWriter(
                str(output_path),
                cv2.VideoWriter_fourcc(*codec),
                float(fps),
                (int(width), int(height)),
            )
            if writer.isOpened():
                return writer
            writer.release()
        raise RuntimeError(f"無法建立影片輸出：{output_path}")

    @staticmethod
    def _even_frame_size(frame: np.ndarray) -> tuple[int, int]:
        height, width = frame.shape[:2]
        return max(2, width - (width % 2)), max(2, height - (height % 2))

    def _prepare_serpentine_video_frame(
        self,
        frame: np.ndarray,
        frame_size: tuple[int, int] | None = None,
    ) -> np.ndarray:
        styled = self._styled_camera_frame(frame)
        prepared = self._prepare_capture_save_frame(styled)
        if frame_size is None:
            width, height = self._even_frame_size(prepared)
            if prepared.shape[1] != width or prepared.shape[0] != height:
                prepared = cv2.resize(prepared, (width, height), interpolation=cv2.INTER_AREA)
            return prepared
        width, height = frame_size
        if prepared.shape[1] != width or prepared.shape[0] != height:
            prepared = cv2.resize(prepared, (width, height), interpolation=cv2.INTER_AREA)
        return prepared

    def _draw_serpentine_video_overlay(
        self,
        frame: np.ndarray,
        x: int,
        y: int,
        row_index: int,
        col_index: int,
        progress: float,
        elapsed_s: float,
        eta_s: float,
        paused: bool,
    ) -> np.ndarray:
        output = frame.copy()
        panel_h = 118
        overlay = output.copy()
        cv2.rectangle(overlay, (0, 0), (output.shape[1], panel_h), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.45, output, 0.55, 0.0, output)
        state = "PAUSED" if paused else "REC"
        lines = [
            f"Serpentine video: {state}",
            f"coord=({x},{y}) row={row_index + 1}/{self.serpentine_video_rows_var.get()} col={col_index + 1}/{self.serpentine_video_cols_var.get()}",
            f"progress={progress * 100.0:5.1f}% elapsed={elapsed_s:.1f}s eta={eta_s:.1f}s",
        ]
        for index, text in enumerate(lines):
            put_text(output, text, (16, 28 + index * 28), 0.62, (255, 255, 255), 2)
        progress_x = 16
        progress_y = panel_h - 16
        progress_w = max(1, output.shape[1] - 32)
        cv2.rectangle(output, (progress_x, progress_y), (progress_x + progress_w, progress_y + 7), (80, 80, 80), -1)
        cv2.rectangle(
            output,
            (progress_x, progress_y),
            (progress_x + int(round(progress_w * max(0.0, min(1.0, progress)))), progress_y + 7),
            (55, 220, 120),
            -1,
        )
        return output

    def _set_serpentine_motor_speed(self, speed_steps_per_s: float) -> int:
        delay_ms = int(round(1000.0 / max(1.0, float(speed_steps_per_s))))
        delay_ms = max(1, min(250, delay_ms))
        for axis_id in (0, 1):
            stepper = self._sync_axis_motion_settings(axis_id)
            if stepper is not None:
                axis = self._axis_name(axis_id)
                try:
                    stepper.set_speed_ms(delay_ms)
                except Exception as exc:
                    self._append_log(
                        f"蛇形連續錄影警告：{axis}-motor 不支援 SPEED_MS 或設定失敗，"
                        f"沿用控制板目前速度。錯誤={exc}"
                    )
        self._append_log(f"蛇形連續錄影馬達速度要求：SPEED_MS={delay_ms}，約 {1000.0 / delay_ms:.1f} steps/s")
        return delay_ms

    def _restore_normal_motor_speed_after_serpentine(self) -> None:
        for axis_id in (0, 1):
            stepper = self._get_stepper(axis_id)
            if stepper is None:
                continue
            axis = self._axis_name(axis_id)
            try:
                stepper.set_speed_ms(_NORMAL_MOTOR_SPEED_MS)
            except Exception as exc:
                self._append_log(f"蛇形連續錄影結束後恢復 {axis}-motor 一般速度失敗：{exc}")
        self._append_log(
            f"蛇形連續錄影結束：已恢復一般操作速度 SPEED_MS={_NORMAL_MOTOR_SPEED_MS}。"
        )

    def _move_serpentine_startup_extra_steps(self, axis_id: int, direction: int) -> None:
        stepper = self._sync_axis_motion_settings(axis_id)
        if stepper is None:
            raise RuntimeError(f"{self._axis_name(axis_id)}-motor 尚未連線。")
        signed_steps = _SERPENTINE_STARTUP_EXTRA_STEPS * (1 if int(direction) >= 0 else -1)
        axis = self._axis_name(axis_id)
        self._append_log(
            f"蛇形移動啟動補償：{axis}-motor 額外 MOVE {signed_steps} steps，"
            "此補償不計入 GUI 座標。"
        )
        stepper.move(int(signed_steps), apply_backlash=False)

    def adaptive_serpentine_movement_with_15_percent_overlap(
        self,
        axis_id: int,
        direction: int,
        max_steps: int,
        reference_frame: np.ndarray,
        adaptive_steps: int,
        *,
        target_overlap: float = _SERPENTINE_VIDEO_TARGET_OVERLAP,
    ) -> tuple[int, np.ndarray, float, float, int]:
        """Move one adaptive scan interval and return a new reference frame.

        Recording is handled by the caller in a separate thread. This method only
        controls motion and decides when the next frame has reached the requested
        overlap against the previous reference frame.
        """
        signed_direction = 1 if int(direction) >= 0 else -1
        remaining = max(0, int(abs(max_steps)))
        if remaining <= 0:
            return 0, reference_frame, 1.0, 1.0, max(_SERPENTINE_VIDEO_MIN_ADAPTIVE_STEPS, int(adaptive_steps))

        chunk_steps = max(
            _SERPENTINE_VIDEO_MIN_ADAPTIVE_STEPS,
            min(_SERPENTINE_VIDEO_MAX_ADAPTIVE_STEPS, int(abs(adaptive_steps))),
        )
        total_moved = 0
        last_overlap = 1.0
        last_response = 0.0
        last_frame = reference_frame
        axis_name = self._axis_name(axis_id)
        frame_height, frame_width = reference_frame.shape[:2]
        axis_pixels = float(frame_width if axis_id == 0 else frame_height)
        target_axis_shift_px = max(1.0, (1.0 - float(target_overlap)) * axis_pixels)

        def _step_count_from_measured_shift(axis_shift_px: float, moved_steps: int, desired_shift_px: float) -> int:
            if axis_shift_px < 0.5 or moved_steps <= 0:
                return chunk_steps
            px_per_step = max(1e-6, float(axis_shift_px) / float(moved_steps))
            estimated_steps = int(round(float(desired_shift_px) / px_per_step))
            return max(
                _SERPENTINE_VIDEO_MIN_ADAPTIVE_STEPS,
                min(_SERPENTINE_VIDEO_MAX_ADAPTIVE_STEPS, estimated_steps),
            )

        while remaining > 0 and not self._serpentine_video_stop.is_set():
            while self._serpentine_video_pause.is_set() and not self._serpentine_video_stop.is_set():
                time.sleep(0.05)
            if self._serpentine_video_stop.is_set():
                break

            step_count = min(chunk_steps, remaining)
            signed_steps = signed_direction * int(step_count)
            self._move_axis_steps(axis_id, signed_steps, apply_backlash=False)
            if axis_id == 0:
                self._shift_virtual_coord(signed_steps, 0)
            else:
                self._shift_virtual_coord(0, signed_steps)

            total_moved += int(step_count)
            remaining -= int(step_count)

            try:
                current_frame = self._capture_motion_tracking_frame(discard_frames=1)
                dx, dy, response = self.estimate_frame_shift(reference_frame, current_frame)
                overlap = self.estimate_overlap_ratio(reference_frame, current_frame, dx, dy)
                axis_shift_px = abs(float(dx if axis_id == 0 else dy))
            except Exception as exc:
                self._append_log(f"蛇形錄影影像位移估測失敗，先縮短下一段移動：{exc}")
                current_frame = last_frame
                dx = dy = 0.0
                response = 0.0
                overlap = last_overlap
                axis_shift_px = 0.0

            last_frame = current_frame
            last_overlap = float(overlap)
            last_response = float(response)

            if response < _SERPENTINE_VIDEO_MIN_SHIFT_RESPONSE:
                next_steps = max(_SERPENTINE_VIDEO_MIN_ADAPTIVE_STEPS, int(round(chunk_steps * 0.65)))
                self._append_log(
                    f"蛇形錄影 overlap 追蹤訊號偏低：axis={axis_name}, "
                    f"response={response:.3f}, overlap={overlap:.2f}，下一段縮短為 {next_steps} steps。"
                )
                return total_moved, current_frame, overlap, response, next_steps

            if overlap <= target_overlap + _SERPENTINE_VIDEO_OVERLAP_TOLERANCE or remaining <= 0:
                next_steps = _step_count_from_measured_shift(axis_shift_px, total_moved, target_axis_shift_px)
                if overlap < target_overlap - _SERPENTINE_VIDEO_OVERLAP_TOLERANCE:
                    next_steps = max(_SERPENTINE_VIDEO_MIN_ADAPTIVE_STEPS, int(round(next_steps * 0.85)))
                    self._append_log(
                        f"蛇形錄影 overlap={overlap:.2f} 低於目標 {target_overlap:.2f}，"
                        f"代表剛剛移動偏遠；下一段縮短為 {next_steps} steps。"
                    )
                elif overlap > target_overlap + _SERPENTINE_VIDEO_OVERLAP_TOLERANCE:
                    next_steps = min(_SERPENTINE_VIDEO_MAX_ADAPTIVE_STEPS, max(chunk_steps + 1, next_steps))
                return total_moved, current_frame, overlap, response, next_steps

            remaining_shift_px = max(1.0, target_axis_shift_px - axis_shift_px)
            next_steps = _step_count_from_measured_shift(
                axis_shift_px,
                total_moved,
                remaining_shift_px,
            )
            if next_steps <= chunk_steps and axis_shift_px < target_axis_shift_px:
                next_steps = min(_SERPENTINE_VIDEO_MAX_ADAPTIVE_STEPS, chunk_steps + 1)
            chunk_steps = min(next_steps, max(1, remaining)) if remaining > 0 else next_steps

        return total_moved, last_frame, last_overlap, last_response, chunk_steps

    def _write_serpentine_video_frame(
        self,
        writer: cv2.VideoWriter,
        frame_size: tuple[int, int],
        window_name: str,
        x: int,
        y: int,
        start_x: int,
        start_y: int,
        rows: int,
        cols: int,
        step_x: int,
        step_y: int,
        progress: float,
        elapsed_s: float,
        eta_s: float,
        paused: bool,
        show_preview: bool = True,
    ) -> bool:
        row_index = min(rows - 1, max(0, int(round(abs(y - start_y) / max(1, abs(step_y))))))
        col_index = min(cols - 1, max(0, int(round(abs(x - start_x) / max(1, abs(step_x))))))
        frame = self._read_latest_frame(discard_frames=1)
        prepared = self._prepare_serpentine_video_frame(frame, frame_size=frame_size)
        output_frame = self._draw_serpentine_video_overlay(
            prepared,
            x=x,
            y=y,
            row_index=row_index,
            col_index=col_index,
            progress=progress,
            elapsed_s=elapsed_s,
            eta_s=eta_s,
            paused=paused,
        )
        writer.write(output_frame)

        if not show_preview:
            return True

        try:
            display_frame = self._resize_for_display_keep_aspect(
                output_frame,
                _PREVIEW_WINDOW_WIDTH,
                720,
            )
            with self._serpentine_video_display_lock:
                self._serpentine_video_display_frame = display_frame.copy()
        except Exception:
            pass
        return True

    def _serpentine_video_worker(
        self,
        path: list[tuple[float, float]],
        rows: int,
        cols: int,
        step_x: int,
        step_y: int,
        speed: float,
        fps: float,
        output_path: Path,
    ) -> None:
        writer: Optional[cv2.VideoWriter] = None
        window_name = "Serpentine Continuous Recording"
        frames_written = 0
        record_stop = threading.Event()
        record_thread: Optional[threading.Thread] = None
        record_error: list[BaseException] = []
        try:
            start_x = int(round(float(path[0][0])))
            start_y = int(round(float(path[0][1])))
            end_x = int(round(float(path[-1][0])))
            end_y = int(round(float(path[-1][1])))
            current_x, current_y = self._get_virtual_coord()
            if (current_x, current_y) != (start_x, start_y):
                self._append_log(
                    f"蛇形連續錄影：先移動到設定起點 ({start_x},{start_y})，"
                    f"目前座標=({current_x},{current_y})。起點定位不計入錄影路徑進度。"
                )
                self._move_serpentine_video_to(start_x, start_y)
            scan_width_steps = float(abs(end_x - start_x))
            scan_height_steps = float(abs(end_y - start_y))
            total_distance = max(1.0, scan_width_steps * max(1, rows) + scan_height_steps)
            estimated_s = 0.0 if speed <= 0 else total_distance / float(speed)
            self._append_log(
                "蛇形連續錄影開始："
                f"start=({start_x},{start_y}), end=({end_x},{end_y}), "
                f"adaptive overlap target={_SERPENTINE_VIDEO_TARGET_OVERLAP:.2f}, speed={speed:.2f}, "
                f"fps={fps:.2f}, 預估距離={total_distance:.1f}, 預估={estimated_s:.1f}s, "
                f"output={output_path.resolve()}"
            )
            self._set_serpentine_video_status(f"蛇形連續錄影：開始，預估 {estimated_s:.1f}s")

            first_frame = self._read_latest_frame(discard_frames=2)
            prepared_first = self._prepare_serpentine_video_frame(first_frame)
            frame_size = (prepared_first.shape[1], prepared_first.shape[0])
            writer = self._open_serpentine_video_writer(output_path, fps, frame_size)

            self._set_serpentine_motor_speed(speed)
            frame_period = 1.0 / float(fps)
            display_every_frames = 1
            started = time.perf_counter()
            last_log_s = -1.0
            stop_notice_logged = False
            startup_extra_done = False
            distance_done = 0.0
            lane_index = 0
            x_scan_direction = 1 if end_x >= start_x else -1
            y_scan_direction = 1 if end_y >= start_y else -1
            current_x_target = end_x
            adaptive_steps_by_axis = {
                0: max(_SERPENTINE_VIDEO_MIN_ADAPTIVE_STEPS, min(_SERPENTINE_VIDEO_MAX_ADAPTIVE_STEPS, int(round(speed * 2.0)))),
                1: max(_SERPENTINE_VIDEO_MIN_ADAPTIVE_STEPS, min(_SERPENTINE_VIDEO_MAX_ADAPTIVE_STEPS, int(round(speed * 2.0)))),
            }

            record_state_lock = threading.Lock()
            record_state = {
                "x": int(start_x),
                "y": int(start_y),
                "progress": 0.0,
                "eta_s": float(estimated_s),
                "paused": False,
            }

            def _update_record_state(
                x: int,
                y: int,
                progress: float,
                eta_s: float,
                paused: bool = False,
            ) -> None:
                with record_state_lock:
                    record_state["x"] = int(x)
                    record_state["y"] = int(y)
                    record_state["progress"] = float(max(0.0, min(1.0, progress)))
                    record_state["eta_s"] = float(max(0.0, eta_s))
                    record_state["paused"] = bool(paused)

            def _record_loop() -> None:
                nonlocal frames_written
                assert writer is not None
                while not record_stop.is_set():
                    loop_started = time.perf_counter()
                    try:
                        with record_state_lock:
                            state_x = int(record_state["x"])
                            state_y = int(record_state["y"])
                            state_progress = float(record_state["progress"])
                            state_eta = float(record_state["eta_s"])
                            state_paused = bool(record_state["paused"])
                        elapsed_s = time.perf_counter() - started
                        show_preview = (frames_written % display_every_frames) == 0
                        self._write_serpentine_video_frame(
                            writer,
                            frame_size,
                            window_name,
                            state_x,
                            state_y,
                            start_x,
                            start_y,
                            rows,
                            cols,
                            step_x,
                            step_y,
                            state_progress,
                            elapsed_s,
                            state_eta,
                            paused=state_paused,
                            show_preview=show_preview,
                        )
                        frames_written += 1
                    except BaseException as exc:
                        record_error.append(exc)
                        self._serpentine_video_stop.set()
                        break
                    sleep_s = frame_period - (time.perf_counter() - loop_started)
                    if sleep_s > 0:
                        time.sleep(sleep_s)

            record_thread = threading.Thread(target=_record_loop, daemon=True)
            record_thread.start()

            reference_frame = self._capture_motion_tracking_frame(discard_frames=2)

            def _update_adaptive_status(overlap: float, response: float) -> None:
                nonlocal last_log_s
                current_x, current_y = self._get_virtual_coord()
                progress = 1.0 if total_distance <= 1e-9 else min(1.0, distance_done / total_distance)
                eta_s = 0.0 if speed <= 0 else max(0.0, (total_distance - distance_done) / float(speed))
                _update_record_state(current_x, current_y, progress, eta_s, paused=False)
                elapsed_s = time.perf_counter() - started
                if elapsed_s - last_log_s >= 1.0:
                    last_log_s = elapsed_s
                    row_index = min(rows - 1, max(0, int(round(abs(current_y - start_y) / max(1, abs(step_y))))))
                    col_index = min(cols - 1, max(0, int(round(abs(current_x - start_x) / max(1, abs(step_x))))))
                    status = (
                        f"蛇形連續錄影：{progress * 100.0:.1f}% "
                        f"座標=({current_x},{current_y}) row={row_index + 1}/{rows} col={col_index + 1}/{cols} "
                        f"overlap={overlap:.2f} response={response:.3f} ETA={eta_s:.1f}s"
                    )
                    self._set_serpentine_video_status(status)
                    self._append_log(status)

            while not self._serpentine_video_stop.is_set():
                if record_error:
                    break

                if self._serpentine_video_restart.is_set():
                    self._serpentine_video_restart.clear()
                    self._move_serpentine_video_to(path[0][0], path[0][1])
                    reference_frame = self._capture_motion_tracking_frame(discard_frames=2)
                    distance_done = 0.0
                    lane_index = 0
                    current_x_target = end_x
                    started = time.perf_counter()

                if self._serpentine_video_pause.is_set():
                    self._set_serpentine_video_status("蛇形連續錄影：暫停")
                    current_x, current_y = self._get_virtual_coord()
                    progress = 1.0 if total_distance <= 1e-9 else min(1.0, distance_done / total_distance)
                    eta_s = 0.0 if speed <= 0 else max(0.0, (total_distance - distance_done) / float(speed))
                    _update_record_state(current_x, current_y, progress, eta_s, paused=True)
                    time.sleep(0.05)
                    continue

                current_x, current_y = self._get_virtual_coord()
                x_remaining = abs(int(current_x_target) - int(current_x))
                if x_remaining > 0:
                    axis_id = 0
                    direction = 1 if current_x_target > current_x else -1
                    if not startup_extra_done:
                        self._move_serpentine_startup_extra_steps(axis_id, direction)
                        startup_extra_done = True
                    moved_steps, reference_frame, overlap, response, next_steps = (
                        self.adaptive_serpentine_movement_with_15_percent_overlap(
                            axis_id=axis_id,
                            direction=direction,
                            max_steps=x_remaining,
                            reference_frame=reference_frame,
                            adaptive_steps=adaptive_steps_by_axis[axis_id],
                        )
                    )
                    distance_done += float(moved_steps)
                    adaptive_steps_by_axis[axis_id] = int(next_steps)
                    _update_adaptive_status(overlap, response)
                    if moved_steps <= 0:
                        break
                    if self._serpentine_video_stop.is_set() and not stop_notice_logged:
                        stop_notice_logged = True
                        self._append_log("停止要求已收到，將在目前 adaptive 移動小段完成後停止。")
                    continue

                y_remaining = abs(int(end_y) - int(current_y))
                if y_remaining <= 0:
                    break

                axis_id = 1
                if not startup_extra_done:
                    self._move_serpentine_startup_extra_steps(axis_id, y_scan_direction)
                    startup_extra_done = True
                moved_steps, reference_frame, overlap, response, next_steps = (
                    self.adaptive_serpentine_movement_with_15_percent_overlap(
                        axis_id=axis_id,
                        direction=y_scan_direction,
                        max_steps=y_remaining,
                        reference_frame=reference_frame,
                        adaptive_steps=adaptive_steps_by_axis[axis_id],
                    )
                )
                distance_done += float(moved_steps)
                adaptive_steps_by_axis[axis_id] = int(next_steps)
                lane_index += 1 if moved_steps > 0 else 0
                current_x_target = start_x if int(current_x_target) == int(end_x) else end_x
                _update_adaptive_status(overlap, response)
                next_x, _next_y = self._get_virtual_coord()
                next_direction_text = "往右" if int(current_x_target) > int(next_x) else "往左"
                self._append_log(
                    f"蛇形連續錄影換列：lane={lane_index + 1}, 下一列方向={next_direction_text}"
                )

                if self._serpentine_video_stop.is_set():
                    break

            if record_error:
                raise RuntimeError(f"錄影寫入失敗：{record_error[0]}") from record_error[0]

            if self._serpentine_video_stop.is_set():
                self._append_log(f"蛇形連續錄影已停止：frames={frames_written}")
            else:
                self._append_log(f"蛇形連續錄影完成：frames={frames_written}, output={output_path.resolve()}")
            self._set_serpentine_video_status(f"蛇形連續錄影：已完成，frames={frames_written}")
        except Exception as exc:
            error_message = str(exc)
            self._append_log(f"蛇形連續錄影失敗: {error_message}")
            self._set_serpentine_video_status(f"蛇形連續錄影：失敗 {error_message}")
            try:
                self.root.after(0, lambda: messagebox.showerror("蛇形連續錄影失敗", error_message))
            except Exception:
                pass
        finally:
            record_stop.set()
            if record_thread is not None and record_thread.is_alive():
                record_thread.join(timeout=2.0)
            with self._serpentine_video_display_lock:
                self._serpentine_video_display_active = False
                self._serpentine_video_display_frame = None
            self._restore_normal_motor_speed_after_serpentine()
            if writer is not None:
                writer.release()
            try:
                if output_path.exists():
                    self._append_log(
                        f"蛇形連續錄影輸出檔案：{output_path.resolve()}，大小={output_path.stat().st_size} bytes"
                    )
            except Exception:
                pass
            self._serpentine_video_running = False
            self._serpentine_video_pause.clear()
            self._serpentine_video_stop.clear()
            self._serpentine_video_restart.clear()

    def _start_full_slide_scan(self, collect_wbc: bool = False) -> None:
        if self._wbc_capture_running:
            messagebox.showwarning("整片掃描", "請先停止白血球固定步數蛇行掃描。")
            return
        if self._backlash_calibration_running:
            messagebox.showwarning("整片掃描", "backlash 校正進行中，請稍後再試。")
            return
        if self._capture_job_running:
            self._append_log("拍攝任務已在執行中。")
            return
        if self._auto_running:
            messagebox.showwarning("整片掃描", "請先停止自動移動，再啟動整片掃描。")
            return
        if self._get_stepper(0) is None or self._get_stepper(1) is None:
            messagebox.showwarning("整片掃描", "整片掃描需要先連線 X-motor 與 Y-motor。")
            return

        try:
            self._ensure_camera_open()
            x_pitch, y_pitch = self._parse_slide_scan_pitches()
            end_x, end_y = self._parse_capture_end_coordinate()
        except Exception as exc:
            messagebox.showerror("整片掃描", str(exc))
            return

        start_x, start_y = self._get_virtual_coord()
        if start_x == end_x and start_y == end_y:
            messagebox.showwarning("整片掃描", "目前座標與終點座標相同，無法進行蛇行拍攝。")
            return

        try:
            coordinates = generate_serpentine_capture_coordinates(
                start_x=start_x,
                start_y=start_y,
                end_x=end_x,
                end_y=end_y,
                step_x=x_pitch,
                step_y=y_pitch,
            )
        except Exception as exc:
            messagebox.showerror("整片掃描", str(exc))
            return

        current_x, current_y = self._get_virtual_coord()
        missing: list[str] = []
        requires_x = (start_x != current_x) or any(x1 != x0 for (x0, _), (x1, _) in zip(coordinates, coordinates[1:]))
        requires_y = (start_y != current_y) or any(y1 != y0 for (_, y0), (_, y1) in zip(coordinates, coordinates[1:]))
        if requires_x and self._get_stepper(0) is None:
            missing.append("X-motor")
        if requires_y and self._get_stepper(1) is None:
            missing.append("Y-motor")
        if missing:
            messagebox.showwarning("整片掃描", f"蛇行拍攝需要連線: {', '.join(missing)}")
            return

        self._capture_job_stop.clear()
        self._capture_job_running = True
        self._capture_job_thread = threading.Thread(
            target=self._capture_and_stitch_worker,
            args=(coordinates, "stitched_serpentine_scan", _SLIDE_SCAN_OVERLAP_RATIO, False, bool(collect_wbc)),
            daemon=True,
        )
        self._capture_job_thread.start()
        mode_text = "掃描收集 WBC" if collect_wbc else "蛇行拍攝"
        self._append_log(
            f"{mode_text}開始："
            f"起點=({start_x},{start_y})，終點=({end_x},{end_y})，"
            f"X 步數={x_pitch}，Y 步數={y_pitch}，模式=先走 X 軸、換列後再走 Y 軸，停點數={len(coordinates)}。"
            "本流程只拍攝，不自動拼接。"
        )

    def _capture_slide_scan_tile(
        self,
        session_dir: Path,
        scan_index: int,
        column_index: int,
        row_index: int,
        x: int,
        y: int,
    ) -> SlideScanTileRecord:
        frame = self._read_latest_frame(discard_frames=4)
        if frame is None:
            raise RuntimeError("讀取相機畫面失敗。")

        styled_frame = self._styled_camera_frame(frame)
        saved_frame = self._prepare_capture_save_frame(styled_frame)
        filename = f"scan_{scan_index + 1:04d}_c{column_index + 1:03d}_r{row_index + 1:03d}_x{x}_y{y}.jpg"
        image_path = session_dir / filename
        if not cv2.imwrite(str(image_path), saved_frame):
            raise RuntimeError(f"無法寫入掃描影像: {image_path}")

        detections = self._detect_objects(saved_frame)
        detection_count = len(detections)
        coverage_ratio = (
            compute_detection_coverage_ratio(saved_frame.shape, detections)
            if compute_detection_coverage_ratio is not None
            else 0.0
        )
        is_sparse = coverage_ratio < _SLIDE_SCAN_TISSUE_THRESHOLD
        self._save_detection_artifacts(image_path, saved_frame, detections=detections, force_features=True)
        self._set_virtual_coord(x, y)
        self._append_log(
            f"掃描 tile {scan_index + 1}: col={column_index + 1} row={row_index + 1} "
            f"coord=({x},{y}) coverage={coverage_ratio:.3f} detections={detection_count} "
            f"{'sparse' if is_sparse else 'tissue'}"
        )
        return SlideScanTileRecord(
            scan_index=int(scan_index),
            column_index=int(column_index),
            row_index=int(row_index),
            x=int(x),
            y=int(y),
            filename=filename,
            image_path=str(image_path.resolve()),
            frame_width=int(saved_frame.shape[1]),
            frame_height=int(saved_frame.shape[0]),
            detection_count=int(detection_count),
            coverage_ratio=float(coverage_ratio),
            is_sparse=bool(is_sparse),
            detections=self._serialize_detections(detections),
        )

    def _probe_slide_position(
        self,
        x: int,
        y: int,
        column_index: int,
        probe_index: int,
    ) -> tuple[float, bool, int]:
        frame = self._read_latest_frame(discard_frames=3)
        if frame is None:
            raise RuntimeError("讀取相機畫面失敗。")
        styled_frame = self._styled_camera_frame(frame)
        probe_frame = self._prepare_capture_save_frame(styled_frame)
        detections = self._detect_objects(probe_frame)
        coverage_ratio = (
            compute_detection_coverage_ratio(probe_frame.shape, detections)
            if compute_detection_coverage_ratio is not None
            else 0.0
        )
        is_sparse = coverage_ratio < _SLIDE_SCAN_TISSUE_THRESHOLD
        self._append_log(
            f"欄位探測 col={column_index + 1} probe={probe_index + 1} "
            f"coord=({x},{y}) coverage={coverage_ratio:.3f} detections={len(detections)} "
            f"{'sparse' if is_sparse else 'tissue'}"
        )
        return float(coverage_ratio), bool(is_sparse), len(detections)

    def _move_scan_axis_to(self, current_x: int, current_y: int, target_x: int, target_y: int, settle_s: float) -> tuple[int, int]:
        dx = int(target_x) - int(current_x)
        dy = int(target_y) - int(current_y)
        if dx != 0:
            self._move_axis_steps(0, dx)
        if dy != 0:
            self._move_axis_steps(1, dy)
        if settle_s > 0 and (dx != 0 or dy != 0):
            time.sleep(settle_s)
        self._set_virtual_coord(target_x, target_y)
        return int(target_x), int(target_y)

    def _seek_slide_column_entry(
        self,
        current_x: int,
        current_y: int,
        column_index: int,
        vertical_dir: int,
        y_pitch: int,
        previous_span: Optional[SlideScanColumnSpan],
        settle_s: float,
    ) -> tuple[Optional[int], int]:
        probe_y = int(current_y)
        probe_limit = slide_scan_search_limit(previous_span)
        for probe_index in range(probe_limit):
            if self._capture_job_stop.is_set():
                return None, probe_y
            self._set_virtual_coord(current_x, probe_y)
            _coverage_ratio, is_sparse, _det_count = self._probe_slide_position(
                x=current_x,
                y=probe_y,
                column_index=column_index,
                probe_index=probe_index,
            )
            if not is_sparse:
                return probe_y, probe_y
            if probe_index + 1 >= probe_limit:
                break
            next_probe_y = probe_y + int(vertical_dir) * int(y_pitch)
            _x, probe_y = self._move_scan_axis_to(current_x, probe_y, current_x, next_probe_y, settle_s)
        return None, probe_y

    def _capture_slide_scan_column(
        self,
        session_dir: Path,
        current_x: int,
        entry_y: int,
        column_index: int,
        vertical_dir: int,
        y_pitch: int,
        scan_index: int,
        settle_s: float,
    ) -> tuple[list[SlideScanTileRecord], SlideScanColumnSpan, int]:
        records: list[SlideScanTileRecord] = []
        tissue_ys: list[int] = []
        current_y = int(entry_y)
        row_index = 0
        trailing_sparse = 0

        while not self._capture_job_stop.is_set():
            if scan_index + len(records) >= _SLIDE_SCAN_MAX_TILES:
                break

            record = self._capture_slide_scan_tile(
                session_dir=session_dir,
                scan_index=scan_index + len(records),
                column_index=column_index,
                row_index=row_index,
                x=current_x,
                y=current_y,
            )
            records.append(record)
            if record.is_sparse:
                if tissue_ys:
                    trailing_sparse += 1
            else:
                tissue_ys.append(current_y)
                trailing_sparse = 0

            if tissue_ys and trailing_sparse >= _SLIDE_SCAN_SPARSE_CONFIRMATION_TILES:
                break

            next_y = current_y + int(vertical_dir) * int(y_pitch)
            _x, current_y = self._move_scan_axis_to(current_x, current_y, current_x, next_y, settle_s)
            row_index += 1

        if not tissue_ys:
            raise RuntimeError(f"第 {column_index + 1} 欄未找到有效 tissue，無法建立整欄掃描範圍。")

        span_top = max(tissue_ys)
        span_bottom = min(tissue_ys)
        span_tiles = max(1, int(round(abs(span_top - span_bottom) / max(1, abs(int(y_pitch))))) + 1)
        return records, SlideScanColumnSpan(top_y=span_top, bottom_y=span_bottom, tile_count=span_tiles), current_y

    def _write_slide_scan_manifest(
        self,
        session_dir: Path,
        records: list[SlideScanTileRecord],
        start_x: int,
        start_y: int,
        x_pitch: int,
        y_pitch: int,
    ) -> tuple[Path, Path, Path]:
        coord_rows = [(record.scan_index + 1, record.x, record.y, record.filename) for record in records]
        coord_map_path = self._write_coordinate_map(session_dir, coord_rows)

        csv_path = session_dir / "scan_manifest.csv"
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                [
                    "scan_index",
                    "column_index",
                    "row_index",
                    "x",
                    "y",
                    "filename",
                    "image_path",
                    "frame_width",
                    "frame_height",
                    "detection_count",
                    "coverage_ratio",
                    "is_sparse",
                ]
            )
            for record in records:
                writer.writerow(
                    [
                        record.scan_index,
                        record.column_index,
                        record.row_index,
                        record.x,
                        record.y,
                        record.filename,
                        record.image_path,
                        record.frame_width,
                        record.frame_height,
                        record.detection_count,
                        f"{record.coverage_ratio:.6f}",
                        int(record.is_sparse),
                    ]
                )

        json_path = session_dir / "scan_manifest.json"
        payload = {
            "scan_type": "full_slide_column_serpentine",
            "start_coordinate": {"x": int(start_x), "y": int(start_y)},
            "scan_pitch": {"x": int(x_pitch), "y": int(y_pitch)},
            "overlap_ratio": float(_SLIDE_SCAN_OVERLAP_RATIO),
            "tissue_threshold": float(_SLIDE_SCAN_TISSUE_THRESHOLD),
            "sparse_confirmation_tiles": int(_SLIDE_SCAN_SPARSE_CONFIRMATION_TILES),
            "empty_column_limit": int(_SLIDE_SCAN_EMPTY_COLUMN_LIMIT),
            "tile_count": len(records),
            "tiles": [
                {
                    "scan_index": record.scan_index,
                    "column_index": record.column_index,
                    "row_index": record.row_index,
                    "x": record.x,
                    "y": record.y,
                    "filename": record.filename,
                    "image_path": record.image_path,
                    "frame_width": record.frame_width,
                    "frame_height": record.frame_height,
                    "detection_count": record.detection_count,
                    "coverage_ratio": record.coverage_ratio,
                    "is_sparse": record.is_sparse,
                    "detections": record.detections,
                }
                for record in records
            ],
        }
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return coord_map_path, csv_path.resolve(), json_path.resolve()

    def _run_slide_scan_worker(
        self,
        session_dir: Path,
        x_pitch: int,
        y_pitch: int,
        resume_preview: bool,
        start_x: int,
        start_y: int,
    ) -> None:
        settle_s = max(0.0, int(self.settle_ms_var.get()) / 1000.0)
        scan_records: list[SlideScanTileRecord] = []
        current_x = int(start_x)
        current_y = int(start_y)
        column_index = 0
        empty_column_run = 0
        scan_index = 0
        previous_span: Optional[SlideScanColumnSpan] = None
        coord_map_path: Optional[Path] = None
        manifest_csv_path: Optional[Path] = None
        manifest_json_path: Optional[Path] = None

        try:
            self._ensure_camera_open()
            self._set_virtual_coord(current_x, current_y)
            self._warmup_connected_axes_for_capture()

            while not self._capture_job_stop.is_set():
                if scan_index >= _SLIDE_SCAN_MAX_TILES:
                    self._append_log(f"整片掃描達到安全上限 {_SLIDE_SCAN_MAX_TILES} 張，停止繼續擴張。")
                    break

                vertical_dir = slide_scan_vertical_direction(column_index)
                direction_label = "上->下" if vertical_dir < 0 else "下->上"
                if previous_span is not None:
                    target_entry_y = slide_scan_column_entry_y(previous_span, vertical_dir, y_pitch)
                    current_x, current_y = self._move_scan_axis_to(
                        current_x,
                        current_y,
                        current_x,
                        target_entry_y,
                        settle_s,
                    )
                self._append_log(
                    f"開始掃描第 {column_index + 1} 欄，方向={direction_label}，探測起點座標=({current_x},{current_y})。"
                )

                entry_y, current_y = self._seek_slide_column_entry(
                    current_x=current_x,
                    current_y=current_y,
                    column_index=column_index,
                    vertical_dir=vertical_dir,
                    y_pitch=y_pitch,
                    previous_span=previous_span,
                    settle_s=settle_s,
                )
                if entry_y is None:
                    empty_column_run += 1
                    self._append_log(
                        f"第 {column_index + 1} 欄未找到 tissue，視為空欄。連續空欄數={empty_column_run}。"
                    )
                else:
                    column_records, column_span, current_y = self._capture_slide_scan_column(
                        session_dir=session_dir,
                        current_x=current_x,
                        entry_y=entry_y,
                        column_index=column_index,
                        vertical_dir=vertical_dir,
                        y_pitch=y_pitch,
                        scan_index=scan_index,
                        settle_s=settle_s,
                    )
                    scan_records.extend(column_records)
                    scan_index += len(column_records)
                    previous_span = column_span
                    empty_column_run = 0
                    self._append_log(
                        f"第 {column_index + 1} 欄完成：tile={len(column_records)}，"
                        f"tissue_top={column_span.top_y}，tissue_bottom={column_span.bottom_y}。"
                    )

                if self._capture_job_stop.is_set() or scan_index >= _SLIDE_SCAN_MAX_TILES:
                    break
                if slide_scan_should_stop(empty_column_run):
                    self._append_log(
                        f"已連續遇到 {empty_column_run} 個空欄，視為掃到玻片左邊界，結束整片掃描。"
                    )
                    break

                current_x, current_y = self._move_scan_axis_to(
                    current_x,
                    current_y,
                    current_x - x_pitch,
                    current_y,
                    settle_s,
                )
                column_index += 1

            if scan_records:
                coord_map_path, manifest_csv_path, manifest_json_path = self._write_slide_scan_manifest(
                    session_dir=session_dir,
                    records=scan_records,
                    start_x=start_x,
                    start_y=start_y,
                    x_pitch=x_pitch,
                    y_pitch=y_pitch,
                )
                self._append_log(f"座標對照已輸出：{coord_map_path}")
                self._append_log(f"scan manifest CSV：{manifest_csv_path}")
                self._append_log(f"scan manifest JSON：{manifest_json_path}")

            if self._capture_job_stop.is_set():
                self._append_log(
                    f"整片掃描已停止，已保留 {len(scan_records)} 張影像於：{session_dir.resolve()}"
                )
                return

            if len(scan_records) < 2:
                self._append_log(f"整片掃描完成，但影像不足 2 張，略過拼接：{session_dir.resolve()}")
                return

            self._append_log(f"整片掃描完成，開始 {float(_SLIDE_SCAN_OVERLAP_RATIO):.0%} overlap 拼接...")
            stitch_result = self._run_stitch_session(
                session_dir=session_dir,
                capture_count=len(scan_records),
                output_prefix="stitched_slide_scan",
                selected_paths=[record.image_path for record in scan_records],
                overlap_ratio=_SLIDE_SCAN_OVERLAP_RATIO,
                save_result_detection=False,
            )
            if stitch_result.stitched_image_path is None:
                raise RuntimeError("整片掃描拼接未產生輸出影像。")

            stitched_path = Path(stitch_result.stitched_image_path).resolve()
            manifest_hint = manifest_json_path or manifest_csv_path or coord_map_path or session_dir.resolve()
            self._append_log(f"整片掃描拼接完成：{stitched_path}")
            self.root.after(
                0,
                lambda: messagebox.showinfo(
                    "整片玻片掃描完成",
                    f"拼接主圖:\n{stitched_path}\n\nscan manifest:\n{manifest_hint}",
                ),
            )
        except Exception as exc:
            self._append_log(f"整片掃描失敗: {exc}")
            error_message = str(exc)
            self.root.after(0, lambda message=error_message: messagebox.showerror("整片掃描失敗", message))
        finally:
            self._capture_job_running = False
            if resume_preview:
                self.root.after(0, self._start_preview)

    def _stitch_manual_capture_session(self) -> None:
        try:
            session_dir = self._ensure_manual_capture_session()
            image_count = sum(
                1
                for path in session_dir.iterdir()
                if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
            )
            if image_count < 2:
                raise RuntimeError("手動拍照資料夾至少需要 2 張照片才能拼接。")
            self._append_log(f"開始拼接手動拍照資料夾：{session_dir.resolve()}")
            stitched_path = self._stitch_session_images(
                session_dir,
                image_count,
                output_prefix="stitched_manual",
            )
            self._append_log(f"手動拍照拼接完成：{stitched_path}")
            messagebox.showinfo("手動拼接完成", f"已輸出至:\n{stitched_path}")
        except Exception as exc:
            self._append_log(f"手動拍照拼接失敗: {exc}")
            messagebox.showerror("手動拍照拼接失敗", str(exc))

    def _stitch_latest_capture_session(self) -> None:
        try:
            session_dir = self._latest_capture_session
            if session_dir is None or not session_dir.exists():
                selected = filedialog.askdirectory(
                    title="選擇要拼接的蛇行拍攝資料夾",
                    initialdir=str(self._resolve_capture_output_dir()),
                )
                if not selected:
                    return
                session_dir = Path(selected)

            coord_map_path = session_dir / "virtual_coordinates.csv"
            if not coord_map_path.exists():
                raise RuntimeError(f"找不到 virtual_coordinates.csv，無法依蛇行座標 SOP 拼接：{session_dir}")

            ordered_paths, _order_source = self._load_session_capture_order(session_dir)
            image_count = len(ordered_paths)
            if image_count < 2:
                raise RuntimeError("蛇行拍攝資料夾至少需要 2 張原圖才能拼接。")

            self._latest_capture_session = session_dir
            self._append_log(f"開始拼接最近蛇行拍攝資料夾：{session_dir.resolve()}")
            stitched_path = self._stitch_session_images(
                session_dir,
                image_count,
                output_prefix="stitched_serpentine_scan",
                overlap_ratio=_SLIDE_SCAN_OVERLAP_RATIO,
            )
            self._append_log(f"蛇行拼接完成：{stitched_path}")
            messagebox.showinfo("蛇行拼接完成", f"已輸出至:\n{stitched_path}")
        except Exception as exc:
            self._append_log(f"蛇行拼接失敗: {exc}")
            messagebox.showerror("蛇行拼接失敗", str(exc))

    def _parse_capture_count(self) -> int:
        try:
            count = int(self.capture_count_var.get().strip())
        except Exception as exc:
            raise ValueError("拍攝張數必須是整數。") from exc
        if count <= 0 or count > 1500:
            raise ValueError("拍攝張數請設定在 1 到 1500 之間。")
        return count

    def _start_capture_and_stitch(self) -> None:
        current_x, current_y = self._get_virtual_coord()
        try:
            capture_count = self._parse_capture_count()
            end_x = current_x + int(self.steps_var.get()) * max(0, capture_count - 1)
            end_y = current_y
        except Exception as exc:
            messagebox.showerror("拍攝任務設定", str(exc))
            return
        self._start_capture_and_stitch_over_range(
            current_x,
            current_y,
            end_x,
            end_y,
            "目前座標",
        )

    def _start_capture_and_stitch_from_inputs(self) -> None:
        try:
            start_x, start_y = self._parse_capture_start_coordinate()
        except Exception as exc:
            messagebox.showerror("起始座標設定", str(exc))
            return
        try:
            capture_count = self._parse_capture_count()
            end_x = start_x + int(self.steps_var.get()) * max(0, capture_count - 1)
            end_y = start_y
        except Exception as exc:
            messagebox.showerror("拍攝任務設定", str(exc))
            return
        self._start_capture_and_stitch_over_range(
            start_x,
            start_y,
            end_x,
            end_y,
            "自訂起始座標",
        )

    def _start_capture_between_inputs(self) -> None:
        try:
            start_x, start_y = self._parse_capture_start_coordinate()
            end_x, end_y = self._parse_capture_end_coordinate()
        except Exception as exc:
            messagebox.showerror("起終點設定", str(exc))
            return
        self._start_capture_and_stitch_by_steps(
            start_x,
            start_y,
            end_x,
            end_y,
            "起終點座標",
        )

    def _start_capture_and_stitch_over_range(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        source_label: str,
    ) -> None:
        if self._wbc_capture_running:
            messagebox.showwarning("拍攝任務", "請先停止白血球固定步數蛇行掃描。")
            return
        if self._capture_job_running:
            self._append_log("拍攝任務已在執行中。")
            return
        try:
            self._ensure_camera_open()
            capture_count = self._parse_capture_count()
            coordinates = self._generate_capture_coordinates(capture_count, start_x, start_y, end_x, end_y)
        except Exception as exc:
            messagebox.showerror("拍攝任務設定", str(exc))
            return

        current_x, current_y = self._get_virtual_coord()
        missing: list[str] = []
        requires_x = (start_x != current_x) or (end_x != start_x)
        requires_y = (start_y != current_y) or (end_y != start_y)
        if requires_x and self._get_stepper(0) is None:
            missing.append("X-motor")
        if requires_y and self._get_stepper(1) is None:
            missing.append("Y-motor")
        if missing:
            messagebox.showwarning("拍攝任務", f"起終點座標需要連線: {', '.join(missing)}")
            return

        self._capture_job_stop.clear()
        self._capture_job_running = True
        self._capture_job_thread = threading.Thread(
            target=self._capture_and_stitch_worker,
            args=(coordinates,),
            daemon=True,
        )
        self._capture_job_thread.start()
        self._append_log(
            f"拍攝任務開始：目標 {len(coordinates)} 張，{source_label}=({start_x},{start_y}) -> ({end_x},{end_y})。"
        )

    def _start_capture_and_stitch_by_steps(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        source_label: str,
    ) -> None:
        if self._wbc_capture_running:
            messagebox.showwarning("拍攝任務", "請先停止白血球固定步數蛇行掃描。")
            return
        if self._capture_job_running:
            self._append_log("拍攝任務已在執行中。")
            return
        try:
            self._ensure_camera_open()
            coordinates = self._generate_capture_coordinates_by_step(start_x, start_y, end_x, end_y)
        except Exception as exc:
            messagebox.showerror("拍攝任務設定", str(exc))
            return

        current_x, current_y = self._get_virtual_coord()
        missing: list[str] = []
        requires_x = (start_x != current_x) or any(x1 != x0 for (x0, _), (x1, _) in zip(coordinates, coordinates[1:]))
        requires_y = (start_y != current_y) or any(y1 != y0 for (_, y0), (_, y1) in zip(coordinates, coordinates[1:]))
        if requires_x and self._get_stepper(0) is None:
            missing.append("X-motor")
        if requires_y and self._get_stepper(1) is None:
            missing.append("Y-motor")
        if missing:
            messagebox.showwarning("拍攝任務", f"起終點座標需要連線: {', '.join(missing)}")
            return

        self._capture_job_stop.clear()
        self._capture_job_running = True
        self._capture_job_thread = threading.Thread(
            target=self._capture_and_stitch_worker,
            args=(coordinates,),
            daemon=True,
        )
        self._capture_job_thread.start()
        self._append_log(
            f"拍攝任務開始：依步數移動 {len(coordinates)} 個停點，{source_label}=({start_x},{start_y}) -> ({end_x},{end_y})。"
        )

    def _stop_capture_and_stitch(self) -> None:
        if not self._capture_job_running:
            self._append_log("目前沒有進行中的拍攝任務。")
            return
        self._capture_job_stop.set()
        self._append_log("已送出終止拍攝要求，將在目前步驟完成後停止。")

    def _set_wbc_capture_status(self, text: str) -> None:
        if threading.current_thread() is not threading.main_thread():
            try:
                self.root.after(0, lambda message=text: self._set_wbc_capture_status(message))
            except Exception:
                pass
            return
        self.wbc_capture_status_var.set(text)

    def _set_wbc_capture_count(self, count: int) -> None:
        self._wbc_capture_count = max(0, int(count))
        text = f"已拍攝白血球數量：{self._wbc_capture_count}"
        if threading.current_thread() is not threading.main_thread():
            try:
                self.root.after(0, lambda message=text: self.wbc_capture_count_var.set(message))
            except Exception:
                pass
            return
        self.wbc_capture_count_var.set(text)

    def _parse_wbc_capture_coordinates(self) -> list[tuple[int, int]]:
        if generate_vertical_serpentine_path is None or generate_vertical_serpentine_path_from_bounds is None:
            raise RuntimeError("White_Blood_Cell 蛇行掃描模組無法載入。")
        start_x = int(self.capture_start_x_var.get())
        start_y = int(self.capture_start_y_var.get())
        end_x = int(self.capture_end_x_var.get())
        end_y = int(self.capture_end_y_var.get())
        step_x = int(WBC_CAPTURE_DEFAULT_CONFIG.get("step_x", 8))
        step_y = int(WBC_CAPTURE_DEFAULT_CONFIG.get("step_y", 8))
        if (start_x, start_y) == (end_x, end_y):
            path = generate_vertical_serpentine_path(
                start_x=start_x,
                start_y=start_y,
                columns=int(WBC_CAPTURE_DEFAULT_CONFIG.get("columns", 5)),
                rows=int(WBC_CAPTURE_DEFAULT_CONFIG.get("rows", 5)),
                step_x=step_x,
                step_y=step_y,
            )
        else:
            path = generate_vertical_serpentine_path_from_bounds(
                start_x,
                start_y,
                end_x,
                end_y,
                step_x=step_x,
                step_y=step_y,
            )
        nodes = [(int(point["x"]), int(point["y"])) for point in path]
        return nodes

    def _start_wbc_serpentine_capture(self) -> None:
        if self._wbc_capture_running:
            self._append_log("White_Blood_Cell 蛇行捕捉已在執行中。")
            return
        if self._capture_job_running or self._serpentine_video_running or self._auto_running:
            messagebox.showwarning("白血球蛇行捕捉", "請先停止其他拍攝、錄影或自動移動任務。")
            return
        if self._backlash_calibration_running or self._image_feedback_running or self._motor_warmup_running:
            messagebox.showwarning("白血球蛇行捕捉", "馬達校正或預熱進行中，請稍後再開始。")
            return

        if self._get_stepper(0) is None or self._get_stepper(1) is None:
            messagebox.showwarning("白血球蛇行捕捉", "請先連線 X-motor 與 Y-motor。")
            return
        try:
            coordinates = self._parse_wbc_capture_coordinates()
            if not coordinates:
                raise RuntimeError("無法產生垂直蛇行掃描座標。")
            experiment_name = self._safe_wbc_experiment_name(self.wbc_capture_experiment_var.get())
            if self._preview_running:
                self._append_log("啟動白血球捕捉前先停止一般 Live Preview，避免相機資源衝突。")
                self._stop_preview()
            self._ensure_camera_open()
            self._get_wbc_capture_detector()
        except Exception as exc:
            self._append_log(f"白血球蛇行捕捉啟動失敗：{exc}")
            messagebox.showerror("白血球蛇行捕捉", str(exc))
            return

        self._wbc_capture_stop.clear()
        self._wbc_capture_manual_capture.clear()
        self._wbc_capture_resume.clear()
        self._wbc_capture_waiting_manual_capture = False
        self._wbc_capture_waiting_resume = False
        self._set_wbc_capture_count(0)
        self._wbc_capture_running = True
        self._wbc_capture_thread = threading.Thread(
            target=self._wbc_serpentine_capture_worker,
            args=(coordinates, experiment_name),
            daemon=True,
        )
        self._wbc_capture_thread.start()
        self._set_wbc_capture_status("白血球蛇行捕捉：執行中")
        self._append_log(
            f"White_Blood_Cell 垂直蛇行捕捉開始：固定步數節點={len(coordinates)}，"
            f"步距=({WBC_CAPTURE_DEFAULT_CONFIG.get('step_x', 8)},"
            f"{WBC_CAPTURE_DEFAULT_CONFIG.get('step_y', 8)}) steps，"
            f"每步停留={WBC_CAPTURE_DEFAULT_CONFIG.get('detection_settle_seconds', 0.5)} 秒後辨識。"
        )

    def _stop_wbc_serpentine_capture(self) -> None:
        if not self._wbc_capture_running:
            self._append_log("White_Blood_Cell 蛇行捕捉尚未開始。")
            return
        self._wbc_capture_stop.set()
        self._wbc_capture_manual_capture.set()
        self._wbc_capture_resume.set()
        self._set_wbc_capture_status("白血球蛇行捕捉：停止中")
        self._append_log("已送出 White_Blood_Cell 蛇行捕捉停止要求。")

    def _manual_capture_wbc_serpentine_capture(self) -> None:
        if not self._wbc_capture_running:
            self._append_log("White_Blood_Cell 蛇行捕捉尚未開始。")
            return
        if not self._wbc_capture_waiting_manual_capture:
            self._append_log("目前沒有等待手動拍攝的 White_Blood_Cell。")
            return
        self._wbc_capture_manual_capture.set()
        self._append_log("已收到手動拍攝要求，將使用目前即時畫面重新辨識並裁切白血球。")

    def _resume_wbc_serpentine_capture(self) -> None:
        if not self._wbc_capture_running:
            self._append_log("White_Blood_Cell 蛇行捕捉尚未開始。")
            return
        if not self._wbc_capture_waiting_resume:
            self._append_log("目前沒有等待繼續的 White_Blood_Cell 捕捉任務。")
            return
        self._wbc_capture_resume.set()
        self._append_log("已收到繼續掃描要求，將前往下一個固定步數蛇行節點。")

    @staticmethod
    def _safe_wbc_experiment_name(value: str) -> str:
        cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in str(value).strip())
        return cleaned.strip("_") or "sample_01"

    def _get_wbc_capture_detector(self) -> ObjectDetector:
        if ObjectDetector is None:
            raise RuntimeError("物件辨識模組不可用。")
        model_path = self._resolve_detect_model_for_gui()
        stop_confidence = float(WBC_CAPTURE_DEFAULT_CONFIG.get("scan_stop_min_confidence", 0.05))
        save_confidence = float(WBC_CAPTURE_DEFAULT_CONFIG.get("min_confidence", 0.50))
        key = (model_path, stop_confidence, save_confidence)
        with self._detector_lock:
            if self._wbc_capture_detector is not None and self._wbc_capture_detector_key == key:
                return self._wbc_capture_detector
            detector = ObjectDetector(
                model_path=model_path,
                conf_threshold=stop_confidence,
                wbc_subtype_model_path=None,
            )
            detector._ensure_model()
            self._wbc_capture_detector = detector
            self._wbc_capture_detector_key = key
        self._append_log(
            f"White_Blood_Cell 捕捉模型已載入：model={model_path} "
            f"停止門檻={stop_confidence:.2f}，保存門檻={save_confidence:.2f}，不執行五分類。"
        )
        return detector

    def _detect_wbc_capture_cells(
        self,
        frame: np.ndarray,
    ) -> list:
        if WBCDetection is None:
            raise RuntimeError("White_Blood_Cell detection helper 無法載入。")
        detections = self._get_wbc_capture_detector().detect(
            frame,
            conf_threshold=float(WBC_CAPTURE_DEFAULT_CONFIG.get("scan_stop_min_confidence", 0.05)),
        )
        return [
            WBCDetection(
                cell_class=WHITE_BLOOD_CELL_CLASS,
                confidence=float(getattr(det, "conf", 0.0)),
                bbox=(
                    int(getattr(det, "x1", 0)),
                    int(getattr(det, "y1", 0)),
                    int(getattr(det, "x2", 0)),
                    int(getattr(det, "y2", 0)),
                ),
            )
            for det in detections
            if is_white_blood_cell_detection(det)
        ]

    @staticmethod
    def _is_wbc_capture_stop_candidate(detection: Any, frame_shape: tuple[int, ...]) -> bool:
        if getattr(detection, "cell_class", "") != WHITE_BLOOD_CELL_CLASS:
            return False
        height, width = int(frame_shape[0]), int(frame_shape[1])
        x1 = max(0, min(width, int(getattr(detection, "x1", 0))))
        y1 = max(0, min(height, int(getattr(detection, "y1", 0))))
        x2 = max(0, min(width, int(getattr(detection, "x2", 0))))
        y2 = max(0, min(height, int(getattr(detection, "y2", 0))))
        if x2 <= x1 or y2 <= y1:
            return False
        area = float((x2 - x1) * (y2 - y1))
        return area >= float(WBC_CAPTURE_DEFAULT_CONFIG.get("min_bbox_area", 900))

    def _move_wbc_capture_to_coordinate(
        self,
        x: int,
        y: int,
        *,
        startup_extra_done: Optional[set[int]] = None,
    ) -> None:
        current_x, current_y = self._get_virtual_coord()
        dx = int(x) - current_x
        dy = int(y) - current_y
        if dx != 0 and dy != 0:
            raise RuntimeError("White_Blood_Cell 掃描只支援水平或垂直分段移動。")
        if dx != 0:
            stepper = self._get_stepper(0)
            if stepper is None:
                raise RuntimeError("White_Blood_Cell 掃描需要連線 X-motor。")
            if startup_extra_done is not None and 0 not in startup_extra_done:
                self._move_serpentine_startup_extra_steps(0, 1 if dx >= 0 else -1)
                startup_extra_done.add(0)
            self._move_axis_steps(0, dx, apply_backlash=True)
            self._wbc_capture_last_move_axis = 0
        if dy != 0:
            stepper = self._get_stepper(1)
            if stepper is None:
                raise RuntimeError("White_Blood_Cell 掃描需要連線 Y-motor。")
            if startup_extra_done is not None and 1 not in startup_extra_done:
                self._move_serpentine_startup_extra_steps(1, 1 if dy >= 0 else -1)
                startup_extra_done.add(1)
            commanded_dy = int(dy)
            if self._wbc_capture_last_move_axis == 0:
                compensation = max(0, int(WBC_CAPTURE_DEFAULT_CONFIG.get("y_after_x_axis_switch_compensation_steps", 0)))
                if compensation:
                    commanded_dy += (1 if dy > 0 else -1) * compensation
                    self._append_log(
                        f"White_Blood_Cell X→Y 換軸補償：Y 原始={dy}，補償={compensation}，送出={commanded_dy}"
                    )
            if self._wbc_capture_resume_y_forward_compensation_pending and dy > 0:
                resume_compensation = max(
                    0,
                    int(WBC_CAPTURE_DEFAULT_CONFIG.get("y_forward_after_wbc_resume_compensation_steps", 0)),
                )
                if resume_compensation:
                    commanded_dy += resume_compensation
                    self._append_log(
                        f"White_Blood_Cell 暫停後續掃 Y 前進補償：Y 原始={dy}，"
                        f"補償={resume_compensation}，送出={commanded_dy}"
                    )
                self._wbc_capture_resume_y_forward_compensation_pending = False
            self._move_axis_steps(1, commanded_dy, apply_backlash=True)
            self._wbc_capture_last_move_axis = 1
        self._set_virtual_coord(int(x), int(y))

    def _stop_wbc_capture_motors(self, *, immediate: bool = False) -> None:
        for axis_id in (0, 1):
            stepper = self._get_stepper(axis_id)
            if stepper is None:
                continue
            try:
                if immediate and hasattr(stepper, "request_stop"):
                    stepper.request_stop()
                else:
                    stepper.stop()
            except Exception:
                pass

    def _show_wbc_capture_preview(
        self,
        frame: np.ndarray,
        detections: list,
        current_x: int,
        current_y: int,
        *,
        message: str = "",
    ) -> None:
        display = frame.copy()
        for detection in detections:
            complete = bool(
                is_complete_white_blood_cell_detection is not None
                and is_complete_white_blood_cell_detection(detection, frame.shape)
            )
            color = (0, 255, 0) if complete else (0, 180, 255)
            cv2.rectangle(display, (detection.x1, detection.y1), (detection.x2, detection.y2), color, 2)
            put_text(
                display,
                f"{WHITE_BLOOD_CELL_CLASS} {float(detection.confidence):.2f}",
                (detection.x1, max(20, detection.y1 - 8)),
                0.55,
                color,
                2,
            )
        put_text(display, f"x={current_x} y={current_y}", (16, 30), 0.7, (255, 255, 255), 2)
        put_text(
            display,
            f"Captured White Blood Cells: {self._wbc_capture_count}",
            (16, 60),
            0.7,
            (255, 255, 255),
            2,
        )
        if message:
            put_text(display, message, (18, display.shape[0] - 28), 0.7, (0, 255, 255), 2)
        display = self._resize_for_display_keep_aspect(display, max_width=960, max_height=720)
        cv2.imshow(self._wbc_capture_display_window, display)
        cv2.waitKey(1)

    @staticmethod
    def _write_wbc_capture_metadata(csv_path: Path, record: dict[str, Any]) -> None:
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        write_header = not csv_path.exists()
        with csv_path.open("a", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(WBC_CAPTURE_METADATA_FIELDS))
            if write_header:
                writer.writeheader()
            writer.writerow({field: record.get(field, "") for field in WBC_CAPTURE_METADATA_FIELDS})

    def _wait_wbc_step_settle(self, current_x: int, current_y: int) -> bool:
        settle_seconds = max(0.0, float(WBC_CAPTURE_DEFAULT_CONFIG.get("detection_settle_seconds", 0.5)))
        deadline = time.monotonic() + settle_seconds
        while time.monotonic() < deadline:
            if self._wbc_capture_stop.is_set():
                return False
            frame = self._read_latest_frame(discard_frames=0)
            self._show_wbc_capture_preview(
                frame,
                [],
                current_x,
                current_y,
                message="Stopped. Waiting for focus before detection...",
            )
            time.sleep(0.05)
        return not self._wbc_capture_stop.is_set()

    def _detect_wbc_after_fixed_step(
        self,
        current_x: int,
        current_y: int,
    ) -> tuple[np.ndarray, list, list]:
        attempts = max(1, int(WBC_CAPTURE_DEFAULT_CONFIG.get("detection_frame_attempts", 3)))
        interval_s = max(0.0, float(WBC_CAPTURE_DEFAULT_CONFIG.get("detection_frame_interval_seconds", 0.15)))
        last_frame: Optional[np.ndarray] = None
        last_detections: list = []
        last_stop_detections: list = []
        for attempt_index in range(attempts):
            if self._wbc_capture_stop.is_set():
                break
            frame = self._read_latest_frame(discard_frames=1)
            detections = self._detect_wbc_capture_cells(frame)
            stop_detections = [
                det
                for det in detections
                if self._is_wbc_capture_stop_candidate(det, frame.shape)
            ]
            self._show_wbc_capture_preview(frame, detections, current_x, current_y)
            last_frame = frame
            last_detections = detections
            last_stop_detections = stop_detections
            if stop_detections:
                break
            if attempt_index < attempts - 1 and interval_s > 0:
                time.sleep(interval_s)
        if last_frame is None:
            last_frame = self._read_latest_frame(discard_frames=1)
        return last_frame, last_detections, last_stop_detections

    def _move_wbc_capture_centering_delta(self, dx_steps: int, dy_steps: int) -> tuple[int, int]:
        dx = int(dx_steps)
        dy = int(dy_steps)
        if dx:
            self._move_axis_steps(0, dx, apply_backlash=True)
            self._shift_virtual_coord(dx, 0)
        if dy:
            self._move_axis_steps(1, dy, apply_backlash=True)
            self._shift_virtual_coord(0, dy)
        return self._get_virtual_coord()

    def _center_wbc_capture_for_high_magnification(
        self,
        current_x: int,
        current_y: int,
        frame: np.ndarray,
        detections: list,
    ) -> tuple[int, int, np.ndarray, list, bool]:
        if not bool(WBC_CAPTURE_DEFAULT_CONFIG.get("center_after_detection", True)):
            return current_x, current_y, frame, detections, False
        if (
            calculate_wbc_centering_steps is None
            or is_wbc_centered is None
            or select_wbc_centering_target is None
            or wbc_center_offset_px is None
            or wbc_detection_center is None
        ):
            self._append_log("白血球置中 helper 無法載入，略過自動置中。")
            return current_x, current_y, frame, detections, False

        max_iterations = max(0, int(WBC_CAPTURE_DEFAULT_CONFIG.get("center_max_iterations", 3)))
        if max_iterations <= 0:
            return current_x, current_y, frame, detections, False

        latest_frame = frame
        latest_detections = list(detections)
        centered = False
        x_pos = int(current_x)
        y_pos = int(current_y)
        for iteration in range(max_iterations):
            if self._wbc_capture_stop.is_set():
                break
            target = select_wbc_centering_target(latest_detections, latest_frame.shape)
            if target is None:
                self._append_log("白血球自動置中：沒有穩定且信心度足夠的候選框，改由手動調整。")
                break
            if is_wbc_centered(target, latest_frame.shape):
                centered = True
                break

            center_x, center_y = wbc_detection_center(target)
            offset_x, offset_y = wbc_center_offset_px(target, latest_frame.shape)
            dx_steps, dy_steps = calculate_wbc_centering_steps(target, latest_frame.shape)
            if dx_steps == 0 and dy_steps == 0:
                self._append_log("白血球自動置中：校正後位移小於 1 step，改由手動微調。")
                break

            self._set_wbc_capture_status(
                f"白血球蛇行捕捉：自動置中 {iteration + 1}/{max_iterations} "
                f"dx={dx_steps}, dy={dy_steps}"
            )
            self._append_log(
                f"白血球自動置中 {iteration + 1}/{max_iterations}："
                f"bbox中心=({center_x:.1f},{center_y:.1f})，"
                f"畫面中心=({latest_frame.shape[1] / 2.0:.1f},{latest_frame.shape[0] / 2.0:.1f})，"
                f"偏移=({offset_x:.1f},{offset_y:.1f})，"
                f"move=({dx_steps},{dy_steps})"
            )
            x_pos, y_pos = self._move_wbc_capture_centering_delta(dx_steps, dy_steps)

            settle_s = max(0.0, float(WBC_CAPTURE_DEFAULT_CONFIG.get("center_settle_seconds", 0.45)))
            deadline = time.monotonic() + settle_s
            while time.monotonic() < deadline:
                if self._wbc_capture_stop.is_set():
                    break
                preview = self._read_latest_frame(discard_frames=0)
                self._show_wbc_capture_preview(
                    preview,
                    [],
                    x_pos,
                    y_pos,
                    message="Centering WBC for 1000x...",
                )
                time.sleep(0.05)
            if self._wbc_capture_stop.is_set():
                break

            attempts = max(1, int(WBC_CAPTURE_DEFAULT_CONFIG.get("center_detection_frame_attempts", 3)))
            interval_s = max(0.0, float(WBC_CAPTURE_DEFAULT_CONFIG.get("center_detection_frame_interval_seconds", 0.12)))
            for attempt_index in range(attempts):
                latest_frame = self._read_latest_frame(discard_frames=1)
                latest_detections = self._detect_wbc_capture_cells(latest_frame)
                self._show_wbc_capture_preview(
                    latest_frame,
                    latest_detections,
                    x_pos,
                    y_pos,
                    message="Centering WBC for 1000x...",
                )
                if select_wbc_centering_target(latest_detections, latest_frame.shape) is not None:
                    break
                if attempt_index < attempts - 1 and interval_s > 0:
                    time.sleep(interval_s)

        target = select_wbc_centering_target(latest_detections, latest_frame.shape)
        if target is not None and is_wbc_centered(target, latest_frame.shape):
            centered = True
        if centered:
            self._append_log(f"白血球已置中，座標=({x_pos},{y_pos})。請切換 1000x 後調焦拍攝。")
        else:
            self._append_log(f"白血球自動置中未完全收斂，座標=({x_pos},{y_pos})。平台已停住，可手動微調。")
        return x_pos, y_pos, latest_frame, latest_detections, centered

    def _wait_for_wbc_manual_capture(
        self,
        frame: np.ndarray,
        detections: list,
        current_x: int,
        current_y: int,
    ) -> bool:
        self._wbc_capture_manual_capture.clear()
        self._wbc_capture_waiting_manual_capture = True
        centering_enabled = bool(WBC_CAPTURE_DEFAULT_CONFIG.get("center_after_detection", True))
        if centering_enabled:
            self._set_wbc_capture_status("白血球蛇行捕捉：平台已暫停。請切換 1000x、調焦後按「手動拍攝白血球」")
            self._append_log("白血球已置中或平台已暫停。請切換 1000x、調焦後按「手動拍攝白血球」。")
            wait_message = 'Switch to 1000x, focus, then press "Manual Capture WBC".'
        else:
            self._set_wbc_capture_status("白血球蛇行捕捉：偵測到白血球，平台已暫停。請調焦後按「手動拍攝白血球」")
            self._append_log("偵測到白血球。平台已暫停，等待調焦與手動拍攝。")
            wait_message = 'WBC detected. Focus, then press "Manual Capture WBC".'
        try:
            while not self._wbc_capture_stop.is_set():
                if self._wbc_capture_manual_capture.wait(timeout=0.05):
                    return not self._wbc_capture_stop.is_set()
                frame = self._read_latest_frame(discard_frames=0)
                detections = self._detect_wbc_capture_cells(frame)
                self._show_wbc_capture_preview(
                    frame,
                    detections,
                    current_x,
                    current_y,
                    message=wait_message,
                )
        finally:
            self._wbc_capture_waiting_manual_capture = False
            self._wbc_capture_manual_capture.clear()
        return False

    def _wait_for_wbc_user_resume(
        self,
        frame: np.ndarray,
        detections: list,
        current_x: int,
        current_y: int,
    ) -> bool:
        self._wbc_capture_resume.clear()
        self._wbc_capture_waiting_resume = True
        self._set_wbc_capture_status("白血球蛇行捕捉：拍攝完成。請按「繼續掃描」")
        self._append_log("白血球拍攝完成。平台保持暫停等待按下「繼續掃描」。")
        try:
            while not self._wbc_capture_stop.is_set():
                if self._wbc_capture_resume.wait(timeout=0.05):
                    return not self._wbc_capture_stop.is_set()
                frame = self._read_latest_frame(discard_frames=0)
                detections = self._detect_wbc_capture_cells(frame)
                self._show_wbc_capture_preview(
                    frame,
                    detections,
                    current_x,
                    current_y,
                    message='Press "Continue Scan" to resume.',
                )
        finally:
            self._wbc_capture_waiting_resume = False
            self._wbc_capture_resume.clear()
        return False

    def _capture_white_blood_cells_at_coordinate(
        self,
        *,
        current_x: int,
        current_y: int,
        experiment_name: str,
        date_time: str,
        crop_dir: Path,
        original_dir: Path,
        metadata_csv: Path,
    ) -> tuple[bool, np.ndarray, list]:
        self._set_wbc_capture_status("白血球蛇行捕捉：執行手動拍攝")
        high_res = self._read_latest_frame(discard_frames=2)
        original_path = original_dir / f"x{current_x}_y{current_y}_original.png"
        if not self._write_capture_image(original_path, high_res):
            raise RuntimeError(f"無法寫入原始照片：{original_path}")

        captured_detections = self._detect_wbc_capture_cells(high_res)
        all_bboxes = [det.bbox for det in captured_detections]
        saved_at_coordinate = 0
        if not captured_detections:
            self._write_wbc_capture_metadata(
                metadata_csv,
                {
                    "experiment_name": experiment_name,
                    "date_time": date_time,
                    "current_x": current_x,
                    "current_y": current_y,
                    "cell_index_at_coordinate": 0,
                    "cell_class": WHITE_BLOOD_CELL_CLASS,
                    "original_image_path": str(original_path.resolve()),
                    "captured_wbc_count": self._wbc_capture_count,
                    "status": "skipped_not_complete",
                },
            )

        for detection_index, detection in enumerate(captured_detections, start=1):
            status = (
                white_blood_cell_detection_status(detection, high_res.shape)
                if white_blood_cell_detection_status is not None
                else "skipped_not_complete"
            )
            crop_path: Optional[Path] = None
            if status == "saved" and crop_white_blood_cell_by_bbox is not None:
                crop = crop_white_blood_cell_by_bbox(
                    high_res,
                    detection.bbox,
                    all_bboxes=all_bboxes,
                    padding=int(WBC_CAPTURE_DEFAULT_CONFIG.get("crop_padding", 10)),
                )
                if crop is None:
                    status = "skipped_ambiguous_crop"
                else:
                    saved_at_coordinate += 1
                    crop_path = (
                        crop_dir
                        / f"x{current_x}_y{current_y}_{saved_at_coordinate:03d}_{WHITE_BLOOD_CELL_CLASS}.png"
                    )
                    if not self._write_capture_image(crop_path, crop):
                        raise RuntimeError(f"無法寫入白血球裁切圖：{crop_path}")
                    self._set_wbc_capture_count(self._wbc_capture_count + 1)
                    self._append_log(
                        f"Captured White Blood Cells: {self._wbc_capture_count}，"
                        f"已儲存：{crop_path.name}"
                    )

            self._write_wbc_capture_metadata(
                metadata_csv,
                {
                    "experiment_name": experiment_name,
                    "date_time": date_time,
                    "current_x": current_x,
                    "current_y": current_y,
                    "cell_index_at_coordinate": detection_index,
                    "cell_class": WHITE_BLOOD_CELL_CLASS,
                    "confidence": f"{float(detection.confidence):.6f}",
                    "bbox_x1": detection.x1,
                    "bbox_y1": detection.y1,
                    "bbox_x2": detection.x2,
                    "bbox_y2": detection.y2,
                    "original_image_path": str(original_path.resolve()),
                    "cropped_image_path": "" if crop_path is None else str(crop_path.resolve()),
                    "captured_wbc_count": self._wbc_capture_count,
                    "status": status,
                },
            )
        return True, high_res, captured_detections

    def _wbc_serpentine_capture_worker(
        self,
        coordinates: list[tuple[int, int]],
        experiment_name: str,
    ) -> None:
        date_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        output_dir = default_output_dir("wbc") / WHITE_BLOOD_CELL_CLASS / experiment_name / date_time
        crop_dir = output_dir / "cropped_cells"
        original_dir = output_dir / "original_frames"
        metadata_csv = output_dir / "metadata.csv"
        crop_dir.mkdir(parents=True, exist_ok=True)
        original_dir.mkdir(parents=True, exist_ok=True)
        self._wbc_capture_latest_output_dir = output_dir
        try:
            self.root.after(0, self._update_wbc_output_button)
        except Exception:
            pass
        self._set_wbc_capture_count(0)
        stopped = False
        error_message = ""
        suppress_detection_until_clear = False
        clear_detection_frames = 0
        startup_extra_done: set[int] = set()
        self._wbc_capture_last_move_axis = None
        self._wbc_capture_resume_y_forward_compensation_pending = False

        try:
            speed_ms = int(WBC_CAPTURE_DEFAULT_CONFIG.get("step_move_speed_ms", _NORMAL_MOTOR_SPEED_MS))
            for axis_id in (0, 1):
                stepper = self._get_stepper(axis_id)
                if stepper is not None:
                    stepper.set_speed_ms(speed_ms)
            self._append_log(f"White_Blood_Cell 蛇行捕捉輸出：{output_dir.resolve()}")
            self._append_log(
                f"White_Blood_Cell 固定步數掃描：step_x={WBC_CAPTURE_DEFAULT_CONFIG.get('step_x', 8)}, "
                f"step_y={WBC_CAPTURE_DEFAULT_CONFIG.get('step_y', 8)}, "
                f"move SPEED_MS={speed_ms}, "
                f"settle={WBC_CAPTURE_DEFAULT_CONFIG.get('detection_settle_seconds', 0.5)}s, "
                f"detection attempts={WBC_CAPTURE_DEFAULT_CONFIG.get('detection_frame_attempts', 3)}"
            )

            for node_index, (current_x, current_y) in enumerate(coordinates, start=1):
                if self._wbc_capture_stop.is_set():
                    stopped = True
                    break

                self._set_wbc_capture_status(
                    f"白血球蛇行捕捉：移動至固定步數節點 {node_index}/{len(coordinates)} "
                    f"({current_x},{current_y})"
                )
                self._move_wbc_capture_to_coordinate(
                    current_x,
                    current_y,
                    startup_extra_done=startup_extra_done,
                )
                if not self._wait_wbc_step_settle(current_x, current_y):
                    stopped = True
                    break

                frame, detections, stop_detections = self._detect_wbc_after_fixed_step(current_x, current_y)
                self._set_wbc_capture_status(
                    f"白血球蛇行捕捉：節點 {node_index}/{len(coordinates)} 已完成辨識 "
                    f"({current_x},{current_y})"
                )

                if suppress_detection_until_clear:
                    if stop_detections:
                        clear_detection_frames = 0
                        continue
                    clear_detection_frames += 1
                    if clear_detection_frames >= int(
                        WBC_CAPTURE_DEFAULT_CONFIG.get("detection_clear_frames_before_rearm", 2)
                    ):
                        suppress_detection_until_clear = False
                        clear_detection_frames = 0
                    continue

                if not stop_detections:
                    continue

                self._stop_wbc_capture_motors()
                current_x, current_y, frame, detections, centered = self._center_wbc_capture_for_high_magnification(
                    current_x,
                    current_y,
                    frame,
                    detections,
                )
                self._stop_wbc_capture_motors()
                if centered:
                    self._set_wbc_capture_status("白血球蛇行捕捉：白血球已置中，等待切換 1000x 拍攝")
                else:
                    self._set_wbc_capture_status("白血球蛇行捕捉：平台已暫停，等待手動微調或 1000x 拍攝")

                if not self._wait_for_wbc_manual_capture(
                    frame,
                    detections,
                    current_x,
                    current_y,
                ):
                    stopped = True
                    break
                capture_ok, captured_frame, captured_detections = self._capture_white_blood_cells_at_coordinate(
                    current_x=current_x,
                    current_y=current_y,
                    experiment_name=experiment_name,
                    date_time=date_time,
                    crop_dir=crop_dir,
                    original_dir=original_dir,
                    metadata_csv=metadata_csv,
                )
                if not capture_ok:
                    stopped = True
                    break
                if not self._wait_for_wbc_user_resume(
                    captured_frame,
                    captured_detections,
                    current_x,
                    current_y,
                ):
                    stopped = True
                    break
                self._wbc_capture_resume_y_forward_compensation_pending = True
                suppress_detection_until_clear = True
                clear_detection_frames = 0
                self._set_wbc_capture_status("白血球蛇行捕捉：繼續前往下一個固定步數節點")
        except Exception as exc:
            error_message = str(exc)
            self._append_log(f"White_Blood_Cell 蛇行捕捉失敗：{error_message}")
            try:
                self.root.after(0, lambda message=error_message: messagebox.showerror("白血球蛇行捕捉失敗", message))
            except Exception:
                pass
        finally:
            summary = {
                "experiment_name": experiment_name,
                "date_time": date_time,
                "cell_class": WHITE_BLOOD_CELL_CLASS,
                "captured_wbc_count": self._wbc_capture_count,
                "coordinate_count": len(coordinates),
                "stopped": bool(stopped or self._wbc_capture_stop.is_set()),
                "error": error_message,
                "metadata_csv": str(metadata_csv.resolve()),
            }
            (output_dir / "summary.json").write_text(
                json.dumps(summary, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            for axis_id in (0, 1):
                stepper = self._get_stepper(axis_id)
                if stepper is not None:
                    try:
                        stepper.set_speed_ms(_NORMAL_MOTOR_SPEED_MS)
                    except Exception:
                        pass
            try:
                cv2.destroyWindow(self._wbc_capture_display_window)
            except Exception:
                pass
            self._wbc_capture_running = False
            self._wbc_capture_stop.clear()
            self._wbc_capture_manual_capture.clear()
            self._wbc_capture_resume.clear()
            self._wbc_capture_waiting_manual_capture = False
            self._wbc_capture_waiting_resume = False
            self._wbc_capture_resume_y_forward_compensation_pending = False

        if error_message:
            self._set_wbc_capture_status(f"白血球蛇行捕捉：失敗 {error_message}")
        elif stopped:
            self._set_wbc_capture_status(f"白血球蛇行捕捉：已停止，已拍攝 {self._wbc_capture_count}")
        else:
            self._set_wbc_capture_status(f"白血球蛇行捕捉：完成，已拍攝 {self._wbc_capture_count}")
            self._append_log(f"White_Blood_Cell 蛇行捕捉完成：已拍攝 {self._wbc_capture_count} 顆。")

    def _write_wbc_collection_manifest(
        self,
        collection_dir: Path,
        records: list[dict[str, Any]],
    ) -> tuple[Path, Path]:
        collection_dir.mkdir(parents=True, exist_ok=True)
        csv_path = collection_dir / "wbc_collection.csv"
        json_path = collection_dir / "wbc_collection.json"
        fieldnames = [
            "collection_id",
            "tile_index",
            "tile_wbc_index",
            "created_at",
            "platform_x",
            "platform_y",
            "source_image",
            "crop_path",
            "frame_width",
            "frame_height",
            "center_x",
            "center_y",
            "bbox_x1",
            "bbox_y1",
            "bbox_x2",
            "bbox_y2",
            "crop_x1",
            "crop_y1",
            "crop_x2",
            "crop_y2",
            "confidence",
            "label",
            "wbc_subtype",
            "wbc_subtype_confidence",
        ]
        rows: list[dict[str, Any]] = []
        for index, record in enumerate(records, start=1):
            row = {"collection_id": index, **record}
            rows.append(row)

        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({key: row.get(key, "") for key in fieldnames})

        payload = {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "total_wbc": len(rows),
            "cell_class": WHITE_BLOOD_CELL_CLASS,
            "records": rows,
        }
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return csv_path.resolve(), json_path.resolve()

    def _capture_and_stitch_worker(
        self,
        coordinates: list[tuple[int, int]],
        output_prefix: str = "stitched_auto",
        overlap_ratio: float = 0.40,
        auto_stitch: bool = True,
        collect_wbc: bool = False,
    ) -> None:
        capture_count = len(coordinates)
        if capture_count <= 0:
            raise RuntimeError("沒有可用的拍攝座標。")
        session_root_dir = self._resolve_capture_output_dir()
        session_dir = session_root_dir / f"session_{_timestamp()}"
        session_dir.mkdir(parents=True, exist_ok=True)
        self._latest_capture_session = session_dir
        wbc_collection_dir = session_dir / "wbc_collection" if collect_wbc else None
        wbc_collection_records: list[dict[str, Any]] = []
        if wbc_collection_dir is not None:
            (wbc_collection_dir / "crops").mkdir(parents=True, exist_ok=True)
            self._append_log(f"WBC 收集資料夾：{wbc_collection_dir.resolve()}")
        self._append_log(
            f"拍照存檔模式: 品質優先降階 (long_side={_CAPTURE_SAVE_MAX_LONG_SIDE}px)"
        )
        settle_s = max(0.0, int(self.settle_ms_var.get()) / 1000.0)
        coord_rows: list[tuple[int, int, int, str]] = []
        start_x, start_y = coordinates[0]

        try:
            cap = self._ensure_camera_open()
            x_stepper = self._get_stepper(0)
            y_stepper = self._get_stepper(1)
            if cap is None:
                raise RuntimeError("相機尚未就緒。")
            self._warmup_connected_axes_for_capture()
            self._move_to_coordinate(start_x, start_y, label="拍攝起點")

            prev_x = start_x
            prev_y = start_y

            for idx in range(capture_count):
                if self._capture_job_stop.is_set():
                    self._append_log("拍攝任務已中止。")
                    break

                vx, vy = coordinates[idx]
                if idx > 0:
                    dx = vx - prev_x
                    dy = vy - prev_y
                    if dx != 0:
                        if x_stepper is None:
                            raise RuntimeError("X-motor 尚未連線，無法移動到下一個拍攝點。")
                        self._move_axis_steps(0, dx)
                    if dy != 0:
                        if y_stepper is None:
                            raise RuntimeError("Y-motor 尚未連線，無法移動到下一個拍攝點。")
                        self._move_axis_steps(1, dy)
                    if settle_s > 0:
                        time.sleep(settle_s)
                    prev_x, prev_y = vx, vy

                frame = self._read_latest_frame(discard_frames=4)
                if frame is None:
                    raise RuntimeError(f"第 {idx + 1} 張讀取相機畫面失敗。")

                self._set_virtual_coord(vx, vy)
                img_name = f"{vx}_{vy}.jpg"
                img_path = session_dir / img_name
                styled_frame = self._styled_camera_frame(frame)
                saved_frame = self._prepare_capture_save_frame(styled_frame)
                if not cv2.imwrite(str(img_path), saved_frame):
                    raise RuntimeError(f"第 {idx + 1} 張寫入失敗。")
                detections = self._detect_objects(saved_frame)
                det_count = self._save_detection_artifacts(
                    img_path,
                    saved_frame,
                    detections=detections,
                    force_features=True,
                )
                if wbc_collection_dir is not None:
                    new_wbc_records = save_wbc_collection_crops(
                        collection_dir=wbc_collection_dir,
                        frame=saved_frame,
                        detections=detections,
                        source_image_path=img_path,
                        tile_index=idx + 1,
                        platform_x=vx,
                        platform_y=vy,
                    )
                    if new_wbc_records:
                        wbc_collection_records.extend(new_wbc_records)
                        self._append_log(
                            f"tile {idx + 1} 收集 WBC {len(new_wbc_records)} 顆，累計={len(wbc_collection_records)}。"
                        )
                coord_rows.append((idx + 1, vx, vy, img_name))
                if (idx + 1) % 20 == 0 or idx == 0 or idx + 1 == capture_count:
                    if det_count is None:
                        self._append_log(f"已拍攝 {idx + 1}/{capture_count} 張，座標=({vx},{vy})")
                    else:
                        self._append_log(
                            f"已拍攝 {idx + 1}/{capture_count} 張，座標=({vx},{vy})，detections={det_count}"
                        )

            if coord_rows:
                coord_map_path = self._write_coordinate_map(session_dir, coord_rows)
                self._append_log(f"座標對照已輸出：{coord_map_path}")

            wbc_manifest_paths: tuple[Path, Path] | None = None
            if wbc_collection_dir is not None:
                wbc_manifest_paths = self._write_wbc_collection_manifest(
                    wbc_collection_dir,
                    wbc_collection_records,
                )
                self._append_log(
                    f"WBC 收集完成：共 {len(wbc_collection_records)} 顆，CSV={wbc_manifest_paths[0]}，JSON={wbc_manifest_paths[1]}"
                )

            if self._capture_job_stop.is_set():
                self._append_log(
                    f"拍攝已停止，已保留 {len(coord_rows)} 張影像於：{session_dir.resolve()}"
                )
                return

            if len(coord_rows) < 2:
                message = f"拍攝完成，但影像不足 2 張：{session_dir.resolve()}"
                self._append_log(message)
                return

            if not auto_stitch:
                completion_message = f"蛇行拍攝完成，已保留 {len(coord_rows)} 張影像與特徵資料：{session_dir.resolve()}"
                if wbc_collection_dir is not None:
                    completion_message += f"，WBC={len(wbc_collection_records)} 顆"
                self._append_log(completion_message)
                self.root.after(
                    0,
                    lambda path=session_dir.resolve(), count=len(coord_rows), wbc_count=len(wbc_collection_records), wbc_dir=wbc_collection_dir: messagebox.showinfo(
                        "掃描完成",
                        (
                            f"已完成拍攝 {count} 張。\n"
                            f"WBC 收集數: {wbc_count}\n\n"
                            f"資料夾:\n{path}\n\n"
                            + (f"WBC 資料夾:\n{wbc_dir.resolve()}\n\n" if wbc_dir is not None else "")
                            + "請按「拼接最近蛇行」執行拼接。"
                        ),
                    ),
                )
                return

            self._append_log("拍攝完成，開始拼接...")
            stitched_path = self._stitch_session_images(
                session_dir,
                len(coord_rows),
                output_prefix=output_prefix,
                overlap_ratio=overlap_ratio,
            )
            self._append_log(f"拼接完成：{stitched_path}")
            self._append_log(f"原始影像資料夾：{session_dir.resolve()}")
        except Exception as exc:
            if wbc_collection_dir is not None and wbc_collection_records:
                try:
                    csv_path, json_path = self._write_wbc_collection_manifest(wbc_collection_dir, wbc_collection_records)
                    self._append_log(f"已保留中斷前 WBC 收集 manifest：{csv_path}，{json_path}")
                except Exception as manifest_exc:
                    self._append_log(f"WBC 收集 manifest 輸出失敗: {manifest_exc}")
            self._append_log(f"拍攝/拼接失敗: {exc}")
            messagebox.showerror("拍攝/拼接失敗", str(exc))
        finally:
            self._capture_job_running = False

    def _generate_capture_coordinates(
        self,
        capture_count: int,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
    ) -> list[tuple[int, int]]:
        coords: list[tuple[int, int]] = []
        if capture_count <= 1:
            return [(int(start_x), int(start_y))]

        x0 = int(start_x)
        y0 = int(start_y)
        x1 = int(end_x)
        y1 = int(end_y)
        for idx in range(capture_count):
            t = idx / float(capture_count - 1)
            x = int(round(x0 + (x1 - x0) * t))
            y = int(round(y0 + (y1 - y0) * t))
            coords.append((x, y))
        return coords

    def _generate_capture_coordinates_by_step(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
    ) -> list[tuple[int, int]]:
        start_x = int(start_x)
        start_y = int(start_y)
        end_x = int(end_x)
        end_y = int(end_y)
        step_x_raw = int(self.steps_var.get())
        step_y_raw = int(self.y_steps_var.get())

        dx_total = end_x - start_x
        dy_total = end_y - start_y

        if dx_total == 0 and dy_total == 0:
            return [(start_x, start_y)]
        if dx_total != 0 and step_x_raw == 0:
            raise ValueError("X 步數不能為 0，否則無法依步數移動到終點。")
        if dy_total != 0 and step_y_raw == 0:
            raise ValueError("Y 步數不能為 0，否則無法依步數移動到終點。")

        step_x = 0 if dx_total == 0 else (1 if dx_total > 0 else -1) * abs(step_x_raw)
        step_y = 0 if dy_total == 0 else (1 if dy_total > 0 else -1) * abs(step_y_raw)

        coords = [(start_x, start_y)]
        cur_x = start_x
        cur_y = start_y

        while cur_x != end_x or cur_y != end_y:
            next_x = cur_x
            next_y = cur_y
            if cur_x != end_x:
                remaining_x = end_x - cur_x
                next_x = end_x if abs(remaining_x) <= abs(step_x) else cur_x + step_x
            if cur_y != end_y:
                remaining_y = end_y - cur_y
                next_y = end_y if abs(remaining_y) <= abs(step_y) else cur_y + step_y
            if next_x == cur_x and next_y == cur_y:
                break
            coords.append((next_x, next_y))
            cur_x, cur_y = next_x, next_y

        return coords

    def _write_coordinate_map(self, session_dir: Path, rows: list[tuple[int, int, int, str]]) -> Path:
        csv_path = session_dir / "virtual_coordinates.csv"
        with csv_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["index", "x", "y", "filename"])
            writer.writerows(rows)
        return csv_path.resolve()

    def _load_session_capture_order(self, session_dir: Path) -> tuple[list[str], str]:
        coord_map_path = session_dir / "virtual_coordinates.csv"
        if coord_map_path.exists():
            ordered_paths: list[str] = []
            with coord_map_path.open("r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                rows = list(reader)

            def _row_index(row: dict[str, str]) -> int:
                try:
                    return int(row.get("index", "0"))
                except Exception:
                    return 0

            for row in sorted(rows, key=_row_index):
                filename = (row.get("filename") or "").strip()
                if not filename:
                    continue
                img_path = session_dir / filename
                if img_path.exists():
                    ordered_paths.append(str(img_path.resolve()))

            if ordered_paths:
                return ordered_paths, "coordinate_map"

        image_paths = sorted(
            (
                str(path.resolve())
                for path in session_dir.iterdir()
                if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp"}
            ),
            key=lambda p: Path(p).name.lower(),
        )
        return image_paths, "filename"

    def _infer_stitcher_mode(self, session_dir: Path) -> str:
        coord_map_path = session_dir / "virtual_coordinates.csv"
        if not coord_map_path.exists():
            return "panorama"

        try:
            with coord_map_path.open("r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                coords = [
                    (int(row["x"]), int(row["y"]))
                    for row in reader
                    if row.get("x") is not None and row.get("y") is not None
                ]
        except Exception:
            return "panorama"

        if len(coords) < 2:
            return "panorama"

        xs = {x for x, _ in coords}
        ys = {y for _, y in coords}
        if len(xs) == 1 or len(ys) == 1:
            return "scans"
        return "panorama"

    def _run_formal_stitcher_session(
        self,
        session_dir: Path,
        capture_count: int,
        output_prefix: str,
        selected_paths: Optional[list[str]],
        overlap_ratio: float,
        save_result_detection: bool,
    ):
        if not _PRACTICAL_STITCHER_SCRIPT.exists():
            raise RuntimeError(f"找不到正式拼接程式：{_PRACTICAL_STITCHER_SCRIPT}")

        image_exts = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
        all_filenames = {
            path.name
            for path in session_dir.iterdir()
            if path.is_file() and path.suffix.lower() in image_exts
        }
        selected_filenames = (
            {Path(path).name for path in selected_paths}
            if selected_paths is not None
            else set(all_filenames)
        )
        if len(selected_filenames) < 2:
            raise RuntimeError("正式拼接至少需要 2 張影像。")

        base_output_dir = self._resolve_stitch_output_dir()
        timestamp = _timestamp()
        formal_output_dir = base_output_dir / f"{output_prefix}_{capture_count}_{timestamp}_formal"
        coord_map_path = session_dir / "virtual_coordinates.csv"
        use_golden = session_dir.name == _FORMAL_GOLDEN_SESSION_NAME and _FORMAL_GOLDEN_PLACEMENTS.exists()
        excluded_filenames = set(all_filenames - selected_filenames)
        if use_golden:
            excluded_filenames.update(_FORMAL_GOLDEN_EXCLUDED_FILENAMES)

        cmd = [
            sys.executable,
            str(_PRACTICAL_STITCHER_SCRIPT),
            "--input",
            str(session_dir.resolve()),
            "--output",
            str(formal_output_dir.resolve()),
            "--overlap",
            f"{float(overlap_ratio):.4f}",
            "--use-cuda",
            "auto",
            "--export-format",
            "tif",
        ]
        if coord_map_path.exists():
            cmd.extend(["--coords", str(coord_map_path.resolve())])
        for filename in sorted(excluded_filenames):
            cmd.extend(["--exclude", filename])
        if use_golden:
            cmd.extend(
                [
                    "--min-edge-score",
                    "0.10",
                    "--cluster-tolerance-full-px",
                    "314",
                ]
            )

        self._append_log(
            "正式實用拼接版本啟動："
            f"input={session_dir.resolve()}，output={formal_output_dir.resolve()}，"
            f"overlap={float(overlap_ratio):.0%}"
        )
        if use_golden:
            self._append_log("偵測到已驗證 session；實用拼接入口會套用 golden/template 與 8_0.jpg 排除規則。")
        elif excluded_filenames:
            self._append_log("正式拼接排除未選取影像：" + ", ".join(sorted(excluded_filenames)))

        env = os.environ.copy()
        env.setdefault("PYTHONIOENCODING", "utf-8")
        startupinfo = None
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        completed = subprocess.run(
            cmd,
            cwd=str(_FORMAL_STITCHER_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            startupinfo=startupinfo,
        )
        stdout_lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
        stderr_lines = [line.strip() for line in completed.stderr.splitlines() if line.strip()]
        for line in stdout_lines[-8:]:
            self._append_log(f"正式拼接輸出: {line}")
        if completed.returncode != 0:
            tail = "\n".join((stderr_lines or stdout_lines)[-12:])
            raise RuntimeError(f"正式拼接失敗，exit={completed.returncode}\n{tail}")

        practical_report_path = formal_output_dir / "practical_stitch_report.json"
        practical_warnings = []
        if practical_report_path.exists():
            try:
                report = json.loads(practical_report_path.read_text(encoding="utf-8-sig"))
                mode = report.get("mode", "unknown")
                quality_status = report.get("quality_status", "unknown")
                human_review_required = bool(report.get("human_review_required", True))
                self._append_log(f"正式拼接品質報告：mode={mode}，quality={quality_status}")
                if human_review_required:
                    practical_warnings.append("此拼接結果為候選輸出，需要人工複核後再交付。")
                    self._append_log("正式拼接警告：此輸出需要人工複核。")
            except Exception as report_exc:
                practical_warnings.append(f"品質報告讀取失敗：{report_exc}")
                self._append_log(f"正式拼接品質報告讀取失敗：{report_exc}")

        if use_golden:
            candidate_path = formal_output_dir / "debug" / "placements.csv"
            compare_json = formal_output_dir / "debug" / "golden_compare.json"
            compare_csv = formal_output_dir / "debug" / "golden_compare.csv"
            verify_cmd = [
                sys.executable,
                str(_FORMAL_GOLDEN_COMPARE_SCRIPT),
                "--candidate",
                str(candidate_path.resolve()),
                "--golden",
                str(_FORMAL_GOLDEN_PLACEMENTS.resolve()),
                "--output-json",
                str(compare_json.resolve()),
                "--output-csv",
                str(compare_csv.resolve()),
            ]
            verify = subprocess.run(
                verify_cmd,
                cwd=str(_FORMAL_STITCHER_ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                startupinfo=startupinfo,
            )
            if verify.returncode != 0:
                verify_tail = "\n".join(
                    [line.strip() for line in (verify.stderr or verify.stdout).splitlines() if line.strip()][-12:]
                )
                raise RuntimeError(f"golden placement 驗證失敗，exit={verify.returncode}\n{verify_tail}")
            self._append_log(f"golden placement 驗證完成：{compare_json.resolve()}")

        final_path = formal_output_dir / "stitched.tif"
        if not final_path.exists():
            for suffix in ("png", "jpg"):
                candidate = formal_output_dir / f"stitched.{suffix}"
                if candidate.exists():
                    final_path = candidate
                    break
        if not final_path.exists():
            raise RuntimeError(f"正式拼接完成但找不到輸出主圖：{formal_output_dir}")

        preview_path = formal_output_dir / "stitched_preview.jpg"
        summary_path = formal_output_dir / "stitch_summary.json"
        self._latest_stitch_output_dir = formal_output_dir
        if save_result_detection:
            self._save_detection_artifacts_from_path(str(final_path))
        return SimpleNamespace(
            stitched_image_path=str(final_path.resolve()),
            warnings=practical_warnings,
            metadata_path=str(summary_path.resolve()) if summary_path.exists() else None,
            overlay_preview_path=str(preview_path.resolve()) if preview_path.exists() else None,
            formal_output_dir=str(formal_output_dir.resolve()),
        )

    def _run_stitch_session(
        self,
        session_dir: Path,
        capture_count: int,
        output_prefix: str = "stitched_auto",
        selected_paths: Optional[list[str]] = None,
        overlap_ratio: float = 0.40,
        save_result_detection: bool = True,
    ):
        output_dir = self._resolve_stitch_output_dir()
        self._latest_stitch_output_dir = output_dir
        timestamp = _timestamp()

        if selected_paths is None:
            ordered_paths, order_source = self._load_session_capture_order(session_dir)
            if order_source == "coordinate_map":
                self._append_log(f"依座標對照順序讀取影像，共 {len(ordered_paths)} 張。")
            else:
                self._append_log("找不到座標對照檔，改用檔名順序讀取影像。")
            selected_paths = ordered_paths[:capture_count] if ordered_paths else None
        else:
            selected_paths = [str(Path(path)) for path in selected_paths]
            self._append_log(f"依指定 capture 順序讀取影像，共 {len(selected_paths)} 張。")

        if selected_paths is not None and len(selected_paths) < 2:
            raise RuntimeError("可用影像不足，至少需要 2 張才能拼接。")
        if selected_paths is None:
            image_candidates = [
                str(path.resolve())
                for path in sorted(session_dir.iterdir(), key=lambda item: item.name.lower())
                if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
            ][:capture_count]
            if len(image_candidates) < 2:
                raise RuntimeError("可用影像不足，至少需要 2 張才能拼接。")
            selected_paths = image_candidates

        try:
            return self._run_formal_stitcher_session(
                session_dir=session_dir,
                capture_count=capture_count,
                output_prefix=output_prefix,
                selected_paths=selected_paths,
                overlap_ratio=overlap_ratio,
                save_result_detection=save_result_detection,
            )
        except Exception as formal_exc:
            self._latest_stitch_output_dir = output_dir
            self._append_log(f"正式拼接版本失敗，改用舊自動流程：{formal_exc}")

        detect_conf = self._get_detect_conf()
        detect_model = self._resolve_detect_model_for_gui()
        coord_map_path = session_dir / "virtual_coordinates.csv"
        if coord_map_path.exists():
            from cell_stitching_project.coordinate_overlay_stitch import stitch_by_coordinates

            self._append_log(
                "拼接設定：內容主導 SOP（stage 座標只作初始估計 -> overlap phase/subpixel 對齊 -> detection/constrained fallback）。"
            )
            stitch_payload = stitch_by_coordinates(
                input_dir=session_dir,
                output_dir=output_dir,
                explicit_paths=selected_paths,
                overlap_ratio=overlap_ratio,
                blend_mode="content_phase",
                strip_axis="auto",
                use_detection_features=True,
                detection_model_path=detect_model,
                detection_confidence=detect_conf,
                detection_feature_max_features=500,
                detection_feature_min_matches=3,
                result_name=f"{output_prefix}_{capture_count}_{timestamp}.png",
                preview_name=f"{output_prefix}_{capture_count}_{timestamp}_preview.jpg",
                metadata_name=f"{output_prefix}_{capture_count}_{timestamp}_metadata.json",
            )
            result_path = Path(str(stitch_payload["result_path"])).resolve()
            if save_result_detection:
                self._save_detection_artifacts_from_path(str(result_path))
            return SimpleNamespace(
                stitched_image_path=str(result_path),
                warnings=[],
                metadata_path=stitch_payload.get("metadata_path"),
                overlay_preview_path=stitch_payload.get("preview_path"),
            )

        from cell_stitching_project.config import StitchingConfig
        from cell_stitching_project.main import run_stitch_pipeline

        object_guided = True
        max_rotation = 3.0
        alignment_method = "auto"
        blending_method = "auto"
        save_debug_images = True

        self._append_log(
            "拼接設定：自動流程（phase -> ecc -> orb/sift，YOLO ROI 輔助自動判斷），"
            f"overlap={float(overlap_ratio):.0%}，compute_device=auto，CUDA 可用時優先使用 GPU。"
        )

        config = StitchingConfig(
            input_dir=session_dir,
            input_paths=selected_paths,
            output_dir=output_dir,
            alignment_method=alignment_method,
            blending_method=blending_method,
            use_grayscale=True,
            use_denoise=True,
            use_clahe=True,
            use_flatfield=True,
            normalize=False,
            max_rotation=max_rotation,
            overlap_ratio=overlap_ratio,
            save_debug_images=save_debug_images,
            use_yolo_guidance=object_guided,
            yolo_model_path=(detect_model if object_guided else None),
            yolo_confidence=detect_conf,
            prefer_gpu=True,
            compute_device="auto",
            gpu_fallback_allowed=True,
            yolo_device="auto",
            output_format="png",
            result_name=f"{output_prefix}_{capture_count}_{timestamp}.png",
            overlay_name=f"{output_prefix}_{capture_count}_{timestamp}_overlay.png",
            shifts_json_name=f"{output_prefix}_{capture_count}_{timestamp}_shifts.json",
            shifts_csv_name=f"{output_prefix}_{capture_count}_{timestamp}_shifts.csv",
            log_name=f"{output_prefix}_{capture_count}_{timestamp}.log",
        )
        result = run_stitch_pipeline(config)
        for warning in result.warnings:
            self._append_log(f"拼接警告: {warning}")
        if result.stitched_image_path is None:
            raise RuntimeError("新拼接引擎未回傳輸出檔案。")
        if save_result_detection:
            self._save_detection_artifacts_from_path(result.stitched_image_path)
        return result

    def _stitch_session_images(
        self,
        session_dir: Path,
        capture_count: int,
        output_prefix: str = "stitched_auto",
        overlap_ratio: float = 0.40,
    ) -> Path:
        result = self._run_stitch_session(
            session_dir=session_dir,
            capture_count=capture_count,
            output_prefix=output_prefix,
            selected_paths=None,
            overlap_ratio=overlap_ratio,
            save_result_detection=True,
        )
        return Path(result.stitched_image_path).resolve()

    def _start_auto(self) -> None:
        if self._wbc_capture_running:
            messagebox.showwarning("自動移動", "請先停止白血球固定步數蛇行掃描。")
            return
        if self._backlash_calibration_running:
            messagebox.showwarning("自動移動", "backlash 校正進行中，請稍後再試。")
            return
        if self._auto_running:
            self._append_log("自動移動已在執行中。")
            return
        x_stepper = self._get_stepper(0)
        if x_stepper is None:
            messagebox.showwarning("自動移動", "請先連線 X-motor。")
            return

        try:
            steps = abs(int(self.steps_var.get()))
            if steps <= 0:
                raise ValueError("步數必須大於 0")
            cycles = int(self.auto_cycles_var.get())
            interval_s = max(0.0, int(self.auto_interval_ms_var.get()) / 1000.0)
            direction = 1
            pingpong = bool(self.pingpong_var.get())
        except Exception as exc:
            messagebox.showerror("自動移動設定", str(exc))
            return

        self._auto_running = True
        self._auto_stop.clear()

        def auto_loop() -> None:
            try:
                step_sign = direction
                done = 0
                while not self._auto_stop.is_set():
                    step_count = steps * step_sign
                    if x_stepper is None:
                        break
                    self._move_axis_steps(0, step_count)
                    x, y = self._shift_virtual_coord(step_count, 0)
                    done += 1
                    self._append_log(f"自動移動: {done}/{cycles or '無限'} -> {step_count}，座標=({x},{y})")
                    if pingpong:
                        step_sign *= -1
                    if cycles > 0 and done >= cycles:
                        break
                    if interval_s > 0:
                        time.sleep(interval_s)
            except Exception as exc:
                self._append_log(f"自動移動錯誤: {exc}")
            finally:
                self._auto_running = False
                self._append_log("自動移動已停止。")

        self._auto_thread = threading.Thread(target=auto_loop, daemon=True)
        self._auto_thread.start()

    def _stop_auto(self) -> None:
        if not self._auto_running:
            return
        self._auto_stop.set()
        thread = self._auto_thread
        if thread is not None:
            thread.join(timeout=1.5)

    def _find_openable_output_folder(self) -> Optional[Path]:
        video_path = self.serpentine_video_output_var.get().strip()
        video_folder = Path(video_path).expanduser().parent if video_path else None
        configured_stitch_dir = self.stitch_output_dir_var.get().strip()
        configured_capture_dir = self.capture_output_dir_var.get().strip()
        candidates = (
            video_folder,
            self._wbc_capture_latest_output_dir,
            self._latest_stitch_output_dir,
            self._latest_capture_session,
            Path(configured_stitch_dir).expanduser() if configured_stitch_dir else None,
            Path(configured_capture_dir).expanduser() if configured_capture_dir else None,
        )
        for folder in candidates:
            if folder is not None and folder.is_dir():
                return folder.resolve()
        return None

    def _open_output_folder(self) -> None:
        folder = self._find_openable_output_folder()
        if folder is None:
            messagebox.showinfo("輸出資料夾", "尚未產生輸出，也尚未選擇輸出資料夾。")
            return

        try:
            if hasattr(os, "startfile"):
                os.startfile(str(folder))
            else:
                subprocess.Popen(["explorer", str(folder)])
            self._append_log(f"已開啟輸出資料夾: {folder}")
        except Exception as exc:
            self._append_log(f"開啟輸出資料夾失敗: {exc}")
            messagebox.showerror("開啟資料夾失敗", str(exc))

    def run(self) -> None:
        self.root.mainloop()

    def _on_close(self) -> None:
        if self._wbc_capture_running:
            self._stop_wbc_serpentine_capture()
        self._stop_serpentine_video_recording()
        self._stop_auto()
        self._stop_preview()
        calibration_thread = self._backlash_calibration_thread
        if calibration_thread is not None and calibration_thread.is_alive():
            calibration_thread.join(timeout=1.0)
        feedback_thread = self._image_feedback_thread
        if feedback_thread is not None and feedback_thread.is_alive():
            feedback_thread.join(timeout=1.0)
        job_thread = self._capture_job_thread
        if job_thread is not None and job_thread.is_alive():
            job_thread.join(timeout=1.0)
        wbc_capture_thread = self._wbc_capture_thread
        if wbc_capture_thread is not None and wbc_capture_thread.is_alive():
            wbc_capture_thread.join(timeout=1.0)
        for axis_id in self.stepper_by_axis:
            stepper = self._get_stepper(axis_id)
            if stepper is not None:
                try:
                    self._stop_and_release_stepper(axis_id, stepper, reason="關閉 GUI")
                    stepper.close()
                except Exception:
                    pass
        try:
            cv2.destroyAllWindows()
        except Exception:
            pass
        self.root.destroy()


def main() -> None:
    StepperDragGUI().run()


if __name__ == "__main__":
    main()

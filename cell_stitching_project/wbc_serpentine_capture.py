from __future__ import annotations

import csv
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import cv2
import numpy as np
from msh_motion_policy import FIXED_STEP_DELAY_MS


SIMULATION_MODE = False
WHITE_BLOOD_CELL_CLASS = "White_Blood_Cell"


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _default_wbc_capture_model_path() -> Path:
    return (
        _workspace_root()
        / "stitched_output"
        / "stitched_output"
        / "stitched_output"
        / "models"
        / "blood_cells_3cls_yolov8n_20260429.pt"
    )

DEFAULT_CONFIG: dict[str, Any] = {
    "experiment_name": "sample_01",
    "output_root": Path("output"),
    "simulation_mode": SIMULATION_MODE,
    "start_x": 0,
    "start_y": 0,
    "columns": 5,
    "rows": 5,
    "step_x": 8,
    "step_y": 8,
    "scan_stop_min_confidence": 0.50,
    "preview_confidence": 0.20,
    "min_confidence": 0.50,
    "crop_padding": 10,
    "border_margin": 8,
    "min_bbox_area": 900,
    "movement_mode": "fixed_step_with_settle",
    "movement_pause_seconds": 0.08,
    "video_quality": "high",
    "camera_index": 0,
    "video_source": "",
    "show_preview": True,
    "preview_window_name": "White Blood Cell Capture",
    "model_path": _default_wbc_capture_model_path(),
    "device": "auto",
    "imgsz": 960,
    "iou": 0.45,
    "hardware_x_port": "",
    "hardware_y_port": "",
    "hardware_baud": 115200,
    "step_move_speed_ms": FIXED_STEP_DELAY_MS,
    "detection_settle_seconds": 0.5,
    "detection_frame_attempts": 8,
    "detection_frame_interval_seconds": 0.25,
    "detection_clear_frames_before_rearm": 2,
    "center_after_detection": False,
    "center_min_confidence": 0.60,
    "center_min_bbox_area": 900,
    "center_tolerance_px": 120.0,
    "center_min_step_improvement_px": 16.0,
    "center_max_iterations": 3,
    "center_max_step_per_axis": 12,
    "center_settle_seconds": 0.45,
    "center_detection_frame_attempts": 3,
    "center_detection_frame_interval_seconds": 0.12,
    "center_x_image_px_per_step": -30.0,
    "center_y_image_px_per_step": -160.0,
    "y_after_x_axis_switch_compensation_steps": 10,
    "y_forward_after_wbc_resume_compensation_steps": 15,
    "simulation_frame_width": 960,
    "simulation_frame_height": 720,
    "simulation_wbc_coordinates": {
        (0, 20): [(320, 280, 74)],
        (10, 30): [(260, 300, 70), (610, 320, 66)],
        (30, 10): [(500, 260, 72)],
    },
}


METADATA_FIELDS = [
    "experiment_name",
    "date_time",
    "current_x",
    "current_y",
    "cell_index_at_coordinate",
    "cell_class",
    "confidence",
    "bbox_x1",
    "bbox_y1",
    "bbox_x2",
    "bbox_y2",
    "original_image_path",
    "cropped_image_path",
    "captured_wbc_count",
    "status",
]


@dataclass(frozen=True)
class WBCDetection:
    cell_class: str
    confidence: float
    bbox: tuple[int, int, int, int]

    @property
    def x1(self) -> int:
        return self.bbox[0]

    @property
    def y1(self) -> int:
        return self.bbox[1]

    @property
    def x2(self) -> int:
        return self.bbox[2]

    @property
    def y2(self) -> int:
        return self.bbox[3]


class SimulationStage:
    def __init__(self) -> None:
        self.current_x = int(DEFAULT_CONFIG["start_x"])
        self.current_y = int(DEFAULT_CONFIG["start_y"])

    def move_to(self, x: int, y: int) -> None:
        self.current_x = int(x)
        self.current_y = int(y)
        print(f"[SIMULATION] move_to_coordinate x={self.current_x}, y={self.current_y}", flush=True)
        time.sleep(float(DEFAULT_CONFIG["movement_pause_seconds"]))

    def stop(self) -> None:
        print(f"[SIMULATION] stop platform at x={self.current_x}, y={self.current_y}", flush=True)

    def close(self) -> None:
        pass


class HardwareStage:
    def __init__(self) -> None:
        self.current_x = int(DEFAULT_CONFIG["start_x"])
        self.current_y = int(DEFAULT_CONFIG["start_y"])
        x_port = str(DEFAULT_CONFIG.get("hardware_x_port", "")).strip()
        y_port = str(DEFAULT_CONFIG.get("hardware_y_port", "")).strip()
        if not x_port or not y_port:
            raise RuntimeError(
                "Hardware mode requires DEFAULT_CONFIG['hardware_x_port'] and "
                "DEFAULT_CONFIG['hardware_y_port']."
            )

        hardware_dir = (
            Path(__file__).resolve().parents[1]
            / "stitched_output"
            / "stitched_output"
            / "stitched_output"
            / "hardware"
        )
        if hardware_dir.exists() and str(hardware_dir) not in sys.path:
            sys.path.insert(0, str(hardware_dir))

        from arduino_stepper import ArduinoStepper

        baud = int(DEFAULT_CONFIG["hardware_baud"])
        self.x_stepper = ArduinoStepper(port=x_port, baud=baud)
        self.y_stepper = ArduinoStepper(port=y_port, baud=baud)
        self.x_stepper.connect()
        self.y_stepper.connect()
        self.x_stepper.set_fixed_speed()
        self.y_stepper.set_fixed_speed()

    def move_to(self, x: int, y: int) -> None:
        target_x = int(x)
        target_y = int(y)
        dx = target_x - self.current_x
        dy = target_y - self.current_y
        if dx:
            self.x_stepper.move(dx)
        if dy:
            self.y_stepper.move(dy)
        self.current_x = target_x
        self.current_y = target_y

    def stop(self) -> None:
        for stepper in (self.x_stepper, self.y_stepper):
            try:
                stepper.stop()
            except Exception:
                pass

    def close(self) -> None:
        for stepper in (self.x_stepper, self.y_stepper):
            try:
                stepper.close()
            except Exception:
                pass


class OpenCVCamera:
    def __init__(self, source: int | str) -> None:
        self.cap = cv2.VideoCapture(source)
        if not self.cap.isOpened():
            raise RuntimeError(f"Cannot open camera/video source: {source}")

    def read(self) -> tuple[bool, np.ndarray | None]:
        ok, frame = self.cap.read()
        if not ok and isinstance(DEFAULT_CONFIG.get("video_source", ""), str) and DEFAULT_CONFIG.get("video_source"):
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = self.cap.read()
        return bool(ok), frame

    def capture_high_resolution_image(self) -> np.ndarray:
        ok, frame = self.read()
        if not ok or frame is None:
            raise RuntimeError("Failed to capture high-resolution image.")
        return frame.copy()

    def release(self) -> None:
        self.cap.release()


class SimulatedCamera:
    def __init__(self) -> None:
        self.width = int(DEFAULT_CONFIG["simulation_frame_width"])
        self.height = int(DEFAULT_CONFIG["simulation_frame_height"])
        self.current_x = int(DEFAULT_CONFIG["start_x"])
        self.current_y = int(DEFAULT_CONFIG["start_y"])

    def set_coordinate(self, x: int, y: int) -> None:
        self.current_x = int(x)
        self.current_y = int(y)

    def read(self) -> tuple[bool, np.ndarray]:
        return True, self._render_frame()

    def capture_high_resolution_image(self) -> np.ndarray:
        return self._render_frame()

    def release(self) -> None:
        pass

    def _render_frame(self) -> np.ndarray:
        x, y = self.current_x, self.current_y
        rng_seed = int(x * 1009 + y * 917 + 17)
        rng = np.random.default_rng(rng_seed)
        frame = np.full((self.height, self.width, 3), (220, 224, 196), dtype=np.uint8)
        noise = rng.normal(0, 6, frame.shape).astype(np.int16)
        frame = np.clip(frame.astype(np.int16) + noise, 0, 255).astype(np.uint8)

        for _ in range(22):
            cx = int(rng.integers(40, self.width - 40))
            cy = int(rng.integers(40, self.height - 40))
            radius = int(rng.integers(22, 42))
            cv2.circle(frame, (cx, cy), radius, (120, 90, 220), 2)
            cv2.circle(frame, (cx, cy), max(2, radius // 4), (170, 150, 245), -1)

        for cx, cy, radius in DEFAULT_CONFIG["simulation_wbc_coordinates"].get((int(x), int(y)), []):
            cv2.circle(frame, (int(cx), int(cy)), int(radius), (210, 60, 190), -1)
            cv2.circle(frame, (int(cx), int(cy)), int(radius), (70, 20, 90), 4)
            cv2.circle(frame, (int(cx), int(cy)), max(8, int(radius) // 3), (235, 205, 250), -1)
        return frame


class SimulatedWBCDetector:
    def detect(self, frame: np.ndarray) -> list[WBCDetection]:
        b, g, r = cv2.split(frame)
        mask = ((r > 145) & (b > 145) & (g < 115)).astype(np.uint8) * 255
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((11, 11), np.uint8))
        contours, _hierarchy = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        detections: list[WBCDetection] = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < float(DEFAULT_CONFIG["min_bbox_area"]):
                continue
            x, y, w, h = cv2.boundingRect(contour)
            detections.append(
                WBCDetection(
                    cell_class=WHITE_BLOOD_CELL_CLASS,
                    confidence=0.96,
                    bbox=(int(x), int(y), int(x + w), int(y + h)),
                )
            )
        return detections


class YoloWhiteBloodCellDetector:
    def __init__(self, model_path: Path) -> None:
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise RuntimeError("ultralytics is required for YOLO inference.") from exc

        self.model_path = Path(model_path)
        if not self.model_path.exists():
            raise FileNotFoundError(f"White blood cell model not found: {self.model_path}")
        self.model = YOLO(str(self.model_path))

    def detect(self, frame: np.ndarray) -> list[WBCDetection]:
        inference_confidence = min(
            float(DEFAULT_CONFIG["preview_confidence"]),
            float(DEFAULT_CONFIG["scan_stop_min_confidence"]),
            float(DEFAULT_CONFIG["min_confidence"]),
        )
        results = self.model.predict(
            source=frame,
            conf=inference_confidence,
            iou=float(DEFAULT_CONFIG["iou"]),
            imgsz=int(DEFAULT_CONFIG["imgsz"]),
            device=None if str(DEFAULT_CONFIG["device"]) == "auto" else str(DEFAULT_CONFIG["device"]),
            verbose=False,
        )
        if not results:
            return []
        result = results[0]
        names = getattr(result, "names", None) or getattr(self.model, "names", {}) or {}
        boxes = getattr(result, "boxes", None)
        if boxes is None or len(boxes) == 0:
            return []
        detections: list[WBCDetection] = []
        xyxy = boxes.xyxy.detach().cpu().numpy()
        confs = boxes.conf.detach().cpu().numpy()
        classes = boxes.cls.detach().cpu().numpy().astype(int)
        for box, conf, class_id in zip(xyxy, confs, classes):
            raw_name = names.get(int(class_id), str(class_id)) if isinstance(names, dict) else str(class_id)
            if _normalize_wbc_name(str(raw_name)) != WHITE_BLOOD_CELL_CLASS:
                continue
            x1, y1, x2, y2 = [int(round(float(value))) for value in np.asarray(box).tolist()]
            detections.append(
                WBCDetection(
                    cell_class=WHITE_BLOOD_CELL_CLASS,
                    confidence=float(conf),
                    bbox=(x1, y1, x2, y2),
                )
            )
        return detections


_ACTIVE_STAGE: SimulationStage | HardwareStage | None = None
_ACTIVE_CAMERA: SimulatedCamera | OpenCVCamera | None = None
_ACTIVE_DETECTOR: SimulatedWBCDetector | YoloWhiteBloodCellDetector | None = None
_ACTIVE_OUTPUT_DIR: Path | None = None
_ACTIVE_METADATA_CSV: Path | None = None
_ACTIVE_DATE_TIME = ""
_CURRENT_COORDINATE = (0, 0)
_CAPTURED_WBC_COUNT = 0
_LAST_PREVIEW_FRAME: np.ndarray | None = None


def generate_vertical_serpentine_path(
    *,
    start_x: int | None = None,
    start_y: int | None = None,
    columns: int | None = None,
    rows: int | None = None,
    step_x: int | None = None,
    step_y: int | None = None,
) -> list[dict[str, int]]:
    start_x = int(DEFAULT_CONFIG["start_x"] if start_x is None else start_x)
    start_y = int(DEFAULT_CONFIG["start_y"] if start_y is None else start_y)
    columns = int(DEFAULT_CONFIG["columns"] if columns is None else columns)
    rows = int(DEFAULT_CONFIG["rows"] if rows is None else rows)
    step_x = int(DEFAULT_CONFIG["step_x"] if step_x is None else step_x)
    step_y = int(DEFAULT_CONFIG["step_y"] if step_y is None else step_y)

    if columns <= 0 or rows <= 0:
        raise ValueError("columns and rows must be positive.")
    if step_x == 0 or step_y == 0:
        raise ValueError("step_x and step_y must not be zero.")

    y_values = [start_y + row * step_y for row in range(rows)]
    path: list[dict[str, int]] = []
    for col in range(columns):
        x = start_x + col * step_x
        column_y_values = y_values if col % 2 == 0 else list(reversed(y_values))
        for y in column_y_values:
            path.append({"x": int(x), "y": int(y)})
    return path


def generate_vertical_serpentine_path_from_bounds(
    start_x: int,
    start_y: int,
    end_x: int,
    end_y: int,
    *,
    step_x: int | None = None,
    step_y: int | None = None,
) -> list[dict[str, int]]:
    def axis_positions(start: int, end: int, step: int) -> list[int]:
        start = int(start)
        end = int(end)
        stride = abs(int(step))
        if stride <= 0:
            raise ValueError("step_x and step_y must be positive.")
        if start == end:
            return [start]
        direction = 1 if end > start else -1
        values = [start]
        current = start
        while current != end:
            remaining = abs(end - current)
            current = end if remaining <= stride else current + direction * stride
            values.append(int(current))
        return values

    step_x = int(DEFAULT_CONFIG["step_x"] if step_x is None else step_x)
    step_y = int(DEFAULT_CONFIG["step_y"] if step_y is None else step_y)
    x_values = axis_positions(start_x, end_x, step_x)
    y_values = axis_positions(start_y, end_y, step_y)
    path: list[dict[str, int]] = []
    for column_index, x in enumerate(x_values):
        column_y_values = y_values if column_index % 2 == 0 else list(reversed(y_values))
        path.extend({"x": int(x), "y": int(y)} for y in column_y_values)
    return path


def move_to_coordinate(x: int, y: int) -> None:
    global _CURRENT_COORDINATE
    stage = _get_stage()
    stage.move_to(int(x), int(y))
    _CURRENT_COORDINATE = (int(x), int(y))
    if _ACTIVE_CAMERA is not None and hasattr(_ACTIVE_CAMERA, "set_coordinate"):
        _ACTIVE_CAMERA.set_coordinate(int(x), int(y))


def start_live_camera() -> SimulatedCamera | OpenCVCamera:
    global _ACTIVE_CAMERA
    if _ACTIVE_CAMERA is not None:
        return _ACTIVE_CAMERA
    if bool(DEFAULT_CONFIG["simulation_mode"]):
        _ACTIVE_CAMERA = SimulatedCamera()
    else:
        video_source = str(DEFAULT_CONFIG.get("video_source", "")).strip()
        source: int | str = video_source if video_source else int(DEFAULT_CONFIG["camera_index"])
        _ACTIVE_CAMERA = OpenCVCamera(source)
    return _ACTIVE_CAMERA


def detect_white_blood_cells(frame: np.ndarray) -> list[WBCDetection]:
    detector = _get_detector()
    return detector.detect(frame)


def is_complete_white_blood_cell_detection(
    detection: WBCDetection,
    frame_shape: tuple[int, ...],
) -> bool:
    return white_blood_cell_detection_status(detection, frame_shape) == "saved"


def white_blood_cell_detection_status(detection: WBCDetection, frame_shape: tuple[int, ...]) -> str:
    return _white_blood_cell_detection_status(detection, frame_shape)


def filter_complete_white_blood_cells(
    detections: Iterable[WBCDetection],
    frame_shape: tuple[int, ...],
) -> list[WBCDetection]:
    return [det for det in detections if is_complete_white_blood_cell_detection(det, frame_shape)]


def is_scan_stop_white_blood_cell_detection(
    detection: WBCDetection,
    frame_shape: tuple[int, ...],
) -> bool:
    if detection.cell_class != WHITE_BLOOD_CELL_CLASS:
        return False
    if float(detection.confidence) < float(DEFAULT_CONFIG["scan_stop_min_confidence"]):
        return False

    height, width = int(frame_shape[0]), int(frame_shape[1])
    x1, y1, x2, y2 = detection.bbox
    if x2 <= x1 or y2 <= y1:
        return False

    margin = int(DEFAULT_CONFIG["border_margin"])
    center_x = (x1 + x2) / 2.0
    center_y = (y1 + y2) / 2.0
    return margin < center_x < width - margin and margin < center_y < height - margin


def filter_scan_stop_white_blood_cells(
    detections: Iterable[WBCDetection],
    frame_shape: tuple[int, ...],
) -> list[WBCDetection]:
    return [det for det in detections if is_scan_stop_white_blood_cell_detection(det, frame_shape)]


def wbc_detection_center(detection: WBCDetection) -> tuple[float, float]:
    x1, y1, x2, y2 = detection.bbox
    return (float(x1 + x2) / 2.0, float(y1 + y2) / 2.0)


def wbc_center_offset_px(
    detection: WBCDetection,
    frame_shape: tuple[int, ...],
) -> tuple[float, float]:
    height, width = int(frame_shape[0]), int(frame_shape[1])
    center_x, center_y = wbc_detection_center(detection)
    return (center_x - (width / 2.0), center_y - (height / 2.0))


def is_wbc_centered(
    detection: WBCDetection,
    frame_shape: tuple[int, ...],
    tolerance_px: float | None = None,
) -> bool:
    tolerance = float(DEFAULT_CONFIG["center_tolerance_px"] if tolerance_px is None else tolerance_px)
    offset_x, offset_y = wbc_center_offset_px(detection, frame_shape)
    return abs(offset_x) <= tolerance and abs(offset_y) <= tolerance


def select_wbc_centering_target(
    detections: Iterable[WBCDetection],
    frame_shape: tuple[int, ...],
    *,
    min_confidence: float | None = None,
) -> WBCDetection | None:
    threshold = float(DEFAULT_CONFIG["center_min_confidence"] if min_confidence is None else min_confidence)
    min_area = float(DEFAULT_CONFIG["center_min_bbox_area"])
    candidates = [
        det
        for det in detections
        if is_scan_stop_white_blood_cell_detection(det, frame_shape)
        and float(det.confidence) >= threshold
        and float(max(0, det.x2 - det.x1) * max(0, det.y2 - det.y1)) >= min_area
    ]
    if not candidates:
        return None

    frame_h, frame_w = int(frame_shape[0]), int(frame_shape[1])
    diagonal = max(1.0, float((frame_w * frame_w + frame_h * frame_h) ** 0.5))

    def score(det: WBCDetection) -> tuple[float, float]:
        offset_x, offset_y = wbc_center_offset_px(det, frame_shape)
        distance_score = -float((offset_x * offset_x + offset_y * offset_y) ** 0.5) / diagonal
        return (float(det.confidence), distance_score)

    return max(candidates, key=score)


def _clamp_step_delta(steps: int, max_abs_steps: int) -> int:
    limit = max(1, int(max_abs_steps))
    return max(-limit, min(limit, int(steps)))


def _calculate_axis_centering_steps(
    offset_px: float,
    image_px_per_step: float,
    *,
    tolerance_px: float,
    max_step_per_axis: int,
    min_improvement_px: float,
) -> int:
    if abs(offset_px) <= tolerance_px or abs(image_px_per_step) < 1e-6:
        return 0

    raw_steps = int(round(-float(offset_px) / float(image_px_per_step)))
    steps = _clamp_step_delta(raw_steps, max_step_per_axis)
    if steps == 0:
        return 0

    predicted_offset = float(offset_px) + (float(steps) * float(image_px_per_step))
    improvement = abs(float(offset_px)) - abs(predicted_offset)
    if improvement < max(0.0, float(min_improvement_px)):
        return 0
    return int(steps)


def calculate_wbc_centering_steps(
    detection: WBCDetection,
    frame_shape: tuple[int, ...],
    *,
    x_image_px_per_step: float | None = None,
    y_image_px_per_step: float | None = None,
    tolerance_px: float | None = None,
    max_step_per_axis: int | None = None,
    min_improvement_px: float | None = None,
) -> tuple[int, int]:
    if is_wbc_centered(detection, frame_shape, tolerance_px=tolerance_px):
        return (0, 0)

    x_px_per_step = float(
        DEFAULT_CONFIG["center_x_image_px_per_step"] if x_image_px_per_step is None else x_image_px_per_step
    )
    y_px_per_step = float(
        DEFAULT_CONFIG["center_y_image_px_per_step"] if y_image_px_per_step is None else y_image_px_per_step
    )
    if abs(x_px_per_step) < 1e-6 or abs(y_px_per_step) < 1e-6:
        return (0, 0)

    offset_x, offset_y = wbc_center_offset_px(detection, frame_shape)
    max_steps = int(DEFAULT_CONFIG["center_max_step_per_axis"] if max_step_per_axis is None else max_step_per_axis)
    tolerance = float(DEFAULT_CONFIG["center_tolerance_px"] if tolerance_px is None else tolerance_px)
    min_improvement = float(
        DEFAULT_CONFIG["center_min_step_improvement_px"] if min_improvement_px is None else min_improvement_px
    )
    return (
        _calculate_axis_centering_steps(
            offset_x,
            x_px_per_step,
            tolerance_px=tolerance,
            max_step_per_axis=max_steps,
            min_improvement_px=min_improvement,
        ),
        _calculate_axis_centering_steps(
            offset_y,
            y_px_per_step,
            tolerance_px=tolerance,
            max_step_per_axis=max_steps,
            min_improvement_px=min_improvement,
        ),
    )


def read_centering_confirmation_frame(
    camera: SimulatedCamera | OpenCVCamera,
    current_x: int,
    current_y: int,
) -> tuple[np.ndarray | None, list[WBCDetection]]:
    attempts = max(1, int(DEFAULT_CONFIG["center_detection_frame_attempts"]))
    interval_seconds = max(0.0, float(DEFAULT_CONFIG["center_detection_frame_interval_seconds"]))
    last_frame: np.ndarray | None = None
    last_detections: list[WBCDetection] = []
    for attempt in range(attempts):
        ok, frame = camera.read()
        if not ok or frame is None:
            if interval_seconds and attempt < attempts - 1:
                time.sleep(interval_seconds)
            continue
        detections = detect_white_blood_cells(frame)
        _show_detection_preview(frame, detections, current_x, current_y)
        last_frame = frame
        last_detections = detections
        if select_wbc_centering_target(detections, frame.shape) is not None:
            break
        if interval_seconds and attempt < attempts - 1:
            time.sleep(interval_seconds)
    return last_frame, last_detections


def center_white_blood_cell_for_high_magnification(
    camera: SimulatedCamera | OpenCVCamera,
    current_x: int,
    current_y: int,
    frame: np.ndarray,
    detections: list[WBCDetection],
) -> tuple[int, int, np.ndarray, list[WBCDetection], bool]:
    if not bool(DEFAULT_CONFIG["center_after_detection"]):
        return current_x, current_y, frame, detections, False

    max_iterations = max(0, int(DEFAULT_CONFIG["center_max_iterations"]))
    if max_iterations <= 0:
        return current_x, current_y, frame, detections, False

    centered = False
    latest_frame = frame
    latest_detections = list(detections)
    x_pos = int(current_x)
    y_pos = int(current_y)

    for iteration in range(max_iterations):
        target = select_wbc_centering_target(latest_detections, latest_frame.shape)
        if target is None:
            print("WBC centering skipped: no stable high-confidence centering target.", flush=True)
            break
        if is_wbc_centered(target, latest_frame.shape):
            centered = True
            print(f"WBC centered at x={x_pos}, y={y_pos}.", flush=True)
            break

        center_x, center_y = wbc_detection_center(target)
        offset_x, offset_y = wbc_center_offset_px(target, latest_frame.shape)
        dx_steps, dy_steps = calculate_wbc_centering_steps(target, latest_frame.shape)
        if dx_steps == 0 and dy_steps == 0:
            print("WBC centering skipped: calibrated movement is below one motor step.", flush=True)
            break

        x_pos += int(dx_steps)
        y_pos += int(dy_steps)
        print(
            f"WBC centering move {iteration + 1}/{max_iterations}: "
            f"bbox_center=({center_x:.1f},{center_y:.1f}), "
            f"image_center=({latest_frame.shape[1] / 2.0:.1f},{latest_frame.shape[0] / 2.0:.1f}), "
            f"offset=({offset_x:.1f},{offset_y:.1f}), "
            f"dx={dx_steps}, dy={dy_steps}, target=({x_pos},{y_pos})",
            flush=True,
        )
        move_to_coordinate(x_pos, y_pos)
        settle_seconds = max(0.0, float(DEFAULT_CONFIG["center_settle_seconds"]))
        if settle_seconds:
            time.sleep(settle_seconds)

        confirmation_frame, confirmation_detections = read_centering_confirmation_frame(camera, x_pos, y_pos)
        if confirmation_frame is None:
            print("WBC centering stopped: camera frame unavailable after movement.", flush=True)
            break
        latest_frame = confirmation_frame
        latest_detections = confirmation_detections

    final_target = select_wbc_centering_target(latest_detections, latest_frame.shape)
    if final_target is not None and is_wbc_centered(final_target, latest_frame.shape):
        centered = True
    return x_pos, y_pos, latest_frame, latest_detections, centered


def wait_for_manual_capture_confirmation() -> None:
    print("Detect White Blood Cell.", flush=True)
    if bool(DEFAULT_CONFIG["center_after_detection"]):
        print("WBC is centered for high magnification. Switch to 1000x, adjust focus, then press Enter to capture.", flush=True)
        _show_preview_message("Centered. Switch to 1000x, focus, then press Enter.", 1)
    else:
        print("Platform paused at detected WBC. Adjust focus, then press Enter to capture.", flush=True)
        _show_preview_message("WBC detected. Adjust focus, then press Enter.", 1)
    if bool(DEFAULT_CONFIG["simulation_mode"]):
        return
    input()


def wait_for_resume_confirmation() -> None:
    print("Manual capture complete. Press Enter to continue scanning.", flush=True)
    _show_preview_message("Press Enter to continue scanning.", 1)
    if bool(DEFAULT_CONFIG["simulation_mode"]):
        return
    input()


def capture_high_resolution_image() -> np.ndarray:
    camera = start_live_camera()
    return camera.capture_high_resolution_image()


def crop_white_blood_cell_by_bbox(
    image: np.ndarray,
    bbox: tuple[int, int, int, int],
    all_bboxes: Iterable[tuple[int, int, int, int]] | None = None,
    padding: int | None = None,
) -> np.ndarray | None:
    crop_rect, status = _safe_crop_rect(image.shape, bbox, all_bboxes or [], padding)
    if status != "saved" or crop_rect is None:
        return None
    x1, y1, x2, y2 = crop_rect
    return image[y1:y2, x1:x2].copy()


def save_original_frame(image: np.ndarray, current_x: int, current_y: int, output_dir: Path) -> Path:
    original_dir = Path(output_dir) / "original_frames"
    original_dir.mkdir(parents=True, exist_ok=True)
    path = original_dir / f"x{int(current_x)}_y{int(current_y)}_original.png"
    cv2.imwrite(str(path), image)
    return path


def save_white_blood_cell_crop(
    crop_img: np.ndarray,
    current_x: int,
    current_y: int,
    index: int,
    output_dir: Path,
) -> Path:
    crop_dir = Path(output_dir) / "cropped_cells"
    crop_dir.mkdir(parents=True, exist_ok=True)
    path = crop_dir / f"x{int(current_x)}_y{int(current_y)}_{int(index):03d}_{WHITE_BLOOD_CELL_CLASS}.png"
    cv2.imwrite(str(path), crop_img)
    return path


def update_captured_wbc_count(count: int) -> int:
    global _CAPTURED_WBC_COUNT
    _CAPTURED_WBC_COUNT += max(0, int(count))
    print(f"Captured White Blood Cells: {_CAPTURED_WBC_COUNT}", flush=True)
    return _CAPTURED_WBC_COUNT


def write_metadata_csv(record: dict[str, Any]) -> None:
    csv_path = _ACTIVE_METADATA_CSV
    if csv_path is None:
        raise RuntimeError("metadata.csv is not initialized.")
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not csv_path.exists()
    with csv_path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=METADATA_FIELDS)
        if write_header:
            writer.writeheader()
        writer.writerow({field: record.get(field, "") for field in METADATA_FIELDS})


def read_preview_until_scan_stop(
    camera: SimulatedCamera | OpenCVCamera,
    current_x: int,
    current_y: int,
) -> tuple[np.ndarray | None, list[WBCDetection], list[WBCDetection]]:
    settle_seconds = max(0.0, float(DEFAULT_CONFIG["detection_settle_seconds"]))
    if settle_seconds:
        time.sleep(settle_seconds)

    attempts = max(1, int(DEFAULT_CONFIG["detection_frame_attempts"]))
    interval_seconds = max(0.0, float(DEFAULT_CONFIG["detection_frame_interval_seconds"]))
    last_frame: np.ndarray | None = None
    last_detections: list[WBCDetection] = []
    last_stop_detections: list[WBCDetection] = []

    for attempt in range(attempts):
        ok, frame = camera.read()
        if not ok or frame is None:
            print("Camera frame unavailable during detection wait.", flush=True)
            if interval_seconds and attempt < attempts - 1:
                time.sleep(interval_seconds)
            continue

        detections = detect_white_blood_cells(frame)
        stop_detections = filter_scan_stop_white_blood_cells(detections, frame.shape)
        _show_detection_preview(frame, detections, current_x, current_y)
        last_frame = frame
        last_detections = detections
        last_stop_detections = stop_detections

        if stop_detections:
            best = max(stop_detections, key=lambda det: det.confidence)
            print(
                f"WBC stop candidate at x={current_x}, y={current_y}, "
                f"confidence={best.confidence:.3f}, bbox={best.bbox}",
                flush=True,
            )
            return frame, detections, stop_detections

        if _preview_quit_requested():
            return frame, detections, stop_detections
        if interval_seconds and attempt < attempts - 1:
            time.sleep(interval_seconds)

    return last_frame, last_detections, last_stop_detections


def run_serpentine_white_blood_cell_capture() -> Path:
    global _ACTIVE_OUTPUT_DIR, _ACTIVE_METADATA_CSV, _ACTIVE_DATE_TIME, _CAPTURED_WBC_COUNT

    _CAPTURED_WBC_COUNT = 0
    _ACTIVE_DATE_TIME = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    experiment_name = str(DEFAULT_CONFIG["experiment_name"])
    output_dir = (
        Path(DEFAULT_CONFIG["output_root"])
        / WHITE_BLOOD_CELL_CLASS
        / experiment_name
        / _ACTIVE_DATE_TIME
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "cropped_cells").mkdir(parents=True, exist_ok=True)
    (output_dir / "original_frames").mkdir(parents=True, exist_ok=True)
    _ACTIVE_OUTPUT_DIR = output_dir
    _ACTIVE_METADATA_CSV = output_dir / "metadata.csv"

    path = generate_vertical_serpentine_path()
    camera = start_live_camera()
    captured_coordinates: set[tuple[int, int]] = set()
    print(f"Output directory: {output_dir.resolve()}", flush=True)
    print(f"Captured White Blood Cells: {_CAPTURED_WBC_COUNT}", flush=True)

    try:
        for coord in path:
            current_x = int(coord["x"])
            current_y = int(coord["y"])
            move_to_coordinate(current_x, current_y)

            frame, preview_detections, scan_stop_preview = read_preview_until_scan_stop(
                camera,
                current_x,
                current_y,
            )
            if frame is None:
                print("Camera frame unavailable; skipping coordinate.", flush=True)
                continue

            if not scan_stop_preview or (current_x, current_y) in captured_coordinates:
                if scan_stop_preview and (current_x, current_y) in captured_coordinates:
                    print(f"WBC detected again at already captured coordinate x={current_x}, y={current_y}; skipping.", flush=True)
                if _preview_quit_requested():
                    break
                continue

            scan_coordinate = (current_x, current_y)
            _get_stage().stop()
            if bool(DEFAULT_CONFIG["center_after_detection"]):
                current_x, current_y, frame, preview_detections, centered = center_white_blood_cell_for_high_magnification(
                    camera,
                    current_x,
                    current_y,
                    frame,
                    preview_detections,
                )
                _get_stage().stop()
                if centered:
                    print("WBC centered. Ready for 1000x detail capture.", flush=True)
                else:
                    print("WBC centering did not fully converge; platform is paused for manual adjustment.", flush=True)
            wait_for_manual_capture_confirmation()

            high_res = capture_high_resolution_image()
            original_path = save_original_frame(high_res, current_x, current_y, output_dir)
            high_res_detections = detect_white_blood_cells(high_res)
            all_bboxes = [det.bbox for det in high_res_detections]
            cell_index_at_coordinate = 0
            saved_at_coordinate = 0

            for det in high_res_detections:
                cell_index_at_coordinate += 1
                status = _white_blood_cell_detection_status(det, high_res.shape)
                crop_path: Path | None = None
                if status == "saved":
                    crop_img = crop_white_blood_cell_by_bbox(
                        high_res,
                        det.bbox,
                        all_bboxes=all_bboxes,
                        padding=int(DEFAULT_CONFIG["crop_padding"]),
                    )
                    if crop_img is None:
                        status = "skipped_ambiguous_crop"
                    else:
                        saved_at_coordinate += 1
                        crop_path = save_white_blood_cell_crop(
                            crop_img,
                            current_x,
                            current_y,
                            saved_at_coordinate,
                            output_dir,
                        )
                        update_captured_wbc_count(1)

                write_metadata_csv(
                    {
                        "experiment_name": experiment_name,
                        "date_time": _ACTIVE_DATE_TIME,
                        "current_x": current_x,
                        "current_y": current_y,
                        "cell_index_at_coordinate": cell_index_at_coordinate,
                        "cell_class": det.cell_class,
                        "confidence": f"{det.confidence:.6f}",
                        "bbox_x1": det.x1,
                        "bbox_y1": det.y1,
                        "bbox_x2": det.x2,
                        "bbox_y2": det.y2,
                        "original_image_path": str(original_path.resolve()),
                        "cropped_image_path": "" if crop_path is None else str(crop_path.resolve()),
                        "captured_wbc_count": _CAPTURED_WBC_COUNT,
                        "status": status,
                    }
                )

            if not high_res_detections:
                write_metadata_csv(
                    {
                        "experiment_name": experiment_name,
                        "date_time": _ACTIVE_DATE_TIME,
                        "current_x": current_x,
                        "current_y": current_y,
                        "cell_index_at_coordinate": 0,
                        "cell_class": WHITE_BLOOD_CELL_CLASS,
                        "original_image_path": str(original_path.resolve()),
                        "captured_wbc_count": _CAPTURED_WBC_COUNT,
                        "status": "skipped_not_complete",
                    }
                )

            captured_coordinates.add(scan_coordinate)
            wait_for_resume_confirmation()
            if _preview_quit_requested():
                break
    finally:
        _write_summary(output_dir, len(path))
        _release_runtime()

    print(f"Scan complete. Captured White Blood Cells: {_CAPTURED_WBC_COUNT}", flush=True)
    return output_dir


def _get_stage() -> SimulationStage | HardwareStage:
    global _ACTIVE_STAGE
    if _ACTIVE_STAGE is None:
        _ACTIVE_STAGE = SimulationStage() if bool(DEFAULT_CONFIG["simulation_mode"]) else HardwareStage()
    return _ACTIVE_STAGE


def _get_detector() -> SimulatedWBCDetector | YoloWhiteBloodCellDetector:
    global _ACTIVE_DETECTOR
    if _ACTIVE_DETECTOR is not None:
        return _ACTIVE_DETECTOR
    if bool(DEFAULT_CONFIG["simulation_mode"]):
        _ACTIVE_DETECTOR = SimulatedWBCDetector()
        return _ACTIVE_DETECTOR
    model_path_text = str(DEFAULT_CONFIG.get("model_path", "")).strip()
    model_path = Path(model_path_text) if model_path_text else None
    if model_path is not None and model_path.is_file():
        _ACTIVE_DETECTOR = YoloWhiteBloodCellDetector(model_path)
    else:
        raise RuntimeError(
            "No white blood cell model configured. Set DEFAULT_CONFIG['model_path'] "
            "to a YOLO model that detects White_Blood_Cell."
        )
    return _ACTIVE_DETECTOR


def _normalize_wbc_name(label: str) -> str | None:
    compact = "".join(ch for ch in str(label).lower() if ch.isalnum())
    if compact in {
        "wbc",
        "whitebloodcell",
        "whitebloodcells",
        "whitebloodcellcomplete",
        "leukocyte",
        "leukocytes",
    }:
        return WHITE_BLOOD_CELL_CLASS
    return None


def _white_blood_cell_detection_status(detection: WBCDetection, frame_shape: tuple[int, ...]) -> str:
    if detection.cell_class != WHITE_BLOOD_CELL_CLASS:
        return "skipped_not_complete"
    if float(detection.confidence) < float(DEFAULT_CONFIG["min_confidence"]):
        return "skipped_low_confidence"

    height, width = int(frame_shape[0]), int(frame_shape[1])
    x1, y1, x2, y2 = detection.bbox
    margin = int(DEFAULT_CONFIG["border_margin"])
    if x1 <= margin or y1 <= margin or x2 >= width - margin or y2 >= height - margin:
        return "skipped_touching_border"
    if x2 <= x1 or y2 <= y1:
        return "skipped_not_complete"
    area = float((x2 - x1) * (y2 - y1))
    if area < float(DEFAULT_CONFIG["min_bbox_area"]):
        return "skipped_not_complete"
    return "saved"


def _safe_crop_rect(
    frame_shape: tuple[int, ...],
    bbox: tuple[int, int, int, int],
    all_bboxes: Iterable[tuple[int, int, int, int]],
    padding: int | None = None,
) -> tuple[tuple[int, int, int, int] | None, str]:
    padding = int(DEFAULT_CONFIG["crop_padding"] if padding is None else padding)
    rect = _clip_rect_with_padding(frame_shape, bbox, padding)
    other_bboxes = [other for other in all_bboxes if tuple(other) != tuple(bbox)]
    if not _rect_intersects_any_bbox(rect, other_bboxes):
        return rect, "saved"
    rect_no_padding = _clip_rect_with_padding(frame_shape, bbox, 0)
    if not _rect_intersects_any_bbox(rect_no_padding, other_bboxes):
        return rect_no_padding, "saved"
    return None, "skipped_ambiguous_crop"


def _clip_rect_with_padding(
    frame_shape: tuple[int, ...],
    bbox: tuple[int, int, int, int],
    padding: int,
) -> tuple[int, int, int, int]:
    height, width = int(frame_shape[0]), int(frame_shape[1])
    x1, y1, x2, y2 = bbox
    return (
        max(0, int(x1) - padding),
        max(0, int(y1) - padding),
        min(width, int(x2) + padding),
        min(height, int(y2) + padding),
    )


def _rect_intersects_any_bbox(
    rect: tuple[int, int, int, int],
    boxes: Iterable[tuple[int, int, int, int]],
) -> bool:
    rx1, ry1, rx2, ry2 = rect
    for bx1, by1, bx2, by2 in boxes:
        ix1 = max(rx1, int(bx1))
        iy1 = max(ry1, int(by1))
        ix2 = min(rx2, int(bx2))
        iy2 = min(ry2, int(by2))
        if ix2 > ix1 and iy2 > iy1:
            return True
    return False


def _show_detection_preview(
    frame: np.ndarray,
    detections: Iterable[WBCDetection],
    current_x: int,
    current_y: int,
) -> None:
    global _LAST_PREVIEW_FRAME
    display = frame.copy()
    for det in detections:
        if is_scan_stop_white_blood_cell_detection(det, frame.shape):
            color = (0, 255, 0)
            state = "STOP"
        else:
            color = (0, 180, 255)
            state = "WBC"
        cv2.rectangle(display, (det.x1, det.y1), (det.x2, det.y2), color, 2)
        cv2.putText(
            display,
            f"{state} {det.confidence:.2f}",
            (det.x1, max(24, det.y1 - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            color,
            2,
            cv2.LINE_AA,
        )
    cv2.putText(
        display,
        f"x={current_x} y={current_y}",
        (16, 32),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        display,
        f"Captured White Blood Cells: {_CAPTURED_WBC_COUNT}",
        (16, 66),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    _LAST_PREVIEW_FRAME = display
    if bool(DEFAULT_CONFIG["show_preview"]):
        cv2.imshow(str(DEFAULT_CONFIG["preview_window_name"]), display)
        cv2.waitKey(1)


def _show_preview_message(message: str, seconds: int) -> None:
    if not bool(DEFAULT_CONFIG["show_preview"]) or _LAST_PREVIEW_FRAME is None:
        return
    display = _LAST_PREVIEW_FRAME.copy()
    cv2.putText(
        display,
        message,
        (24, display.shape[0] - 40),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.9,
        (0, 255, 255),
        2,
        cv2.LINE_AA,
    )
    cv2.imshow(str(DEFAULT_CONFIG["preview_window_name"]), display)
    cv2.waitKey(1)


def _preview_quit_requested() -> bool:
    if not bool(DEFAULT_CONFIG["show_preview"]):
        return False
    key = cv2.waitKey(1) & 0xFF
    return key in {ord("q"), 27}


def _write_summary(output_dir: Path, path_length: int) -> None:
    summary = {
        "experiment_name": str(DEFAULT_CONFIG["experiment_name"]),
        "date_time": _ACTIVE_DATE_TIME,
        "cell_class": WHITE_BLOOD_CELL_CLASS,
        "path_length": int(path_length),
        "captured_wbc_count": int(_CAPTURED_WBC_COUNT),
        "metadata_csv": str((_ACTIVE_METADATA_CSV or output_dir / "metadata.csv").resolve()),
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


def _release_runtime() -> None:
    global _ACTIVE_CAMERA, _ACTIVE_STAGE, _ACTIVE_DETECTOR
    if _ACTIVE_CAMERA is not None:
        try:
            _ACTIVE_CAMERA.release()
        except Exception:
            pass
        _ACTIVE_CAMERA = None
    if _ACTIVE_STAGE is not None:
        try:
            _ACTIVE_STAGE.close()
        except Exception:
            pass
        _ACTIVE_STAGE = None
    _ACTIVE_DETECTOR = None
    if bool(DEFAULT_CONFIG["show_preview"]):
        try:
            cv2.destroyWindow(str(DEFAULT_CONFIG["preview_window_name"]))
        except Exception:
            pass


def main() -> int:
    output_dir = run_serpentine_white_blood_cell_capture()
    print(f"Saved output: {output_dir.resolve()}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

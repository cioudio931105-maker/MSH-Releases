from __future__ import annotations

import argparse
import sys
import math
import shutil
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence

import cv2
import numpy as np
from msh_motion_policy import FIXED_STEP_DELAY_MS

Point = tuple[float, float]


class Camera(Protocol):
    def open(self) -> None:
        ...

    def read(self) -> np.ndarray:
        ...

    def close(self) -> None:
        ...


class Stage(Protocol):
    @property
    def position(self) -> Point:
        ...

    def move_to(self, x: float, y: float) -> None:
        ...


@dataclass(slots=True)
class RecordingStatus:
    x: float
    y: float
    row_index: int
    col_index: int
    segment_index: int
    segment_fraction: float
    distance_done: float
    total_distance: float
    progress: float
    elapsed_s: float
    eta_s: float
    frame_index: int
    paused: bool
    stopped: bool


class SimulatedStage:
    def __init__(self, initial_position: Point = (0.0, 0.0)) -> None:
        self._position = (float(initial_position[0]), float(initial_position[1]))
        self._lock = threading.Lock()

    @property
    def position(self) -> Point:
        with self._lock:
            return self._position

    def move_to(self, x: float, y: float) -> None:
        with self._lock:
            self._position = (float(x), float(y))


class SimulatedCamera:
    def __init__(
        self,
        stage: Stage,
        frame_size: tuple[int, int] = (960, 540),
        path: Sequence[Point] | None = None,
        seed: int = 7,
    ) -> None:
        self.stage = stage
        self.frame_size = (int(frame_size[0]), int(frame_size[1]))
        self.path = list(path or [(0.0, 0.0)])
        self.seed = int(seed)
        self._canvas: np.ndarray | None = None
        self._margin = 160

    def open(self) -> None:
        if self._canvas is None:
            self._canvas = self._make_canvas()

    def close(self) -> None:
        self._canvas = None

    def read(self) -> np.ndarray:
        if self._canvas is None:
            self.open()
        assert self._canvas is not None

        width, height = self.frame_size
        x, y = self.stage.position
        left = int(round(x)) + self._margin
        top = int(round(y)) + self._margin
        right = left + width
        bottom = top + height

        if left < 0 or top < 0 or right > self._canvas.shape[1] or bottom > self._canvas.shape[0]:
            padded = cv2.copyMakeBorder(
                self._canvas,
                height,
                height,
                width,
                width,
                cv2.BORDER_REFLECT_101,
            )
            left += width
            right += width
            top += height
            bottom += height
            return np.ascontiguousarray(padded[top:bottom, left:right])

        return np.ascontiguousarray(self._canvas[top:bottom, left:right].copy())

    def _make_canvas(self) -> np.ndarray:
        width, height = self.frame_size
        max_x = max((point[0] for point in self.path), default=0.0)
        max_y = max((point[1] for point in self.path), default=0.0)
        canvas_w = max(width + 2 * self._margin, int(math.ceil(max_x)) + width + 2 * self._margin)
        canvas_h = max(height + 2 * self._margin, int(math.ceil(max_y)) + height + 2 * self._margin)

        rng = np.random.default_rng(self.seed)
        base = np.full((canvas_h, canvas_w, 3), (226, 220, 236), dtype=np.uint8)
        noise = rng.normal(0.0, 8.0, size=base.shape).astype(np.int16)
        canvas = np.clip(base.astype(np.int16) + noise, 0, 255).astype(np.uint8)
        canvas = cv2.GaussianBlur(canvas, (0, 0), 1.2)

        cell_count = max(900, int(canvas_w * canvas_h / 2800))
        for _ in range(cell_count):
            cx = int(rng.integers(0, canvas_w))
            cy = int(rng.integers(0, canvas_h))
            radius = int(rng.integers(5, 19))
            color = (
                int(rng.integers(130, 205)),
                int(rng.integers(80, 145)),
                int(rng.integers(150, 225)),
            )
            cv2.circle(canvas, (cx, cy), radius, color, -1, lineType=cv2.LINE_AA)
            cv2.circle(canvas, (cx, cy), max(2, radius // 3), (90, 45, 125), 1, lineType=cv2.LINE_AA)

        for x in range(0, canvas_w, 200):
            cv2.line(canvas, (x, 0), (x, canvas_h - 1), (210, 205, 218), 1, cv2.LINE_AA)
        for y in range(0, canvas_h, 160):
            cv2.line(canvas, (0, y), (canvas_w - 1, y), (210, 205, 218), 1, cv2.LINE_AA)

        return canvas


class OpenCVCamera:
    def __init__(
        self,
        camera_index: int = 0,
        frame_size: tuple[int, int] | None = None,
    ) -> None:
        self.camera_index = int(camera_index)
        self.frame_size = frame_size
        self._capture: cv2.VideoCapture | None = None

    def open(self) -> None:
        self._capture = cv2.VideoCapture(self.camera_index)
        if not self._capture.isOpened():
            raise RuntimeError(f"Unable to open camera index {self.camera_index}.")
        if self.frame_size is not None:
            width, height = self.frame_size
            self._capture.set(cv2.CAP_PROP_FRAME_WIDTH, int(width))
            self._capture.set(cv2.CAP_PROP_FRAME_HEIGHT, int(height))

    def read(self) -> np.ndarray:
        if self._capture is None:
            self.open()
        assert self._capture is not None
        ok, frame = self._capture.read()
        if not ok or frame is None:
            raise RuntimeError("Camera frame read failed.")
        return np.ascontiguousarray(frame)

    def close(self) -> None:
        if self._capture is not None:
            self._capture.release()
        self._capture = None


class BaslerRecorderCamera:
    def __init__(
        self,
        camera_serial: str | None = None,
        camera_index: int = 0,
        width: int | None = None,
        height: int | None = None,
        exposure_us: float | None = None,
        gain: float | None = None,
        fps: float | None = None,
        pixel_format: str | None = None,
    ) -> None:
        self.camera_serial = camera_serial
        self.camera_index = int(camera_index)
        self.width = width
        self.height = height
        self.exposure_us = exposure_us
        self.gain = gain
        self.fps = fps
        self.pixel_format = pixel_format
        self._camera = None

    def open(self) -> None:
        from .camera import BaslerCamera, BaslerCameraConfig

        config = BaslerCameraConfig(
            camera_serial=self.camera_serial,
            camera_index=self.camera_index,
            width=self.width,
            height=self.height,
            exposure_us=self.exposure_us,
            gain=self.gain,
            fps=self.fps,
            pixel_format=self.pixel_format,
        )
        self._camera = BaslerCamera(config).open()

    def read(self) -> np.ndarray:
        if self._camera is None:
            self.open()
        assert self._camera is not None
        return self._camera.read()

    def close(self) -> None:
        if self._camera is not None:
            self._camera.close()
        self._camera = None


class SerialXYStage:
    def __init__(
        self,
        x_port: str | None = None,
        y_port: str | None = None,
        xy_port: str | None = None,
        baud: int = 115200,
        timeout_s: float = 2.0,
        boot_wait_s: float = 2.0,
        motor_speed_ms: int = FIXED_STEP_DELAY_MS,
        hold: bool = True,
        x_sign: int = 1,
        y_sign: int = 1,
        apply_backlash: bool = False,
        x_stepper=None,
        y_stepper=None,
        xy_stepper=None,
    ) -> None:
        self.x_port = x_port
        self.y_port = y_port
        self.xy_port = xy_port
        self.baud = int(baud)
        self.timeout_s = float(timeout_s)
        self.boot_wait_s = float(boot_wait_s)
        self.motor_speed_ms = int(motor_speed_ms)
        if self.motor_speed_ms != FIXED_STEP_DELAY_MS:
            raise ValueError("Hardware motion is fixed at 0.02 RPM.")
        self.hold = bool(hold)
        self.x_sign = 1 if int(x_sign) >= 0 else -1
        self.y_sign = 1 if int(y_sign) >= 0 else -1
        self.apply_backlash = False
        self._x_stepper = x_stepper
        self._y_stepper = y_stepper
        self._xy_stepper = xy_stepper
        self._position = (0.0, 0.0)
        self._lock = threading.Lock()
        self._connected = False

    @property
    def position(self) -> Point:
        with self._lock:
            return self._position

    def connect(self) -> None:
        if self._connected:
            return
        if self._xy_stepper is None and self._x_stepper is None and self._y_stepper is None:
            arduino_stepper = _load_arduino_stepper_class()
            if self.xy_port:
                self._xy_stepper = arduino_stepper(
                    port=self.xy_port,
                    baud=self.baud,
                    timeout_s=self.timeout_s,
                    boot_wait_s=self.boot_wait_s,
                )
            else:
                if not self.x_port or not self.y_port:
                    raise ValueError("Hardware stage requires --x-port and --y-port, or --xy-port for a dual-axis controller.")
                self._x_stepper = arduino_stepper(
                    port=self.x_port,
                    baud=self.baud,
                    timeout_s=self.timeout_s,
                    boot_wait_s=self.boot_wait_s,
                )
                self._y_stepper = arduino_stepper(
                    port=self.y_port,
                    baud=self.baud,
                    timeout_s=self.timeout_s,
                    boot_wait_s=self.boot_wait_s,
                )

        for stepper in self._unique_steppers():
            stepper.connect()
            if stepper is self._xy_stepper:
                stepper.set_speed_ms(self.motor_speed_ms, motor_id=0)
                stepper.set_speed_ms(self.motor_speed_ms, motor_id=1)
            else:
                stepper.set_speed_ms(self.motor_speed_ms)
            try:
                stepper.set_hold(self.hold)
            except Exception:
                pass

        self._connected = True

    def close(self) -> None:
        for stepper in self._unique_steppers():
            try:
                stepper.close()
            except Exception:
                pass
        self._connected = False

    def move_to(self, x: float, y: float) -> None:
        self.connect()
        with self._lock:
            current_x, current_y = self._position
            target_x = float(round(float(x)))
            target_y = float(round(float(y)))
            dx = int(round(target_x - current_x))
            dy = int(round(target_y - current_y))

        if dx != 0:
            self._move_axis("x", dx * self.x_sign)
        if dy != 0:
            self._move_axis("y", dy * self.y_sign)

        with self._lock:
            self._position = (target_x, target_y)

    def stop(self) -> None:
        for stepper in self._unique_steppers():
            try:
                stepper.stop()
            except Exception:
                pass

    def _move_axis(self, axis: str, steps: int) -> None:
        if self._xy_stepper is not None:
            motor_id = 0 if axis == "x" else 1
            self._xy_stepper.move(int(steps), motor_id=motor_id, apply_backlash=self.apply_backlash)
            return
        stepper = self._x_stepper if axis == "x" else self._y_stepper
        if stepper is None:
            raise RuntimeError(f"{axis.upper()} stepper is not connected.")
        stepper.move(int(steps), apply_backlash=self.apply_backlash)

    def _unique_steppers(self) -> list:
        steppers = [self._xy_stepper, self._x_stepper, self._y_stepper]
        unique = []
        seen: set[int] = set()
        for stepper in steppers:
            if stepper is None:
                continue
            marker = id(stepper)
            if marker not in seen:
                seen.add(marker)
                unique.append(stepper)
        return unique


def serpentine_path(rows: int, cols: int, step_x: float, step_y: float) -> list[Point]:
    rows = int(rows)
    cols = int(cols)
    step_x = float(step_x)
    step_y = float(step_y)
    if rows <= 0:
        raise ValueError("rows must be greater than 0.")
    if cols <= 0:
        raise ValueError("cols must be greater than 0.")
    if step_x <= 0:
        raise ValueError("step_x must be greater than 0.")
    if step_y <= 0:
        raise ValueError("step_y must be greater than 0.")

    path: list[Point] = []
    for row in range(rows):
        col_range = range(cols) if row % 2 == 0 else range(cols - 1, -1, -1)
        y = row * step_y
        for col in col_range:
            path.append((col * step_x, y))
    return path


def _axis_values_from_bounds(start: float, end: float, step: float) -> list[float]:
    start = float(start)
    end = float(end)
    step = float(step)
    if step <= 0:
        raise ValueError("step must be greater than 0.")
    if math.isclose(start, end, rel_tol=0.0, abs_tol=1e-9):
        return [start]

    direction = 1.0 if end > start else -1.0
    distance = abs(end - start)
    full_steps = int(math.floor(distance / step))
    values = [start + direction * step * index for index in range(full_steps + 1)]
    if not math.isclose(values[-1], end, rel_tol=0.0, abs_tol=1e-9):
        values.append(end)
    return values


def serpentine_path_from_bounds(
    start_x: float,
    start_y: float,
    end_x: float,
    end_y: float,
    step_x: float,
    step_y: float,
) -> list[Point]:
    """Build an absolute serpentine path from explicit start/end coordinates.

    The first row moves from start_x toward end_x. Each row change moves from
    start_y toward end_y. If the final interval is shorter than step_x/step_y,
    the exact end coordinate is appended so the requested boundary is covered.
    """
    x_values = _axis_values_from_bounds(start_x, end_x, step_x)
    y_values = _axis_values_from_bounds(start_y, end_y, step_y)

    path: list[Point] = []
    for row_index, y in enumerate(y_values):
        xs = x_values if row_index % 2 == 0 else list(reversed(x_values))
        for x in xs:
            path.append((float(x), float(y)))
    return path


def path_total_distance(path: Sequence[Point]) -> float:
    total = 0.0
    for index in range(len(path) - 1):
        x0, y0 = path[index]
        x1, y1 = path[index + 1]
        total += math.hypot(float(x1) - float(x0), float(y1) - float(y0))
    return total


def estimate_duration_seconds(rows: int, cols: int, step_x: float, step_y: float, speed: float) -> float:
    speed = float(speed)
    if speed <= 0:
        raise ValueError("speed must be greater than 0.")
    return path_total_distance(serpentine_path(rows, cols, step_x, step_y)) / speed


def _hardware_dir() -> Path:
    current = Path(__file__).resolve()
    for candidate in [current.parent, *current.parents, Path.cwd(), *Path.cwd().parents]:
        hardware_dir = candidate / "msh_app" / "hardware"
        if (hardware_dir / "arduino_stepper.py").exists():
            return hardware_dir
    raise FileNotFoundError(
        "Cannot find msh_app/hardware/arduino_stepper.py from this workspace."
    )


def _load_arduino_stepper_class():
    hardware_dir = _hardware_dir()
    if str(hardware_dir) not in sys.path:
        sys.path.insert(0, str(hardware_dir))
    from arduino_stepper import ArduinoStepper

    return ArduinoStepper


def sample_path_at_distance(path: Sequence[Point], distance: float) -> tuple[Point, int, float]:
    if not path:
        raise ValueError("path must contain at least one point.")
    if len(path) == 1:
        return (float(path[0][0]), float(path[0][1])), 0, 1.0

    remaining = max(0.0, float(distance))
    for index in range(len(path) - 1):
        x0, y0 = path[index]
        x1, y1 = path[index + 1]
        segment_length = math.hypot(float(x1) - float(x0), float(y1) - float(y0))
        if segment_length <= 1e-9:
            continue
        if remaining <= segment_length:
            fraction = remaining / segment_length
            x = float(x0) + (float(x1) - float(x0)) * fraction
            y = float(y0) + (float(y1) - float(y0)) * fraction
            return (x, y), index, fraction
        remaining -= segment_length

    return (float(path[-1][0]), float(path[-1][1])), len(path) - 2, 1.0


class SerpentineRecorder:
    def __init__(
        self,
        rows: int = 3,
        cols: int = 4,
        step_x: float = 200.0,
        step_y: float = 150.0,
        speed: float = 100.0,
        fps: float = 30.0,
        output_path: str | Path = "serpentine_demo.mp4",
        camera: Camera | None = None,
        stage: Stage | None = None,
        frame_size: tuple[int, int] = (960, 540),
        preview: bool = True,
        window_name: str = "Serpentine Recording",
    ) -> None:
        self.rows = int(rows)
        self.cols = int(cols)
        self.step_x = float(step_x)
        self.step_y = float(step_y)
        self.speed = float(speed)
        self.fps = float(fps)
        self.output_path = Path(output_path)
        self.frame_size = (int(frame_size[0]), int(frame_size[1]))
        self.preview = bool(preview)
        self.window_name = str(window_name)
        self.path = serpentine_path(self.rows, self.cols, self.step_x, self.step_y)

        self.stage: Stage = stage if stage is not None else SimulatedStage(self.path[0])
        self.camera: Camera = camera if camera is not None else SimulatedCamera(
            self.stage,
            frame_size=self.frame_size,
            path=self.path,
        )

        self._writer: cv2.VideoWriter | None = None
        self._recording_path: Path | None = None
        self._pause_requested = threading.Event()
        self._stop_requested = threading.Event()
        self._restart_requested = threading.Event()
        self._moving = False
        self._recording = False
        self._frame_count = 0
        self._last_status: RecordingStatus | None = None

    @property
    def is_paused(self) -> bool:
        return self._pause_requested.is_set()

    @property
    def is_recording(self) -> bool:
        return self._recording

    @property
    def frame_count(self) -> int:
        return self._frame_count

    @property
    def last_status(self) -> RecordingStatus | None:
        return self._last_status

    def start_recording(self) -> None:
        if self.fps <= 0:
            raise ValueError("fps must be greater than 0.")
        if self.speed <= 0:
            raise ValueError("speed must be greater than 0.")
        if self._recording:
            return

        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        connect = getattr(self.stage, "connect", None)
        if callable(connect):
            connect()
        self.camera.open()
        self.stage.move_to(*self.path[0])
        self._writer = _open_video_writer(self.output_path, self.fps, self.frame_size)
        self._recording_path = self.output_path
        self._pause_requested.clear()
        self._stop_requested.clear()
        self._restart_requested.clear()
        self._frame_count = 0
        self._last_status = None
        self._recording = True

    def pause(self) -> None:
        self._pause_requested.set()

    def resume(self) -> None:
        self._pause_requested.clear()

    def restart(self) -> None:
        self._restart_requested.set()
        self.resume()

    def stop_recording(self) -> None:
        self._stop_requested.set()
        self.resume()
        stop = getattr(self.stage, "stop", None)
        if callable(stop):
            stop()
        if self._recording and not self._moving:
            self.save_video(self.output_path)

    def save_video(self, output_path: str | Path | None = None) -> Path:
        target_path = Path(output_path) if output_path is not None else self.output_path
        if self._writer is not None:
            self._writer.release()
            self._writer = None
        self.camera.close()
        close_stage = getattr(self.stage, "close", None)
        if callable(close_stage):
            close_stage()
        self._recording = False

        source_path = self._recording_path or self.output_path
        if target_path.resolve() != source_path.resolve():
            target_path.parent.mkdir(parents=True, exist_ok=True)
            if target_path.exists():
                target_path.unlink()
            shutil.move(str(source_path), str(target_path))
            self._recording_path = target_path
            self.output_path = target_path

        if not target_path.exists() or target_path.stat().st_size <= 0:
            raise RuntimeError(f"Video was not written: {target_path}")
        return target_path.resolve()

    def move_along_path_smoothly(
        self,
        path: Sequence[Point] | None = None,
        speed: float | None = None,
    ) -> RecordingStatus | None:
        if path is not None:
            self.path = [(float(x), float(y)) for x, y in path]
        if not self.path:
            raise ValueError("path must contain at least one point.")
        if speed is not None:
            self.speed = float(speed)
        if self.speed <= 0:
            raise ValueError("speed must be greater than 0.")
        if self.fps <= 0:
            raise ValueError("fps must be greater than 0.")
        if not self._recording:
            self.start_recording()

        total_distance = path_total_distance(self.path)
        distance_done = 0.0
        frame_step = self.speed / self.fps
        frame_period = 1.0 / self.fps
        self._moving = True

        try:
            while not self._stop_requested.is_set():
                frame_started = time.perf_counter()

                if self._restart_requested.is_set():
                    distance_done = 0.0
                    self._restart_requested.clear()
                    self.stage.move_to(*self.path[0])

                point, segment_index, segment_fraction = sample_path_at_distance(self.path, distance_done)
                self.stage.move_to(*point)
                status = self._make_status(
                    point=point,
                    segment_index=segment_index,
                    segment_fraction=segment_fraction,
                    distance_done=distance_done,
                    total_distance=total_distance,
                )
                self._write_current_frame(status)

                if total_distance <= 1e-9:
                    break
                if not self._pause_requested.is_set():
                    if distance_done >= total_distance:
                        break
                    distance_done = min(total_distance, distance_done + frame_step)

                elapsed = time.perf_counter() - frame_started
                sleep_s = frame_period - elapsed
                if sleep_s > 0:
                    time.sleep(sleep_s)
        finally:
            self._moving = False

        return self._last_status

    def _make_status(
        self,
        point: Point,
        segment_index: int,
        segment_fraction: float,
        distance_done: float,
        total_distance: float,
    ) -> RecordingStatus:
        x, y = point
        row_index = min(self.rows - 1, max(0, int(round(y / self.step_y)))) if self.step_y > 0 else 0
        col_index = min(self.cols - 1, max(0, int(round(x / self.step_x)))) if self.step_x > 0 else 0
        progress = 1.0 if total_distance <= 1e-9 else min(1.0, max(0.0, distance_done / total_distance))
        elapsed_s = self._frame_count / self.fps
        eta_s = 0.0 if self.speed <= 0 else max(0.0, (total_distance - distance_done) / self.speed)
        status = RecordingStatus(
            x=float(x),
            y=float(y),
            row_index=row_index,
            col_index=col_index,
            segment_index=int(segment_index),
            segment_fraction=float(segment_fraction),
            distance_done=float(distance_done),
            total_distance=float(total_distance),
            progress=float(progress),
            elapsed_s=float(elapsed_s),
            eta_s=float(eta_s),
            frame_index=int(self._frame_count),
            paused=self._pause_requested.is_set(),
            stopped=self._stop_requested.is_set(),
        )
        self._last_status = status
        return status

    def _write_current_frame(self, status: RecordingStatus) -> None:
        if self._writer is None:
            raise RuntimeError("Recording has not been started.")

        frame = self.camera.read()
        frame = _resize_to_frame_size(frame, self.frame_size)
        frame = self._draw_overlay(frame, status)
        self._writer.write(frame)
        self._frame_count += 1

        if self.preview:
            cv2.imshow(self.window_name, frame)
            key = cv2.waitKey(1) & 0xFF
            self._handle_key(key)

    def _handle_key(self, key: int) -> None:
        if key in (ord("q"), 27):
            self.stop_recording()
        elif key == ord("p"):
            if self.is_paused:
                self.resume()
            else:
                self.pause()
        elif key == ord("r"):
            self.restart()

    def _draw_overlay(self, frame: np.ndarray, status: RecordingStatus) -> np.ndarray:
        output = frame.copy()
        panel_h = 126
        overlay = output.copy()
        cv2.rectangle(overlay, (0, 0), (output.shape[1], panel_h), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.46, output, 0.54, 0.0, output)

        state = "PAUSED" if status.paused else "RUNNING"
        if status.stopped:
            state = "STOPPED"
        lines = [
            f"state={state} frame={status.frame_index} fps={self.fps:.1f}",
            f"x={status.x:.2f} y={status.y:.2f} row={status.row_index + 1}/{self.rows} col={status.col_index + 1}/{self.cols}",
            f"progress={status.progress * 100.0:5.1f}% distance={status.distance_done:.1f}/{status.total_distance:.1f}",
            f"elapsed={status.elapsed_s:.1f}s eta={status.eta_s:.1f}s speed={self.speed:.1f}",
        ]
        for index, text in enumerate(lines):
            cv2.putText(
                output,
                text,
                (18, 28 + index * 27),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.68,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )

        progress_w = max(1, output.shape[1] - 36)
        progress_x = 18
        progress_y = panel_h - 13
        cv2.rectangle(output, (progress_x, progress_y), (progress_x + progress_w, progress_y + 6), (80, 80, 80), -1)
        cv2.rectangle(
            output,
            (progress_x, progress_y),
            (progress_x + int(round(progress_w * status.progress)), progress_y + 6),
            (60, 220, 120),
            -1,
        )
        return output


def _resize_to_frame_size(frame: np.ndarray, frame_size: tuple[int, int]) -> np.ndarray:
    width, height = frame_size
    if frame.shape[1] == width and frame.shape[0] == height:
        return np.ascontiguousarray(frame)
    return cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)


def _open_video_writer(output_path: Path, fps: float, frame_size: tuple[int, int]) -> cv2.VideoWriter:
    output_path = Path(output_path)
    width, height = frame_size
    suffix = output_path.suffix.lower()
    if suffix == ".mp4":
        codecs = ("mp4v", "avc1", "H264")
    elif suffix == ".avi":
        codecs = ("MJPG", "XVID", "mp4v")
    else:
        codecs = ("mp4v", "MJPG", "XVID")

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
    raise RuntimeError(f"Unable to create video writer for {output_path}.")


_DEFAULT_RECORDER: SerpentineRecorder | None = None


def configure_default_recorder(**kwargs) -> SerpentineRecorder:
    global _DEFAULT_RECORDER
    _DEFAULT_RECORDER = SerpentineRecorder(**kwargs)
    return _DEFAULT_RECORDER


def _default_recorder() -> SerpentineRecorder:
    global _DEFAULT_RECORDER
    if _DEFAULT_RECORDER is None:
        _DEFAULT_RECORDER = SerpentineRecorder()
    return _DEFAULT_RECORDER


def start_recording() -> None:
    _default_recorder().start_recording()


def move_along_path_smoothly(path: Sequence[Point], speed: float) -> RecordingStatus | None:
    return _default_recorder().move_along_path_smoothly(path, speed)


def stop_recording() -> None:
    _default_recorder().stop_recording()


def save_video(output_path: str | Path) -> Path:
    return _default_recorder().save_video(output_path)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Continuous smooth serpentine video recorder.")
    parser.add_argument("--simulate", action="store_true", help="Use generated microscope-like simulation frames.")
    parser.add_argument("--hardware", action="store_true", help="Use a real serial X/Y stage instead of the simulated stage.")
    parser.add_argument("--simulate-camera", action="store_true", help="Use simulated frames while moving a real stage.")
    parser.add_argument("--basler", action="store_true", help="Use a Basler camera through pypylon.")
    parser.add_argument("--camera-index", type=int, default=None, help="OpenCV camera index, or Basler index when --basler is set.")
    parser.add_argument("--camera-serial", default=None, help="Optional Basler camera serial number.")
    parser.add_argument("--exposure-us", type=float, default=None, help="Optional Basler exposure time in microseconds.")
    parser.add_argument("--gain", type=float, default=None, help="Optional Basler gain.")
    parser.add_argument("--pixel-format", default=None, help="Optional Basler pixel format.")
    parser.add_argument("--x-port", default=None, help="Serial port for the X-axis Arduino, e.g. COM7.")
    parser.add_argument("--y-port", default=None, help="Serial port for the Y-axis Arduino, e.g. COM8.")
    parser.add_argument("--xy-port", default=None, help="Serial port for a single dual-axis Arduino controller.")
    parser.add_argument("--stage-baud", type=int, default=115200)
    parser.add_argument("--stage-timeout-s", type=float, default=2.0)
    parser.add_argument("--stage-boot-wait-s", type=float, default=2.0)
    parser.add_argument("--motor-speed-ms", type=int, default=FIXED_STEP_DELAY_MS, choices=[FIXED_STEP_DELAY_MS], help="Fixed 0.02 RPM compatibility delay; not an adjustable speed.")
    parser.add_argument("--x-sign", type=int, choices=(-1, 1), default=1, help="Invert X movement with -1 if needed.")
    parser.add_argument("--y-sign", type=int, choices=(-1, 1), default=1, help="Invert Y movement with -1 if needed.")
    parser.add_argument("--no-hold", action="store_true", help="Disable motor hold after connecting, if firmware supports HOLD.")
    parser.add_argument("--apply-backlash", action="store_true", help="Use ArduinoStepper backlash compensation during smooth moves.")
    parser.add_argument("--rows", type=int, default=3)
    parser.add_argument("--cols", type=int, default=4)
    parser.add_argument("--step-x", type=float, default=200.0)
    parser.add_argument("--step-y", type=float, default=150.0)
    parser.add_argument("--speed", type=float, default=100.0)
    parser.add_argument("--fps", type=float, default=30.0)
    parser.add_argument("--output", "--output-path", dest="output_path", default="serpentine_demo.mp4")
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--height", type=int, default=540)
    parser.add_argument("--no-preview", action="store_true", help="Disable preview window and keyboard controls.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    path = serpentine_path(args.rows, args.cols, args.step_x, args.step_y)
    frame_size = (int(args.width), int(args.height))

    if args.hardware:
        stage: Stage = SerialXYStage(
            x_port=args.x_port,
            y_port=args.y_port,
            xy_port=args.xy_port,
            baud=args.stage_baud,
            timeout_s=args.stage_timeout_s,
            boot_wait_s=args.stage_boot_wait_s,
            motor_speed_ms=args.motor_speed_ms,
            hold=not args.no_hold,
            x_sign=args.x_sign,
            y_sign=args.y_sign,
            apply_backlash=args.apply_backlash,
        )
    else:
        stage = SimulatedStage(path[0])

    camera_index = 0 if args.camera_index is None else int(args.camera_index)
    if args.simulate or args.simulate_camera:
        camera: Camera = SimulatedCamera(stage, frame_size=frame_size, path=path)
        camera_mode = "simulated"
    elif args.basler:
        camera = BaslerRecorderCamera(
            camera_serial=args.camera_serial,
            camera_index=camera_index,
            width=args.width,
            height=args.height,
            exposure_us=args.exposure_us,
            gain=args.gain,
            fps=args.fps,
            pixel_format=args.pixel_format,
        )
        camera_mode = "basler"
    elif args.camera_index is not None:
        camera = OpenCVCamera(camera_index, frame_size=frame_size)
        camera_mode = f"opencv:{camera_index}"
    elif args.hardware:
        camera = BaslerRecorderCamera(
            camera_serial=args.camera_serial,
            camera_index=camera_index,
            width=args.width,
            height=args.height,
            exposure_us=args.exposure_us,
            gain=args.gain,
            fps=args.fps,
            pixel_format=args.pixel_format,
        )
        camera_mode = "basler"
    else:
        camera = SimulatedCamera(stage, frame_size=frame_size, path=path)
        camera_mode = "simulated"

    recorder = SerpentineRecorder(
        rows=args.rows,
        cols=args.cols,
        step_x=args.step_x,
        step_y=args.step_y,
        speed=args.speed,
        fps=args.fps,
        output_path=args.output_path,
        camera=camera,
        stage=stage,
        frame_size=frame_size,
        preview=not args.no_preview,
    )

    total_distance = path_total_distance(path)
    estimated_s = 0.0 if args.speed <= 0 else total_distance / float(args.speed)
    stage_mode = "hardware" if args.hardware else "simulated"
    print(f"path_points={len(path)}")
    print(f"stage={stage_mode}")
    print(f"camera={camera_mode}")
    print(f"total_distance={total_distance:.3f}")
    print(f"estimated_time_s={estimated_s:.3f}")
    print("preview_keys=p pause/resume, r restart, q or Esc stop")

    try:
        recorder.start_recording()
        recorder.move_along_path_smoothly(path, args.speed)
        output_path = recorder.save_video(args.output_path)
    finally:
        if not args.no_preview:
            cv2.destroyAllWindows()

    print(f"output_path={output_path}")
    print(f"frames_written={recorder.frame_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

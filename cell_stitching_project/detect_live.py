from __future__ import annotations

import argparse
from collections import Counter, deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import time
from typing import Any

import cv2

from .camera import BaslerCamera, BaslerCameraConfig
from .cell_identification import CLASS_COLORS, CellDetection, CellIdentificationDetector, draw_detections, load_class_names
from .io_utils import append_jsonl, save_image, save_json, save_text_lines
from .model_presets import DEFAULT_LIVE_DETECTION_PRESET, available_detection_preset_names, resolve_detection_preset
from .ssd.detector import SSDDetector
from .text_overlay import get_text_size, put_text

DEFAULT_LIVE_PRESET = DEFAULT_LIVE_DETECTION_PRESET


@dataclass(slots=True)
class DetectionSessionPaths:
    root: Path
    frames_dir: Path
    crops_dir: Path
    manual_dir: Path
    detections_json: Path
    summary_json: Path
    stable_events_jsonl: Path


@dataclass(slots=True)
class StableDetectionDecision:
    label: str | None
    votes: int
    history: list[str]


@dataclass(slots=True)
class StableDetectionEvent:
    event_index: int
    frame_index: int
    label: str
    votes: int
    history: list[str]
    counts: dict[str, int]
    command: str | None = None
    command_status: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "event_index": self.event_index,
            "frame_index": self.frame_index,
            "label": self.label,
            "votes": self.votes,
            "history": list(self.history),
            "counts": dict(self.counts),
            "command": self.command,
            "command_status": self.command_status,
        }


class DetectionStabilizer:
    def __init__(self, window_size: int, trigger_threshold: int | None = None) -> None:
        self.window_size = max(1, int(window_size))
        default_threshold = max(1, int(round(self.window_size * 0.7)))
        self.trigger_threshold = max(1, min(self.window_size, int(trigger_threshold or default_threshold)))
        self.history: deque[str] = deque(maxlen=self.window_size)

    def update(self, detections: list[CellDetection]) -> StableDetectionDecision:
        if detections:
            top_detection = max(detections, key=lambda detection: detection.confidence)
            current_label = top_detection.label
        else:
            current_label = "None"

        self.history.append(current_label)
        counts = Counter(self.history)
        most_common_label, votes = counts.most_common(1)[0]
        stable_label = most_common_label if most_common_label != "None" and votes >= self.trigger_threshold else None
        return StableDetectionDecision(
            label=stable_label,
            votes=int(votes),
            history=list(self.history),
        )


class SerialCommandSink:
    def __init__(self, port: str, baudrate: int = 9600, timeout: float = 0.1) -> None:
        try:
            import serial
        except ImportError as exc:  # pragma: no cover - import error is environment-specific
            raise RuntimeError("pyserial is required for --serial-port output.") from exc

        self._serial = serial.Serial(port, int(baudrate), timeout=float(timeout))

    def send(self, command: str) -> None:
        payload = command if command.endswith("\n") else f"{command}\n"
        self._serial.write(payload.encode("utf-8"))

    def close(self) -> None:
        self._serial.close()


class StableEventDispatcher:
    def __init__(
        self,
        cooldown_frames: int = 0,
        event_log_path: str | Path | None = None,
        command_template: str | None = None,
        command_sink: Any | None = None,
    ) -> None:
        self.cooldown_frames = max(0, int(cooldown_frames))
        self.event_log_path = None if event_log_path is None else Path(event_log_path)
        self.command_template = command_template.strip() if command_template else None
        self.command_sink = command_sink
        self.last_emitted_label: str | None = None
        self.last_emitted_frame = -1_000_000
        self.event_count = 0
        self.emitted_events: list[dict[str, object]] = []

    def _should_emit(self, frame_index: int, label: str) -> bool:
        if self.last_emitted_label != label:
            return True
        return (frame_index - self.last_emitted_frame) >= self.cooldown_frames

    def _render_command(self, decision: StableDetectionDecision, frame_index: int) -> str | None:
        if not self.command_template or not decision.label:
            return None
        return self.command_template.format(
            label=decision.label,
            votes=decision.votes,
            frame_index=frame_index,
        )

    def handle(
        self,
        frame_index: int,
        decision: StableDetectionDecision | None,
        counts: dict[str, int],
    ) -> dict[str, object] | None:
        if decision is None or not decision.label:
            return None
        if not self._should_emit(frame_index, decision.label):
            return None

        self.event_count += 1
        command = self._render_command(decision, frame_index)
        command_status: str | None = None
        if command is not None and self.command_sink is not None:
            try:
                self.command_sink.send(command)
                command_status = "sent"
            except Exception as exc:
                command_status = f"error: {exc}"
        elif command is not None:
            command_status = "rendered"

        stable_event = StableDetectionEvent(
            event_index=self.event_count,
            frame_index=frame_index,
            label=decision.label,
            votes=decision.votes,
            history=list(decision.history),
            counts=dict(counts),
            command=command,
            command_status=command_status,
        )
        payload = stable_event.to_dict()
        if self.event_log_path is not None:
            append_jsonl(self.event_log_path, payload)

        self.emitted_events.append(payload)
        self.last_emitted_label = decision.label
        self.last_emitted_frame = frame_index
        return payload

    def close(self) -> None:
        if self.command_sink is not None and hasattr(self.command_sink, "close"):
            self.command_sink.close()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run live Basler detection with SSD or YOLO/ONNX backends.")
    parser.add_argument("--source", choices=("basler",), default="basler")
    parser.add_argument(
        "--preset",
        choices=available_detection_preset_names() + ("none",),
        default=DEFAULT_LIVE_PRESET,
        help="Integrated model preset. Default uses the 3-class blood-cell YOLO model.",
    )
    parser.add_argument("--backend", choices=("ssd", "ultralytics", "onnx"), default=None)
    parser.add_argument("--net", default="mb1-ssd", help="SSD network type for `--backend ssd`.")
    parser.add_argument("--model", default=None, help="Model path (.pth for SSD, .pt/.onnx for other backends).")
    parser.add_argument("--labels", default=None, help="Optional label file path. Ultralytics models can use embedded class names.")
    parser.add_argument("--confidence", type=float, default=0.35, help="Confidence threshold.")
    parser.add_argument("--class-confidence", default=None, help="Optional per-class thresholds, e.g. WBC,RBC,Platelets as `0.25,0.55,0.45`.")
    parser.add_argument("--iou-threshold", type=float, default=0.45, help="IoU threshold.")
    parser.add_argument("--top-k", type=int, default=10, help="Maximum detections per frame for SSD.")
    parser.add_argument("--output-dir", required=True, help="Directory for session outputs.")
    parser.add_argument("--save-crops", action="store_true", help="Automatically save each detected ROI.")
    parser.add_argument("--save-frames", action="store_true", help="Save each annotated frame.")
    parser.add_argument("--no-preview", action="store_true", help="Disable the preview window.")
    parser.add_argument("--max-frames", type=int, default=None, help="Optional maximum number of processed frames.")
    parser.add_argument("--camera-serial", default=None, help="Optional Basler camera serial number.")
    parser.add_argument("--camera-index", type=int, default=0, help="Basler camera index when serial is not provided.")
    parser.add_argument("--width", type=int, default=None)
    parser.add_argument("--height", type=int, default=None)
    parser.add_argument("--exposure-us", type=float, default=None)
    parser.add_argument("--gain", type=float, default=None)
    parser.add_argument("--fps", type=float, default=None)
    parser.add_argument("--pixel-format", default=None)
    parser.add_argument("--use-cuda", default="true", help="Enable CUDA for SSD where available.")
    parser.add_argument("--mb2-width-mult", type=float, default=1.0, help="Width multiplier for mb2-ssd-lite.")
    parser.add_argument("--preview-max-width", type=int, default=1280, help="Downscale the preview window to this width to improve display FPS.")
    parser.add_argument("--stabilization-window", type=int, default=None, help="Rolling window size for stable-label voting. Use 0 to disable.")
    parser.add_argument("--stabilization-threshold", type=int, default=None, help="Votes required inside the rolling window to trigger a stable label.")
    parser.add_argument("--stable-event-cooldown", type=int, default=None, help="Minimum frame gap before the same stable label can emit again.")
    parser.add_argument("--command-template", default=None, help="Optional command template rendered on stable events, e.g. `{label}`.")
    parser.add_argument("--serial-port", default=None, help="Optional serial port for stable-event commands.")
    parser.add_argument("--serial-baudrate", type=int, default=9600, help="Baudrate used with --serial-port.")
    parser.add_argument("--serial-timeout", type=float, default=0.1, help="Serial timeout in seconds.")
    parser.add_argument("--export-label-template", default=None, help="Write the current detector labels to a text file and exit.")
    return parser


def _infer_backend(model: str | None) -> str:
    if model is None:
        return "ssd"
    suffix = Path(model).suffix.lower()
    if suffix == ".onnx":
        return "onnx"
    if suffix == ".pt":
        return "ultralytics"
    return "ssd"


def _apply_preset(args: argparse.Namespace) -> None:
    if not args.preset or args.preset == "none":
        return

    preset = resolve_detection_preset(args.preset)
    if args.backend is None:
        args.backend = preset.backend
    if args.model is None:
        args.model = str(preset.model_path)
    if args.labels is None and preset.class_file is not None:
        args.labels = str(preset.class_file)
    if args.confidence == 0.35 and preset.confidence is not None:
        args.confidence = preset.confidence
    if getattr(args, "class_confidence", None) is None and preset.class_confidence is not None:
        args.class_confidence = ",".join(str(value) for value in preset.class_confidence)
    if args.iou_threshold == 0.45 and preset.iou_threshold is not None:
        args.iou_threshold = preset.iou_threshold
    if args.stabilization_window is None:
        args.stabilization_window = preset.stabilization_window
    if args.stabilization_threshold is None:
        args.stabilization_threshold = preset.stabilization_threshold
    if args.stable_event_cooldown is None:
        args.stable_event_cooldown = preset.stable_event_cooldown


def _validate_args(args: argparse.Namespace) -> None:
    _apply_preset(args)
    if args.backend is None:
        args.backend = _infer_backend(args.model)
    if args.stabilization_window is None:
        args.stabilization_window = 0
    if args.stabilization_threshold is None and args.stabilization_window > 0:
        args.stabilization_threshold = max(1, int(round(args.stabilization_window * 0.7)))
    if args.stable_event_cooldown is None:
        args.stable_event_cooldown = 0
    if args.model is None:
        raise ValueError("`--model` is required unless `--preset` provides one.")
    if args.backend == "ssd" and not args.labels:
        raise ValueError("`--labels` is required when `--backend ssd` is used.")
    if args.backend == "onnx" and not args.labels:
        raise ValueError("`--labels` is required when `--backend onnx` is used.")
    if args.stabilization_window < 0:
        raise ValueError("`--stabilization-window` must be zero or a positive integer.")
    if args.stabilization_window > 0 and args.stabilization_threshold is not None and args.stabilization_threshold > args.stabilization_window:
        raise ValueError("`--stabilization-threshold` cannot be greater than `--stabilization-window`.")
    if args.stabilization_threshold is not None and args.stabilization_threshold <= 0:
        raise ValueError("`--stabilization-threshold` must be positive.")
    if args.stable_event_cooldown < 0:
        raise ValueError("`--stable-event-cooldown` must be zero or a positive integer.")
    if args.serial_port and not args.command_template:
        raise ValueError("`--command-template` is required when `--serial-port` is set.")


def _create_session_paths(output_dir: str | Path) -> DetectionSessionPaths:
    root = Path(output_dir)
    frames_dir = root / "frames"
    crops_dir = root / "cropped_objects"
    manual_dir = root / "manual_captures"
    for path in (root, frames_dir, crops_dir, manual_dir):
        path.mkdir(parents=True, exist_ok=True)
    return DetectionSessionPaths(
        root=root,
        frames_dir=frames_dir,
        crops_dir=crops_dir,
        manual_dir=manual_dir,
        detections_json=root / "detections.json",
        summary_json=root / "session_summary.json",
        stable_events_jsonl=root / "stable_events.jsonl",
    )


def _build_detector(args: argparse.Namespace) -> Any:
    if args.backend == "ssd":
        return SSDDetector(
            net_type=args.net,
            model_path=args.model,
            label_file=args.labels,
            confidence=args.confidence,
            iou_threshold=args.iou_threshold,
            top_k=args.top_k,
            use_cuda=str(args.use_cuda).strip().lower() in {"true", "1", "yes"},
            mb2_width_mult=args.mb2_width_mult,
        )
    class_names = load_class_names(args.labels) if args.labels else None
    if class_names and class_names[0].upper() == "BACKGROUND":
        class_names = class_names[1:]
    return CellIdentificationDetector(
        model_path=args.model,
        backend=args.backend,
        class_names=class_names,
        confidence=args.confidence,
        class_confidence=args.class_confidence,
        iou_threshold=args.iou_threshold,
        device=None,
        prefer_gpu=True,
    )


def count_labels(detections: list[CellDetection]) -> dict[str, int]:
    return dict(Counter(detection.label for detection in detections))


def draw_count_overlay(frame, label_counts: dict[str, int], copy_frame: bool = True):
    if not label_counts:
        return frame
    annotated = frame.copy() if copy_frame else frame
    width = annotated.shape[1]
    x_origin = max(8, width - 260)
    line_height = 28
    box_height = 18 + line_height * (len(label_counts) + 1)
    cv2.rectangle(annotated, (x_origin - 10, 10), (width - 10, 10 + box_height), (0, 0, 0), -1)
    put_text(annotated, "Counts:", (x_origin, 36), 0.8, (255, 255, 255), 2)
    for index, (label, count) in enumerate(sorted(label_counts.items())):
        put_text(
            annotated,
            f"{label}: {count}",
            (x_origin, 36 + (index + 1) * line_height),
            0.7,
            (0, 255, 0),
            2,
        )
    return annotated


def _resize_for_preview(frame, max_width: int | None) -> tuple[Any, float]:
    if max_width is None or max_width <= 0 or frame.shape[1] <= max_width:
        return frame, 1.0
    scale = max_width / float(frame.shape[1])
    resized_height = max(1, int(round(frame.shape[0] * scale)))
    resized = cv2.resize(frame, (int(max_width), resized_height), interpolation=cv2.INTER_AREA)
    return resized, scale


def _draw_preview_detections(frame, detections: list[CellDetection], preview_max_width: int | None) -> Any:
    preview_frame, scale = _resize_for_preview(frame, preview_max_width)
    annotated = preview_frame.copy()
    thickness = 2 if scale >= 0.75 else 1
    font_scale = 0.6 if scale >= 0.75 else 0.5
    text_thickness = 2 if scale >= 0.75 else 1

    for detection in detections:
        draw_color = CLASS_COLORS[detection.class_id % len(CLASS_COLORS)] if CLASS_COLORS else (0, 255, 0)
        x1 = int(round(detection.bbox.x1 * scale))
        y1 = int(round(detection.bbox.y1 * scale))
        x2 = int(round(detection.bbox.x2 * scale))
        y2 = int(round(detection.bbox.y2 * scale))
        label = f"{detection.label} {detection.confidence:.2f}"

        cv2.rectangle(annotated, (x1, y1), (x2, y2), draw_color, thickness)
        text_width, text_height, baseline = get_text_size(label, font_scale=font_scale, thickness=text_thickness)
        box_top = max(y1 - text_height - baseline - 8, 0)
        box_bottom = box_top + text_height + baseline + 8
        cv2.rectangle(annotated, (x1, box_top), (x1 + text_width + 10, box_bottom), draw_color, -1)
        put_text(
            annotated,
            label,
            (x1 + 5, box_bottom - baseline - 4),
            font_scale,
            (0, 0, 0),
            text_thickness,
        )
    return annotated


def _draw_status_overlay(frame, preview_fps: float, inference_ms: float, copy_frame: bool = True) -> Any:
    annotated = frame.copy() if copy_frame else frame
    lines = [
        f"preview_fps={preview_fps:.1f}",
        f"inference_ms={inference_ms:.1f}",
    ]
    y = 30
    for line in lines:
        put_text(annotated, line, (18, y), 0.75, (0, 255, 255), 2)
        y += 28
    return annotated


def _draw_stabilization_overlay(frame, decision: StableDetectionDecision, copy_frame: bool = True) -> Any:
    annotated = frame.copy() if copy_frame else frame
    status = decision.label or "pending"
    lines = [
        f"stable_label={status}",
        f"stable_votes={decision.votes}",
        f"history={decision.history}",
    ]
    y = max(40, annotated.shape[0] - 84)
    for line in lines:
        put_text(annotated, line, (18, y), 0.55, (0, 165, 255), 2)
        y += 24
    return annotated


def _reload_detector_class_names(detector: Any, labels_path: str | None) -> list[str] | None:
    if not labels_path or not hasattr(detector, "class_names"):
        return None
    class_names = load_class_names(labels_path)
    if class_names and class_names[0].upper() == "BACKGROUND":
        class_names = class_names[1:]
    detector.class_names = list(class_names)
    return list(class_names)


def _export_label_template(detector: Any, target_path: str | Path) -> Path:
    class_names = list(getattr(detector, "class_names", []) or [])
    if not class_names:
        raise ValueError("The current detector does not expose editable class names.")
    return save_text_lines(target_path, class_names)


def save_detection_crops(frame, detections: list[CellDetection], crops_dir: Path, frame_index: int) -> list[dict[str, str]]:
    crop_records: list[dict[str, str]] = []
    for detection_index, detection in enumerate(detections):
        x1 = max(0, detection.bbox.x1)
        y1 = max(0, detection.bbox.y1)
        x2 = min(frame.shape[1], detection.bbox.x2)
        y2 = min(frame.shape[0], detection.bbox.y2)
        if x2 <= x1 or y2 <= y1:
            continue
        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            continue
        output_path = crops_dir / f"{detection.label}_frame{frame_index:06d}_{detection_index:03d}.png"
        save_image(output_path, crop)
        crop_records.append({"label": detection.label, "path": str(output_path.resolve())})
    return crop_records


def process_frame(
    frame,
    detector: Any,
    session_paths: DetectionSessionPaths,
    frame_index: int,
    save_crops: bool,
    save_frames: bool,
    stabilizer: DetectionStabilizer | None = None,
):
    detections = detector.predict(frame)
    counts = count_labels(detections)
    stable_decision = stabilizer.update(detections) if stabilizer is not None else None

    crop_records = save_detection_crops(frame, detections, session_paths.crops_dir, frame_index) if save_crops else []
    frame_path = None
    if save_frames:
        annotated = draw_count_overlay(draw_detections(frame, detections), counts, copy_frame=False)
        if stable_decision is not None:
            annotated = _draw_stabilization_overlay(annotated, stable_decision, copy_frame=False)
        frame_path = session_paths.frames_dir / f"frame_{frame_index:06d}.png"
        save_image(frame_path, annotated)

    event = {
        "frame_index": frame_index,
        "counts": counts,
        "detections": [detection.to_dict() for detection in detections],
        "annotated_frame": None if frame_path is None else str(frame_path.resolve()),
        "crops": crop_records,
        "stabilized_label": None if stable_decision is None else stable_decision.label,
        "stabilized_votes": None if stable_decision is None else stable_decision.votes,
        "stabilized_history": None if stable_decision is None else stable_decision.history,
    }
    return detections, counts, event


def main() -> int:
    args = _parser().parse_args()
    _validate_args(args)
    session_paths = _create_session_paths(args.output_dir)
    detector = _build_detector(args)
    if args.export_label_template:
        target = _export_label_template(detector, args.export_label_template)
        print(f"exported_label_template={target.resolve()}")
        return 0
    stabilizer = DetectionStabilizer(args.stabilization_window, args.stabilization_threshold) if args.stabilization_window else None
    command_sink = None if not args.serial_port else SerialCommandSink(args.serial_port, args.serial_baudrate, args.serial_timeout)
    event_dispatcher = StableEventDispatcher(
        cooldown_frames=args.stable_event_cooldown,
        event_log_path=session_paths.stable_events_jsonl,
        command_template=args.command_template,
        command_sink=command_sink,
    )
    camera_config = BaslerCameraConfig(
        camera_serial=args.camera_serial,
        camera_index=args.camera_index,
        width=args.width,
        height=args.height,
        exposure_us=args.exposure_us,
        gain=args.gain,
        fps=args.fps,
        pixel_format=args.pixel_format,
    )

    frame_events: list[dict[str, Any]] = []
    total_counts: Counter[str] = Counter()
    frame_index = 0
    preview_fps = 0.0

    try:
        with BaslerCamera(camera_config) as camera:
            while True:
                frame = camera.read()
                frame_index += 1
                loop_started_at = time.perf_counter()
                detections, counts, event = process_frame(
                    frame=frame,
                    detector=detector,
                    session_paths=session_paths,
                    frame_index=frame_index,
                    save_crops=args.save_crops,
                    save_frames=args.save_frames,
                    stabilizer=stabilizer,
                )
                stable_decision = None if stabilizer is None else StableDetectionDecision(
                    label=event["stabilized_label"],
                    votes=int(event["stabilized_votes"] or 0),
                    history=list(event["stabilized_history"] or []),
                )
                emitted_event = event_dispatcher.handle(frame_index, stable_decision, counts)
                event["stable_event"] = emitted_event
                frame_events.append(event)
                total_counts.update(event["counts"])
                inference_ms = (time.perf_counter() - loop_started_at) * 1000.0
                loop_seconds = max(time.perf_counter() - loop_started_at, 1e-6)
                instant_fps = 1.0 / loop_seconds
                preview_fps = instant_fps if preview_fps <= 0.0 else (preview_fps * 0.85) + (instant_fps * 0.15)

                if not args.no_preview:
                    preview = _draw_preview_detections(frame, detections, args.preview_max_width)
                    preview = draw_count_overlay(preview, counts, copy_frame=False)
                    if stable_decision is not None:
                        preview = _draw_stabilization_overlay(preview, stable_decision, copy_frame=False)
                    preview = _draw_status_overlay(preview, preview_fps=preview_fps, inference_ms=inference_ms, copy_frame=False)
                    cv2.imshow("Basler Live Detection", preview)
                    key = cv2.waitKey(1) & 0xFF
                    if key == ord("q") or key == 27:
                        break
                    if key == ord("s"):
                        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                        save_image(session_paths.manual_dir / f"manual_{stamp}.png", frame)
                    if key == ord("r"):
                        try:
                            reloaded = _reload_detector_class_names(detector, args.labels)
                        except Exception as exc:
                            print(f"reload_labels_error={exc}")
                        else:
                            if reloaded is not None:
                                print(f"reloaded_labels={reloaded}")

                if args.max_frames is not None and frame_index >= args.max_frames:
                    break
    finally:
        event_dispatcher.close()
        cv2.destroyAllWindows()

    detections_payload = {
        "preset": None if args.preset == "none" else args.preset,
        "backend": args.backend,
        "model": str(Path(args.model).resolve()),
        "labels": None if args.labels is None else str(Path(args.labels).resolve()),
        "frames_processed": frame_index,
        "stabilization_window": args.stabilization_window,
        "stabilization_threshold": args.stabilization_threshold,
        "stable_event_cooldown": args.stable_event_cooldown,
        "stable_events_jsonl": str(session_paths.stable_events_jsonl.resolve()),
        "stable_events_emitted": event_dispatcher.event_count,
        "command_template": args.command_template,
        "serial_port": args.serial_port,
        "events": frame_events,
    }
    summary_payload = {
        "preset": None if args.preset == "none" else args.preset,
        "backend": args.backend,
        "frames_processed": frame_index,
        "total_counts": dict(total_counts),
        "stable_events_emitted": event_dispatcher.event_count,
        "stable_events": list(event_dispatcher.emitted_events),
        "output_dir": str(session_paths.root.resolve()),
    }
    save_json(session_paths.detections_json, detections_payload)
    save_json(session_paths.summary_json, summary_payload)

    print(f"output_dir={session_paths.root.resolve()}")
    print(f"frames_processed={frame_index}")
    print(f"detections_json={session_paths.detections_json.resolve()}")
    print(f"summary_json={session_paths.summary_json.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import cv2
import numpy as np

from .cell_classes import WBC_5_CLASS_NAMES
from .io_utils import read_image, save_image, save_json
from .text_overlay import get_text_size, put_text


DEFAULT_CELL_CLASS_NAMES: list[str] = list(WBC_5_CLASS_NAMES)
DEFAULT_INPUT_SIZE = 512
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
CLASS_COLORS: list[tuple[int, int, int]] = [
    (80, 180, 70),
    (60, 120, 255),
    (255, 180, 60),
    (180, 90, 255),
    (255, 90, 120),
]


@dataclass(frozen=True, slots=True)
class BoundingBox:
    x1: int
    y1: int
    x2: int
    y2: int

    def as_xyxy(self) -> tuple[int, int, int, int]:
        return self.x1, self.y1, self.x2, self.y2

    def to_dict(self) -> dict[str, int]:
        return {
            "x1": self.x1,
            "y1": self.y1,
            "x2": self.x2,
            "y2": self.y2,
        }


@dataclass(frozen=True, slots=True)
class CellDetection:
    class_id: int
    label: str
    confidence: float
    bbox: BoundingBox

    def to_dict(self) -> dict[str, object]:
        return {
            "class_id": self.class_id,
            "label": self.label,
            "confidence": round(self.confidence, 6),
            "bbox": self.bbox.to_dict(),
        }


@dataclass(slots=True)
class CellIdentificationConfig:
    model_path: str | Path
    source: str | Path
    output_dir: str | Path = Path("output") / "cell_identification"
    backend: Literal["auto", "ultralytics", "onnx"] = "auto"
    class_file: str | Path | None = None
    confidence: float = 0.35
    class_confidence: str | tuple[float, ...] | list[float] | None = None
    iou_threshold: float = 0.45
    imgsz: int | tuple[int, int] = DEFAULT_INPUT_SIZE
    device: str | int | None = None
    prefer_gpu: bool = True
    json_output: str | Path | None = None

    def __post_init__(self) -> None:
        self.model_path = Path(self.model_path)
        self.source = Path(self.source)
        self.output_dir = Path(self.output_dir)
        self.backend = str(self.backend).lower()  # type: ignore[assignment]
        self.confidence = float(min(1.0, max(0.01, self.confidence)))
        self.iou_threshold = float(min(1.0, max(0.01, self.iou_threshold)))
        if isinstance(self.imgsz, tuple):
            self.imgsz = (max(32, int(self.imgsz[0])), max(32, int(self.imgsz[1])))
        else:
            self.imgsz = max(32, int(self.imgsz))
        if self.class_file is not None:
            self.class_file = Path(self.class_file)
        if self.json_output is not None:
            self.json_output = Path(self.json_output)
        if self.backend not in {"auto", "ultralytics", "onnx"}:
            raise ValueError(f"Unsupported backend: {self.backend}")


@dataclass(slots=True)
class CellIdentificationResult:
    success: bool
    backend: str
    model_path: str
    source: str
    output_dir: str
    json_output_path: str
    images_processed: int
    total_detections: int
    message: str
    results: list[dict[str, object]] = field(default_factory=list)


def _import_ultralytics() -> Any:
    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise ImportError(
            "Ultralytics is not installed. Activate the project environment and run "
            "`pip install \"ultralytics>=8.3\"`."
        ) from exc
    return YOLO


def _import_onnxruntime() -> Any:
    try:
        import onnxruntime as ort
    except ImportError as exc:
        raise ImportError(
            "ONNX Runtime is not installed. Install `onnxruntime` for CPU inference or "
            "`onnxruntime-gpu` for CUDA inference."
        ) from exc
    return ort


def _normalize_class_names(names: Any) -> list[str]:
    if isinstance(names, dict):
        ordered_keys = sorted(names, key=lambda key: int(key) if str(key).isdigit() else str(key))
        return [str(names[key]) for key in ordered_keys]
    if isinstance(names, (list, tuple)):
        return [str(name) for name in names]
    return []


def _strip_optional_class_index(line: str) -> str:
    parts = line.strip().split(maxsplit=1)
    if len(parts) == 2 and parts[0].isdigit():
        return parts[1].strip()
    return line.strip()


def _parse_yaml_names(text: str) -> list[str]:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("names:"):
            continue
        value = stripped.split(":", 1)[1].strip()
        if value:
            parsed = ast.literal_eval(value)
            return _normalize_class_names(parsed)

        names: list[str] = []
        for child in lines[index + 1:]:
            child_stripped = child.strip()
            if not child_stripped:
                continue
            if child_stripped.startswith("-"):
                names.append(child_stripped[1:].strip().strip("'\""))
                continue
            if ":" in child_stripped and child[: len(child) - len(child.lstrip())] == "":
                break
        return names
    return []


def load_class_names(class_file: str | Path | None = None) -> list[str]:
    if class_file is None:
        return list(DEFAULT_CELL_CLASS_NAMES)

    path = Path(class_file)
    text: str | None = None
    for encoding in ("utf-8-sig", "utf-8", "cp950", "big5"):
        try:
            text = path.read_text(encoding=encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        text = path.read_text(encoding="utf-8", errors="replace")

    if path.suffix.lower() in {".yaml", ".yml"}:
        class_names = _parse_yaml_names(text)
        if not class_names:
            raise ValueError(f"No `names` entries were found in {path}")
        return class_names

    class_names = [
        _strip_optional_class_index(line)
        for line in text.splitlines()
        if line.strip()
    ]
    if not class_names:
        raise ValueError(f"No class names were found in {path}")
    return class_names


def collect_image_paths(source: str | Path) -> list[Path]:
    source_path = Path(source)
    if source_path.is_file():
        return [source_path]
    if not source_path.exists():
        raise FileNotFoundError(f"Source path does not exist: {source_path}")

    image_paths = [
        path
        for path in sorted(source_path.rglob("*"))
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    ]
    if not image_paths:
        raise FileNotFoundError(f"No image files were found in {source_path}")
    return image_paths


def draw_detections(
    frame: np.ndarray,
    detections: list[CellDetection],
    thickness: int = 2,
) -> np.ndarray:
    annotated = frame.copy()
    for detection in detections:
        draw_color = CLASS_COLORS[detection.class_id % len(CLASS_COLORS)] if CLASS_COLORS else (0, 255, 0)
        x1, y1, x2, y2 = detection.bbox.as_xyxy()
        label = f"{detection.label} {detection.confidence:.2f}"

        cv2.rectangle(annotated, (x1, y1), (x2, y2), draw_color, thickness)
        text_width, text_height, baseline = get_text_size(label, font_scale=0.6, thickness=2)
        box_top = max(y1 - text_height - baseline - 8, 0)
        box_bottom = box_top + text_height + baseline + 8

        cv2.rectangle(annotated, (x1, box_top), (x1 + text_width + 10, box_bottom), draw_color, -1)
        put_text(
            annotated,
            label,
            (x1 + 5, box_bottom - baseline - 4),
            0.6,
            (0, 0, 0),
            2,
        )
    return annotated


def _normalize_device(device: str | int | None, prefer_gpu: bool) -> str:
    if isinstance(device, int):
        return "cuda"
    if device is None:
        return "cuda" if prefer_gpu else "cpu"
    value = str(device).strip().lower()
    if value in {"0", "cuda", "gpu"}:
        return "cuda"
    return "cpu"


def parse_class_confidence_thresholds(
    value: str | tuple[float, ...] | list[float] | None,
    class_count: int,
) -> tuple[float, ...] | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        parts = [float(item.strip()) for item in stripped.split(",")]
    else:
        parts = [float(item) for item in value]
    if len(parts) != class_count:
        raise ValueError(f"class confidence threshold count must be {class_count}, got {len(parts)}")
    return tuple(float(min(1.0, max(0.01, item))) for item in parts)


def _create_onnx_session(
    model_path: str | Path,
    device: str | int | None = None,
    prefer_gpu: bool = True,
) -> tuple[Any, list[str]]:
    ort = _import_onnxruntime()
    if hasattr(ort, "preload_dlls"):
        try:
            ort.preload_dlls()
        except Exception:
            pass

    normalized_device = _normalize_device(device, prefer_gpu)
    preferred_providers: list[Any]
    if normalized_device == "cuda":
        preferred_providers = [
            ("CUDAExecutionProvider", {"device_id": 0}),
            "CPUExecutionProvider",
        ]
    else:
        preferred_providers = ["CPUExecutionProvider"]

    try:
        session = ort.InferenceSession(str(model_path), providers=preferred_providers)
    except Exception:
        session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
    return session, session.get_providers()


def _letterbox(
    image: np.ndarray,
    new_shape: int | tuple[int, int] = DEFAULT_INPUT_SIZE,
    color: tuple[int, int, int] = (114, 114, 114),
) -> tuple[np.ndarray, float, tuple[float, float]]:
    if isinstance(new_shape, int):
        new_shape = (new_shape, new_shape)

    height, width = image.shape[:2]
    new_height, new_width = new_shape
    scale = min(new_width / width, new_height / height)
    resized_width = int(round(width * scale))
    resized_height = int(round(height * scale))
    resized = cv2.resize(image, (resized_width, resized_height), interpolation=cv2.INTER_LINEAR)

    dw = new_width - resized_width
    dh = new_height - resized_height
    left = int(round(dw / 2 - 0.1))
    right = int(round(dw / 2 + 0.1))
    top = int(round(dh / 2 - 0.1))
    bottom = int(round(dh / 2 + 0.1))

    bordered = cv2.copyMakeBorder(
        resized,
        top,
        bottom,
        left,
        right,
        cv2.BORDER_CONSTANT,
        value=color,
    )
    return bordered, scale, (left, top)


def _preprocess_onnx(
    frame: np.ndarray,
    input_size: int | tuple[int, int] = DEFAULT_INPUT_SIZE,
) -> tuple[np.ndarray, float, tuple[float, float]]:
    image, scale, pad = _letterbox(frame, input_size)
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    image = image.transpose(2, 0, 1)
    image = np.ascontiguousarray(image, dtype=np.float32) / 255.0
    return np.expand_dims(image, axis=0), scale, pad


def _compute_iou(box: np.ndarray, boxes: np.ndarray) -> np.ndarray:
    x1 = np.maximum(box[0], boxes[:, 0])
    y1 = np.maximum(box[1], boxes[:, 1])
    x2 = np.minimum(box[2], boxes[:, 2])
    y2 = np.minimum(box[3], boxes[:, 3])

    inter_w = np.maximum(0.0, x2 - x1)
    inter_h = np.maximum(0.0, y2 - y1)
    inter_area = inter_w * inter_h

    box_area = max((box[2] - box[0]) * (box[3] - box[1]), 0.0)
    boxes_area = np.maximum((boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1]), 0.0)
    union_area = box_area + boxes_area - inter_area + 1e-7
    return inter_area / union_area


def _nms(boxes: np.ndarray, scores: np.ndarray, iou_threshold: float) -> list[int]:
    if boxes.size == 0:
        return []

    order = scores.argsort()[::-1]
    keep: list[int] = []
    while order.size > 0:
        index = int(order[0])
        keep.append(index)
        if order.size == 1:
            break
        remaining = order[1:]
        ious = _compute_iou(boxes[index], boxes[remaining])
        order = remaining[ious < iou_threshold]
    return keep


def _xywh_to_xyxy(boxes: np.ndarray) -> np.ndarray:
    converted = np.empty_like(boxes)
    converted[:, 0] = boxes[:, 0] - boxes[:, 2] / 2
    converted[:, 1] = boxes[:, 1] - boxes[:, 3] / 2
    converted[:, 2] = boxes[:, 0] + boxes[:, 2] / 2
    converted[:, 3] = boxes[:, 1] + boxes[:, 3] / 2
    return converted


def _scale_boxes(
    boxes: np.ndarray,
    original_shape: tuple[int, int],
    scale: float,
    pad: tuple[float, float],
) -> np.ndarray:
    scaled = boxes.copy()
    scaled[:, [0, 2]] -= pad[0]
    scaled[:, [1, 3]] -= pad[1]
    scaled[:, :4] /= scale

    height, width = original_shape
    scaled[:, [0, 2]] = scaled[:, [0, 2]].clip(0, width)
    scaled[:, [1, 3]] = scaled[:, [1, 3]].clip(0, height)
    return scaled


def _decode_onnx_output(
    output: np.ndarray,
    class_names: list[str],
    confidence: float,
    class_confidence: tuple[float, ...] | None,
    iou_threshold: float,
    original_shape: tuple[int, int],
    scale: float,
    pad: tuple[float, float],
) -> list[CellDetection]:
    predictions = np.asarray(output)
    predictions = np.squeeze(predictions)
    if predictions.ndim == 3:
        predictions = predictions[0]

    expected_channels = len(class_names) + 4
    if predictions.ndim != 2:
        raise ValueError(f"Unexpected ONNX output shape: {predictions.shape}")

    if predictions.shape[0] in {expected_channels, expected_channels + 1}:
        predictions = predictions.T

    if predictions.shape[1] == len(class_names) + 4:
        boxes = predictions[:, :4]
        class_scores = predictions[:, 4:]
    elif predictions.shape[1] == len(class_names) + 5:
        boxes = predictions[:, :4]
        objectness = predictions[:, 4:5]
        class_scores = predictions[:, 5:] * objectness
    else:
        raise ValueError(f"Unexpected ONNX output shape: {predictions.shape}")

    class_ids = class_scores.argmax(axis=1)
    scores = class_scores[np.arange(class_scores.shape[0]), class_ids]
    if class_confidence:
        thresholds = np.asarray(class_confidence, dtype=np.float32)
        valid = scores >= thresholds[class_ids]
    else:
        valid = scores >= confidence
    if not np.any(valid):
        return []

    boxes = _xywh_to_xyxy(boxes[valid])
    boxes = _scale_boxes(boxes, original_shape, scale, pad)
    scores = scores[valid]
    class_ids = class_ids[valid]

    keep_indices: list[int] = []
    for class_id in sorted(set(class_ids.tolist())):
        class_mask = np.where(class_ids == class_id)[0]
        kept = _nms(boxes[class_mask], scores[class_mask], iou_threshold)
        keep_indices.extend(class_mask[index] for index in kept)

    keep_indices.sort(key=lambda index: float(scores[index]), reverse=True)
    detections: list[CellDetection] = []
    for index in keep_indices:
        x1, y1, x2, y2 = [int(round(value)) for value in boxes[index].tolist()]
        class_id = int(class_ids[index])
        label = class_names[class_id] if 0 <= class_id < len(class_names) else str(class_id)
        detections.append(
            CellDetection(
                class_id=class_id,
                label=label,
                confidence=float(scores[index]),
                bbox=BoundingBox(x1=x1, y1=y1, x2=x2, y2=y2),
            )
        )
    return detections


class CellIdentificationDetector:
    def __init__(
        self,
        model_path: str | Path,
        backend: str | None = None,
        class_names: list[str] | None = None,
        confidence: float = 0.35,
        class_confidence: str | tuple[float, ...] | list[float] | None = None,
        iou_threshold: float = 0.45,
        imgsz: int | tuple[int, int] = DEFAULT_INPUT_SIZE,
        device: str | int | None = None,
        prefer_gpu: bool = True,
    ) -> None:
        self.model_path = Path(model_path)
        self.backend = (backend or self._infer_backend(self.model_path)).lower()
        self.class_names = list(class_names) if class_names else []
        self.confidence = float(confidence)
        self.class_confidence = parse_class_confidence_thresholds(class_confidence, len(self.class_names)) if self.class_names else None
        self.iou_threshold = float(iou_threshold)
        self.imgsz = imgsz
        self.device = device
        self.prefer_gpu = prefer_gpu

        if self.backend == "ultralytics":
            YOLO = _import_ultralytics()
            self.model = YOLO(str(self.model_path))
            self.providers: list[str] = []
            if not self.class_names:
                self.class_names = _normalize_class_names(getattr(self.model, "names", []))
            if not self.class_names:
                self.class_names = list(DEFAULT_CELL_CLASS_NAMES)
            self.class_confidence = parse_class_confidence_thresholds(class_confidence, len(self.class_names))
        elif self.backend == "onnx":
            if not self.class_names:
                self.class_names = list(DEFAULT_CELL_CLASS_NAMES)
            self.class_confidence = parse_class_confidence_thresholds(class_confidence, len(self.class_names))
            self.session, self.providers = _create_onnx_session(
                model_path=self.model_path,
                device=self.device,
                prefer_gpu=self.prefer_gpu,
            )
            self.input_name = self.session.get_inputs()[0].name
        else:
            raise ValueError("backend must be 'ultralytics' or 'onnx'")

    @staticmethod
    def _infer_backend(model_path: Path) -> str:
        return "onnx" if model_path.suffix.lower() == ".onnx" else "ultralytics"

    def predict(self, frame: np.ndarray) -> list[CellDetection]:
        if self.backend == "onnx":
            return self._predict_onnx(frame)
        return self._predict_ultralytics(frame)

    def _predict_ultralytics(self, frame: np.ndarray) -> list[CellDetection]:
        predict_confidence = min(self.class_confidence) if self.class_confidence else self.confidence
        results = self.model.predict(
            source=frame,
            conf=predict_confidence,
            iou=self.iou_threshold,
            device=self.device,
            verbose=False,
        )
        result = results[0]
        detections: list[CellDetection] = []
        for box in result.boxes:
            cls_id = int(box.cls.item())
            confidence = float(box.conf.item())
            threshold = self.class_confidence[cls_id] if self.class_confidence and 0 <= cls_id < len(self.class_confidence) else self.confidence
            if confidence < threshold:
                continue
            x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
            if 0 <= cls_id < len(self.class_names):
                label = self.class_names[cls_id]
            else:
                label = str(result.names.get(cls_id, cls_id))
            detections.append(
                CellDetection(
                    class_id=cls_id,
                    label=label,
                    confidence=confidence,
                    bbox=BoundingBox(x1=x1, y1=y1, x2=x2, y2=y2),
                )
            )
        return detections

    def _predict_onnx(self, frame: np.ndarray) -> list[CellDetection]:
        tensor, scale, pad = _preprocess_onnx(frame, self.imgsz)
        outputs = self.session.run(None, {self.input_name: tensor})
        return _decode_onnx_output(
            output=outputs[0],
            class_names=self.class_names,
            confidence=self.confidence,
            class_confidence=self.class_confidence,
            iou_threshold=self.iou_threshold,
            original_shape=frame.shape[:2],
            scale=scale,
            pad=pad,
        )

    def predict_and_annotate(self, frame: np.ndarray) -> tuple[list[CellDetection], np.ndarray]:
        detections = self.predict(frame)
        annotated = draw_detections(frame, detections)
        return detections, annotated

    def predict_image(self, image_path: str | Path) -> tuple[list[CellDetection], np.ndarray]:
        image = read_image(image_path)
        return self.predict_and_annotate(image)


def run_cell_identification(config: CellIdentificationConfig) -> CellIdentificationResult:
    image_paths = collect_image_paths(config.source)
    class_names = load_class_names(config.class_file) if config.class_file is not None else None
    detector = CellIdentificationDetector(
        model_path=config.model_path,
        backend=None if config.backend == "auto" else config.backend,
        class_names=class_names,
        confidence=config.confidence,
        class_confidence=config.class_confidence,
        iou_threshold=config.iou_threshold,
        imgsz=config.imgsz,
        device=config.device,
        prefer_gpu=config.prefer_gpu,
    )

    config.output_dir.mkdir(parents=True, exist_ok=True)
    is_single_image = Path(config.source).is_file()
    annotated_dir = config.output_dir if is_single_image else config.output_dir / "annotated"
    annotated_dir.mkdir(parents=True, exist_ok=True)
    json_output = Path(config.json_output) if config.json_output is not None else (
        config.output_dir / f"{Path(config.source).stem}_result.json"
        if is_single_image
        else config.output_dir / "results.json"
    )

    results: list[dict[str, object]] = []
    total_detections = 0
    for image_path in image_paths:
        detections, annotated = detector.predict_image(image_path)
        output_path = (
            annotated_dir / f"{image_path.stem}_pred{image_path.suffix}"
            if is_single_image
            else annotated_dir / image_path.name
        )
        save_image(output_path, annotated)
        detection_rows = [detection.to_dict() for detection in detections]
        total_detections += len(detection_rows)
        results.append(
            {
                "image": str(image_path.resolve()),
                "annotated_image": str(output_path.resolve()),
                "detections": detection_rows,
            }
        )

    label_counts: dict[str, int] = {}
    for item in results:
        for detection in item["detections"]:
            label = str(detection["label"])
            label_counts[label] = label_counts.get(label, 0) + 1

    payload = {
        "model": str(config.model_path.resolve()),
        "backend": detector.backend,
        "providers": list(getattr(detector, "providers", [])),
        "source": str(Path(config.source).resolve()),
        "images_processed": len(results),
        "total_detections": total_detections,
        "label_counts": label_counts,
        "results": results,
    }
    save_json(json_output, payload)

    return CellIdentificationResult(
        success=True,
        backend=detector.backend,
        model_path=str(config.model_path.resolve()),
        source=str(Path(config.source).resolve()),
        output_dir=str(config.output_dir.resolve()),
        json_output_path=str(json_output.resolve()),
        images_processed=len(results),
        total_detections=total_detections,
        message="Cell identification completed successfully",
        results=results,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run white-blood-cell or cell identification on an image or folder.")
    parser.add_argument("--model", required=True, help="Path to trained model weights (.pt or .onnx)")
    parser.add_argument("--source", required=True, help="Image file or directory to process")
    parser.add_argument(
        "--backend",
        choices=("auto", "ultralytics", "onnx"),
        default="auto",
        help="Auto selects ONNX for .onnx files and Ultralytics for .pt files.",
    )
    parser.add_argument("--class-file", default=None, help="Optional class name file. Defaults to 5 WBC classes.")
    parser.add_argument("--confidence", type=float, default=0.35, help="Confidence threshold.")
    parser.add_argument("--class-confidence", default=None, help="Optional per-class thresholds, e.g. WBC,RBC,Platelets as `0.25,0.55,0.45`.")
    parser.add_argument("--iou-threshold", type=float, default=0.45, help="NMS IoU threshold.")
    parser.add_argument("--imgsz", type=int, default=DEFAULT_INPUT_SIZE, help="Input size used for ONNX inference.")
    parser.add_argument("--output-dir", default=str(Path("output") / "cell_identification"), help="Output directory.")
    parser.add_argument("--json-output", default=None, help="Optional JSON output path.")
    parser.add_argument("--device", default=None, help="Optional device override, for example cpu or 0.")
    parser.add_argument("--cpu", action="store_true", help="Force CPU execution where supported.")
    return parser


def main() -> int:
    args = _parser().parse_args()
    config = CellIdentificationConfig(
        model_path=args.model,
        source=args.source,
        output_dir=args.output_dir,
        backend=args.backend,
        class_file=args.class_file,
        confidence=args.confidence,
        class_confidence=args.class_confidence,
        iou_threshold=args.iou_threshold,
        imgsz=args.imgsz,
        device="cpu" if args.cpu else args.device,
        prefer_gpu=not args.cpu,
        json_output=args.json_output,
    )
    result = run_cell_identification(config)
    print(result.message)
    print(f"backend={result.backend}")
    print(f"images_processed={result.images_processed}")
    print(f"total_detections={result.total_detections}")
    print(f"output_dir={result.output_dir}")
    print(f"json_output_path={result.json_output_path}")
    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())

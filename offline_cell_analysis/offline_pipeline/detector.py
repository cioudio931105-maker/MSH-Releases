from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

import numpy as np

from .models import Detection, FrameRecord
from .utils import ensure_dir, normalize_cell_class


def write_detections_csv(detections: Iterable[Detection], csv_path: Path) -> None:
    ensure_dir(csv_path.parent)
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "frame_id",
                "source_frame_index",
                "frame_path",
                "detection_index",
                "class_id",
                "class_name",
                "confidence",
                "x1",
                "y1",
                "x2",
                "y2",
                "center_x",
                "center_y",
                "track_id",
                "is_unique_best",
            ],
        )
        writer.writeheader()
        for det in detections:
            writer.writerow(
                {
                    "frame_id": det.frame_id,
                    "source_frame_index": det.source_frame_index,
                    "frame_path": str(det.frame_path),
                    "detection_index": det.detection_index,
                    "class_id": det.class_id,
                    "class_name": det.class_name,
                    "confidence": f"{det.confidence:.6f}",
                    "x1": f"{det.x1:.2f}",
                    "y1": f"{det.y1:.2f}",
                    "x2": f"{det.x2:.2f}",
                    "y2": f"{det.y2:.2f}",
                    "center_x": f"{det.center_x:.2f}",
                    "center_y": f"{det.center_y:.2f}",
                    "track_id": "" if det.track_id is None else det.track_id,
                    "is_unique_best": int(det.is_unique_best),
                }
            )


class YoloV8Detector:
    def __init__(
        self,
        model_path: Path,
        *,
        confidence: float = 0.25,
        iou: float = 0.45,
        device: str | None = None,
        imgsz: int = 640,
    ) -> None:
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise RuntimeError(
                "ultralytics is required for YOLOv8 inference. Install with: pip install ultralytics"
            ) from exc

        self.model_path = Path(model_path)
        if not self.model_path.exists():
            raise FileNotFoundError(f"YOLO model not found: {self.model_path}")
        self.model = YOLO(str(self.model_path))
        self.confidence = float(confidence)
        self.iou = float(iou)
        self.device = self._resolve_device(device)
        self.imgsz = int(imgsz)

    @staticmethod
    def _resolve_device(device: str | None) -> str | None:
        if device in {None, "", "auto"}:
            try:
                import torch

                return "0" if torch.cuda.is_available() else "cpu"
            except Exception:
                return "cpu"
        requested = str(device).strip()
        normalized = requested.lower()
        wants_cuda = normalized == "cuda" or normalized.startswith("cuda:") or normalized.isdigit()
        if wants_cuda:
            try:
                import torch

                if not torch.cuda.is_available():
                    print(
                        f"CUDA device '{requested}' was requested, but this Python environment has no CUDA. "
                        "Falling back to CPU.",
                        flush=True,
                    )
                    return "cpu"
            except Exception as exc:
                print(
                    f"CUDA device '{requested}' was requested, but CUDA availability could not be checked: {exc}. "
                    "Falling back to CPU.",
                    flush=True,
                )
                return "cpu"
        return "0" if wants_cuda else requested

    @property
    def _use_half_precision(self) -> bool:
        return self.device not in {None, "cpu"}

    def predict_frames(self, frame_records: list[FrameRecord], *, batch_size: int = 8) -> list[Detection]:
        saved_records = [record for record in frame_records if record.saved and record.path is not None]
        detections: list[Detection] = []
        det_index = 0

        for start in range(0, len(saved_records), max(1, int(batch_size))):
            batch_records = saved_records[start : start + max(1, int(batch_size))]
            batch_paths = [str(record.path) for record in batch_records if record.path is not None]
            if not batch_paths:
                continue

            results = self.model.predict(
                source=batch_paths,
                conf=self.confidence,
                iou=self.iou,
                imgsz=self.imgsz,
                device=self.device,
                quantize=16 if self._use_half_precision else None,
                verbose=False,
                stream=False,
            )

            for record, result in zip(batch_records, results):
                names = getattr(result, "names", None) or getattr(self.model, "names", {}) or {}
                boxes = getattr(result, "boxes", None)
                if boxes is None or len(boxes) == 0:
                    continue

                xyxy = boxes.xyxy.detach().cpu().numpy()
                confs = boxes.conf.detach().cpu().numpy()
                classes = boxes.cls.detach().cpu().numpy().astype(int)

                for box, conf, class_id in zip(xyxy, confs, classes):
                    x1, y1, x2, y2 = [float(value) for value in np.asarray(box).tolist()]
                    raw_name = names.get(int(class_id), str(class_id)) if isinstance(names, dict) else str(class_id)
                    class_name = normalize_cell_class(str(raw_name))
                    det_index += 1
                    detections.append(
                        Detection(
                            frame_id=record.frame_id,
                            source_frame_index=record.source_frame_index,
                            frame_path=Path(record.path),
                            detection_index=det_index,
                            class_id=int(class_id),
                            class_name=class_name,
                            confidence=float(conf),
                            x1=x1,
                            y1=y1,
                            x2=x2,
                            y2=y2,
                            center_x=(x1 + x2) / 2.0,
                            center_y=(y1 + y2) / 2.0,
                        )
                    )

        return detections

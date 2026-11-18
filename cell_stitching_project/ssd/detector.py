from __future__ import annotations

from pathlib import Path

import cv2

from ..cell_identification import BoundingBox, CellDetection
from .common import create_ssd, create_ssd_predictor, load_label_file, resolve_device


class SSDDetector:
    def __init__(
        self,
        net_type: str,
        model_path: str | Path,
        label_file: str | Path,
        confidence: float = 0.35,
        iou_threshold: float = 0.45,
        candidate_size: int = 200,
        top_k: int = 10,
        use_cuda: bool = True,
        mb2_width_mult: float = 1.0,
    ) -> None:
        self.model_path = Path(model_path)
        self.class_names = load_label_file(label_file)
        self.net_type = net_type
        self.device = resolve_device(use_cuda=use_cuda)
        self.top_k = int(top_k)
        self.confidence = float(confidence)

        net, _ = create_ssd(
            net_type=net_type,
            num_classes=len(self.class_names),
            is_test=True,
            mb2_width_mult=mb2_width_mult,
        )
        net.load(str(self.model_path))
        net.to(self.device)
        self.predictor = create_ssd_predictor(
            net_type=net_type,
            net=net,
            device=self.device,
            iou_threshold=iou_threshold,
            candidate_size=candidate_size,
        )

    def predict(self, frame_bgr):
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        boxes, labels, probs = self.predictor.predict(frame_rgb, self.top_k, self.confidence)
        detections: list[CellDetection] = []
        for index in range(boxes.size(0)):
            class_id = int(labels[index].item())
            if class_id <= 0:
                continue
            x1, y1, x2, y2 = [int(value) for value in boxes[index].tolist()]
            detections.append(
                CellDetection(
                    class_id=class_id,
                    label=self.class_names[class_id] if class_id < len(self.class_names) else str(class_id),
                    confidence=float(probs[index].item()),
                    bbox=BoundingBox(x1=x1, y1=y1, x2=x2, y2=y2),
                )
            )
        return detections


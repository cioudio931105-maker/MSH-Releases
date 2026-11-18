"""
將 YOLOv8 偵測與 EfficientNet 分類疊加，用偵測框切圖再做分類。
使用範例（專案根目錄執行）:
  python scripts/detect_classify_ensemble.py --source data/sample.jpg \
         --yolo_model models/yolov8n.pt \
         --effnet_weights models/efficientnet_b0.pth \
         --labels data/labels.txt
"""

from __future__ import annotations

from msh_model_policy import require_local_model

import argparse
import os
from pathlib import Path
from typing import List, Optional, Sequence

import cv2
import numpy as np
import torch
from torchvision import transforms
from torchvision.models import efficientnet_b0, EfficientNet_B0_Weights
from ultralytics import YOLO


def load_labels(labels_path: Optional[str]) -> List[str]:
    if not labels_path:
        # 沒給 labels 時，預設 1000 類（ImageNet），名稱用索引代替
        return [str(i) for i in range(1000)]
    with open(labels_path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def load_effnet(weights_path: Optional[str], num_classes: Optional[int], device: str):
    """
    載入使用者提供的本機 EfficientNet-B0 權重，不下載預訓練模型。
    若有自訂權重，接受 torch.save(state_dict) 或含 state_dict 的 checkpoint。
    """
    weights_path = require_local_model(weights_path)
    model = efficientnet_b0(weights=None)
    if num_classes and num_classes != model.classifier[1].out_features:
        # 自訂類別數時替換最後全連接層
        model.classifier[1] = torch.nn.Linear(model.classifier[1].in_features, num_classes)
    state = torch.load(weights_path, map_location=device)
    # 可接受純 state_dict 或含 'state_dict' 的 checkpoint
    if isinstance(state, dict) and "state_dict" in state:
        state = {k.replace("model.", "").replace("module.", ""): v for k, v in state["state_dict"].items()}
    model.load_state_dict(state, strict=False)

    model.eval().to(device)
    return model


def preprocess(img_bgr: np.ndarray, size: int = 224) -> torch.Tensor:
    rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    pil = transforms.functional.to_pil_image(rgb)
    tfm = transforms.Compose(
        [
            transforms.Resize(size),
            transforms.CenterCrop(size),
            transforms.ToTensor(),
            transforms.Normalize(mean=EfficientNet_B0_Weights.IMAGENET1K_V1.meta["mean"],
                                 std=EfficientNet_B0_Weights.IMAGENET1K_V1.meta["std"]),
        ]
    )
    return tfm(pil)


def ensemble_conf(det_conf: float, cls_conf: float) -> float:
    # 幾何平均：平衡偵測與分類的置信度，避免單側主導
    return float(np.sqrt(det_conf * cls_conf))


def run_ensemble(
    source: str,
    yolo_model_path: str,
    effnet_weights: Optional[str],
    labels_path: Optional[str],
    conf_threshold: float,
    save_dir: str,
    device: str = "cpu",
):
    effnet_weights = require_local_model(effnet_weights)
    os.makedirs(save_dir, exist_ok=True)
    labels = load_labels(labels_path)
    num_classes = len(labels) if labels_path else None

    print(f"Loading YOLO model: {yolo_model_path}")
    detector = YOLO(require_local_model(yolo_model_path))

    print(f"Loading local EfficientNet-B0 weights: {effnet_weights}")
    classifier = load_effnet(effnet_weights, num_classes, device)

    img = cv2.imread(source)
    if img is None:
        raise FileNotFoundError(f"Cannot read image: {source}")

    print(f"Running detection on {source}")
    det_results = detector(img, conf=conf_threshold, verbose=False)
    if len(det_results) == 0 or len(det_results[0].boxes) == 0:
        print("No objects detected.")
        return

    boxes = det_results[0].boxes
    annotated = img.copy()
    results = []

    for idx, box in enumerate(boxes):
        x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
        det_conf = float(box.conf[0])
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(img.shape[1], x2), min(img.shape[0], y2)
        crop = img[y1:y2, x1:x2]  # 切出的框送去分類
        if crop.size == 0:
            continue

        with torch.no_grad():
            inp = preprocess(crop).unsqueeze(0).to(device)
            logits = classifier(inp)
            probs = torch.softmax(logits, dim=1)
            cls_conf, cls_idx = torch.max(probs, dim=1)
            cls_conf = cls_conf.item()
            cls_idx = int(cls_idx.item())
            cls_name = labels[cls_idx] if cls_idx < len(labels) else str(cls_idx)

        fused = ensemble_conf(det_conf, cls_conf)  # 融合偵測與分類置信度
        results.append(
            {
                "bbox": [x1, y1, x2, y2],
                "det_conf": det_conf,
                "cls_conf": cls_conf,
                "fused_conf": fused,
                "label": cls_name,
            }
        )

        # draw box
        color = (0, 255, 0)
        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
        label_text = f"{cls_name} {fused:.2f}"
        (tw, th), baseline = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        cv2.rectangle(annotated, (x1, y1 - th - 6), (x1 + tw, y1), color, -1)
        cv2.putText(annotated, label_text, (x1, y1 - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)

        print(
            f"[{idx+1}] box=({x1},{y1},{x2},{y2}) det={det_conf:.2f} cls={cls_name} ({cls_conf:.2f}) fused={fused:.2f}"
        )

    out_img = os.path.join(save_dir, Path(source).name)
    out_txt = os.path.join(save_dir, Path(source).stem + "_ensemble.txt")
    cv2.imwrite(out_img, annotated)
    with open(out_txt, "w", encoding="utf-8") as f:
        f.write(f"source: {source}\n")
        for r in results:
            f.write(
                f"bbox={r['bbox']}, det={r['det_conf']:.3f}, cls={r['cls_conf']:.3f}, fused={r['fused_conf']:.3f}, label={r['label']}\n"
            )

    print(f"Annotated image saved to {out_img}")
    print(f"Results saved to {out_txt}")


def build_args():
    p = argparse.ArgumentParser(description="YOLOv8 detection + EfficientNet classification ensemble")
    p.add_argument("--source", required=True, help="Path to image")
    p.add_argument("--yolo_model", default="models/yolov8n.pt", help="YOLO detection model path")
    p.add_argument("--effnet_weights", required=True, help="User-supplied local EfficientNet weight file (.pth/.pt); no download fallback.")
    p.add_argument("--labels", default=None, help="Optional labels file (one class name per line)")
    p.add_argument("--conf", type=float, default=0.25, help="YOLO detection confidence threshold")
    p.add_argument("--save_dir", default="runs/detect_effnet", help="Output directory")
    p.add_argument("--device", default="cpu", help="torch device, e.g., cpu or cuda:0")
    return p.parse_args()


if __name__ == "__main__":
    args = build_args()
    run_ensemble(
        source=args.source,
        yolo_model_path=args.yolo_model,
        effnet_weights=args.effnet_weights,
        labels_path=args.labels,
        conf_threshold=args.conf,
        save_dir=args.save_dir,
        device=args.device,
    )

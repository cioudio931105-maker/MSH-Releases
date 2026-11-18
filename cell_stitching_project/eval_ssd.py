from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np
import torch

from .ssd import vision as _vision  # noqa: F401
from .ssd.common import create_ssd, create_ssd_predictor, load_label_file, resolve_device, str2bool
from .ssd.vision.datasets.voc_dataset import VOCDataset
from .ssd.vision.utils import box_utils, measurements


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate an SSD model on VOC or Open Images style datasets.")
    parser.add_argument("--net", default="mb1-ssd")
    parser.add_argument("--trained-model", required=True)
    parser.add_argument("--dataset-type", default="voc", choices=("voc", "open_images"))
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--label-file", required=True)
    parser.add_argument("--use-cuda", default=True, type=str2bool)
    parser.add_argument("--use-2007-metric", default=True, type=str2bool)
    parser.add_argument("--nms-method", default="hard")
    parser.add_argument("--iou-threshold", default=0.5, type=float)
    parser.add_argument("--eval-dir", default="eval_results")
    parser.add_argument("--mb2-width-mult", default=1.0, type=float)
    return parser


def group_annotation_by_class(dataset):
    true_case_stat = {}
    all_gt_boxes = {}
    all_difficult_cases = {}
    for index in range(len(dataset)):
        image_id, annotation = dataset.get_annotation(index)
        gt_boxes, classes, is_difficult = annotation
        gt_boxes = torch.from_numpy(gt_boxes)
        for entry_index, difficult in enumerate(is_difficult):
            class_index = int(classes[entry_index])
            gt_box = gt_boxes[entry_index]
            if not difficult:
                true_case_stat[class_index] = true_case_stat.get(class_index, 0) + 1

            all_gt_boxes.setdefault(class_index, {}).setdefault(image_id, []).append(gt_box)
            all_difficult_cases.setdefault(class_index, {}).setdefault(image_id, []).append(difficult)

    for class_index, image_map in all_gt_boxes.items():
        for image_id, boxes in image_map.items():
            image_map[image_id] = torch.stack(boxes)
    for class_index, image_map in all_difficult_cases.items():
        for image_id, difficult in image_map.items():
            image_map[image_id] = torch.tensor(difficult)
    return true_case_stat, all_gt_boxes, all_difficult_cases


def compute_average_precision_per_class(num_true_cases, gt_boxes, difficult_cases, prediction_file, iou_threshold, use_2007_metric):
    image_ids: list[str] = []
    boxes = []
    scores = []
    with open(prediction_file, encoding="utf-8") as handle:
        for line in handle:
            parts = line.rstrip().split("\t")
            if len(parts) < 6:
                continue
            image_ids.append(parts[0])
            scores.append(float(parts[1]))
            box = torch.tensor([float(value) for value in parts[2:]], dtype=torch.float32).unsqueeze(0)
            box -= 1.0
            boxes.append(box)
    if not image_ids:
        return 0.0

    scores_arr = np.array(scores)
    sorted_indexes = np.argsort(-scores_arr)
    boxes = [boxes[index] for index in sorted_indexes]
    image_ids = [image_ids[index] for index in sorted_indexes]
    true_positive = np.zeros(len(image_ids))
    false_positive = np.zeros(len(image_ids))
    matched = set()
    for index, image_id in enumerate(image_ids):
        box = boxes[index]
        if image_id not in gt_boxes:
            false_positive[index] = 1
            continue
        gt_box = gt_boxes[image_id]
        ious = box_utils.iou_of(box, gt_box)
        max_iou = torch.max(ious).item()
        max_arg = torch.argmax(ious).item()
        if max_iou > iou_threshold:
            if difficult_cases[image_id][max_arg] == 0:
                token = (image_id, max_arg)
                if token not in matched:
                    true_positive[index] = 1
                    matched.add(token)
                else:
                    false_positive[index] = 1
        else:
            false_positive[index] = 1

    true_positive = true_positive.cumsum()
    false_positive = false_positive.cumsum()
    precision = true_positive / np.maximum(true_positive + false_positive, 1e-12)
    recall = true_positive / max(num_true_cases, 1)
    return (
        measurements.compute_voc2007_average_precision(precision, recall)
        if use_2007_metric
        else measurements.compute_average_precision(precision, recall)
    )


def main() -> int:
    args = _parser().parse_args()
    logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(asctime)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    eval_dir = Path(args.eval_dir)
    eval_dir.mkdir(parents=True, exist_ok=True)
    class_names = load_label_file(args.label_file)
    if args.dataset_type == "voc":
        dataset = VOCDataset(args.dataset, is_test=True)
    else:
        from .ssd.vision.datasets.open_images import OpenImagesDataset

        dataset = OpenImagesDataset(args.dataset, dataset_type="test")
    true_case_stat, all_gt_boxes, all_difficult_cases = group_annotation_by_class(dataset)

    device = resolve_device(use_cuda=args.use_cuda)
    net, _ = create_ssd(args.net, len(class_names), is_test=True, mb2_width_mult=args.mb2_width_mult)
    net.load(args.trained_model)
    net.to(device)
    predictor = create_ssd_predictor(args.net, net, device=device, nms_method=args.nms_method)

    results = []
    for index in range(len(dataset)):
        image = dataset.get_image(index)
        boxes, labels, probs = predictor.predict(image)
        if labels.numel() == 0:
            continue
        indexes = torch.ones(labels.size(0), 1, dtype=torch.float32) * index
        results.append(
            torch.cat(
                [
                    indexes.reshape(-1, 1),
                    labels.reshape(-1, 1).float(),
                    probs.reshape(-1, 1),
                    boxes + 1.0,
                ],
                dim=1,
            )
        )
    results_tensor = torch.cat(results) if results else torch.empty((0, 7), dtype=torch.float32)

    aps = []
    ap_by_class = {}
    for class_index, class_name in enumerate(class_names):
        if class_index == 0:
            continue
        prediction_path = eval_dir / f"det_test_{class_name}.txt"
        with open(prediction_path, "w", encoding="utf-8") as handle:
            sub = results_tensor[results_tensor[:, 1] == class_index, :]
            for row_index in range(sub.size(0)):
                prob_box = sub[row_index, 2:].numpy()
                image_id = dataset.ids[int(sub[row_index, 0])]
                handle.write(image_id + "\t" + "\t".join(str(value) for value in prob_box) + "\n")
        ap = compute_average_precision_per_class(
            true_case_stat.get(class_index, 0),
            all_gt_boxes.get(class_index, {}),
            all_difficult_cases.get(class_index, {}),
            prediction_path,
            args.iou_threshold,
            args.use_2007_metric,
        )
        aps.append(ap)
        ap_by_class[class_name] = ap

    summary = {
        "model": str(Path(args.trained_model).resolve()),
        "dataset": str(Path(args.dataset).resolve()),
        "label_file": str(Path(args.label_file).resolve()),
        "mean_ap": float(sum(aps) / len(aps)) if aps else 0.0,
        "per_class_ap": ap_by_class,
    }
    (eval_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"eval_dir={eval_dir.resolve()}")
    print(f"mean_ap={summary['mean_ap']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

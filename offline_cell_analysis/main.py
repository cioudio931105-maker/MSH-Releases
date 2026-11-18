from __future__ import annotations

import argparse
import traceback
from datetime import datetime
from pathlib import Path

from offline_pipeline.crops import crop_unique_cells, save_annotated_frames, write_crops_csv
from offline_pipeline.detector import YoloV8Detector, write_detections_csv
from offline_pipeline.duplicates import assign_tracks, unique_best_detections
from offline_pipeline.single_cell_crops import find_default_wbc_classifier, run_single_cell_crop_pipeline
from offline_pipeline.stats import build_summary, write_summary, write_tracks_csv
from offline_pipeline.utils import ensure_dir
from offline_pipeline.video_frames import extract_frames


PROJECT_DIR = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Offline microscope scan video analysis pipeline.")
    parser.add_argument("--video", required=True, type=Path, help="Input microscope scan video.")
    parser.add_argument("--model", required=True, type=Path, help="YOLOv8 .pt model path.")
    parser.add_argument("--project-dir", type=Path, default=PROJECT_DIR, help="Pipeline project directory.")
    parser.add_argument("--every-n-frames", type=int, default=1, help="Extract one frame every N video frames.")
    parser.add_argument("--every-seconds", type=float, default=None, help="Extract one frame every N seconds.")
    parser.add_argument("--blur-threshold", type=float, default=0.0, help="Skip frames below this Laplacian variance. 0 disables filtering.")
    parser.add_argument("--jpeg-quality", type=int, default=95, help="Extracted JPG quality.")
    parser.add_argument("--conf", type=float, default=0.25, help="YOLO confidence threshold.")
    parser.add_argument("--yolo-iou", type=float, default=0.45, help="YOLO NMS IoU threshold.")
    parser.add_argument("--device", default="auto", help="YOLO device: auto, cpu, cuda, 0, 1, etc.")
    parser.add_argument("--imgsz", type=int, default=640, help="YOLO inference image size.")
    parser.add_argument("--batch-size", type=int, default=8, help="YOLO inference batch size.")
    parser.add_argument("--duplicate-iou", type=float, default=0.35, help="Track match IoU threshold.")
    parser.add_argument("--duplicate-centroid", type=float, default=80.0, help="Track match centroid distance in pixels.")
    parser.add_argument("--track-gap", type=int, default=8, help="Max frame gap for duplicate tracking.")
    parser.add_argument("--crop-margin", type=float, default=0.10, help="Extra crop margin around bbox as a ratio.")
    parser.add_argument("--save-annotated", action="store_true", help="Save annotated frame images with bounding boxes.")
    parser.add_argument("--single-cell-crops", action="store_true", help="Run single-cell crop/classification export mode.")
    parser.add_argument("--wbc-classifier", type=Path, default=None, help="Optional WBC five-subtype classifier model.")
    parser.add_argument("--wbc-conf", type=float, default=0.70, help="WBC subtype confidence threshold.")
    parser.add_argument("--low-confidence", type=float, default=0.25, help="Detections below this are written as low_confidence_skipped.")
    parser.add_argument("--crop-padding", type=float, default=0.10, help="Single-cell crop padding. <1 means bbox ratio, >=1 means pixels.")
    return parser.parse_args()


def create_run_dirs(project_dir: Path, video_path: Path) -> dict[str, Path]:
    run_name = f"{video_path.stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    dirs = {
        "frames": project_dir / "extracted_frames" / run_name,
        "detections": project_dir / "detections" / run_name,
        "crops": project_dir / "cropped_cells" / run_name,
        "outputs": project_dir / "outputs" / run_name,
        "annotated": project_dir / "outputs" / run_name / "annotated_frames",
    }
    for path in dirs.values():
        ensure_dir(path)
    return dirs


def run_pipeline(args: argparse.Namespace) -> dict:
    project_dir = ensure_dir(Path(args.project_dir))
    video_path = Path(args.video)
    model_path = Path(args.model)
    dirs = create_run_dirs(project_dir, video_path)

    if args.single_cell_crops:
        print("[single-cell] 影片逐幀解析、細胞偵測、單顆裁切與分類存檔...", flush=True)
        wbc_classifier = args.wbc_classifier or find_default_wbc_classifier()
        summary = run_single_cell_crop_pipeline(
            video_path=video_path,
            detection_model_path=model_path,
            output_root=project_dir / "cropped_cells_single",
            csv_path=dirs["outputs"] / "single_cell_crops.csv",
            wbc_classifier_path=wbc_classifier,
            every_n_frames=args.every_n_frames,
            every_seconds=args.every_seconds,
            confidence=args.conf,
            low_confidence=args.low_confidence,
            wbc_confidence=args.wbc_conf,
            device=args.device,
            imgsz=args.imgsz,
            padding=args.crop_padding,
            duplicate_iou=args.duplicate_iou,
            duplicate_centroid=args.duplicate_centroid,
            track_gap=args.track_gap,
        )
        summary["run_dir"] = str(dirs["outputs"].resolve())
        write_summary(summary, dirs["outputs"] / "single_cell_summary.json")
        return summary

    print("[1/6] Extracting frames...", flush=True)
    frame_manifest = dirs["outputs"] / "frames_manifest.csv"
    frame_records = extract_frames(
        video_path,
        dirs["frames"],
        every_n_frames=args.every_n_frames,
        every_seconds=args.every_seconds,
        blur_threshold=args.blur_threshold,
        jpeg_quality=args.jpeg_quality,
        manifest_path=frame_manifest,
    )
    saved_frames = [record for record in frame_records if record.saved]
    print(f"Saved frames: {len(saved_frames)} / sampled records: {len(frame_records)}", flush=True)
    if not saved_frames:
        raise RuntimeError("No frames were saved. Lower blur-threshold or change extraction interval.")

    print("[2/6] Loading YOLOv8 model...", flush=True)
    detector = YoloV8Detector(
        model_path,
        confidence=args.conf,
        iou=args.yolo_iou,
        device=args.device,
        imgsz=args.imgsz,
    )
    print("[3/6] Running YOLOv8 inference...", flush=True)
    detections = detector.predict_frames(saved_frames, batch_size=args.batch_size)
    print(f"Detections found: {len(detections)}", flush=True)
    write_detections_csv(detections, dirs["detections"] / "detections_all.csv")

    print("[4/6] Filtering duplicate cells...", flush=True)
    tracks = assign_tracks(
        detections,
        iou_threshold=args.duplicate_iou,
        centroid_threshold=args.duplicate_centroid,
        max_frame_gap=args.track_gap,
    )
    unique_detections = unique_best_detections(tracks)
    write_detections_csv(detections, dirs["detections"] / "detections_tracked.csv")
    write_detections_csv(unique_detections, dirs["detections"] / "unique_cells.csv")
    write_tracks_csv(tracks, dirs["detections"] / "tracks.csv")

    print("[5/6] Cropping unique cell ROIs...", flush=True)
    crops = crop_unique_cells(unique_detections, dirs["crops"], margin_ratio=args.crop_margin)
    write_crops_csv(crops, dirs["outputs"] / "crops.csv")

    if args.save_annotated:
        save_annotated_frames(detections, dirs["annotated"])

    print("[6/6] Writing summary...", flush=True)
    summary = build_summary(
        video_path=video_path,
        frame_records=frame_records,
        detections=detections,
        tracks=tracks,
        crops=crops,
        run_dir=dirs["outputs"],
    )
    write_summary(summary, dirs["outputs"] / "summary.json")
    return summary


def main() -> None:
    try:
        args = parse_args()
        summary = run_pipeline(args)
        print("Offline analysis complete", flush=True)
        print(f"Run dir: {summary['run_dir']}", flush=True)
        if "frames_saved" in summary:
            print(f"Frames saved: {summary['frames_saved']}", flush=True)
            print(f"Detections: {summary['detections_total']}", flush=True)
            print(f"Unique cells: {summary['unique_cells_total']}", flush=True)
            print(f"Crops saved: {summary['crops_saved']}", flush=True)
            print(f"By class: {summary['unique_cells_by_class']}", flush=True)
        else:
            print(f"Total detections: {summary['total_detections']}", flush=True)
            print(f"Saved crops: {summary['saved']}", flush=True)
            print(f"Duplicate skipped: {summary['duplicate_skipped']}", flush=True)
            print(f"Ambiguous skipped: {summary['ambiguous_skipped']}", flush=True)
            print(f"Low confidence skipped: {summary['low_confidence_skipped']}", flush=True)
            print(f"CSV: {summary['csv_path']}", flush=True)
    except Exception:
        print("Offline analysis failed:", flush=True)
        traceback.print_exc()
        raise SystemExit(1)


if __name__ == "__main__":
    main()

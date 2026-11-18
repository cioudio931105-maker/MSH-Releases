from __future__ import annotations

import argparse
import binascii
import struct
import sys
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from tqdm import tqdm

from .alignment import AlignmentResult, YoloGuidance, estimate_pairwise_shift, prepare_guidance
from .blending import blend_streaming_chunk, blend_tiles
from .cell_identification import CellIdentificationConfig, CellIdentificationDetector, load_class_names, run_cell_identification
from .config import StitchingConfig, make_config_from_args
from .io_utils import configure_logger, create_output_paths, list_image_paths, parse_image_coordinates, read_image, save_image, save_json, save_shift_records_csv
from .layout import CanvasLayout, TilePlacement, build_layout
from .preprocess import preprocess_image
from .runtime import load_torch, probe_runtime
from .visualization import save_intermediate_mosaics, save_overlay_preview, save_pair_debug, save_tile_placement_preview

try:
    import tifffile
except Exception:  # pragma: no cover - optional dependency
    tifffile = None  # type: ignore[assignment]


@dataclass(slots=True)
class StitchingResult:
    success: bool
    stitched_image_path: str | None
    overlay_preview_path: str | None
    shifts_json_path: str | None
    shifts_csv_path: str | None
    debug_dir: str | None
    log_path: str | None
    message: str
    pairwise_shifts: list[dict[str, Any]] = field(default_factory=list)
    placements: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    runtime: dict[str, Any] = field(default_factory=dict)
    post_detection: dict[str, Any] = field(default_factory=dict)


class _NullProgressStream:
    def write(self, _text: str) -> int:
        return 0

    def flush(self) -> None:
        return None


def _tqdm_stream() -> tuple[object, bool]:
    stream = getattr(sys, "stderr", None) or getattr(sys, "stdout", None)
    if stream is not None and hasattr(stream, "write") and hasattr(stream, "flush"):
        return stream, False
    return _NullProgressStream(), True


def _progress(iterable: Any, **kwargs: Any) -> Any:
    stream, disable = _tqdm_stream()
    return tqdm(iterable, file=stream, disable=disable, **kwargs)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Automatic cell image stitching pipeline")
    parser.add_argument("--input_dir", required=True, help="Directory containing overlapping microscope images")
    parser.add_argument("--output_dir", default="output", help="Directory where the stitched outputs will be written")
    parser.add_argument("--image_extension", default="auto", help="Optional extension filter, e.g. png or tif")
    parser.add_argument(
        "--input_order",
        choices=("auto", "natural", "coordinates"),
        default="auto",
        help="Image ordering strategy before adjacent stitching",
    )
    parser.add_argument(
        "--coordinate_priority",
        choices=("row-major", "column-major"),
        default="row-major",
        help="Coordinate traversal order when filenames contain explicit coordinates",
    )
    parser.add_argument("--output_format", choices=("png", "tif", "tiff"), default="png")
    parser.add_argument("--max_images", type=int, default=None, help="Optional limit for smoke testing")
    parser.add_argument(
        "--performance_profile",
        choices=("quality", "balanced", "resource"),
        default="balanced",
        help="Quality/resource preset for alignment resize and GPU memory strategy",
    )
    parser.add_argument("--compute_device", choices=("auto", "cuda", "cpu"), default="auto", help="Preferred runtime device")
    parser.add_argument("--gpu_memory_budget_mb", type=int, default=None, help="Approximate VRAM budget for GPU blending")
    parser.add_argument("--disable_gpu_fallback", action="store_true", help="Fail instead of falling back to CPU for unsupported GPU stages")
    parser.add_argument("--yolo_device", default="auto", help="YOLO device override, e.g. auto, cpu, or 0")
    parser.add_argument("--max_alignment_long_side", type=int, default=None, help="Resize only alignment images to this long side while preserving high-resolution output")
    parser.add_argument("--disable_post_stitch_detection", action="store_true", help="Skip object detection on the stitched result image")
    parser.add_argument("--post_detection_model_path", default=None, help="Optional model path for post-stitch detection. Defaults to the YOLO guidance model or yolov8n.pt")
    parser.add_argument("--post_detection_class_file", default=None, help="Optional class-name file for post-stitch detection")
    parser.add_argument("--post_detection_confidence", type=float, default=0.35, help="Confidence threshold for post-stitch detection")
    parser.add_argument("--post_detection_iou_threshold", type=float, default=0.45, help="IoU threshold for post-stitch detection")
    parser.add_argument("--post_detection_imgsz", type=int, default=512, help="Input size used for post-stitch ONNX detection")
    return parser


def _shift_records(paths: list, shifts: list[AlignmentResult]) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for index, shift in enumerate(shifts):
        ref_coords = parse_image_coordinates(paths[index])
        mov_coords = parse_image_coordinates(paths[index + 1])
        records.append(
            {
                "pair_index": index,
                "ref_image": paths[index].name,
                "mov_image": paths[index + 1].name,
                "ref_coord": None if ref_coords is None else [ref_coords[0], ref_coords[1]],
                "mov_coord": None if mov_coords is None else [mov_coords[0], mov_coords[1]],
                "dx": round(shift.dx, 4),
                "dy": round(shift.dy, 4),
                "angle": round(shift.angle, 4),
                "score": round(shift.score, 6),
                "method": shift.method,
                "direction": shift.direction,
                "used_yolo_guidance": shift.used_yolo_guidance,
            }
        )
    return records


def _placement_records(placements: list[TilePlacement]) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for placement in placements:
        coordinates = parse_image_coordinates(placement.path)
        records.append(
            {
                "index": placement.index,
                "image": placement.path.name,
                "coord": None if coordinates is None else [coordinates[0], coordinates[1]],
                "x": placement.x,
                "y": placement.y,
                "width": placement.width,
                "height": placement.height,
            }
        )
    return records


def _resolve_blending_method(config: StitchingConfig, canvas: CanvasLayout, image_count: int) -> str:
    if config.blending_method != "auto":
        return config.blending_method
    if config.performance_profile == "resource":
        return "feather"
    total_pixels = canvas.width * canvas.height
    if config.performance_profile == "quality":
        if image_count <= 8 and total_pixels <= 80_000_000:
            return "multiband"
        return "feather"
    if image_count <= 6 and total_pixels <= 60_000_000:
        return "multiband"
    return "feather"


def _should_use_streaming_mode(image_count: int) -> bool:
    return image_count >= 50


def _feather_weight_map(height: int, width: int) -> np.ndarray:
    mask = np.ones((height, width), dtype=np.uint8)
    mask[0, :] = 0
    mask[-1, :] = 0
    mask[:, 0] = 0
    mask[:, -1] = 0
    distance = cv2.distanceTransform(mask, cv2.DIST_L2, 3)
    if float(distance.max()) <= 0.0:
        return np.ones((height, width), dtype=np.float32)
    weight = distance / float(distance.max())
    return np.clip(weight, 0.05, 1.0).astype(np.float32)


def _prepare_tile(
    path: Path,
    config: StitchingConfig,
    detector: YoloGuidance | None,
    output_paths: Any,
    save_detection_debug: bool,
) -> tuple[Any, tuple[int, int]]:
    image = read_image(path)
    processed = preprocess_image(path, image, config)
    if detector is not None and detector.available:
        mask, overlay, count = prepare_guidance(processed, detector)
        if mask is not None and mask.shape[:2] != processed.alignment_gray.shape[:2]:
            mask = cv2.resize(
                mask,
                (processed.alignment_gray.shape[1], processed.alignment_gray.shape[0]),
                interpolation=cv2.INTER_NEAREST,
            )
            mask = (mask > 0).astype(np.uint8) * 255
        processed.guidance_mask = mask
        processed.detection_overlay = overlay
        processed.detection_count = count
        if save_detection_debug and overlay is not None:
            save_image(output_paths.debug_dir / f"{processed.path.stem}_detection.png", overlay)
    return processed, image.shape[:2]


def _compute_pairwise_streaming(
    image_paths: list[Path],
    config: StitchingConfig,
    detector: YoloGuidance | None,
    output_paths: Any,
    logger: Any,
) -> tuple[list[tuple[int, int]], list[AlignmentResult]]:
    image_shapes: list[tuple[int, int]] = []
    pairwise: list[AlignmentResult] = []
    previous_tile = None
    previous_shape: tuple[int, int] | None = None
    debug_detection_limit = 32
    debug_pair_limit = 24

    for index, path in enumerate(_progress(image_paths, desc="Streaming preprocess", unit="img")):
        tile, image_shape = _prepare_tile(
            path,
            config,
            detector,
            output_paths,
            save_detection_debug=config.save_debug_images and index < debug_detection_limit,
        )
        image_shapes.append(image_shape)

        if previous_tile is not None and previous_shape is not None:
            result = estimate_pairwise_shift(previous_tile, tile, config, logger=logger)
            if not result.success:
                logger.error(
                    "Alignment failed for pair %d (%s -> %s): %s",
                    index - 1,
                    previous_tile.path.name,
                    tile.path.name,
                    result.error,
                )
                raise RuntimeError(result.error or f"Alignment failed for pair {index - 1}")
            pairwise.append(result)
            if config.save_debug_images and (index - 1) < debug_pair_limit:
                save_pair_debug(index - 1, previous_tile, tile, result, output_paths.debug_matches_dir)

        previous_tile = tile
        previous_shape = image_shape

    return image_shapes, pairwise


def _ensure_large_result_path(output_paths: Any, config: StitchingConfig, logger: Any) -> None:
    if output_paths.result_path.suffix.lower() not in {".tif", ".tiff"}:
        output_paths.result_path = output_paths.result_path.with_suffix(".tiff")
        config.result_name = output_paths.result_path.name
        logger.warning("Large streaming stitch switched output format to TIFF for reliability.")


def _write_png_chunk(handle: Any, chunk_type: bytes, data: bytes) -> None:
    handle.write(struct.pack(">I", len(data)))
    handle.write(chunk_type)
    handle.write(data)
    checksum = binascii.crc32(chunk_type)
    checksum = binascii.crc32(data, checksum) & 0xFFFFFFFF
    handle.write(struct.pack(">I", checksum))


def _export_png_companion(source_path: str | Path, logger: Any) -> Path:
    source = Path(source_path)
    target = source.with_suffix(".png")
    if source.suffix.lower() == ".png":
        return source

    logger.info("Exporting PNG companion: %s -> %s", source.name, target.name)
    if target.exists():
        target.unlink()

    if source.suffix.lower() in {".tif", ".tiff"}:
        if tifffile is None:
            raise RuntimeError("tifffile is required to export PNG from TIFF results")
        image_mm = tifffile.memmap(str(source))
        if image_mm.ndim != 3 or image_mm.shape[2] != 3:
            raise RuntimeError(f"Unsupported TIFF image shape for PNG export: {image_mm.shape}")
        height, width, _channels = image_mm.shape
        with target.open("wb") as handle:
            handle.write(b"\x89PNG\r\n\x1a\n")
            header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
            _write_png_chunk(handle, b"IHDR", header)
            compressor = zlib.compressobj(level=1)
            rows_per_chunk = 256
            raw_rows: list[bytes] = []
            for row_index in range(height):
                raw_rows.append(b"\x00" + image_mm[row_index].tobytes())
                if len(raw_rows) >= rows_per_chunk:
                    compressed = compressor.compress(b"".join(raw_rows))
                    if compressed:
                        _write_png_chunk(handle, b"IDAT", compressed)
                    raw_rows.clear()
            if raw_rows:
                compressed = compressor.compress(b"".join(raw_rows))
                if compressed:
                    _write_png_chunk(handle, b"IDAT", compressed)
            remainder = compressor.flush()
            if remainder:
                _write_png_chunk(handle, b"IDAT", remainder)
            _write_png_chunk(handle, b"IEND", b"")
        return target

    save_image(target, read_image(source))
    return target


def _save_streaming_preview(
    image_paths: list[Path],
    placements: list[TilePlacement],
    canvas: CanvasLayout,
    output_path: str | Path,
) -> Path:
    max_dim = 10000.0
    scale = min(1.0, max_dim / max(1, max(canvas.width, canvas.height)))
    preview_h = max(1, int(round(canvas.height * scale)))
    preview_w = max(1, int(round(canvas.width * scale)))
    accum = np.zeros((preview_h, preview_w, 3), dtype=np.float32)
    weight_accum = np.zeros((preview_h, preview_w), dtype=np.float32)

    for path, placement in _progress(list(zip(image_paths, placements)), desc="Preview", unit="img"):
        image = read_image(path)
        scaled_w = max(1, int(round(image.shape[1] * scale)))
        scaled_h = max(1, int(round(image.shape[0] * scale)))
        resized = cv2.resize(image, (scaled_w, scaled_h), interpolation=cv2.INTER_AREA)
        x0 = int(round(placement.x * scale))
        y0 = int(round(placement.y * scale))
        x1 = min(preview_w, x0 + scaled_w)
        y1 = min(preview_h, y0 + scaled_h)
        if x1 <= x0 or y1 <= y0:
            continue
        valid = resized[: y1 - y0, : x1 - x0]
        alpha = np.ones((valid.shape[0], valid.shape[1]), dtype=np.float32)
        accum[y0:y1, x0:x1] += valid.astype(np.float32) * alpha[:, :, None]
        weight_accum[y0:y1, x0:x1] += alpha

    preview = np.clip(accum / np.maximum(weight_accum[:, :, None], 1e-6), 0, 255).astype(np.uint8)
    return save_image(output_path, preview)


def _blend_tiles_streaming_to_tiff(
    image_paths: list[Path],
    placements: list[TilePlacement],
    canvas: CanvasLayout,
    config: StitchingConfig,
    result_path: str | Path,
) -> tuple[Path, list[str]]:
    if tifffile is None:
        raise RuntimeError("tifffile is required for large streaming stitches")

    warnings: list[str] = []

    target = Path(result_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()
    output_mm = tifffile.memmap(
        str(target),
        shape=(canvas.height, canvas.width, 3),
        dtype=np.uint8,
        photometric="rgb",
        bigtiff=True,
    )

    chunk_width = 2048
    chunk_height = 2048
    chunk_cols = max(1, (canvas.width + chunk_width - 1) // chunk_width)
    chunk_rows = max(1, (canvas.height + chunk_height - 1) // chunk_height)
    chunk_members: list[list[list[int]]] = [[[] for _ in range(chunk_cols)] for _ in range(chunk_rows)]
    for index, placement in enumerate(placements):
        start_chunk_x = placement.x // chunk_width
        end_chunk_x = (placement.x + placement.width - 1) // chunk_width
        start_chunk_y = placement.y // chunk_height
        end_chunk_y = (placement.y + placement.height - 1) // chunk_height
        for chunk_y in range(start_chunk_y, end_chunk_y + 1):
            for chunk_x in range(start_chunk_x, end_chunk_x + 1):
                chunk_members[chunk_y][chunk_x].append(index)

    weight_cache: dict[tuple[int, int], np.ndarray] = {}
    streaming_method = config.blending_method
    low_memory_warning: str | None = None
    total_chunks = chunk_rows * chunk_cols
    for chunk_index in _progress(range(total_chunks), desc="Streaming blend", unit="chunk"):
        chunk_y = chunk_index // chunk_cols
        chunk_x = chunk_index % chunk_cols
        x0 = chunk_x * chunk_width
        x1 = min(canvas.width, x0 + chunk_width)
        y0 = chunk_y * chunk_height
        y1 = min(canvas.height, y0 + chunk_height)
        chunk_tiles: list[tuple[np.ndarray, np.ndarray, int, int]] = []

        for image_index in chunk_members[chunk_y][chunk_x]:
            placement = placements[image_index]
            image = read_image(image_paths[image_index])
            height, width = image.shape[:2]
            if streaming_method == "average":
                weight = weight_cache.setdefault((height, width), np.ones((height, width), dtype=np.float32))
            else:
                try:
                    weight = weight_cache.setdefault((height, width), _feather_weight_map(height, width))
                except MemoryError:
                    streaming_method = "average"
                    weight_cache.clear()
                    if low_memory_warning is None:
                        low_memory_warning = (
                            "Streaming feather blending ran out of host memory; "
                            "fell back to average blending for the remaining chunks."
                        )
                        warnings.append(low_memory_warning)
                    weight = weight_cache.setdefault((height, width), np.ones((height, width), dtype=np.float32))

            overlap_x0 = max(x0, placement.x)
            overlap_x1 = min(x1, placement.x + width)
            overlap_y0 = max(y0, placement.y)
            overlap_y1 = min(y1, placement.y + height)
            if overlap_x1 <= overlap_x0 or overlap_y1 <= overlap_y0:
                continue

            src_x0 = overlap_x0 - placement.x
            src_x1 = overlap_x1 - placement.x
            src_y0 = overlap_y0 - placement.y
            src_y1 = overlap_y1 - placement.y
            dst_x0 = overlap_x0 - x0
            dst_y0 = overlap_y0 - y0
            tile = image[src_y0:src_y1, src_x0:src_x1].astype(np.float32)
            tile_weight = weight[src_y0:src_y1, src_x0:src_x1]
            chunk_tiles.append((tile, tile_weight, dst_y0, dst_x0))

        blended_chunk, chunk_warnings = blend_streaming_chunk(chunk_tiles, y1 - y0, x1 - x0, config)
        for warning in chunk_warnings:
            if warning not in warnings:
                warnings.append(warning)
        output_mm[y0:y1, x0:x1, :] = blended_chunk
        output_mm.flush()

    del output_mm
    return target, warnings


def _run_post_stitch_detection_projected(
    image_paths: list[Path],
    placements: list[TilePlacement],
    canvas: CanvasLayout,
    config: StitchingConfig,
    logger: Any,
) -> dict[str, Any]:
    if not config.post_stitch_detection_enabled:
        return {
            "enabled": False,
            "success": False,
            "message": "Post-stitch detection is disabled",
        }

    model_path = config.post_stitch_detection_model_path or config.yolo_model_path or "yolov8n.pt"
    output_dir = Path(config.output_dir) / config.post_stitch_detection_output_dirname
    output_dir.mkdir(parents=True, exist_ok=True)
    runtime_device = None
    prefer_gpu = config.prefer_gpu
    if config.runtime is not None:
        runtime_device = config.runtime.yolo_device
        prefer_gpu = config.runtime.device == "cuda"

    try:
        detector = CellIdentificationDetector(
            model_path=model_path,
            class_names=(
                load_class_names(config.post_stitch_detection_class_file)
                if config.post_stitch_detection_class_file is not None
                else None
            ),
            confidence=config.post_stitch_detection_confidence,
            iou_threshold=config.post_stitch_detection_iou_threshold,
            imgsz=config.post_stitch_detection_imgsz,
            device=runtime_device,
            prefer_gpu=prefer_gpu,
        )
    except Exception as exc:
        warning = f"Projected post-stitch detection failed to initialize: {exc}"
        logger.warning(warning)
        config.with_warning(warning)
        return {
            "enabled": True,
            "success": False,
            "message": warning,
            "model_path": str(Path(model_path).resolve()),
            "output_dir": str(output_dir.resolve()),
        }

    preview_scale = min(1.0, 10000.0 / max(1, max(canvas.width, canvas.height)))
    preview_h = max(1, int(round(canvas.height * preview_scale)))
    preview_w = max(1, int(round(canvas.width * preview_scale)))
    preview = np.full((preview_h, preview_w, 3), 20, dtype=np.uint8)

    results: list[dict[str, object]] = []
    total_detections = 0
    label_counts: dict[str, int] = {}
    for path, placement in _progress(list(zip(image_paths, placements)), desc="Projected detection", unit="img"):
        image = read_image(path)
        detections = detector.predict(image)
        mapped_detections: list[dict[str, object]] = []
        for detection in detections:
            mapped = detection.to_dict()
            bbox = dict(mapped["bbox"])
            bbox["x1"] += placement.x
            bbox["x2"] += placement.x
            bbox["y1"] += placement.y
            bbox["y2"] += placement.y
            mapped["bbox"] = bbox
            mapped["tile_image"] = path.name
            mapped_detections.append(mapped)
            total_detections += 1
            label = str(mapped["label"])
            label_counts[label] = label_counts.get(label, 0) + 1

            x0 = int(round(bbox["x1"] * preview_scale))
            y0 = int(round(bbox["y1"] * preview_scale))
            x1 = int(round(bbox["x2"] * preview_scale))
            y1 = int(round(bbox["y2"] * preview_scale))
            if x1 > x0 and y1 > y0:
                cv2.rectangle(preview, (x0, y0), (x1, y1), (0, 255, 0), 1)

        results.append(
            {
                "image": str(path.resolve()),
                "placement": {
                    "x": placement.x,
                    "y": placement.y,
                    "width": placement.width,
                    "height": placement.height,
                },
                "detections": mapped_detections,
            }
        )

    preview_path = output_dir / "global_detection_preview.png"
    save_image(preview_path, preview)
    json_output = output_dir / "global_detections.json"
    payload = {
        "model": str(Path(model_path).resolve()),
        "backend": detector.backend,
        "providers": list(getattr(detector, "providers", [])),
        "images_processed": len(results),
        "total_detections": total_detections,
        "label_counts": label_counts,
        "preview_path": str(preview_path.resolve()),
        "results": results,
    }
    save_json(json_output, payload)
    logger.info(
        "Projected post-stitch detection completed using %s backend with %d detections",
        detector.backend,
        total_detections,
    )
    return {
        "enabled": True,
        "success": True,
        "message": "Projected post-stitch detection completed successfully",
        "backend": detector.backend,
        "model_path": str(Path(model_path).resolve()),
        "output_dir": str(output_dir.resolve()),
        "json_output_path": str(json_output.resolve()),
        "preview_path": str(preview_path.resolve()),
        "images_processed": len(results),
        "total_detections": total_detections,
        "results": results,
    }


def _run_post_stitch_detection(
    stitched_image_path: str,
    config: StitchingConfig,
    logger: Any,
) -> dict[str, Any]:
    if not config.post_stitch_detection_enabled:
        return {
            "enabled": False,
            "success": False,
            "message": "Post-stitch detection is disabled",
        }

    model_path = config.post_stitch_detection_model_path or config.yolo_model_path or "yolov8n.pt"
    output_dir = Path(config.output_dir) / config.post_stitch_detection_output_dirname
    runtime_device = None
    prefer_gpu = config.prefer_gpu
    if config.runtime is not None:
        runtime_device = config.runtime.yolo_device
        prefer_gpu = config.runtime.device == "cuda"

    try:
        result = run_cell_identification(
            CellIdentificationConfig(
                model_path=model_path,
                source=stitched_image_path,
                output_dir=output_dir,
                class_file=config.post_stitch_detection_class_file,
                confidence=config.post_stitch_detection_confidence,
                iou_threshold=config.post_stitch_detection_iou_threshold,
                imgsz=config.post_stitch_detection_imgsz,
                device=runtime_device,
                prefer_gpu=prefer_gpu,
            )
        )
    except Exception as exc:
        warning = f"Post-stitch detection failed: {exc}"
        logger.warning(warning)
        config.with_warning(warning)
        return {
            "enabled": True,
            "success": False,
            "message": warning,
            "model_path": str(Path(model_path).resolve()),
            "output_dir": str(output_dir.resolve()),
        }

    logger.info(
        "Post-stitch detection completed using %s backend with %d detections",
        result.backend,
        result.total_detections,
    )
    return {
        "enabled": True,
        "success": result.success,
        "message": result.message,
        "backend": result.backend,
        "model_path": result.model_path,
        "output_dir": result.output_dir,
        "json_output_path": result.json_output_path,
        "images_processed": result.images_processed,
        "total_detections": result.total_detections,
        "results": result.results,
    }


def run_stitch_pipeline(config: StitchingConfig) -> StitchingResult:
    """Run the full stitching pipeline and return artifact paths for CLI or UI usage."""

    output_paths = create_output_paths(
        output_dir=config.output_dir,
        result_name=config.result_name,
        shifts_json_name=config.shifts_json_name,
        shifts_csv_name=config.shifts_csv_name,
        overlay_name=config.overlay_name,
        log_name=config.log_name,
        debug_matches_dirname=config.debug_matches_dirname,
        intermediate_dirname=config.intermediate_dirname,
    )
    logger = configure_logger(output_paths.log_path)
    config.runtime = probe_runtime(
        compute_device=config.compute_device,
        prefer_gpu=config.prefer_gpu,
        gpu_fallback_allowed=config.gpu_fallback_allowed,
        gpu_memory_budget_mb=config.gpu_memory_budget_mb,
        yolo_device=config.yolo_device,
    )
    logger.info("Cell stitching start")
    logger.info("Input directory: %s", config.input_dir)
    logger.info("Output directory: %s", output_paths.root)
    logger.info(
        "Runtime device=%s requested=%s cuda_available=%s gpu=%s torch_cuda=%s cv2_cuda_devices=%s yolo_device=%s profile=%s alignment_long_side=%s gpu_budget_mb=%s",
        config.runtime.device,
        config.runtime.requested_device,
        config.runtime.cuda_available,
        config.runtime.gpu_name or "n/a",
        config.runtime.torch_cuda_version or "n/a",
        config.runtime.cv2_cuda_devices,
        config.runtime.yolo_device,
        config.performance_profile,
        config.max_alignment_long_side,
        config.gpu_memory_budget_mb,
    )

    image_paths = list_image_paths(
        input_dir=config.input_dir,
        image_extension=config.image_extension,
        explicit_paths=config.input_paths,
        max_images=config.max_images,
        input_order=config.input_order,
        coordinate_priority=config.coordinate_priority,
    )
    if len(image_paths) < 2:
        raise RuntimeError("At least two valid images are required for stitching.")
    streaming_mode = _should_use_streaming_mode(len(image_paths))
    coordinate_count = sum(1 for path in image_paths if parse_image_coordinates(path) is not None)
    logger.info(
        "Image ordering mode=%s coordinate_priority=%s parsed_coordinates=%d/%d",
        config.input_order,
        config.coordinate_priority,
        coordinate_count,
        len(image_paths),
    )
    if streaming_mode:
        _ensure_large_result_path(output_paths, config, logger)
        logger.info("Streaming mode enabled for large batch stitching (%d images).", len(image_paths))

    detector = YoloGuidance(
        config.yolo_model_path,
        config.yolo_confidence,
        config.detector_expand_ratio,
        device=config.runtime.yolo_device if config.runtime is not None else config.yolo_device,
    ) if config.use_yolo_guidance else None
    if detector is not None and detector.warning:
        logger.warning(detector.warning)
        config.with_warning(detector.warning)

    if streaming_mode:
        image_shapes, pairwise = _compute_pairwise_streaming(image_paths, config, detector, output_paths, logger)
        if detector is not None and detector.available and not any(item.used_yolo_guidance for item in pairwise):
            warning = "YOLO guidance was enabled, but no ROI masks were produced for the current images."
            logger.warning(warning)
            config.with_warning(warning)
        elif config.use_yolo_guidance and (detector is None or not detector.available):
            logger.warning("YOLO guidance requested but unavailable; continuing without ROI masks.")
    else:
        raw_images = [read_image(path) for path in _progress(image_paths, desc="Loading images", unit="img")]
        processed = [preprocess_image(path, image, config) for path, image in _progress(list(zip(image_paths, raw_images)), desc="Preprocessing", unit="img")]

        if detector is not None and detector.available:
            for tile in _progress(processed, desc="YOLO guidance", unit="img"):
                mask, overlay, count = prepare_guidance(tile, detector)
                tile.guidance_mask = mask
                tile.detection_overlay = overlay
                tile.detection_count = count
                if config.save_debug_images and overlay is not None:
                    save_image(output_paths.debug_dir / f"{tile.path.stem}_detection.png", overlay)
            if not any(tile.guidance_mask is not None for tile in processed):
                warning = "YOLO guidance was enabled, but no ROI masks were produced for the current images."
                logger.warning(warning)
                config.with_warning(warning)
        elif config.use_yolo_guidance:
            logger.warning("YOLO guidance requested but unavailable; continuing without ROI masks.")

        pairwise = []
        for index in _progress(range(len(processed) - 1), desc="Aligning", unit="pair"):
            result = estimate_pairwise_shift(processed[index], processed[index + 1], config, logger=logger)
            if not result.success:
                logger.error("Alignment failed for pair %d (%s -> %s): %s", index, processed[index].path.name, processed[index + 1].path.name, result.error)
                raise RuntimeError(result.error or f"Alignment failed for pair {index}")
            pairwise.append(result)
            if config.save_debug_images:
                save_pair_debug(index, processed[index], processed[index + 1], result, output_paths.debug_matches_dir)
        image_shapes = [image.shape[:2] for image in raw_images]

    if config.alignment_method in {"orb", "sift"} and not any(item.method == config.alignment_method for item in pairwise):
        warning = f"Requested alignment method '{config.alignment_method}' did not produce a valid pairwise solution and fell back to translation methods."
        logger.warning(warning)
        config.with_warning(warning)

    placements, canvas = build_layout(
        image_paths=image_paths,
        image_shapes=image_shapes,
        shifts=pairwise,
    )
    if streaming_mode:
        _save_streaming_preview(image_paths, placements, canvas, output_paths.overlay_preview_path)
    resolved_blending = _resolve_blending_method(config, canvas, len(image_paths))
    if resolved_blending != config.blending_method:
        logger.info("Auto-selected blending method: %s", resolved_blending)
    config.blending_method = resolved_blending
    if config.runtime is not None and config.runtime.device == "cuda":
        torch_module = load_torch()
        if torch_module is not None and torch_module.cuda.is_available():
            torch_module.cuda.empty_cache()
    if streaming_mode:
        streamed_result_path, blend_warnings = _blend_tiles_streaming_to_tiff(
            image_paths=image_paths,
            placements=placements,
            canvas=canvas,
            config=config,
            result_path=output_paths.result_path,
        )
        output_paths.result_path = streamed_result_path
        for warning in blend_warnings:
            logger.warning(warning)
            config.with_warning(warning)
    else:
        blended, blend_warnings = blend_tiles([tile.blend_bgr for tile in processed], placements, canvas, config)
        for warning in blend_warnings:
            logger.warning(warning)
            config.with_warning(warning)

    if config.runtime is not None and config.runtime.fallbacks:
        for fallback in config.runtime.fallbacks:
            logger.warning(
                "Fallback at %s: %s (%s -> %s)",
                fallback.stage,
                fallback.reason,
                fallback.requested_device,
                fallback.actual_device,
            )

    if streaming_mode:
        if config.save_debug_images:
            save_tile_placement_preview(placements, canvas, output_paths.debug_dir / "tile_placement.png")
        post_detection = _run_post_stitch_detection_projected(image_paths, placements, canvas, config, logger)
    else:
        save_image(output_paths.result_path, blended)
        save_overlay_preview(blended, placements, output_paths.overlay_preview_path)
        if config.save_debug_images:
            save_tile_placement_preview(placements, canvas, output_paths.debug_dir / "tile_placement.png")
            save_intermediate_mosaics([tile.blend_bgr for tile in processed], placements, canvas, output_paths.intermediate_dir)
        post_detection = _run_post_stitch_detection(str(output_paths.result_path), config, logger)

    if output_paths.result_path.suffix.lower() != ".png":
        png_result_path = _export_png_companion(output_paths.result_path, logger)
        output_paths.result_path = png_result_path
        config.result_name = png_result_path.name

    shift_rows = _shift_records(image_paths, pairwise)
    placement_rows = _placement_records(placements)
    save_shift_records_csv(output_paths.shifts_csv_path, shift_rows)
    save_json(
        output_paths.shifts_json_path,
        {
            "config": config.describe(),
            "runtime": config.runtime.as_dict() if config.runtime is not None else {},
            "pairwise_shifts": shift_rows,
            "placements": placement_rows,
            "canvas": {
                "width": canvas.width,
                "height": canvas.height,
                "origin_shift_x": canvas.origin_shift_x,
                "origin_shift_y": canvas.origin_shift_y,
            },
            "post_stitch_detection": post_detection,
        },
    )

    return StitchingResult(
        success=True,
        stitched_image_path=str(output_paths.result_path.resolve()),
        overlay_preview_path=str(output_paths.overlay_preview_path.resolve()),
        shifts_json_path=str(output_paths.shifts_json_path.resolve()),
        shifts_csv_path=str(output_paths.shifts_csv_path.resolve()),
        debug_dir=str(output_paths.debug_dir.resolve()),
        log_path=str(output_paths.log_path.resolve()),
        message="Stitching completed successfully",
        pairwise_shifts=shift_rows,
        placements=placement_rows,
        warnings=list(config.warnings),
        runtime=config.runtime.as_dict() if config.runtime is not None else {},
        post_detection=post_detection,
    )


def main() -> int:
    args = _parser().parse_args()
    config = make_config_from_args(args)
    result = run_stitch_pipeline(config)
    print(result.message)
    print(f"stitched_image_path={result.stitched_image_path}")
    print(f"overlay_preview_path={result.overlay_preview_path}")
    print(f"shifts_json_path={result.shifts_json_path}")
    print(f"shifts_csv_path={result.shifts_csv_path}")
    if result.post_detection:
        print(f"post_detection_enabled={result.post_detection.get('enabled')}")
        print(f"post_detection_success={result.post_detection.get('success')}")
        if result.post_detection.get("json_output_path"):
            print(f"post_detection_json_path={result.post_detection.get('json_output_path')}")
        if result.post_detection.get("total_detections") is not None:
            print(f"post_detection_total_detections={result.post_detection.get('total_detections')}")
    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())

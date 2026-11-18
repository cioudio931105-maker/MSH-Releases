from __future__ import annotations

from msh_model_policy import require_local_model

import math
import re
from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np

from .config import StitchingConfig
from .preprocess import PreprocessedImage
from .runtime import load_torch
from .text_overlay import put_text


@dataclass(slots=True)
class Detection:
    x1: int
    y1: int
    x2: int
    y2: int
    conf: float
    label: str


@dataclass(slots=True)
class AlignmentResult:
    success: bool
    dx: float
    dy: float
    angle: float
    score: float
    method: str
    direction: str
    used_yolo_guidance: bool
    error: str | None = None
    debug: dict[str, Any] = field(default_factory=dict)


class YoloGuidance:
    """Optional YOLO wrapper used only for ROI guidance and debug overlays."""

    def __init__(self, model_path: str | None, confidence: float, expand_ratio: float, device: str | int = "auto") -> None:
        self.model_path = model_path or ""
        self.confidence = float(confidence)
        self.expand_ratio = float(expand_ratio)
        self.device = str(device)
        self.available = False
        self.warning: str | None = None
        self._model = None

        try:
            from ultralytics import YOLO
        except Exception as exc:  # pragma: no cover - depends on environment
            self.warning = f"YOLO guidance unavailable: {exc}"
            return

        try:
            self._model = YOLO(require_local_model(self.model_path))
            self.available = True
        except Exception as exc:  # pragma: no cover - depends on environment
            self.warning = f"Failed to load YOLO model '{self.model_path}': {exc}"

    def detect(self, image_bgr: np.ndarray) -> list[Detection]:
        if not self.available or self._model is None:
            return []

        try:
            results = self._model.predict(
                source=image_bgr,
                conf=self.confidence,
                verbose=False,
                device=self.device,
            )
        except Exception as exc:
            if str(self.device).lower() != "cpu":
                self.warning = f"YOLO guidance fell back to CPU after device error: {exc}"
                self.device = "cpu"
                try:
                    results = self._model.predict(
                        source=image_bgr,
                        conf=self.confidence,
                        verbose=False,
                        device="cpu",
                    )
                except Exception:
                    return []
            else:
                return []
        if not results:
            return []

        result = results[0]
        boxes = getattr(result, "boxes", None)
        names = getattr(result, "names", {})
        if boxes is None:
            return []

        detections: list[Detection] = []
        for box in boxes:
            xyxy = box.xyxy[0].tolist()
            x1, y1, x2, y2 = [int(round(value)) for value in xyxy]
            conf = float(box.conf[0]) if box.conf is not None else 0.0
            cls_id = int(box.cls[0]) if box.cls is not None else -1
            label = str(names.get(cls_id, cls_id)) if isinstance(names, dict) else str(cls_id)
            detections.append(Detection(x1=max(0, x1), y1=max(0, y1), x2=max(0, x2), y2=max(0, y2), conf=conf, label=label))
        return detections

    def build_mask(self, image_shape: tuple[int, int] | tuple[int, int, int], detections: list[Detection]) -> np.ndarray | None:
        if not detections:
            return None

        height = int(image_shape[0])
        width = int(image_shape[1])
        expand = max(4, int(round(min(height, width) * max(0.0, self.expand_ratio))))
        mask = np.zeros((height, width), dtype=np.uint8)
        for det in detections:
            x1 = max(0, det.x1 - expand)
            y1 = max(0, det.y1 - expand)
            x2 = min(width - 1, det.x2 + expand)
            y2 = min(height - 1, det.y2 + expand)
            if x2 <= x1 or y2 <= y1:
                continue
            cv2.rectangle(mask, (x1, y1), (x2, y2), 255, -1)

        if cv2.countNonZero(mask) < 16:
            return None
        return mask

    def annotate(self, image_bgr: np.ndarray, detections: list[Detection]) -> np.ndarray:
        output = image_bgr.copy()
        for det in detections:
            cv2.rectangle(output, (det.x1, det.y1), (det.x2, det.y2), (0, 255, 0), 2)
            text = f"{det.label} {det.conf:.2f}"
            put_text(output, text, (det.x1, max(18, det.y1 - 6)), 0.5, (0, 255, 0), 1)
        return output


def _make_masked_float(image: np.ndarray, mask: np.ndarray | None, use_window: bool = True) -> np.ndarray:
    work = image.astype(np.float32)
    if mask is not None:
        binary = (mask > 0).astype(np.float32)
        if float(binary.sum()) >= 16.0:
            work = work * binary
            valid = work[binary > 0]
            if valid.size > 0:
                work = work - float(valid.mean())
    else:
        work = work - float(work.mean())

    if use_window and work.shape[0] > 1 and work.shape[1] > 1:
        window = cv2.createHanningWindow((work.shape[1], work.shape[0]), cv2.CV_32F)
        work *= window
    return work


def _estimate_phase_cpu(ref_strip: np.ndarray, mov_strip: np.ndarray, ref_mask: np.ndarray | None, mov_mask: np.ndarray | None) -> tuple[float, float, float, float]:
    combined_mask = None
    if ref_mask is not None and mov_mask is not None:
        combined_mask = cv2.bitwise_and(ref_mask, mov_mask)
        if cv2.countNonZero(combined_mask) < 16:
            combined_mask = None

    shift, response = cv2.phaseCorrelate(
        _make_masked_float(ref_strip, combined_mask, use_window=True),
        _make_masked_float(mov_strip, combined_mask, use_window=True),
    )
    return float(shift[0]), float(shift[1]), 0.0, float(response)


def _phase_response(correlation: Any, y: int, x: int) -> tuple[float, float, float]:
    height, width = correlation.shape
    center = float(correlation[y, x].item())
    left = float(correlation[y, (x - 1) % width].item())
    right = float(correlation[y, (x + 1) % width].item())
    up = float(correlation[(y - 1) % height, x].item())
    down = float(correlation[(y + 1) % height, x].item())
    return center, left + right, up + down


def _parabolic_offset(left: float, center: float, right: float) -> float:
    denom = left - (2.0 * center) + right
    if abs(denom) <= 1e-6:
        return 0.0
    return 0.5 * (left - right) / denom


def _estimate_phase_gpu(ref_strip: np.ndarray, mov_strip: np.ndarray, ref_mask: np.ndarray | None, mov_mask: np.ndarray | None) -> tuple[float, float, float, float]:
    torch_module = load_torch()
    if torch_module is None or not torch_module.cuda.is_available():
        raise RuntimeError("PyTorch CUDA is not available for phase correlation")

    device = torch_module.device("cuda")
    ref = torch_module.from_numpy(ref_strip.astype(np.float32)).to(device=device)
    mov = torch_module.from_numpy(mov_strip.astype(np.float32)).to(device=device)
    combined_mask = None
    if ref_mask is not None and mov_mask is not None:
        ref_mask_tensor = torch_module.from_numpy((ref_mask > 0).astype(np.float32)).to(device=device)
        mov_mask_tensor = torch_module.from_numpy((mov_mask > 0).astype(np.float32)).to(device=device)
        combined_mask = ref_mask_tensor * mov_mask_tensor
        if float(combined_mask.sum().item()) < 16.0:
            combined_mask = None

    def _masked_center(tensor: Any, mask: Any | None) -> Any:
        work = tensor.clone()
        if mask is not None:
            valid = work[mask > 0]
            mean = valid.mean() if valid.numel() > 0 else work.mean()
            work = (work - mean) * mask
        else:
            work = work - work.mean()
        window_y = torch_module.hann_window(work.shape[0], periodic=False, device=device, dtype=work.dtype)
        window_x = torch_module.hann_window(work.shape[1], periodic=False, device=device, dtype=work.dtype)
        return work * window_y[:, None] * window_x[None, :]

    ref_work = _masked_center(ref, combined_mask)
    mov_work = _masked_center(mov, combined_mask)
    ref_fft = torch_module.fft.fft2(ref_work)
    mov_fft = torch_module.fft.fft2(mov_work)
    cross_power = ref_fft * torch_module.conj(mov_fft)
    cross_power = cross_power / torch_module.clamp(torch_module.abs(cross_power), min=1e-6)
    correlation = torch_module.fft.ifft2(cross_power).real
    flat_index = int(torch_module.argmax(correlation).item())
    height, width = correlation.shape
    peak_y, peak_x = divmod(flat_index, width)

    center = float(correlation[peak_y, peak_x].item())
    x_left = float(correlation[peak_y, (peak_x - 1) % width].item())
    x_right = float(correlation[peak_y, (peak_x + 1) % width].item())
    y_up = float(correlation[(peak_y - 1) % height, peak_x].item())
    y_down = float(correlation[(peak_y + 1) % height, peak_x].item())
    subpixel_x = _parabolic_offset(x_left, center, x_right)
    subpixel_y = _parabolic_offset(y_up, center, y_down)

    shift_x = float(peak_x)
    shift_y = float(peak_y)
    if shift_x > width // 2:
        shift_x -= float(width)
    if shift_y > height // 2:
        shift_y -= float(height)
    shift_x += subpixel_x
    shift_y += subpixel_y

    response = float(center / (float(torch_module.sum(torch_module.abs(correlation)).item()) + 1e-6))
    torch_module.cuda.synchronize()
    return shift_x, shift_y, 0.0, response


def _estimate_ecc(ref_strip: np.ndarray, mov_strip: np.ndarray, ref_mask: np.ndarray | None, mov_mask: np.ndarray | None, allow_rotation: bool) -> tuple[float, float, float, float]:
    motion_type = cv2.MOTION_EUCLIDEAN if allow_rotation else cv2.MOTION_TRANSLATION
    warp = np.eye(2, 3, dtype=np.float32)
    mask = None
    if ref_mask is not None and mov_mask is not None:
        mask = cv2.bitwise_and(ref_mask, mov_mask)
        if cv2.countNonZero(mask) < 32:
            mask = None

    cc, warp = cv2.findTransformECC(
        ref_strip.astype(np.float32) / 255.0,
        mov_strip.astype(np.float32) / 255.0,
        warp,
        motion_type,
        (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-5),
        inputMask=mask,
        gaussFiltSize=5,
    )
    angle = math.degrees(math.atan2(float(warp[1, 0]), float(warp[0, 0]))) if allow_rotation else 0.0
    return float(warp[0, 2]), float(warp[1, 2]), angle, float(cc)


def _estimate_feature(
    method: str,
    ref_strip: np.ndarray,
    mov_strip: np.ndarray,
    ref_mask: np.ndarray | None,
    mov_mask: np.ndarray | None,
    config: StitchingConfig,
) -> tuple[float, float, float, float, np.ndarray]:
    if method == "sift":
        if not hasattr(cv2, "SIFT_create"):
            raise RuntimeError("SIFT requires opencv-contrib-python")
        detector = cv2.SIFT_create(nfeatures=config.feature_max_keypoints)
        matcher = cv2.BFMatcher(cv2.NORM_L2)
    else:
        detector = cv2.ORB_create(nfeatures=config.feature_max_keypoints)
        matcher = cv2.BFMatcher(cv2.NORM_HAMMING)

    ref_u8 = np.clip(ref_strip, 0, 255).astype(np.uint8)
    mov_u8 = np.clip(mov_strip, 0, 255).astype(np.uint8)
    key_ref, desc_ref = detector.detectAndCompute(ref_u8, ref_mask)
    key_mov, desc_mov = detector.detectAndCompute(mov_u8, mov_mask)
    if desc_ref is None or desc_mov is None or len(key_ref) < config.feature_min_matches or len(key_mov) < config.feature_min_matches:
        raise RuntimeError("Not enough keypoints for feature alignment")

    raw_matches = matcher.knnMatch(desc_ref, desc_mov, k=2)
    good_matches = [first for first, second in raw_matches if second is not None and first.distance < 0.75 * second.distance]
    if len(good_matches) < config.feature_min_matches:
        raise RuntimeError("Not enough reliable feature matches")

    src = np.float32([key_ref[match.queryIdx].pt for match in good_matches]).reshape(-1, 1, 2)
    dst = np.float32([key_mov[match.trainIdx].pt for match in good_matches]).reshape(-1, 1, 2)
    matrix, inliers = cv2.estimateAffinePartial2D(dst, src, method=cv2.RANSAC, ransacReprojThreshold=3.0)
    if matrix is None or inliers is None:
        raise RuntimeError("Feature alignment could not estimate a transform")

    inlier_mask = inliers.ravel().astype(bool)
    score = float(np.count_nonzero(inlier_mask)) / float(max(1, len(good_matches)))
    angle = math.degrees(math.atan2(float(matrix[1, 0]), float(matrix[0, 0])))
    matches_image = cv2.drawMatches(
        cv2.cvtColor(ref_u8, cv2.COLOR_GRAY2BGR),
        key_ref,
        cv2.cvtColor(mov_u8, cv2.COLOR_GRAY2BGR),
        key_mov,
        [good_matches[index] for index, keep in enumerate(inlier_mask.tolist()) if keep][:50],
        None,
        flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS,
    )
    return float(matrix[0, 2]), float(matrix[1, 2]), angle, score, matches_image


def _candidate_views(
    ref_gray: np.ndarray,
    mov_gray: np.ndarray,
    ref_mask: np.ndarray | None,
    mov_mask: np.ndarray | None,
    overlap_ratio: float,
    candidate_min_pixels: int,
) -> list[dict[str, Any]]:
    height, width = ref_gray.shape[:2]
    overlap_x = max(candidate_min_pixels, int(round(width * overlap_ratio)))
    overlap_y = max(candidate_min_pixels, int(round(height * overlap_ratio)))
    overlap_x = min(width - 1, overlap_x)
    overlap_y = min(height - 1, overlap_y)

    return [
        {
            "direction": "right",
            "ref_strip": ref_gray[:, width - overlap_x :],
            "mov_strip": mov_gray[:, :overlap_x],
            "ref_mask": None if ref_mask is None else ref_mask[:, width - overlap_x :],
            "mov_mask": None if mov_mask is None else mov_mask[:, :overlap_x],
            "base_dx": float(width - overlap_x),
            "base_dy": 0.0,
        },
        {
            "direction": "left",
            "ref_strip": ref_gray[:, :overlap_x],
            "mov_strip": mov_gray[:, width - overlap_x :],
            "ref_mask": None if ref_mask is None else ref_mask[:, :overlap_x],
            "mov_mask": None if mov_mask is None else mov_mask[:, width - overlap_x :],
            "base_dx": float(-(width - overlap_x)),
            "base_dy": 0.0,
        },
        {
            "direction": "down",
            "ref_strip": ref_gray[height - overlap_y :, :],
            "mov_strip": mov_gray[:overlap_y, :],
            "ref_mask": None if ref_mask is None else ref_mask[height - overlap_y :, :],
            "mov_mask": None if mov_mask is None else mov_mask[:overlap_y, :],
            "base_dx": 0.0,
            "base_dy": float(height - overlap_y),
        },
        {
            "direction": "up",
            "ref_strip": ref_gray[:overlap_y, :],
            "mov_strip": mov_gray[height - overlap_y :, :],
            "ref_mask": None if ref_mask is None else ref_mask[:overlap_y, :],
            "mov_mask": None if mov_mask is None else mov_mask[height - overlap_y :, :],
            "base_dx": 0.0,
            "base_dy": float(-(height - overlap_y)),
        },
    ]


def _compute_axis_overlap(direction: str, dx: float, dy: float, width: int, height: int) -> float:
    if direction in {"right", "left"}:
        return max(0.0, min(1.0, (width - abs(dx)) / float(max(1, width))))
    return max(0.0, min(1.0, (height - abs(dy)) / float(max(1, height))))


def _validate_candidate(result: AlignmentResult, width: int, height: int, config: StitchingConfig) -> bool:
    if not result.success:
        return False
    if abs(result.angle) > config.max_rotation + 1e-3:
        return False
    if result.direction == "right" and result.dx <= 0:
        return False
    if result.direction == "left" and result.dx >= 0:
        return False
    if result.direction == "down" and result.dy <= 0:
        return False
    if result.direction == "up" and result.dy >= 0:
        return False
    if result.direction in {"right", "left"} and abs(result.dy) > height * config.max_relative_shift:
        return False
    if result.direction in {"up", "down"} and abs(result.dx) > width * config.max_relative_shift:
        return False
    axis_overlap = _compute_axis_overlap(result.direction, result.dx, result.dy, width, height)
    return 0.05 <= axis_overlap <= 0.95


def _rank_value(result: AlignmentResult, width: int, height: int, target_overlap: float) -> tuple[float, float]:
    axis_overlap = _compute_axis_overlap(result.direction, result.dx, result.dy, width, height)
    return (result.score, -abs(axis_overlap - target_overlap))


def _method_chain(primary: str) -> list[str]:
    if primary == "auto":
        return ["phase", "ecc", "orb", "sift"]
    if primary == "phase":
        return ["phase", "ecc", "orb", "sift"]
    if primary == "ecc":
        return ["ecc", "phase", "orb", "sift"]
    if primary == "orb":
        return ["orb", "phase", "ecc", "sift"]
    if primary == "sift":
        return ["sift", "phase", "ecc", "orb"]
    return [primary]


_XY_FILENAME_PATTERN = re.compile(r"^(?P<x>-?\d+)[_](?P<y>-?\d+)$")


def _infer_direction_hint(ref_name: str, mov_name: str) -> str | None:
    ref_match = _XY_FILENAME_PATTERN.match(ref_name)
    mov_match = _XY_FILENAME_PATTERN.match(mov_name)
    if ref_match is None or mov_match is None:
        return None

    ref_x = int(ref_match.group("x"))
    ref_y = int(ref_match.group("y"))
    mov_x = int(mov_match.group("x"))
    mov_y = int(mov_match.group("y"))

    dx = mov_x - ref_x
    dy = mov_y - ref_y
    if dx > 0 and dy == 0:
        return "right"
    if dx < 0 and dy == 0:
        return "left"
    if dy > 0 and dx == 0:
        return "down"
    if dy < 0 and dx == 0:
        return "up"
    return None


def prepare_guidance(tile: PreprocessedImage, detector: YoloGuidance | None) -> tuple[np.ndarray | None, np.ndarray | None, int]:
    if detector is None or not detector.available:
        return None, None, 0
    detections = detector.detect(tile.blend_bgr)
    if not detections:
        return None, tile.blend_bgr.copy(), 0
    return detector.build_mask(tile.blend_bgr.shape[:2], detections), detector.annotate(tile.blend_bgr, detections), len(detections)


def estimate_pairwise_shift(
    ref_tile: PreprocessedImage,
    mov_tile: PreprocessedImage,
    config: StitchingConfig,
    logger: Any | None = None,
) -> AlignmentResult:
    """Estimate the relative translation of two neighboring images."""

    height, width = ref_tile.original_bgr.shape[:2]
    guidance_modes = [False]
    if config.use_yolo_guidance and ref_tile.guidance_mask is not None and mov_tile.guidance_mask is not None:
        guidance_modes = [True, False]
    direction_hint = _infer_direction_hint(ref_tile.path.stem, mov_tile.path.stem)

    last_error = "No valid alignment candidate"
    for guided in guidance_modes:
        ref_mask = ref_tile.guidance_mask if guided else None
        mov_mask = mov_tile.guidance_mask if guided else None
        for method in _method_chain(config.alignment_method):
            best_result: AlignmentResult | None = None
            candidates = _candidate_views(
                ref_tile.alignment_gray,
                mov_tile.alignment_gray,
                ref_mask,
                mov_mask,
                config.overlap_ratio,
                config.candidate_min_pixels,
            )
            if direction_hint is not None:
                hinted_candidates = [candidate for candidate in candidates if candidate["direction"] == direction_hint]
                if hinted_candidates:
                    candidates = hinted_candidates
            for candidate in candidates:
                try:
                    if method == "phase":
                        if config.runtime is not None and config.runtime.device == "cuda":
                            local_dx, local_dy, angle, score = _estimate_phase_gpu(
                                candidate["ref_strip"],
                                candidate["mov_strip"],
                                candidate["ref_mask"],
                                candidate["mov_mask"],
                            )
                            if score < config.phase_score_floor:
                                raise RuntimeError(f"GPU phase score {score:.6f} below floor {config.phase_score_floor:.6f}")
                        else:
                            local_dx, local_dy, angle, score = _estimate_phase_cpu(
                                candidate["ref_strip"],
                                candidate["mov_strip"],
                                candidate["ref_mask"],
                                candidate["mov_mask"],
                            )
                        matches_image = None
                    elif method == "ecc":
                        local_dx, local_dy, angle, score = _estimate_ecc(candidate["ref_strip"], candidate["mov_strip"], candidate["ref_mask"], candidate["mov_mask"], allow_rotation=config.max_rotation > 0.0)
                        matches_image = None
                    else:
                        local_dx, local_dy, angle, score, matches_image = _estimate_feature(method, candidate["ref_strip"], candidate["mov_strip"], candidate["ref_mask"], candidate["mov_mask"], config)
                except Exception as exc:
                    if method == "phase" and config.runtime is not None and config.runtime.device == "cuda":
                        if config.gpu_fallback_allowed:
                            reason = str(exc)
                            if reason.startswith("GPU phase score"):
                                reason = "GPU phase correlation score fell below the configured floor."
                            config.record_fallback("alignment.phase", reason, "cuda", "cpu")
                            try:
                                local_dx, local_dy, angle, score = _estimate_phase_cpu(
                                    candidate["ref_strip"],
                                    candidate["mov_strip"],
                                    candidate["ref_mask"],
                                    candidate["mov_mask"],
                                )
                                matches_image = None
                            except Exception as cpu_exc:
                                last_error = f"{method}/{candidate['direction']}: {cpu_exc}"
                                continue
                        else:
                            raise
                    else:
                        last_error = f"{method}/{candidate['direction']}: {exc}"
                        continue

                result = AlignmentResult(
                    success=True,
                    dx=(candidate["base_dx"] + float(local_dx)) * float(ref_tile.alignment_scale_x),
                    dy=(candidate["base_dy"] + float(local_dy)) * float(ref_tile.alignment_scale_y),
                    angle=float(angle),
                    score=float(score),
                    method=method,
                    direction=str(candidate["direction"]),
                    used_yolo_guidance=guided,
                    debug={
                        "ref_strip": candidate["ref_strip"],
                        "mov_strip": candidate["mov_strip"],
                        "ref_mask": candidate["ref_mask"],
                        "mov_mask": candidate["mov_mask"],
                        "local_dx": float(local_dx),
                        "local_dy": float(local_dy),
                        "matches_image": matches_image,
                    },
                )
                if not _validate_candidate(result, width, height, config):
                    continue
                if best_result is None or _rank_value(result, width, height, config.overlap_ratio) > _rank_value(best_result, width, height, config.overlap_ratio):
                    best_result = result

            if best_result is not None:
                if logger is not None:
                    logger.info(
                        "Aligned %s -> %s using %s (%s, yolo_guided=%s): dx=%.2f dy=%.2f angle=%.2f score=%.4f",
                        ref_tile.path.name,
                        mov_tile.path.name,
                        best_result.method,
                        best_result.direction,
                        best_result.used_yolo_guidance,
                        best_result.dx,
                        best_result.dy,
                        best_result.angle,
                        best_result.score,
                    )
                return best_result

    return AlignmentResult(
        success=False,
        dx=0.0,
        dy=0.0,
        angle=0.0,
        score=0.0,
        method=config.alignment_method,
        direction="unknown",
        used_yolo_guidance=False,
        error=last_error,
    )

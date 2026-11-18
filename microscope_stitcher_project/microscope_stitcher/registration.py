from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from .config import StitchConfig
from .features import detect_and_compute
from .matching import ratio_match
from .types import DetectionFeature, PairEdge


def estimate_pair_transform(
    ref_gray: np.ndarray,
    mov_gray: np.ndarray,
    ref_color: np.ndarray,
    mov_color: np.ndarray,
    ref_features: list[DetectionFeature],
    mov_features: list[DetectionFeature],
    expected_dx: float,
    expected_dy: float,
    ref_name: str,
    mov_name: str,
    edge_ref: int,
    edge_mov: int,
    config: StitchConfig,
    debug_pair_dir: Path | None,
) -> PairEdge:
    attempts: list[PairEdge] = []

    if config.use_detection_features:
        detection_edge = _detection_feature_registration(
            ref_features,
            mov_features,
            expected_dx,
            expected_dy,
            edge_ref,
            edge_mov,
            config,
        )
        attempts.append(detection_edge)
        if detection_edge.success:
            _save_pair_debug(debug_pair_dir, ref_color, mov_color, ref_name, mov_name, detection_edge)
            return detection_edge

    phase_edge = _phase_ecc_registration(ref_gray, mov_gray, expected_dx, expected_dy, edge_ref, edge_mov, config)
    attempts.append(phase_edge)
    if phase_edge.success and phase_edge.score >= 0.08:
        _save_pair_debug(debug_pair_dir, ref_color, mov_color, ref_name, mov_name, phase_edge)
        return phase_edge

    feature_edge = _feature_registration(ref_gray, mov_gray, ref_color, mov_color, expected_dx, expected_dy, edge_ref, edge_mov, config, debug_pair_dir, ref_name, mov_name)
    attempts.append(feature_edge)
    if feature_edge.success and feature_edge.score >= 0.06:
        return feature_edge

    ncc_edge = _ncc_search(ref_gray, mov_gray, expected_dx, expected_dy, edge_ref, edge_mov, config)
    attempts.append(ncc_edge)
    if ncc_edge.success:
        _save_pair_debug(debug_pair_dir, ref_color, mov_color, ref_name, mov_name, ncc_edge)
        return ncc_edge

    best = max(attempts, key=lambda item: item.score)
    fallback = PairEdge(
        ref=edge_ref,
        mov=edge_mov,
        expected_dx=expected_dx,
        expected_dy=expected_dy,
        dx=expected_dx,
        dy=expected_dy,
        method="stage_coordinate_fallback",
        score=max(0.01, best.score),
        success=False,
        details={"failed_attempts": [edge.method for edge in attempts]},
    )
    _save_pair_debug(debug_pair_dir, ref_color, mov_color, ref_name, mov_name, fallback)
    return fallback


def _detection_feature_registration(
    ref_features: list[DetectionFeature],
    mov_features: list[DetectionFeature],
    expected_dx: float,
    expected_dy: float,
    edge_ref: int,
    edge_mov: int,
    config: StitchConfig,
) -> PairEdge:
    if not ref_features or not mov_features:
        return _failed(edge_ref, edge_mov, expected_dx, expected_dy, "detection_features_unavailable")

    primary_is_y = abs(expected_dy) >= abs(expected_dx)
    primary_radius = max(35.0, min(170.0, abs(expected_dy if primary_is_y else expected_dx) * 0.35))
    secondary_radius = max(25.0, min(95.0, abs(expected_dx if primary_is_y else expected_dy) * 0.35 + 65.0))
    candidates = []
    for ref_idx, ref_feature in enumerate(ref_features):
        for mov_idx, mov_feature in enumerate(mov_features):
            if ref_feature.cls_id != mov_feature.cls_id:
                continue
            if _landmark_label_weight(ref_feature.label) <= 1.0:
                continue
            area_ratio = min(ref_feature.area, mov_feature.area) / max(ref_feature.area, mov_feature.area, 1.0)
            if area_ratio < 0.45:
                continue
            dx = ref_feature.cx - mov_feature.cx
            dy = ref_feature.cy - mov_feature.cy
            primary_delta = abs((dy if primary_is_y else dx) - (expected_dy if primary_is_y else expected_dx))
            secondary_delta = abs((dx if primary_is_y else dy) - (expected_dx if primary_is_y else expected_dy))
            if primary_delta > primary_radius or secondary_delta > secondary_radius:
                continue
            label_weight = _landmark_label_weight(ref_feature.label)
            distance_score = 1.0
            distance_score -= min(1.0, primary_delta / max(primary_radius, 1.0)) * 0.55
            distance_score -= min(1.0, secondary_delta / max(secondary_radius, 1.0)) * 0.35
            score = (distance_score + area_ratio * 0.25 + min(ref_feature.conf, mov_feature.conf) * 0.20) * label_weight
            candidates.append((score, dx, dy, ref_idx, mov_idx, ref_feature, mov_feature))

    if not candidates:
        return _failed(edge_ref, edge_mov, expected_dx, expected_dy, "detection_features_no_candidates")

    cluster_tolerance = float(config.detection_feature_cluster_tolerance_px)
    best_cluster = []
    best_support = -1.0
    for candidate in candidates:
        center = np.array([candidate[1], candidate[2]], dtype=np.float64)
        cluster = [
            item for item in candidates
            if np.linalg.norm(np.array([item[1], item[2]], dtype=np.float64) - center) <= cluster_tolerance
        ]
        deduped_cluster = _dedupe_detection_cluster(cluster)
        support = float(sum(item[0] for item in deduped_cluster))
        if (len(deduped_cluster), support) > (len(best_cluster), best_support):
            best_cluster = deduped_cluster
            best_support = support

    required_matches = int(config.detection_feature_min_matches)
    if len(best_cluster) < required_matches:
        return _failed(edge_ref, edge_mov, expected_dx, expected_dy, "detection_features_not_enough_cluster_matches", len(best_cluster))

    weights = np.array([max(0.01, item[0]) for item in best_cluster], dtype=np.float64)
    dx = float(np.average([item[1] for item in best_cluster], weights=weights))
    dy = float(np.average([item[2] for item in best_cluster], weights=weights))
    points = np.array([[item[1], item[2]] for item in best_cluster], dtype=np.float64)
    spread = float(max(np.linalg.norm(point - np.array([dx, dy])) for point in points)) if len(points) > 1 else 0.0
    normalized_support = min(1.0, best_support / max(1.0, required_matches * 1.2))
    score = float(max(0.05, normalized_support * (1.0 - min(0.8, spread / max(cluster_tolerance * 2.0, 1.0)))))
    success = score >= 0.45
    return PairEdge(
        ref=edge_ref,
        mov=edge_mov,
        expected_dx=expected_dx,
        expected_dy=expected_dy,
        dx=dx,
        dy=dy,
        method="detection_feature_landmark",
        score=score,
        success=success,
        matches=len(best_cluster),
        matrix=[[1.0, 0.0, dx], [0.0, 1.0, dy], [0.0, 0.0, 1.0]],
        details={
            "candidate_matches": len(candidates),
            "cluster_matches": len(best_cluster),
            "important_matches": len(best_cluster),
            "cluster_spread_px": spread,
            "cluster_tolerance_px": cluster_tolerance,
            "sample_matches": [
                {
                    "score": float(item[0]),
                    "dx": float(item[1]),
                    "dy": float(item[2]),
                    "label": item[5].label,
                    "ref": {"cx": item[5].cx, "cy": item[5].cy, "conf": item[5].conf},
                    "mov": {"cx": item[6].cx, "cy": item[6].cy, "conf": item[6].conf},
                }
                for item in best_cluster[:10]
            ],
        },
    )


def _dedupe_detection_cluster(cluster):
    deduped = []
    used_ref = set()
    used_mov = set()
    for item in sorted(cluster, key=lambda candidate: candidate[0], reverse=True):
        ref_idx = int(item[3])
        mov_idx = int(item[4])
        if ref_idx in used_ref or mov_idx in used_mov:
            continue
        used_ref.add(ref_idx)
        used_mov.add(mov_idx)
        deduped.append(item)
    return deduped


def _landmark_label_weight(label: str) -> float:
    normalized = label.strip().lower()
    if normalized in {"platelet", "platelets", "plt", "血小板"}:
        return 3.0
    if normalized in {"wbc", "white_blood_cell", "white blood cell", "白血球"}:
        return 4.0
    return 1.0


def _phase_ecc_registration(
    ref: np.ndarray,
    mov: np.ndarray,
    expected_dx: float,
    expected_dy: float,
    edge_ref: int,
    edge_mov: int,
    config: StitchConfig,
) -> PairEdge:
    ref_roi, mov_roi = _overlap_rois(ref, mov, expected_dx, expected_dy, config.min_overlap_px)
    if ref_roi is None or mov_roi is None:
        return _failed(edge_ref, edge_mov, expected_dx, expected_dy, "phase_overlap_too_small")

    ref_f = _prep_float(ref_roi)
    mov_f = _prep_float(mov_roi)
    window = cv2.createHanningWindow((ref_f.shape[1], ref_f.shape[0]), cv2.CV_32F)
    try:
        shift, response = cv2.phaseCorrelate(ref_f, mov_f, window)
    except cv2.error:
        return _failed(edge_ref, edge_mov, expected_dx, expected_dy, "phase_correlation_failed")

    candidates = [
        (expected_dx + shift[0], expected_dy + shift[1], "phase_overlap_subpixel"),
        (expected_dx - shift[0], expected_dy - shift[1], "phase_overlap_subpixel"),
    ]

    try:
        criteria = (
            cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT,
            config.ecc_iterations,
            config.ecc_eps,
        )
        warp = np.eye(2, 3, dtype=np.float32)
        cc, warp = cv2.findTransformECC(ref_f, mov_f, warp, cv2.MOTION_TRANSLATION, criteria, None, 5)
        tx, ty = float(warp[0, 2]), float(warp[1, 2])
        candidates.extend(
            [
                (expected_dx + tx, expected_dy + ty, "phase_ecc_refined"),
                (expected_dx - tx, expected_dy - ty, "phase_ecc_refined"),
            ]
        )
    except cv2.error:
        cc = None

    dx, dy, method, score = _best_scored_candidate(ref, mov, candidates, config)
    success = score > 0.03
    return PairEdge(
        ref=edge_ref,
        mov=edge_mov,
        expected_dx=expected_dx,
        expected_dy=expected_dy,
        dx=dx,
        dy=dy,
        method=method,
        score=float(score),
        success=success,
        matrix=[[1.0, 0.0, dx], [0.0, 1.0, dy], [0.0, 0.0, 1.0]],
        details={"phase_response": float(response), "ecc_score": None if cc is None else float(cc), "subpixel": True},
    )


def _feature_registration(
    ref_gray: np.ndarray,
    mov_gray: np.ndarray,
    ref_color: np.ndarray,
    mov_color: np.ndarray,
    expected_dx: float,
    expected_dy: float,
    edge_ref: int,
    edge_mov: int,
    config: StitchConfig,
    debug_pair_dir: Path | None,
    ref_name: str,
    mov_name: str,
) -> PairEdge:
    kp_ref, desc_ref, norm = detect_and_compute(ref_gray, config.feature_method, config.max_features)
    kp_mov, desc_mov, _ = detect_and_compute(mov_gray, config.feature_method, config.max_features)
    matches = ratio_match(desc_mov, desc_ref, norm, config.ratio_test)
    if len(matches) < config.min_feature_matches:
        return _failed(edge_ref, edge_mov, expected_dx, expected_dy, f"{config.feature_method}_not_enough_matches", len(matches))

    mov_pts = np.float32([kp_mov[m.queryIdx].pt for m in matches]).reshape(-1, 1, 2)
    ref_pts = np.float32([kp_ref[m.trainIdx].pt for m in matches]).reshape(-1, 1, 2)
    matrix, mask = cv2.findHomography(mov_pts, ref_pts, cv2.RANSAC, 4.0)
    if matrix is None or mask is None:
        return _failed(edge_ref, edge_mov, expected_dx, expected_dy, "homography_failed", len(matches))

    inliers = int(mask.ravel().sum())
    if inliers < config.min_feature_matches:
        return _failed(edge_ref, edge_mov, expected_dx, expected_dy, "homography_not_enough_inliers", len(matches))

    dx = float(matrix[0, 2])
    dy = float(matrix[1, 2])
    deviation = float(np.hypot(dx - expected_dx, dy - expected_dy))
    max_deviation = max(ref_gray.shape[:2]) * 0.45
    score = _alignment_score_for_shift(ref_gray, mov_gray, dx, dy, config) * (inliers / max(1, len(matches)))
    if abs(expected_dx) >= abs(expected_dy):
        orthogonal_deviation = abs(dy - expected_dy)
    else:
        orthogonal_deviation = abs(dx - expected_dx)
    high_confidence_feature = (
        score >= config.feature_override_score
        and inliers >= config.feature_override_inliers
        and orthogonal_deviation <= config.feature_override_max_orthogonal_px
    )
    success = score > 0.02 and (deviation <= max_deviation or high_confidence_feature)
    edge = PairEdge(
        ref=edge_ref,
        mov=edge_mov,
        expected_dx=expected_dx,
        expected_dy=expected_dy,
        dx=dx,
        dy=dy,
        method=f"{config.feature_method}_homography_fallback",
        score=float(score),
        success=success,
        matches=inliers,
        matrix=matrix.tolist(),
        details={
            "raw_matches": len(matches),
            "inliers": inliers,
            "deviation_from_stage": deviation,
            "orthogonal_deviation_from_stage": orthogonal_deviation,
            "feature_override_max_orthogonal_px": config.feature_override_max_orthogonal_px,
        },
    )
    edge.details["stage_deviation_allowed_by_high_confidence_feature"] = bool(
        deviation > max_deviation and high_confidence_feature
    )
    _save_matches_debug(debug_pair_dir, ref_color, mov_color, kp_ref, kp_mov, matches, mask, ref_name, mov_name)
    _save_pair_debug(debug_pair_dir, ref_color, mov_color, ref_name, mov_name, edge)
    return edge


def _ncc_search(
    ref: np.ndarray,
    mov: np.ndarray,
    expected_dx: float,
    expected_dy: float,
    edge_ref: int,
    edge_mov: int,
    config: StitchConfig,
) -> PairEdge:
    radius = int(config.ncc_search_radius)
    step = int(config.ncc_search_step)
    candidates = []
    for yy in range(-radius, radius + 1, step):
        for xx in range(-radius, radius + 1, step):
            candidates.append((expected_dx + xx, expected_dy + yy, "local_ncc_search"))
    dx, dy, method, score = _best_scored_candidate(ref, mov, candidates, config)
    return PairEdge(
        ref=edge_ref,
        mov=edge_mov,
        expected_dx=expected_dx,
        expected_dy=expected_dy,
        dx=dx,
        dy=dy,
        method=method,
        score=float(score),
        success=score > 0.025,
        matrix=[[1.0, 0.0, dx], [0.0, 1.0, dy], [0.0, 0.0, 1.0]],
        details={"search_radius": radius, "search_step": step},
    )


def _best_scored_candidate(
    ref: np.ndarray,
    mov: np.ndarray,
    candidates: list[tuple[float, float, str]],
    config: StitchConfig,
):
    best = (0.0, 0.0, "none", -1.0)
    for dx, dy, method in candidates:
        score = _alignment_score_for_shift(ref, mov, dx, dy, config)
        if score > best[3]:
            best = (float(dx), float(dy), method, float(score))
    return best


def _alignment_score_for_shift(ref: np.ndarray, mov: np.ndarray, dx: float, dy: float, config: StitchConfig) -> float:
    base_score = _ncc_score_for_shift(ref, mov, dx, dy)
    weight = float(config.small_feature_weight)
    if weight <= 1e-6:
        return base_score
    small_feature_score = _small_feature_score_for_shift(ref, mov, dx, dy)
    if small_feature_score < -0.5:
        return base_score
    return float((1.0 - weight) * base_score + weight * small_feature_score)


def _overlap_rois(ref: np.ndarray, mov: np.ndarray, dx: float, dy: float, min_size: int):
    h, w = ref.shape[:2]
    hm, wm = mov.shape[:2]
    ix = int(round(dx))
    iy = int(round(dy))
    x0_ref = max(0, ix)
    y0_ref = max(0, iy)
    x1_ref = min(w, ix + wm)
    y1_ref = min(h, iy + hm)
    x0_mov = max(0, -ix)
    y0_mov = max(0, -iy)
    x1_mov = x0_mov + (x1_ref - x0_ref)
    y1_mov = y0_mov + (y1_ref - y0_ref)
    if (x1_ref - x0_ref) < min_size or (y1_ref - y0_ref) < min_size:
        return None, None
    return ref[y0_ref:y1_ref, x0_ref:x1_ref], mov[y0_mov:y1_mov, x0_mov:x1_mov]


def _ncc_score_for_shift(ref: np.ndarray, mov: np.ndarray, dx: float, dy: float) -> float:
    ref_roi, mov_roi = _overlap_rois(ref, mov, dx, dy, 24)
    if ref_roi is None or mov_roi is None:
        return -1.0
    if max(ref_roi.shape[:2]) > 420:
        scale = 420.0 / max(ref_roi.shape[:2])
        size = (max(8, int(ref_roi.shape[1] * scale)), max(8, int(ref_roi.shape[0] * scale)))
        ref_roi = cv2.resize(ref_roi, size, interpolation=cv2.INTER_AREA)
        mov_roi = cv2.resize(mov_roi, size, interpolation=cv2.INTER_AREA)
    return _ncc_arrays(ref_roi, mov_roi)


def _small_feature_score_for_shift(ref: np.ndarray, mov: np.ndarray, dx: float, dy: float) -> float:
    ref_roi, mov_roi = _overlap_rois(ref, mov, dx, dy, 24)
    if ref_roi is None or mov_roi is None:
        return -1.0
    if max(ref_roi.shape[:2]) > 420:
        scale = 420.0 / max(ref_roi.shape[:2])
        size = (max(8, int(ref_roi.shape[1] * scale)), max(8, int(ref_roi.shape[0] * scale)))
        ref_roi = cv2.resize(ref_roi, size, interpolation=cv2.INTER_AREA)
        mov_roi = cv2.resize(mov_roi, size, interpolation=cv2.INTER_AREA)
    return _ncc_arrays(_small_feature_map(ref_roi), _small_feature_map(mov_roi))


def _ncc_arrays(a: np.ndarray, b: np.ndarray) -> float:
    a = a.astype(np.float32)
    b = b.astype(np.float32)
    a -= float(a.mean())
    b -= float(b.mean())
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom <= 1e-6:
        return -1.0
    return float(np.sum(a * b) / denom)


def _small_feature_map(gray: np.ndarray) -> np.ndarray:
    if gray.ndim == 3:
        gray = cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)
    src = gray.astype(np.uint8, copy=False)
    blurred = cv2.GaussianBlur(src, (3, 3), 0)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    blackhat = cv2.morphologyEx(blurred, cv2.MORPH_BLACKHAT, kernel).astype(np.float32)
    tophat = cv2.morphologyEx(blurred, cv2.MORPH_TOPHAT, kernel).astype(np.float32)
    lap = np.abs(cv2.Laplacian(blurred, cv2.CV_32F, ksize=3))
    combined = blackhat * 1.6 + tophat * 0.7 + lap * 0.25
    combined = cv2.GaussianBlur(combined, (3, 3), 0)
    return cv2.normalize(combined, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)


def _prep_float(gray: np.ndarray) -> np.ndarray:
    arr = gray.astype(np.float32)
    arr -= float(arr.mean())
    std = float(arr.std())
    if std > 1e-6:
        arr /= std
    return arr


def _failed(ref: int, mov: int, expected_dx: float, expected_dy: float, method: str, matches: int = 0) -> PairEdge:
    return PairEdge(ref, mov, expected_dx, expected_dy, expected_dx, expected_dy, method, -1.0, False, matches=matches)


def _save_pair_debug(debug_pair_dir: Path | None, ref_color: np.ndarray, mov_color: np.ndarray, ref_name: str, mov_name: str, edge: PairEdge) -> None:
    if debug_pair_dir is None:
        return
    ref_roi, mov_roi = _overlap_rois(ref_color, mov_color, edge.dx, edge.dy, 12)
    if ref_roi is None or mov_roi is None:
        return
    overlay = cv2.addWeighted(ref_roi, 0.5, mov_roi, 0.5, 0)
    out = debug_pair_dir / f"{Path(ref_name).stem}__{Path(mov_name).stem}__overlap_{edge.method}.jpg"
    cv2.imwrite(str(out), overlay)
    edge.details["overlap_debug"] = str(out)


def _save_matches_debug(debug_pair_dir: Path | None, ref_color, mov_color, kp_ref, kp_mov, matches, mask, ref_name: str, mov_name: str) -> None:
    if debug_pair_dir is None:
        return
    selected = matches[:80]
    inlier_mask = None
    if mask is not None:
        inlier_mask = [int(value) for value in mask.ravel().tolist()[: len(selected)]]
    drawn = cv2.drawMatches(
        mov_color,
        kp_mov,
        ref_color,
        kp_ref,
        selected,
        None,
        matchesMask=inlier_mask,
        flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS,
    )
    out = debug_pair_dir / f"{Path(ref_name).stem}__{Path(mov_name).stem}__matches.jpg"
    cv2.imwrite(str(out), drawn)

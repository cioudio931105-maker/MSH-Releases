from __future__ import annotations

import cv2
import numpy as np


def laplacian_variance(frame_bgr: np.ndarray) -> float:
    """Return a simple focus score. Lower values mean a blurrier image."""
    if frame_bgr is None or frame_bgr.size == 0:
        return 0.0
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def is_blurry(frame_bgr: np.ndarray, threshold: float) -> tuple[bool, float]:
    score = laplacian_variance(frame_bgr)
    return score < float(threshold), score


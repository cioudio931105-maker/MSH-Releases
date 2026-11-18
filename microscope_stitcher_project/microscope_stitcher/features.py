from __future__ import annotations

import cv2
import numpy as np


def create_detector(method: str, max_features: int):
    if method == "sift" and hasattr(cv2, "SIFT_create"):
        return cv2.SIFT_create(nfeatures=max_features), cv2.NORM_L2
    return cv2.ORB_create(nfeatures=max_features, fastThreshold=7, edgeThreshold=12), cv2.NORM_HAMMING


def detect_and_compute(gray: np.ndarray, method: str, max_features: int):
    detector, norm = create_detector(method, max_features)
    keypoints, descriptors = detector.detectAndCompute(gray, None)
    if descriptors is None:
        descriptors = np.empty((0, 32), dtype=np.uint8)
    return keypoints, descriptors, norm

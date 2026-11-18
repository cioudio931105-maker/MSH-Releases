from __future__ import annotations

import cv2
import numpy as np


def to_gray(image_bgr: np.ndarray) -> np.ndarray:
    if image_bgr.ndim == 2:
        return image_bgr
    return cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)


def preprocess_for_alignment(image_bgr: np.ndarray) -> np.ndarray:
    gray = to_gray(image_bgr)
    gray = flat_field_correction(gray)
    gray = denoise_and_equalize(gray)
    return np.ascontiguousarray(gray)


def flat_field_correction(gray: np.ndarray, sigma: float = 45.0) -> np.ndarray:
    src = gray.astype(np.float32)
    background = cv2.GaussianBlur(src, (0, 0), sigmaX=sigma, sigmaY=sigma)
    background = np.maximum(background, 1.0)
    corrected = src / background * float(np.mean(background))
    return np.clip(corrected, 0, 255).astype(np.uint8)


def denoise_and_equalize(gray: np.ndarray) -> np.ndarray:
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    return clahe.apply(blurred)

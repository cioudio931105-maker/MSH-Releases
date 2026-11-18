from __future__ import annotations

import cv2
import numpy as np


def ratio_match(desc_a: np.ndarray, desc_b: np.ndarray, norm: int, ratio: float):
    if desc_a is None or desc_b is None or len(desc_a) < 2 or len(desc_b) < 2:
        return []
    matcher = cv2.BFMatcher(norm)
    pairs = matcher.knnMatch(desc_a, desc_b, k=2)
    good = []
    for pair in pairs:
        if len(pair) != 2:
            continue
        first, second = pair
        if first.distance < ratio * second.distance:
            good.append(first)
    return good

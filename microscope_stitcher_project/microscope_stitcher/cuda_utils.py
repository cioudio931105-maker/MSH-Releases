from __future__ import annotations

import cv2


def resolve_cuda(mode: str) -> tuple[bool, str]:
    if mode == "off":
        return False, "disabled by user"
    try:
        count = cv2.cuda.getCudaEnabledDeviceCount() if hasattr(cv2, "cuda") else 0
    except Exception as exc:  # pragma: no cover - depends on OpenCV build
        count = 0
        reason = f"cv2.cuda unavailable: {exc}"
    else:
        reason = f"OpenCV CUDA devices: {count}"

    if count > 0:
        return True, reason
    if mode == "on":
        raise RuntimeError(
            "CUDA was requested, but this OpenCV build cannot see a CUDA device. "
            "Install/build OpenCV with CUDA support for GTX1050, or use --use-cuda auto/off."
        )
    return False, reason

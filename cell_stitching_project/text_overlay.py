from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np


_OPENCV_PUT_TEXT = cv2.putText

_WINDOWS_FONT_CANDIDATES = (
    Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "msjh.ttc",
    Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "mingliu.ttc",
    Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "simsun.ttc",
    Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "simhei.ttf",
)


def _needs_unicode_renderer(text: str) -> bool:
    return any(ord(char) > 127 for char in text)


@lru_cache(maxsize=16)
def _load_font(pixel_size: int):
    try:
        from PIL import ImageFont
    except ImportError:
        return None

    configured = os.environ.get("CELL_PROJECT_FONT_PATH")
    candidates = [Path(configured)] if configured else []
    candidates.extend(_WINDOWS_FONT_CANDIDATES)

    for candidate in candidates:
        if candidate.exists():
            try:
                return ImageFont.truetype(str(candidate), pixel_size)
            except OSError:
                continue
    return None


def _font_pixel_size(font_scale: float) -> int:
    return max(10, int(round(float(font_scale) * 28)))


def _fallback_ascii(text: str) -> str:
    return text.encode("ascii", errors="replace").decode("ascii")


def _is_mojibake_char(char: str) -> bool:
    codepoint = ord(char)
    return (
        char == "\ufffd"
        or 0xE000 <= codepoint <= 0xF8FF
        or 0xFFF0 <= codepoint <= 0xFFFF
    )


def _sanitize_broken_overlay_text(text: str) -> str:
    if "?" not in text and not any(_is_mojibake_char(char) for char in text):
        return text

    normalized = "".join("?" if _is_mojibake_char(char) else char for char in text)
    lower = normalized.lower()
    if lower.startswith("model:") or lower.startswith("detections:"):
        return re.sub(r"\?+", "", normalized).strip()

    detected_count = re.search(r"\(\D*(\d+)\D*\)", normalized)
    if detected_count is not None:
        return f"Blood cell classification (detected {detected_count.group(1)} cells)"

    if "detection" in lower:
        return "cell detection"

    numeric_value = re.search(r"[-+]?\d+(?:\.\d+)?", normalized)
    if numeric_value is not None:
        return f"value: {numeric_value.group(0)}"

    cleaned = re.sub(r"\?+", " ", normalized).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned or "cell overlay"


def get_text_size(
    text: str,
    font_scale: float,
    thickness: int,
    font_face: int = cv2.FONT_HERSHEY_SIMPLEX,
) -> tuple[int, int, int]:
    text = _sanitize_broken_overlay_text(str(text))
    if _needs_unicode_renderer(text):
        font = _load_font(_font_pixel_size(font_scale))
        if font is not None:
            left, top, right, bottom = font.getbbox(text)
            return max(1, right - left), max(1, bottom - top), max(1, int(round(thickness * 2)))
        text = _fallback_ascii(text)

    (text_width, text_height), baseline = cv2.getTextSize(text, font_face, font_scale, thickness)
    return int(text_width), int(text_height), int(baseline)


def put_text(
    image_bgr: np.ndarray,
    text: str,
    origin: tuple[int, int],
    font_scale: float,
    color_bgr: tuple[int, int, int],
    thickness: int = 1,
    font_face: int = cv2.FONT_HERSHEY_SIMPLEX,
    line_type: int = cv2.LINE_AA,
) -> None:
    text = _sanitize_broken_overlay_text(str(text))
    if not _needs_unicode_renderer(text):
        _OPENCV_PUT_TEXT(image_bgr, text, origin, font_face, font_scale, color_bgr, thickness, line_type)
        return

    font = _load_font(_font_pixel_size(font_scale))
    if font is None:
        _OPENCV_PUT_TEXT(image_bgr, _fallback_ascii(text), origin, font_face, font_scale, color_bgr, thickness, line_type)
        return

    from PIL import Image, ImageDraw

    pil_image = Image.fromarray(cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil_image)
    x, baseline_y = origin
    left, top, _right, bottom = font.getbbox(text)
    y = baseline_y - (bottom - top)
    color_rgb = (int(color_bgr[2]), int(color_bgr[1]), int(color_bgr[0]))
    draw.text((int(x - left), int(y - top)), text, font=font, fill=color_rgb)
    image_bgr[:] = cv2.cvtColor(np.asarray(pil_image), cv2.COLOR_RGB2BGR)


def put_text_cv2_compatible(
    image_bgr: np.ndarray,
    text: str,
    origin: tuple[int, int],
    font_face: int,
    font_scale: float,
    color_bgr: tuple[int, int, int],
    thickness: int = 1,
    lineType: int = cv2.LINE_AA,
    bottomLeftOrigin: bool = False,
) -> np.ndarray:
    text = _sanitize_broken_overlay_text(str(text))
    _log_suspicious_text(text)
    if bottomLeftOrigin:
        text = str(text)
        if not _needs_unicode_renderer(text):
            return _OPENCV_PUT_TEXT(
                image_bgr,
                text,
                origin,
                font_face,
                font_scale,
                color_bgr,
                thickness,
                lineType,
                bottomLeftOrigin,
            )
        text = _fallback_ascii(text)
    put_text(
        image_bgr=image_bgr,
        text=str(text),
        origin=origin,
        font_scale=font_scale,
        color_bgr=color_bgr,
        thickness=thickness,
        font_face=font_face,
        line_type=lineType,
    )
    return image_bgr


def _log_suspicious_text(text: object) -> None:
    value = str(text)
    if "?" not in value and not _needs_unicode_renderer(value):
        return
    try:
        log_path = Path(r"C:\Cell_Project\Cell_Project\output\cv2_text_overlay_debug.log")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(repr(value) + "\n")
    except Exception:
        pass


def install_cv2_unicode_puttext_patch() -> None:
    if cv2.putText is put_text_cv2_compatible:
        return
    cv2.putText = put_text_cv2_compatible

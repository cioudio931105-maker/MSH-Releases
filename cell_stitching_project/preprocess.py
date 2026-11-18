from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .config import StitchingConfig
from .runtime import load_torch


@dataclass(slots=True)
class PreprocessedImage:
    """Bundle the original image with preprocessed variants used later."""

    path: Path
    original_bgr: np.ndarray
    blend_bgr: np.ndarray
    alignment_gray: np.ndarray
    alignment_scale_x: float = 1.0
    alignment_scale_y: float = 1.0
    guidance_mask: np.ndarray | None = None
    detection_overlay: np.ndarray | None = None
    detection_count: int = 0


def _normalize_percentile(image: np.ndarray, low_q: float, high_q: float) -> np.ndarray:
    image_f32 = image.astype(np.float32)
    low = float(np.percentile(image_f32, low_q))
    high = float(np.percentile(image_f32, high_q))
    if high <= low:
        return np.clip(image_f32, 0, 255).astype(np.uint8)
    stretched = (image_f32 - low) * (255.0 / (high - low))
    return np.clip(stretched, 0, 255).astype(np.uint8)


def _flatfield_gray(gray: np.ndarray, sigma_ratio: float) -> np.ndarray:
    gray_f32 = gray.astype(np.float32)
    sigma = max(15.0, min(gray.shape[:2]) * float(max(0.01, sigma_ratio)))
    background = cv2.GaussianBlur(gray_f32, (0, 0), sigmaX=sigma, sigmaY=sigma)
    background = np.clip(background, 1.0, None)
    corrected = gray_f32 / background
    corrected *= float(np.mean(background))
    return _normalize_percentile(corrected, 1.0, 99.0)


def _flatfield_bgr(image: np.ndarray, sigma_ratio: float) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float32)
    sigma = max(15.0, min(gray.shape[:2]) * float(max(0.01, sigma_ratio)))
    background = cv2.GaussianBlur(gray, (0, 0), sigmaX=sigma, sigmaY=sigma)
    background = np.clip(background, 1.0, None)
    scale = float(np.mean(background)) / background
    corrected = image.astype(np.float32) * scale[:, :, None]
    return np.clip(corrected, 0, 255).astype(np.uint8)


def _load_kornia() -> Any | None:
    try:
        import kornia
    except Exception:
        return None
    return kornia


def _kernel_size_from_sigma(sigma: float, max_kernel: int = 63) -> int:
    kernel = int(max(5, min(max_kernel, math.ceil(sigma * 6.0) | 1)))
    return kernel if kernel % 2 == 1 else kernel + 1


def _normalize_torch_channel(tensor: Any, low_q: float, high_q: float) -> Any:
    low = tensor.quantile(low_q / 100.0)
    high = tensor.quantile(high_q / 100.0)
    if float((high - low).item()) <= 1e-6:
        return tensor.clamp(0.0, 1.0)
    return ((tensor - low) / (high - low)).clamp(0.0, 1.0)


def _torch_to_uint8_image(tensor: Any) -> np.ndarray:
    tensor = tensor.detach().clamp(0.0, 1.0)
    return (tensor.permute(1, 2, 0).cpu().numpy() * 255.0).round().astype(np.uint8)


def _torch_to_uint8_gray(tensor: Any) -> np.ndarray:
    tensor = tensor.detach().clamp(0.0, 1.0)
    return (tensor.squeeze(0).cpu().numpy() * 255.0).round().astype(np.uint8)


def _approximate_background(gray: Any, sigma_ratio: float, kornia: Any, torch_module: Any) -> Any:
    _, _, height, width = gray.shape
    min_dim = min(height, width)
    target_min_dim = min(256, min_dim)
    scale = float(target_min_dim) / float(min_dim) if min_dim > target_min_dim else 1.0
    reduced = gray
    if scale < 1.0:
        reduced = torch_module.nn.functional.interpolate(
            gray,
            scale_factor=scale,
            mode="bilinear",
            align_corners=False,
        )

    sigma = max(3.0, min(reduced.shape[-2:]) * float(max(0.01, sigma_ratio)))
    kernel_size = _kernel_size_from_sigma(sigma)
    blurred = kornia.filters.gaussian_blur2d(reduced, (kernel_size, kernel_size), (sigma, sigma))
    if scale < 1.0:
        blurred = torch_module.nn.functional.interpolate(
            blurred,
            size=(height, width),
            mode="bilinear",
            align_corners=False,
        )
    return blurred.clamp_min(1e-3)


def _resize_alignment_gray(gray: np.ndarray, max_alignment_long_side: int | None) -> tuple[np.ndarray, float, float]:
    if max_alignment_long_side is None:
        return gray.astype(np.float32), 1.0, 1.0
    height, width = gray.shape[:2]
    long_side = max(height, width)
    if long_side <= int(max_alignment_long_side):
        return gray.astype(np.float32), 1.0, 1.0

    scale = float(max_alignment_long_side) / float(long_side)
    new_width = max(1, int(round(width * scale)))
    new_height = max(1, int(round(height * scale)))
    resized = cv2.resize(gray, (new_width, new_height), interpolation=cv2.INTER_AREA)
    return resized.astype(np.float32), float(width) / float(new_width), float(height) / float(new_height)


def _preprocess_on_gpu(path: Path, image_bgr: np.ndarray, config: StitchingConfig) -> PreprocessedImage:
    torch_module = load_torch()
    kornia = _load_kornia()
    if torch_module is None or kornia is None:
        missing = "torch" if torch_module is None else "kornia"
        raise RuntimeError(f"{missing} is required for GPU preprocessing")
    if config.runtime is None or config.runtime.device != "cuda":
        raise RuntimeError("GPU preprocessing requested without an active CUDA runtime")

    device = torch_module.device("cuda")
    image_tensor = torch_module.from_numpy(image_bgr).to(device=device, dtype=torch_module.float32)
    image_tensor = image_tensor.permute(2, 0, 1).contiguous() / 255.0
    blend_tensor = image_tensor.clone()
    gray = (
        image_tensor[0:1] * 0.1140
        + image_tensor[1:2] * 0.5870
        + image_tensor[2:3] * 0.2990
    )

    if config.use_flatfield:
        gray_batch = gray.unsqueeze(0)
        background = _approximate_background(gray_batch, config.flatfield_sigma_ratio, kornia, torch_module)
        gray = (gray_batch / background * background.mean()).squeeze(0)

        scale = (background.mean() / background).clamp(0.25, 4.0)
        blend_tensor = (blend_tensor.unsqueeze(0) * scale).squeeze(0).clamp(0.0, 1.0)

    if config.use_denoise:
        sigma = max(0.6, float(config.denoise_strength) / 4.0)
        kernel_size = _kernel_size_from_sigma(sigma, max_kernel=15)
        gray = kornia.filters.gaussian_blur2d(
            gray.unsqueeze(0),
            (kernel_size, kernel_size),
            (sigma, sigma),
        ).squeeze(0)

    blend_bgr = _torch_to_uint8_image(blend_tensor)
    alignment_gray = _torch_to_uint8_gray(gray).astype(np.float32)
    if torch_module.cuda.is_available():
        torch_module.cuda.synchronize()

    if config.use_clahe:
        config.record_fallback(
            "preprocess.clahe",
            "GPU CLAHE is unstable on this GPU; used CPU CLAHE.",
            "cuda",
            "cpu",
        )
        clahe = cv2.createCLAHE(
            clipLimit=float(max(0.5, config.clahe_clip_limit)),
            tileGridSize=(int(max(2, config.clahe_tile_grid_size)), int(max(2, config.clahe_tile_grid_size))),
        )
        alignment_gray = clahe.apply(np.clip(alignment_gray, 0, 255).astype(np.uint8)).astype(np.float32)
        blend_bgr = cv2.merge([clahe.apply(channel) for channel in cv2.split(blend_bgr)])

    if config.normalize:
        low_q, high_q = config.normalize_percentiles
        alignment_gray = _normalize_percentile(alignment_gray, low_q, high_q).astype(np.float32)
        blend_bgr = cv2.merge([
            _normalize_percentile(channel, low_q, high_q)
            for channel in cv2.split(blend_bgr)
        ])

    alignment_gray, alignment_scale_x, alignment_scale_y = _resize_alignment_gray(
        alignment_gray,
        config.max_alignment_long_side,
    )

    if alignment_scale_x != 1.0 or alignment_scale_y != 1.0:
        config.with_warning(
            f"Alignment images resized for quality-preserving acceleration (max_alignment_long_side={config.max_alignment_long_side})."
        )

    return PreprocessedImage(
        path=Path(path),
        original_bgr=image_bgr,
        blend_bgr=blend_bgr,
        alignment_gray=alignment_gray,
        alignment_scale_x=alignment_scale_x,
        alignment_scale_y=alignment_scale_y,
    )


def preprocess_image(path: Path, image_bgr: np.ndarray, config: StitchingConfig) -> PreprocessedImage:
    """Generate the alignment grayscale image and the blend-ready image."""

    if config.runtime is not None and config.runtime.device == "cuda":
        try:
            return _preprocess_on_gpu(Path(path), image_bgr, config)
        except Exception as exc:
            if not config.gpu_fallback_allowed:
                raise
            config.record_fallback("preprocess", str(exc), "cuda", "cpu")

    blend_image = image_bgr.copy()
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)

    if config.use_flatfield:
        gray = _flatfield_gray(gray, config.flatfield_sigma_ratio)
        blend_image = _flatfield_bgr(blend_image, config.flatfield_sigma_ratio)

    if config.use_denoise:
        gray = cv2.fastNlMeansDenoising(gray, None, h=float(max(1, config.denoise_strength)))

    if config.use_clahe:
        clahe = cv2.createCLAHE(
            clipLimit=float(max(0.5, config.clahe_clip_limit)),
            tileGridSize=(int(max(2, config.clahe_tile_grid_size)), int(max(2, config.clahe_tile_grid_size))),
        )
        gray = clahe.apply(gray)

    if config.normalize:
        low_q, high_q = config.normalize_percentiles
        gray = _normalize_percentile(gray, low_q, high_q)
        blend_image = cv2.merge([
            _normalize_percentile(channel, low_q, high_q)
            for channel in cv2.split(blend_image)
        ])

    alignment_gray, alignment_scale_x, alignment_scale_y = _resize_alignment_gray(
        gray,
        config.max_alignment_long_side,
    )

    if alignment_scale_x != 1.0 or alignment_scale_y != 1.0:
        config.with_warning(
            f"Alignment images resized for quality-preserving acceleration (max_alignment_long_side={config.max_alignment_long_side})."
        )

    return PreprocessedImage(
        path=Path(path),
        original_bgr=image_bgr,
        blend_bgr=blend_image,
        alignment_gray=alignment_gray,
        alignment_scale_x=alignment_scale_x,
        alignment_scale_y=alignment_scale_y,
    )

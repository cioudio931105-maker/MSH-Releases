from __future__ import annotations

import cv2
import numpy as np

from .config import StitchingConfig
from .layout import CanvasLayout, TilePlacement
from .runtime import load_torch


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


def _gaussian_pyramid(image: np.ndarray, levels: int) -> list[np.ndarray]:
    pyramid = [image.astype(np.float32)]
    for _ in range(1, levels):
        pyramid.append(cv2.pyrDown(pyramid[-1]))
    return pyramid


def _laplacian_pyramid(image: np.ndarray, levels: int) -> list[np.ndarray]:
    gaussian = _gaussian_pyramid(image, levels)
    laplacian: list[np.ndarray] = []
    for index in range(levels - 1):
        expanded = cv2.pyrUp(gaussian[index + 1], dstsize=(gaussian[index].shape[1], gaussian[index].shape[0]))
        laplacian.append(gaussian[index] - expanded)
    laplacian.append(gaussian[-1])
    return laplacian


def _reconstruct_laplacian(pyramid: list[np.ndarray]) -> np.ndarray:
    current = pyramid[-1]
    for level in range(len(pyramid) - 2, -1, -1):
        current = cv2.pyrUp(current, dstsize=(pyramid[level].shape[1], pyramid[level].shape[0]))
        current = current + pyramid[level]
    return current


def _blend_tiles_cpu(images: list[np.ndarray], placements: list[TilePlacement], canvas: CanvasLayout, config: StitchingConfig) -> tuple[np.ndarray, list[str]]:
    warnings: list[str] = []
    method = config.blending_method
    if method == "multiband":
        total_pixels = canvas.width * canvas.height * max(1, len(images))
        if total_pixels > 100_000_000:
            warnings.append("Canvas too large for multiband blending; fell back to feather blending.")
            method = "feather"

    if method in {"average", "feather"}:
        accum = np.zeros((canvas.height, canvas.width, 3), dtype=np.float32)
        weight_accum = np.zeros((canvas.height, canvas.width), dtype=np.float32)
        for image, placement in zip(images, placements):
            height, width = image.shape[:2]
            weight = np.ones((height, width), dtype=np.float32) if method == "average" else _feather_weight_map(height, width)
            y0 = placement.y
            y1 = placement.y + height
            x0 = placement.x
            x1 = placement.x + width
            accum[y0:y1, x0:x1] += image.astype(np.float32) * weight[:, :, None]
            weight_accum[y0:y1, x0:x1] += weight

        output = accum / np.maximum(weight_accum[:, :, None], 1e-6)
        return np.clip(output, 0, 255).astype(np.uint8), warnings

    levels = int(max(1, config.multiband_levels))
    summed_laplacian: list[np.ndarray] | None = None
    summed_weights: list[np.ndarray] | None = None
    for image, placement in zip(images, placements):
        padded = np.zeros((canvas.height, canvas.width, 3), dtype=np.float32)
        weight_map = np.zeros((canvas.height, canvas.width), dtype=np.float32)
        tile_weight = _feather_weight_map(image.shape[0], image.shape[1])
        y0 = placement.y
        y1 = placement.y + image.shape[0]
        x0 = placement.x
        x1 = placement.x + image.shape[1]
        padded[y0:y1, x0:x1] = image.astype(np.float32)
        weight_map[y0:y1, x0:x1] = tile_weight

        laplacian_pyramid = _laplacian_pyramid(padded, levels)
        gaussian_weights = _gaussian_pyramid(weight_map, levels)
        if summed_laplacian is None or summed_weights is None:
            summed_laplacian = [np.zeros_like(level) for level in laplacian_pyramid]
            summed_weights = [np.zeros_like(level) for level in gaussian_weights]

        for index, (lap_level, weight_level) in enumerate(zip(laplacian_pyramid, gaussian_weights)):
            summed_laplacian[index] += lap_level * weight_level[:, :, None]
            summed_weights[index] += weight_level

    assert summed_laplacian is not None and summed_weights is not None
    normalized = [lap_level / np.maximum(weight_level[:, :, None], 1e-6) for lap_level, weight_level in zip(summed_laplacian, summed_weights)]
    output = _reconstruct_laplacian(normalized)
    return np.clip(output, 0, 255).astype(np.uint8), warnings


def _torch_image(image: np.ndarray, torch_module: object, device: object) -> object:
    tensor = torch_module.from_numpy(image.astype(np.float32)).to(device=device)
    return tensor.permute(2, 0, 1).contiguous()


def _torch_weight_map(height: int, width: int, method: str, torch_module: object, device: object) -> object:
    if method == "average":
        return torch_module.ones((1, height, width), dtype=torch_module.float32, device=device)
    if height <= 2 or width <= 2:
        return torch_module.ones((1, height, width), dtype=torch_module.float32, device=device)

    x = torch_module.linspace(0.0, 1.0, width, device=device, dtype=torch_module.float32)
    y = torch_module.linspace(0.0, 1.0, height, device=device, dtype=torch_module.float32)
    x = 1.0 - torch_module.abs((x * 2.0) - 1.0)
    y = 1.0 - torch_module.abs((y * 2.0) - 1.0)
    weight = torch_module.outer(y.clamp_min(0.05), x.clamp_min(0.05))
    return weight.unsqueeze(0)


def _torch_gaussian_pyramid(image: object, levels: int, torch_module: object) -> list[object]:
    pyramid = [image]
    for _ in range(1, levels):
        pyramid.append(
            torch_module.nn.functional.avg_pool2d(
                pyramid[-1].unsqueeze(0),
                kernel_size=2,
                stride=2,
                ceil_mode=True,
            ).squeeze(0)
        )
    return pyramid


def _torch_laplacian_pyramid(image: object, levels: int, torch_module: object) -> list[object]:
    gaussian = _torch_gaussian_pyramid(image, levels, torch_module)
    laplacian: list[object] = []
    for index in range(levels - 1):
        expanded = torch_module.nn.functional.interpolate(
            gaussian[index + 1].unsqueeze(0),
            size=gaussian[index].shape[-2:],
            mode="bilinear",
            align_corners=False,
        ).squeeze(0)
        laplacian.append(gaussian[index] - expanded)
    laplacian.append(gaussian[-1])
    return laplacian


def _torch_reconstruct_laplacian(pyramid: list[object], torch_module: object) -> object:
    current = pyramid[-1]
    for level in range(len(pyramid) - 2, -1, -1):
        current = torch_module.nn.functional.interpolate(
            current.unsqueeze(0),
            size=pyramid[level].shape[-2:],
            mode="bilinear",
            align_corners=False,
        ).squeeze(0)
        current = current + pyramid[level]
    return current


def _estimate_multiband_memory_mb(canvas: CanvasLayout, levels: int, image_count: int) -> int:
    pixel_bytes = canvas.width * canvas.height * 4
    pyramid_factor = sum(1.0 / (4**level) for level in range(levels))
    total = pixel_bytes * pyramid_factor * (8 + image_count)
    return int(total / (1024 * 1024))


def _torch_to_numpy_image(tensor: object) -> np.ndarray:
    return tensor.permute(1, 2, 0).clamp(0.0, 255.0).round().byte().cpu().numpy()


def _blend_tiles_gpu_weighted(
    images: list[np.ndarray],
    placements: list[TilePlacement],
    canvas: CanvasLayout,
    method: str,
    torch_module: object,
    device: object,
) -> np.ndarray:
    accum = torch_module.zeros((3, canvas.height, canvas.width), dtype=torch_module.float32, device=device)
    weight_accum = torch_module.zeros((1, canvas.height, canvas.width), dtype=torch_module.float32, device=device)
    for image, placement in zip(images, placements):
        tile = _torch_image(image, torch_module, device)
        weight = _torch_weight_map(image.shape[0], image.shape[1], method, torch_module, device)
        y0 = placement.y
        y1 = placement.y + image.shape[0]
        x0 = placement.x
        x1 = placement.x + image.shape[1]
        accum[:, y0:y1, x0:x1] += tile * weight
        weight_accum[:, y0:y1, x0:x1] += weight
    output = accum / weight_accum.clamp_min(1e-6)
    torch_module.cuda.synchronize()
    return _torch_to_numpy_image(output)


def _blend_streaming_chunk_cpu(
    chunk_tiles: list[tuple[np.ndarray, np.ndarray, int, int]],
    chunk_height: int,
    chunk_width: int,
) -> np.ndarray:
    accum = np.zeros((chunk_height, chunk_width, 3), dtype=np.float32)
    weight_accum = np.zeros((chunk_height, chunk_width), dtype=np.float32)
    for tile, tile_weight, y0, x0 in chunk_tiles:
        height, width = tile.shape[:2]
        y1 = y0 + height
        x1 = x0 + width
        accum[y0:y1, x0:x1] += tile.astype(np.float32) * tile_weight[:, :, None]
        weight_accum[y0:y1, x0:x1] += tile_weight
    output = accum / np.maximum(weight_accum[:, :, None], 1e-6)
    return np.clip(output, 0, 255).astype(np.uint8)


def _blend_streaming_chunk_gpu(
    chunk_tiles: list[tuple[np.ndarray, np.ndarray, int, int]],
    chunk_height: int,
    chunk_width: int,
    torch_module: object,
    device: object,
) -> np.ndarray:
    accum = torch_module.zeros((3, chunk_height, chunk_width), dtype=torch_module.float32, device=device)
    weight_accum = torch_module.zeros((1, chunk_height, chunk_width), dtype=torch_module.float32, device=device)
    for tile, tile_weight, y0, x0 in chunk_tiles:
        height, width = tile.shape[:2]
        y1 = y0 + height
        x1 = x0 + width
        tile_tensor = _torch_image(tile, torch_module, device)
        weight_tensor = torch_module.from_numpy(tile_weight.astype(np.float32)).to(device=device).unsqueeze(0)
        accum[:, y0:y1, x0:x1] += tile_tensor * weight_tensor
        weight_accum[:, y0:y1, x0:x1] += weight_tensor
    output = accum / weight_accum.clamp_min(1e-6)
    torch_module.cuda.synchronize()
    return _torch_to_numpy_image(output)


def blend_streaming_chunk(
    chunk_tiles: list[tuple[np.ndarray, np.ndarray, int, int]],
    chunk_height: int,
    chunk_width: int,
    config: StitchingConfig,
) -> tuple[np.ndarray, list[str]]:
    warnings: list[str] = []
    if not chunk_tiles:
        return np.zeros((chunk_height, chunk_width, 3), dtype=np.uint8), warnings

    if config.runtime is not None and config.runtime.device == "cuda":
        torch_module = load_torch()
        if torch_module is not None and torch_module.cuda.is_available():
            try:
                device = torch_module.device("cuda")
                torch_module.cuda.empty_cache()
                return _blend_streaming_chunk_gpu(chunk_tiles, chunk_height, chunk_width, torch_module, device), warnings
            except Exception as exc:
                if not config.gpu_fallback_allowed:
                    raise
                reason = f"Chunked GPU feather blending failed: {exc}"
                config.record_fallback("blend.chunk", reason, "cuda", "cpu")
                warnings.append(reason)

    return _blend_streaming_chunk_cpu(chunk_tiles, chunk_height, chunk_width), warnings


def _blend_tiles_gpu(images: list[np.ndarray], placements: list[TilePlacement], canvas: CanvasLayout, config: StitchingConfig) -> tuple[np.ndarray, list[str]]:
    torch_module = load_torch()
    if torch_module is None or not torch_module.cuda.is_available():
        raise RuntimeError("PyTorch CUDA is not available for GPU blending")

    warnings: list[str] = []
    device = torch_module.device("cuda")
    torch_module.cuda.empty_cache()
    method = config.blending_method
    if method == "multiband":
        estimated_mb = _estimate_multiband_memory_mb(canvas, int(max(1, config.multiband_levels)), len(images))
        free_mb = None
        if hasattr(torch_module.cuda, "mem_get_info"):
            try:
                free_mb = int(torch_module.cuda.mem_get_info(device=device)[0] / (1024 * 1024))
            except Exception:
                free_mb = None
        allowed_mb = config.gpu_memory_budget_mb if free_mb is None else min(config.gpu_memory_budget_mb, max(256, int(free_mb * 0.7)))
        if estimated_mb > allowed_mb:
            warnings.append(
                f"Estimated multiband GPU memory {estimated_mb}MB exceeds available budget {allowed_mb}MB; fell back to feather blending on GPU."
            )
            config.record_fallback(
                "blend.multiband",
                f"Estimated multiband GPU memory {estimated_mb}MB exceeded available budget {allowed_mb}MB; used GPU feather blending.",
                "cuda.multiband",
                "cuda.feather",
            )
            method = "feather"

    if method in {"average", "feather"}:
        return _blend_tiles_gpu_weighted(images, placements, canvas, method, torch_module, device), warnings

    levels = int(max(1, config.multiband_levels))
    try:
        summed_laplacian: list[object] | None = None
        summed_weights: list[object] | None = None
        for image, placement in zip(images, placements):
            padded = torch_module.zeros((3, canvas.height, canvas.width), dtype=torch_module.float32, device=device)
            weight_map = torch_module.zeros((1, canvas.height, canvas.width), dtype=torch_module.float32, device=device)
            tile = _torch_image(image, torch_module, device)
            tile_weight = _torch_weight_map(image.shape[0], image.shape[1], "feather", torch_module, device)
            y0 = placement.y
            y1 = placement.y + image.shape[0]
            x0 = placement.x
            x1 = placement.x + image.shape[1]
            padded[:, y0:y1, x0:x1] = tile
            weight_map[:, y0:y1, x0:x1] = tile_weight

            laplacian_pyramid = _torch_laplacian_pyramid(padded, levels, torch_module)
            gaussian_weights = _torch_gaussian_pyramid(weight_map, levels, torch_module)
            if summed_laplacian is None or summed_weights is None:
                summed_laplacian = [torch_module.zeros_like(level) for level in laplacian_pyramid]
                summed_weights = [torch_module.zeros_like(level) for level in gaussian_weights]

            for index, (lap_level, weight_level) in enumerate(zip(laplacian_pyramid, gaussian_weights)):
                summed_laplacian[index] += lap_level * weight_level
                summed_weights[index] += weight_level

            del padded, weight_map, tile, tile_weight, laplacian_pyramid, gaussian_weights
            torch_module.cuda.empty_cache()

        assert summed_laplacian is not None and summed_weights is not None
        normalized = [lap_level / weight_level.clamp_min(1e-6) for lap_level, weight_level in zip(summed_laplacian, summed_weights)]
        output = _torch_reconstruct_laplacian(normalized, torch_module)
        torch_module.cuda.synchronize()
        return _torch_to_numpy_image(output), warnings
    except RuntimeError as exc:
        if "out of memory" not in str(exc).lower():
            raise
        torch_module.cuda.empty_cache()
        warnings.append("GPU multiband blending ran out of memory; fell back to GPU feather blending.")
        config.record_fallback(
            "blend.multiband",
            "GPU multiband blending ran out of memory; used GPU feather blending.",
            "cuda.multiband",
            "cuda.feather",
        )
        return _blend_tiles_gpu_weighted(images, placements, canvas, "feather", torch_module, device), warnings


def blend_tiles(images: list[np.ndarray], placements: list[TilePlacement], canvas: CanvasLayout, config: StitchingConfig) -> tuple[np.ndarray, list[str]]:
    """Blend all tiles into a single mosaic."""

    if not images:
        raise ValueError("No images provided for blending")

    if config.runtime is not None and config.runtime.device == "cuda":
        try:
            return _blend_tiles_gpu(images, placements, canvas, config)
        except Exception as exc:
            if not config.gpu_fallback_allowed:
                raise
            config.record_fallback("blend", str(exc), "cuda", "cpu")

    return _blend_tiles_cpu(images, placements, canvas, config)

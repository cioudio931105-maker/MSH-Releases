from __future__ import annotations

import importlib.util
from dataclasses import dataclass, field
from typing import Any

import cv2
from msh_environment import probe_compute


@dataclass(slots=True)
class RuntimeFallback:
    stage: str
    reason: str
    requested_device: str
    actual_device: str

    def as_dict(self) -> dict[str, str]:
        return {
            "stage": self.stage,
            "reason": self.reason,
            "requested_device": self.requested_device,
            "actual_device": self.actual_device,
        }


@dataclass(slots=True)
class RuntimeInfo:
    requested_device: str = "auto"
    device: str = "cpu"
    prefer_gpu: bool = True
    gpu_fallback_allowed: bool = True
    gpu_memory_budget_mb: int = 1536
    torch_available: bool = False
    cuda_available: bool = False
    torch_cuda_version: str | None = None
    gpu_name: str | None = None
    gpu_total_memory_mb: int | None = None
    cv2_cuda_devices: int = 0
    cv2_cuda_built: bool = False
    cupy_available: bool = False
    yolo_device: str = "cpu"
    fallbacks: list[RuntimeFallback] = field(default_factory=list)

    def record_fallback(self, stage: str, reason: str, requested_device: str, actual_device: str) -> None:
        fallback = RuntimeFallback(
            stage=stage,
            reason=reason,
            requested_device=requested_device,
            actual_device=actual_device,
        )
        if fallback.as_dict() not in [item.as_dict() for item in self.fallbacks]:
            self.fallbacks.append(fallback)

    def as_dict(self) -> dict[str, Any]:
        return {
            "requested_device": self.requested_device,
            "device": self.device,
            "prefer_gpu": self.prefer_gpu,
            "gpu_fallback_allowed": self.gpu_fallback_allowed,
            "gpu_memory_budget_mb": self.gpu_memory_budget_mb,
            "torch_available": self.torch_available,
            "cuda_available": self.cuda_available,
            "torch_cuda_version": self.torch_cuda_version,
            "gpu_name": self.gpu_name,
            "gpu_total_memory_mb": self.gpu_total_memory_mb,
            "cv2_cuda_devices": self.cv2_cuda_devices,
            "cv2_cuda_built": self.cv2_cuda_built,
            "cupy_available": self.cupy_available,
            "yolo_device": self.yolo_device,
            "fallbacks": [item.as_dict() for item in self.fallbacks],
        }


def load_torch() -> Any | None:
    try:
        import torch
    except Exception:
        return None
    return torch


def configure_torch_performance(torch_module: Any) -> None:
    """Enable safe CUDA throughput settings for fixed-size vision workloads."""
    try:
        if not torch_module.cuda.is_available():
            return
        torch_module.backends.cudnn.benchmark = True
        torch_module.backends.cudnn.enabled = True
        if hasattr(torch_module, "set_float32_matmul_precision"):
            torch_module.set_float32_matmul_precision("high")
    except Exception:
        # Runtime probing must never fail only because an optional backend
        # performance switch is unavailable in a particular torch build.
        return


def _cv2_cuda_device_count() -> int:
    try:
        if hasattr(cv2, "cuda"):
            return int(cv2.cuda.getCudaEnabledDeviceCount())
    except Exception:
        return 0
    return 0


def _torch_memory_mb(torch_module: Any) -> int | None:
    try:
        props = torch_module.cuda.get_device_properties(0)
        return int(props.total_memory // (1024 * 1024))
    except Exception:
        return None


def probe_runtime(
    compute_device: str = "auto",
    prefer_gpu: bool = True,
    gpu_fallback_allowed: bool = True,
    gpu_memory_budget_mb: int = 1536,
    yolo_device: str | int = "auto",
) -> RuntimeInfo:
    runtime = RuntimeInfo(
        requested_device=str(compute_device),
        prefer_gpu=bool(prefer_gpu),
        gpu_fallback_allowed=bool(gpu_fallback_allowed),
        gpu_memory_budget_mb=int(max(256, gpu_memory_budget_mb)),
    )
    runtime.cv2_cuda_devices = _cv2_cuda_device_count()
    runtime.cv2_cuda_built = runtime.cv2_cuda_devices > 0
    runtime.cupy_available = bool(importlib.util.find_spec("cupy") or importlib.util.find_spec("cupy_cuda11x"))

    torch_module = load_torch()
    runtime.torch_available = torch_module is not None
    if torch_module is not None:
        try:
            runtime.cuda_available = probe_compute(torch_module).device.startswith("cuda")
        except Exception:
            runtime.cuda_available = False
        if runtime.cuda_available:
            configure_torch_performance(torch_module)
        runtime.torch_cuda_version = getattr(torch_module.version, "cuda", None)
        if runtime.cuda_available:
            try:
                runtime.gpu_name = str(torch_module.cuda.get_device_name(0))
            except Exception:
                runtime.gpu_name = None
            runtime.gpu_total_memory_mb = _torch_memory_mb(torch_module)

    wants_cuda = compute_device == "cuda" or (compute_device == "auto" and prefer_gpu)
    runtime.device = "cuda" if wants_cuda and runtime.cuda_available else "cpu"
    if wants_cuda and runtime.device != "cuda":
        runtime.record_fallback(
            stage="runtime",
            reason="CUDA was requested but is not available in the active Python environment.",
            requested_device="cuda",
            actual_device="cpu",
        )

    if yolo_device == "auto":
        runtime.yolo_device = "0" if runtime.device == "cuda" else "cpu"
    else:
        runtime.yolo_device = str(yolo_device)

    return runtime

"""Read-only software capability checks; never open cameras or serial ports."""
from __future__ import annotations

from dataclasses import dataclass
import importlib
import os
import platform
import struct
import subprocess
from functools import lru_cache
from typing import Any

NVIDIA_DRIVER_URL = "https://www.nvidia.com/Download/index.aspx"
BASLER_DOWNLOAD_URL = "https://www.baslerweb.com/en/downloads/software/"


@dataclass(frozen=True)
class ComputeCapability:
    device: str
    reason: str
    gpu_name: str = ""
    torch_version: str = ""


def probe_compute(torch_module: Any = None) -> ComputeCapability:
    """A real CUDA kernel must complete before GPU is marked usable."""
    try:
        torch = torch_module if torch_module is not None else importlib.import_module("torch")
        version = str(torch.__version__)
    except Exception as exc:
        return ComputeCapability("unavailable", f"運算套件無法載入：{exc}")
    if not getattr(torch.version, "cuda", None):
        return ComputeCapability("cpu", "目前安裝的是 CPU 運算版本；啟用 GPU 需安裝 GPU 版本。", torch_version=version)
    try:
        if not torch.cuda.is_available():
            return ComputeCapability("cpu", "NVIDIA CUDA 無法使用，請檢查顯卡與官方驅動。", torch_version=version)
        name = str(torch.cuda.get_device_name(0))
        sample = torch.ones((2, 2), device="cuda:0")
        if float((sample @ sample).sum().item()) != 8.0:
            raise RuntimeError("GPU 計算結果不符")
        torch.cuda.synchronize()
        return ComputeCapability("cuda:0", "NVIDIA GPU 運算測試通過。", name, version)
    except Exception as exc:
        return ComputeCapability("cpu", f"GPU 運算測試失敗，改用 CPU：{exc}", torch_version=version)


@lru_cache(maxsize=1)
def compute_capability() -> ComputeCapability:
    return probe_compute()


def inference_device() -> str:
    capability = compute_capability()
    if capability.device == "unavailable":
        raise RuntimeError(capability.reason)
    return "0" if capability.device.startswith("cuda") else "cpu"


def nvidia_adapter_present() -> bool:
    """Driver inventory only; CUDA compatibility is checked by probe_compute."""
    if os.name != "nt":
        return False
    try:
        completed = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=8, check=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return completed.returncode == 0 and bool(completed.stdout.strip())
    except (OSError, subprocess.TimeoutExpired):
        return False


def installed_pylon_products() -> list[str]:
    """Registry evidence is not proof that a USB driver or camera works."""
    if os.name != "nt":
        return []
    import winreg
    products: set[str] = set()
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(hive, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", 0,
                                    winreg.KEY_READ | view) as root:
                    for index in range(winreg.QueryInfoKey(root)[0]):
                        try:
                            with winreg.OpenKey(root, winreg.EnumKey(root, index)) as item:
                                name = str(winreg.QueryValueEx(item, "DisplayName")[0])
                                if "pylon" in name.lower() and "basler" in name.lower():
                                    products.add(name)
                        except OSError:
                            continue
            except OSError:
                continue
    return sorted(products)


def environment_report(compute: ComputeCapability | None = None) -> str:
    capability = compute or compute_capability()
    products = installed_pylon_products()
    try:
        importlib.import_module("pypylon.pylon")
        binding = "可載入"
    except Exception:
        binding = "無法載入，請修復 MSH 安裝"
    return "\n".join([
        f"作業系統：{platform.system()} {platform.release()} / {platform.machine()} / {struct.calcsize('P') * 8} 位元",
        "支援目標：Windows 10/11，Intel/AMD 64 位元（實際驗收以發行說明為準）",
        f"運算模式：{'NVIDIA GPU' if capability.device.startswith('cuda') else capability.device.upper()}",
        capability.reason,
        f"GPU：{capability.gpu_name or '未通過 GPU 驗證'}",
        f"PyTorch：{capability.torch_version or '無法載入'}",
        f"Basler Python 介面：{binding}",
        f"Basler 安裝紀錄：{', '.join(products) if products else '未找到；不代表一定缺少 USB 驅動'}",
        "USB 驅動與實際取像仍需使用指定設備驗證；本檢查不開啟相機或 COM。",
        "CPU 備用模式的即時掃描速度尚需實機驗證。",
    ])

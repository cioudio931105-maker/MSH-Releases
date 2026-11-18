from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Callable

import torch

from . import vision as _vision  # noqa: F401
from .vision.ssd.config import mobilenetv1_ssd_config, squeezenet_ssd_config, vgg_ssd_config
from .vision.ssd.mobilenet_v2_ssd_lite import create_mobilenetv2_ssd_lite, create_mobilenetv2_ssd_lite_predictor
from .vision.ssd.mobilenetv1_ssd import create_mobilenetv1_ssd, create_mobilenetv1_ssd_predictor
from .vision.ssd.mobilenetv1_ssd_lite import create_mobilenetv1_ssd_lite, create_mobilenetv1_ssd_lite_predictor
from .vision.ssd.squeezenet_ssd_lite import create_squeezenet_ssd_lite, create_squeezenet_ssd_lite_predictor
from .vision.ssd.vgg_ssd import create_vgg_ssd, create_vgg_ssd_predictor


SUPPORTED_NET_TYPES = (
    "vgg16-ssd",
    "mb1-ssd",
    "mb1-ssd-lite",
    "mb2-ssd-lite",
    "sq-ssd-lite",
)
_LOSS_PATTERN = re.compile(r"-Loss-([0-9.eE+-]+)\.pth$")


def str2bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def resolve_device(use_cuda: bool = True) -> torch.device:
    return torch.device("cuda:0" if use_cuda and torch.cuda.is_available() else "cpu")


def ensure_background_label(class_names: list[str]) -> list[str]:
    cleaned = [name.strip() for name in class_names if name.strip()]
    if not cleaned:
        raise ValueError("At least one class label is required.")
    if cleaned[0].upper() != "BACKGROUND":
        cleaned.insert(0, "BACKGROUND")
    return cleaned


def load_label_file(label_file: str | Path) -> list[str]:
    path = Path(label_file)
    return ensure_background_label(path.read_text(encoding="utf-8").splitlines())


def store_label_file(label_file: str | Path, class_names: list[str]) -> Path:
    path = Path(label_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(ensure_background_label(class_names)) + "\n", encoding="utf-8")
    return path


def create_network_factory(
    net_type: str,
    mb2_width_mult: float = 1.0,
) -> tuple[Callable[[int], torch.nn.Module], object]:
    net_type = net_type.strip().lower()
    if net_type == "vgg16-ssd":
        return create_vgg_ssd, vgg_ssd_config
    if net_type == "mb1-ssd":
        return create_mobilenetv1_ssd, mobilenetv1_ssd_config
    if net_type == "mb1-ssd-lite":
        return create_mobilenetv1_ssd_lite, mobilenetv1_ssd_config
    if net_type == "sq-ssd-lite":
        return create_squeezenet_ssd_lite, squeezenet_ssd_config
    if net_type == "mb2-ssd-lite":
        return lambda num_classes: create_mobilenetv2_ssd_lite(num_classes, width_mult=mb2_width_mult), mobilenetv1_ssd_config
    raise ValueError(f"Unsupported SSD net type: {net_type}")


def create_predictor_factory(net_type: str) -> Callable[..., object]:
    net_type = net_type.strip().lower()
    if net_type == "vgg16-ssd":
        return create_vgg_ssd_predictor
    if net_type == "mb1-ssd":
        return create_mobilenetv1_ssd_predictor
    if net_type == "mb1-ssd-lite":
        return create_mobilenetv1_ssd_lite_predictor
    if net_type == "sq-ssd-lite":
        return create_squeezenet_ssd_lite_predictor
    if net_type == "mb2-ssd-lite":
        return create_mobilenetv2_ssd_lite_predictor
    raise ValueError(f"Unsupported SSD net type: {net_type}")


def create_ssd(
    net_type: str,
    num_classes: int,
    is_test: bool,
    mb2_width_mult: float = 1.0,
) -> tuple[torch.nn.Module, object]:
    create_net, config = create_network_factory(net_type=net_type, mb2_width_mult=mb2_width_mult)
    return create_net(num_classes, is_test=is_test), config


def create_ssd_predictor(
    net_type: str,
    net: torch.nn.Module,
    device: torch.device | None = None,
    nms_method: str | None = None,
    iou_threshold: float = 0.45,
    candidate_size: int = 200,
    sigma: float = 0.5,
):
    factory = create_predictor_factory(net_type)
    predictor = factory(
        net,
        nms_method=nms_method,
        candidate_size=candidate_size,
        sigma=sigma,
        device=device,
    )
    predictor.iou_threshold = iou_threshold
    return predictor

def find_best_checkpoint(model_dir: str | Path) -> Path | None:
    root = Path(model_dir)
    best_path: Path | None = None
    best_loss: float | None = None
    for path in root.glob("*.pth"):
        match = _LOSS_PATTERN.search(path.name)
        if match is None:
            continue
        try:
            loss = float(match.group(1))
        except ValueError:
            continue
        if best_loss is None or loss < best_loss:
            best_loss = loss
            best_path = path
    return best_path


def configure_torch_runtime(use_cuda: bool) -> torch.device:
    device = resolve_device(use_cuda=use_cuda)
    if device.type == "cuda":
        torch.backends.cudnn.benchmark = True
        logging.info("Using CUDA for SSD execution.")
    else:
        logging.info("Using CPU for SSD execution.")
    return device

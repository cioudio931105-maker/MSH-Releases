from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


def _import_pypylon() -> tuple[Any, Any]:
    try:
        from pypylon import genicam, pylon
    except ImportError as exc:  # pragma: no cover - hardware dependency
        raise ImportError(
            "Basler support requires `pypylon`. Install it in the active environment with `pip install pypylon`."
        ) from exc
    return pylon, genicam


@dataclass(slots=True)
class BaslerCameraConfig:
    camera_serial: str | None = None
    camera_index: int = 0
    width: int | None = None
    height: int | None = None
    exposure_us: float | None = None
    gain: float | None = None
    fps: float | None = None
    pixel_format: str | None = None
    timeout_ms: int = 5000


def _device_serial(device_info: Any) -> str:
    if hasattr(device_info, "GetSerialNumber"):
        return str(device_info.GetSerialNumber())
    return str(getattr(device_info, "serial_number", ""))


def _device_model(device_info: Any) -> str:
    if hasattr(device_info, "GetModelName"):
        return str(device_info.GetModelName())
    return str(getattr(device_info, "model_name", ""))


def _select_device_info(devices: list[Any], camera_serial: str | None, camera_index: int) -> Any:
    if not devices:
        raise RuntimeError("No Basler cameras were found.")
    if camera_serial:
        for device_info in devices:
            if _device_serial(device_info) == camera_serial:
                return device_info
        raise RuntimeError(f"Basler camera with serial `{camera_serial}` was not found.")
    if camera_index < 0 or camera_index >= len(devices):
        raise RuntimeError(f"Basler camera index {camera_index} is out of range. Found {len(devices)} device(s).")
    return devices[camera_index]


def list_basler_devices() -> list[dict[str, str]]:
    pylon, _ = _import_pypylon()
    factory = pylon.TlFactory.GetInstance()
    devices = list(factory.EnumerateDevices())
    return [
        {
            "serial_number": _device_serial(device),
            "model_name": _device_model(device),
        }
        for device in devices
    ]


def _set_if_writable(camera: Any, attribute_name: str, value: Any) -> None:
    if value is None or not hasattr(camera, attribute_name):
        return
    node = getattr(camera, attribute_name)
    try:
        if hasattr(node, "SetValue"):
            node.SetValue(value)
        elif hasattr(node, "Value"):
            node.Value = value
    except Exception:
        return


def _configure_camera(camera: Any, config: BaslerCameraConfig) -> None:
    _set_if_writable(camera, "Width", config.width)
    _set_if_writable(camera, "Height", config.height)
    _set_if_writable(camera, "ExposureTime", config.exposure_us)
    _set_if_writable(camera, "Gain", config.gain)
    if config.fps is not None:
        _set_if_writable(camera, "AcquisitionFrameRateEnable", True)
        _set_if_writable(camera, "AcquisitionFrameRate", config.fps)
    _set_if_writable(camera, "PixelFormat", config.pixel_format)


class BaslerCamera:
    def __init__(self, config: BaslerCameraConfig | None = None) -> None:
        self.config = config or BaslerCameraConfig()
        self.camera = None
        self.converter = None
        self._pylon = None
        self._genicam = None

    def open(self) -> "BaslerCamera":
        pylon, genicam = _import_pypylon()
        factory = pylon.TlFactory.GetInstance()
        devices = list(factory.EnumerateDevices())
        device_info = _select_device_info(
            devices=devices,
            camera_serial=self.config.camera_serial,
            camera_index=self.config.camera_index,
        )
        self.camera = pylon.InstantCamera(factory.CreateDevice(device_info))
        self.camera.Open()
        _configure_camera(self.camera, self.config)

        self.converter = pylon.ImageFormatConverter()
        self.converter.OutputPixelFormat = pylon.PixelType_BGR8packed
        self.converter.OutputBitAlignment = pylon.OutputBitAlignment_MsbAligned
        self.camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)

        self._pylon = pylon
        self._genicam = genicam
        return self

    def close(self) -> None:
        if self.camera is None:
            return
        try:
            if self.camera.IsGrabbing():
                self.camera.StopGrabbing()
        finally:
            if self.camera.IsOpen():
                self.camera.Close()
        self.camera = None

    def read(self) -> np.ndarray:
        if self.camera is None or self.converter is None or self._pylon is None:
            raise RuntimeError("Basler camera is not open.")
        result = self.camera.RetrieveResult(self.config.timeout_ms, self._pylon.TimeoutHandling_ThrowException)
        try:
            if not result.GrabSucceeded():
                raise RuntimeError(f"Basler frame grab failed: {result.ErrorCode} {result.ErrorDescription}")
            converted = self.converter.Convert(result)
            frame = converted.GetArray()
            return np.ascontiguousarray(frame)
        finally:
            result.Release()

    def __enter__(self) -> "BaslerCamera":
        return self.open()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


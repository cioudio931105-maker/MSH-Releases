"""Runtime paths and diagnostics shared by source and PyInstaller builds."""

from __future__ import annotations

import ctypes
import logging
import os
import sys
from ctypes import wintypes
from logging.handlers import RotatingFileHandler
from pathlib import Path
from types import TracebackType

APP_NAME = "MSH"
DEFAULT_INSTANCE_MUTEX = r"Local\MSH_Hardware_GUI_Launcher"
ERROR_ALREADY_EXISTS = 183


class SingleInstanceLock:
    """Keep one Windows process alive for a named desktop application instance."""

    def __init__(self, name: str = DEFAULT_INSTANCE_MUTEX) -> None:
        self.name = name
        self._handle: object | None = None
        self._kernel32: object | None = None

    def acquire(self) -> bool:
        if self._handle is not None:
            return True
        if os.name != "nt":
            self._handle = self
            return True

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL

        ctypes.set_last_error(0)
        handle = kernel32.CreateMutexW(None, False, self.name)
        error = ctypes.get_last_error()
        if not handle:
            raise ctypes.WinError(error)
        if error == ERROR_ALREADY_EXISTS:
            kernel32.CloseHandle(handle)
            return False

        self._kernel32 = kernel32
        self._handle = handle
        return True

    def close(self) -> None:
        if self._handle is None:
            return
        if self._kernel32 is not None:
            self._kernel32.CloseHandle(self._handle)
        self._handle = None
        self._kernel32 = None


def application_root() -> Path:
    """Return the read-only application-resource root in source or frozen mode."""
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root)
    return Path(__file__).resolve().parents[2]


def local_app_data_dir() -> Path:
    """Return the per-user writable directory for logs and application state."""
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    path = base / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_output_dir(kind: str) -> Path:
    """Return a writable default for research output, outside Program Files."""
    documents = Path(os.environ.get("USERPROFILE", Path.home())) / "Documents"
    path = documents / APP_NAME / kind
    path.mkdir(parents=True, exist_ok=True)
    return path


def _add_rotating_handler(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    normalized_path = os.path.normcase(os.path.abspath(log_path))
    root_logger = logging.getLogger()
    if any(
        isinstance(handler, RotatingFileHandler)
        and os.path.normcase(os.path.abspath(handler.baseFilename)) == normalized_path
        for handler in root_logger.handlers
    ):
        return
    handler = RotatingFileHandler(log_path, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)


def configure_logging(*, startup_log_path: Path | None = None, console: bool = False) -> Path:
    """Configure bounded runtime and optional source-launcher logging."""
    log_path = local_app_data_dir() / "msh.log"
    _add_rotating_handler(log_path)
    if startup_log_path is not None:
        _add_rotating_handler(startup_log_path)
    root_logger = logging.getLogger()
    if console and not any(getattr(handler, "_msh_diagnostics", False) for handler in root_logger.handlers):
        handler = logging.StreamHandler()
        handler._msh_diagnostics = True  # type: ignore[attr-defined]
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        root_logger.addHandler(handler)
    return log_path


def configure_runtime_environment() -> None:
    """Keep third-party writable state out of the installed application folder."""
    ultralytics_dir = local_app_data_dir() / "ultralytics"
    ultralytics_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("YOLO_CONFIG_DIR", str(ultralytics_dir))


def log_unhandled_exception(
    exc_type: type[BaseException], exc_value: BaseException, exc_traceback: TracebackType | None
) -> None:
    logging.getLogger("msh.crash").critical("Unhandled application exception", exc_info=(exc_type, exc_value, exc_traceback))

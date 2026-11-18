"""Runtime paths and diagnostics shared by source and PyInstaller builds."""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from types import TracebackType

APP_NAME = "MSH"


def application_root() -> Path:
    """Return the read-only application-resource root in source or frozen mode."""
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root)
    return Path(__file__).resolve().parent


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


def configure_logging() -> Path:
    """Configure bounded local logging and return the active log path."""
    log_path = local_app_data_dir() / "msh.log"
    root_logger = logging.getLogger()
    if not any(isinstance(handler, RotatingFileHandler) and handler.baseFilename == str(log_path) for handler in root_logger.handlers):
        handler = RotatingFileHandler(log_path, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        root_logger.addHandler(handler)
        root_logger.setLevel(logging.INFO)
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

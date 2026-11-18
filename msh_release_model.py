"""Approved external model identity for the current MSH review release."""

from pathlib import Path


RELEASE_MODEL_FILENAME = "wbc_focus_yolov8n_e_20260611.pt"
RELEASE_MODEL_RELATIVE_PATH = (
    Path("stitched_output")
    / "stitched_output"
    / "stitched_output"
    / "models"
    / RELEASE_MODEL_FILENAME
)
RELEASE_MODEL_SHA256 = "fe5a6587e1fce3a39c7dcb9131c8a1f2a28a40afd2e07b22fac57dd3be1fa885"
RELEASE_MODEL_TASK = "detect"
RELEASE_MODEL_CLASSES = ("WBC",)

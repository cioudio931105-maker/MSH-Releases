"""Standalone offline entrypoints must never ask Ultralytics to fetch weights."""

from pathlib import Path


def require_local_model(model_path: str | Path | None) -> str:
    if model_path is None or not str(model_path).strip() or not Path(model_path).expanduser().is_file():
        raise FileNotFoundError("Select an existing local model file; MSH does not supply or download models.")
    return str(Path(model_path).expanduser().resolve())


def local_training_options(model_path: str | Path) -> dict[str, object]:
    path = require_local_model(model_path)
    return {"pretrained": path if Path(path).suffix.lower() == ".pt" else False, "amp": False}

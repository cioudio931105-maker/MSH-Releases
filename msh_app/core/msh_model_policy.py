"""Local-only model loading. MSH distributes functionality, never weights."""

from pathlib import Path


MODEL_DISTRIBUTION = "user-supplied"


def require_local_model(model_path: str | Path | None) -> str:
    """Reject missing paths and download aliases before invoking a model backend."""
    if model_path is None or not str(model_path).strip():
        raise FileNotFoundError("MSH includes no models. Select your own local model file first.")
    path = Path(model_path).expanduser()
    if not path.is_file():
        raise FileNotFoundError(
            f"Local model file not found: {model_path}. "
            "MSH does not supply or download models; select an existing local file."
        )
    return str(path.resolve())


def local_training_options(model_path: str | Path) -> dict[str, object]:
    """Use supplied checkpoint weights; avoid the backend's remote AMP probe model."""
    path = require_local_model(model_path)
    return {"pretrained": path if Path(path).suffix.lower() == ".pt" else False, "amp": False}

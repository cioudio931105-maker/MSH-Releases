from __future__ import annotations

from msh_model_policy import require_local_model, local_training_options

import argparse
import shutil
from datetime import datetime
from pathlib import Path


EXPECTED_NAMES = ("WBC", "RBC", "Platelets")


def workspace_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_data_yaml() -> Path:
    return (
        workspace_root()
        / "stitched_output"
        / "stitched_output"
        / "stitched_output"
        / "captured"
        / "manual_annotation_dataset"
        / "data.yaml"
    )


def default_model_path() -> Path:
    return (
        workspace_root()
        / "stitched_output"
        / "stitched_output"
        / "stitched_output"
        / "models"
        / "blood_cells_3cls_400x_refine_20260517.pt"
    )


def default_project_dir() -> Path:
    return workspace_root() / "staging" / "train"


def _auto_device() -> str:
    try:
        import torch

        return "0" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


def validate_manual_annotation_dataset(data_yaml: Path) -> None:
    if not data_yaml.is_file():
        raise FileNotFoundError(f"manual annotation data.yaml not found: {data_yaml}")
    dataset_root = data_yaml.parent
    images_dir = dataset_root / "images" / "train"
    labels_dir = dataset_root / "labels" / "train"
    if not images_dir.is_dir():
        raise FileNotFoundError(f"images/train not found: {images_dir}")
    if not labels_dir.is_dir():
        raise FileNotFoundError(f"labels/train not found: {labels_dir}")

    image_count = sum(1 for path in images_dir.iterdir() if path.is_file())
    label_count = sum(1 for path in labels_dir.glob("*.txt"))
    if image_count == 0:
        raise ValueError(f"No training images found: {images_dir}")
    if label_count == 0:
        raise ValueError(f"No YOLO labels found: {labels_dir}")

    text = data_yaml.read_text(encoding="utf-8", errors="ignore")
    missing_names = [name for name in EXPECTED_NAMES if name not in text]
    if missing_names:
        raise ValueError(f"data.yaml must contain {EXPECTED_NAMES}; missing: {missing_names}")

    bad_rows: list[str] = []
    for label_path in labels_dir.glob("*.txt"):
        for line_number, line in enumerate(label_path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
            stripped = line.strip()
            if not stripped:
                continue
            parts = stripped.split()
            if len(parts) != 5:
                bad_rows.append(f"{label_path}:{line_number}: {stripped}")
                continue
            try:
                class_id = int(parts[0])
                values = [float(value) for value in parts[1:]]
            except ValueError:
                bad_rows.append(f"{label_path}:{line_number}: {stripped}")
                continue
            if class_id < 0 or class_id >= len(EXPECTED_NAMES):
                bad_rows.append(f"{label_path}:{line_number}: class_id={class_id}")
            if any(value < 0.0 or value > 1.0 for value in values):
                bad_rows.append(f"{label_path}:{line_number}: normalized value out of range")
    if bad_rows:
        preview = "\n".join(bad_rows[:10])
        raise ValueError(f"Invalid YOLO labels found:\n{preview}")


def print_training_artifacts(save_dir: Path) -> None:
    artifacts = {
        "results_png": save_dir / "results.png",
        "confusion_matrix": save_dir / "confusion_matrix.png",
        "labels_plot": save_dir / "labels.jpg",
        "best_model": save_dir / "weights" / "best.pt",
        "last_model": save_dir / "weights" / "last.pt",
    }
    for name, path in artifacts.items():
        if path.exists():
            print(f"{name}={path.resolve()}")


def promote_model(best_model: Path, target_model: Path) -> Path:
    if not best_model.is_file():
        raise FileNotFoundError(f"best model not found: {best_model}")
    if not target_model.is_file():
        raise FileNotFoundError(f"target model not found: {target_model}")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = target_model.with_name(f"{target_model.stem}.backup_{stamp}{target_model.suffix}")
    shutil.copy2(target_model, backup)
    shutil.copy2(best_model, target_model)
    print(f"backup_model={backup.resolve()}")
    print(f"promoted_model={target_model.resolve()}")
    return backup


def _parser() -> argparse.ArgumentParser:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    parser = argparse.ArgumentParser(
        description="Fine-tune WBC/RBC/Platelets detector from manual live-camera annotations.",
    )
    parser.add_argument("--data", type=Path, default=default_data_yaml())
    parser.add_argument("--model", type=Path, default=default_model_path())
    parser.add_argument("--project", type=Path, default=default_project_dir())
    parser.add_argument("--name", default=f"blood_cells_3cls_manual_annotation_refine_{stamp}")
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--imgsz", type=int, default=960)
    parser.add_argument("--batch", type=int, default=1)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--lr0", type=float, default=0.00015)
    parser.add_argument("--patience", type=int, default=8)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--promote-to-default",
        action="store_true",
        help="After training, backup --model and replace it with weights/best.pt.",
    )
    return parser


def train_manual_annotation_3cls(args: argparse.Namespace) -> Path | None:
    data_yaml = Path(args.data)
    model_path = Path(args.model)
    validate_manual_annotation_dataset(data_yaml)
    if not model_path.is_file():
        raise FileNotFoundError(f"base model not found: {model_path}")

    device = _auto_device() if str(args.device).lower() == "auto" else str(args.device)
    train_kwargs = {
        "data": str(data_yaml),
        "epochs": int(args.epochs),
        "imgsz": int(args.imgsz),
        "batch": int(args.batch),
        "workers": int(args.workers),
        "project": str(Path(args.project)),
        "name": str(args.name),
        "exist_ok": True,
        "patience": int(args.patience),
        "optimizer": "AdamW",
        "lr0": float(args.lr0),
        "cos_lr": True,
        "seed": 42,

        "device": device,
        "cache": False,
        "mosaic": 0.05,
        "mixup": 0.0,
        "copy_paste": 0.0,
        "degrees": 15.0,
        "scale": 0.08,
        "translate": 0.03,
        "fliplr": 0.5,
        "flipud": 0.5,
        "close_mosaic": 5,
    }
    print(f"data_yaml={data_yaml.resolve()}")
    print(f"model={model_path.resolve()}")
    print(f"train_kwargs={train_kwargs}")
    if args.dry_run:
        return None

    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise ImportError("Ultralytics is required for YOLO training.") from exc

    model = YOLO(require_local_model(str(model_path)))
    result = model.train(**(train_kwargs | local_training_options(model_path)))
    save_dir = Path(getattr(result, "save_dir", Path(args.project) / str(args.name)))
    best_path = save_dir / "weights" / "best.pt"
    print_training_artifacts(save_dir)
    print(f"best_model={best_path.resolve()}")
    if args.promote_to_default:
        promote_model(best_path, model_path)
    return best_path


def main() -> int:
    args = _parser().parse_args()
    train_manual_annotation_3cls(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

from msh_model_policy import require_local_model, local_training_options

import argparse
import ast
from pathlib import Path
from typing import Any

from .cell_classes import WBC_5_CLASS_NAMES

WBC_SINGLE_CLASS_NAMES: tuple[str, ...] = ("WBC",)


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_data_yaml() -> Path:
    return _workspace_root() / "datasets" / "wbc_400x" / "data.yaml"


ULTRALYTICS_MODEL_NAMES = {
    "yolov8n.pt",
    "yolov8s.pt",
    "yolov8m.pt",
    "yolo11n.pt",
    "yolo11s.pt",
    "yolo11m.pt",
}


def default_base_model() -> str:
    return "yolov8s.pt"


def default_project_dir() -> Path:
    d_root = Path("D:/")
    if d_root.exists():
        return Path("D:/Cell_Project_training_staging") / "train" / "wbc_400x"
    return _workspace_root() / "output" / "training" / "wbc_400x"


def _normalize_names(names: Any) -> list[str]:
    if isinstance(names, dict):
        return [str(names[key]) for key in sorted(names, key=lambda value: int(value) if str(value).isdigit() else str(value))]
    if isinstance(names, (list, tuple)):
        return [str(name) for name in names]
    return []


def _parse_names_value(value: str) -> list[str]:
    try:
        return _normalize_names(ast.literal_eval(value))
    except (SyntaxError, ValueError):
        pass

    if value.startswith("{") and value.endswith("}"):
        rows = [row.strip() for row in value[1:-1].split(",") if row.strip()]
        parsed: dict[str, str] = {}
        for row in rows:
            key, separator, name = row.partition(":")
            if separator:
                parsed[key.strip().strip("'\"")] = name.strip().strip("'\"")
        return _normalize_names(parsed)

    if value.startswith("[") and value.endswith("]"):
        return [name.strip().strip("'\"") for name in value[1:-1].split(",") if name.strip()]

    return []


def read_yolo_names(data_yaml: str | Path) -> list[str]:
    path = Path(data_yaml)
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("names:"):
            continue
        value = stripped.split(":", 1)[1].strip()
        if value:
            return _parse_names_value(value)

        names: list[str] = []
        mapped_names: dict[str, str] = {}
        for child in lines[index + 1:]:
            child_stripped = child.strip()
            if not child_stripped:
                continue
            if child_stripped.startswith("-"):
                names.append(child_stripped[1:].strip().strip("'\""))
                continue
            if ":" in child_stripped:
                if not child.startswith((" ", "\t")):
                    break
                key, _separator, name = child_stripped.partition(":")
                if key.strip().isdigit() and name.strip():
                    mapped_names[key.strip()] = name.strip().strip("'\"")
                    continue
                break
            if not child.startswith((" ", "\t")):
                break
        if mapped_names:
            return _normalize_names(mapped_names)
        return names
    return []


def validate_wbc5_data_yaml(data_yaml: str | Path) -> list[str]:
    names = read_yolo_names(data_yaml)
    expected = list(WBC_5_CLASS_NAMES)
    if names != expected:
        raise ValueError(
            f"{data_yaml} must define YOLO names as {expected}. "
            f"Found {names or 'no names'}."
        )
    return names


def validate_wbc_data_yaml(data_yaml: str | Path, *, wbc_only: bool = False, single_cls: bool = False) -> list[str]:
    names = read_yolo_names(data_yaml)
    expected_wbc5 = list(WBC_5_CLASS_NAMES)
    expected_wbc_only = list(WBC_SINGLE_CLASS_NAMES)
    accepted_wbc_only = [expected_wbc_only, ["white_blood_cell"]]

    if wbc_only:
        if names in accepted_wbc_only:
            return names
        raise ValueError(
            f"{data_yaml} must define one WBC class when --wbc-only is used. "
            f"Expected {expected_wbc_only}. Found {names or 'no names'}."
        )

    if single_cls and (names == expected_wbc5 or names in accepted_wbc_only):
        return names

    return validate_wbc5_data_yaml(data_yaml)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fine-tune YOLO for 400x five-class white-blood-cell recognition.",
    )
    parser.add_argument("--data", default=str(default_data_yaml()), help="YOLO data.yaml with five WBC classes.")
    parser.add_argument("--model", default=str(default_base_model()), help="Base YOLO .pt/.yaml model.")
    parser.add_argument("--project", default=str(default_project_dir()), help="Training output project directory.")
    parser.add_argument("--name", default="wbc_5cls_400x_yolov8s_highconf", help="Ultralytics run name.")
    parser.add_argument("--epochs", type=int, default=260)
    parser.add_argument("--imgsz", type=int, default=1280, help="Higher size preserves 400x cell morphology.")
    parser.add_argument("--batch", type=int, default=4)
    parser.add_argument("--patience", type=int, default=60)
    parser.add_argument("--device", default=None, help="Example: 0, cuda, or cpu.")
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--optimizer", default="AdamW")
    parser.add_argument("--lr0", type=float, default=0.0008)
    parser.add_argument("--no-cos-lr", action="store_true", help="Disable cosine learning-rate scheduling.")
    parser.add_argument("--close-mosaic", type=int, default=40)
    parser.add_argument("--mosaic", type=float, default=0.35)
    parser.add_argument("--mixup", type=float, default=0.03)
    parser.add_argument("--degrees", type=float, default=180.0)
    parser.add_argument("--scale", type=float, default=0.25)
    parser.add_argument("--translate", type=float, default=0.05)
    parser.add_argument("--cls-loss-gain", type=float, default=0.8, help="Higher value emphasizes subtype confidence.")
    parser.add_argument("--box-loss-gain", type=float, default=7.5)
    parser.add_argument("--dfl-loss-gain", type=float, default=1.5)
    parser.add_argument("--cache", action="store_true", help="Cache images during training if memory allows.")
    parser.add_argument("--single-cls", action="store_true", help="Train as one WBC class instead of five subtypes.")
    parser.add_argument("--wbc-only", action="store_true", help="Accept a one-class data.yaml with names: ['WBC'].")
    parser.add_argument("--dry-run", action="store_true", help="Validate inputs and print the training command payload.")
    return parser


def train_wbc400(args: argparse.Namespace) -> Path | None:
    data_yaml = Path(args.data)
    if not data_yaml.exists():
        raise FileNotFoundError(f"Data yaml not found: {data_yaml}")
    class_names = validate_wbc_data_yaml(data_yaml, wbc_only=bool(args.wbc_only), single_cls=bool(args.single_cls))

    model_arg = str(args.model)
    model_path = Path(model_arg)
    if not model_path.exists() and model_path.suffix and model_path.name not in ULTRALYTICS_MODEL_NAMES:
        raise FileNotFoundError(f"Base model not found: {model_path}")

    train_kwargs = {
        "data": str(data_yaml),
        "epochs": int(args.epochs),
        "imgsz": int(args.imgsz),
        "batch": int(args.batch),
        "workers": int(args.workers),
        "project": str(Path(args.project)),
        "name": str(args.name),
        "patience": int(args.patience),
        "optimizer": str(args.optimizer),
        "lr0": float(args.lr0),
        "cos_lr": not bool(args.no_cos_lr),
        "close_mosaic": int(args.close_mosaic),
        "seed": int(args.seed),
        "single_cls": bool(args.single_cls or args.wbc_only),

        "cache": bool(args.cache),
        "mosaic": float(args.mosaic),
        "mixup": float(args.mixup),
        "copy_paste": 0.0,
        "degrees": float(args.degrees),
        "scale": float(args.scale),
        "translate": float(args.translate),
        "fliplr": 0.5,
        "flipud": 0.5,
        "cls": float(args.cls_loss_gain),
        "box": float(args.box_loss_gain),
        "dfl": float(args.dfl_loss_gain),
    }
    if args.device is not None:
        train_kwargs["device"] = args.device

    if args.dry_run:
        print(f"classes={class_names}")
        print(f"model={model_arg}")
        print(f"train_kwargs={train_kwargs}")
        return None

    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise ImportError(
            "Ultralytics is required for YOLO training. Install the GPU requirements first."
        ) from exc

    model = YOLO(require_local_model(model_arg))
    result = model.train(**(train_kwargs | local_training_options(model_arg)))
    save_dir = Path(getattr(result, "save_dir", Path(args.project) / str(args.name)))
    best_path = save_dir / "weights" / "best.pt"
    print(f"classes={class_names}")
    print(f"best_model={best_path.resolve()}")
    return best_path


def main() -> int:
    args = _parser().parse_args()
    train_wbc400(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

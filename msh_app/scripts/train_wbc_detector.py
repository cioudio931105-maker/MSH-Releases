from __future__ import annotations

# Direct source entrypoints also resolve shared modules from the workspace.
import sys as _msh_sys
from pathlib import Path as _MshPath
if not getattr(_msh_sys, "frozen", False):
    _msh_sys.path.insert(0, str(_MshPath(__file__).resolve().parents[2]))


from msh_app.core.msh_model_policy import require_local_model, local_training_options

import argparse
from pathlib import Path

from ultralytics import YOLO


def main() -> int:
    from msh_app.research_paths import original_research_root
    project_root = original_research_root()
    parser = argparse.ArgumentParser(description="Fine-tune a WBC-only YOLO detector.")
    parser.add_argument("--model", type=Path, default=project_root / "models" / "blood_cells_3cls_yolov8n_20260429.pt")
    parser.add_argument("--data", type=Path, default=project_root / "data" / "wbc_detection_focus" / "data.yaml")
    parser.add_argument("--project", type=Path, default=project_root / "outputs" / "runs" / "detect")
    parser.add_argument("--name", default="wbc_focus_20260611")
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=4)
    parser.add_argument("--patience", type=int, default=10)
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--plots", action="store_true")
    parser.add_argument("--exist-ok", action="store_true")
    args = parser.parse_args()

    model = YOLO(require_local_model(str(args.model)))
    model.train(
        **local_training_options(args.model),
        data=str(args.data),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        patience=args.patience,
        project=str(args.project),
        name=args.name,
        device=args.device,
        workers=args.workers,
        cache=False,
        plots=args.plots,
        save=True,
        exist_ok=args.exist_ok,
        single_cls=False,
        amp=False,
        hsv_h=0.015,
        hsv_s=0.55,
        hsv_v=0.35,
        degrees=12.0,
        translate=0.08,
        scale=0.35,
        shear=3.0,
        fliplr=0.5,
        flipud=0.5,
        close_mosaic=10,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
from pathlib import Path

import torch
import torch.onnx

from .ssd.common import create_ssd, find_best_checkpoint, load_label_file, resolve_device, str2bool


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export an SSD checkpoint to ONNX.")
    parser.add_argument("--net", default="mb1-ssd")
    parser.add_argument("--input", default="", help="Input .pth path. When omitted with --model-dir, the best checkpoint is used.")
    parser.add_argument("--output", default="", help="Output ONNX path.")
    parser.add_argument("--labels", default="labels.txt", help="Label file path.")
    parser.add_argument("--width", type=int, default=300)
    parser.add_argument("--height", type=int, default=300)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--model-dir", default="", help="Optional directory for checkpoint/labels discovery.")
    parser.add_argument("--use-cuda", default=True, type=str2bool)
    parser.add_argument("--mb2-width-mult", default=1.0, type=float)
    return parser


def main() -> int:
    args = _parser().parse_args()
    model_dir = Path(args.model_dir) if args.model_dir else None
    input_path = Path(args.input) if args.input else None
    labels_path = Path(args.labels)

    if model_dir is not None:
        if input_path is None:
            input_path = find_best_checkpoint(model_dir)
            if input_path is None:
                raise FileNotFoundError(f"No checkpoint matching `*-Loss-*.pth` was found in {model_dir}")
        elif not input_path.is_file():
            input_path = model_dir / input_path
        if not labels_path.is_file():
            labels_path = model_dir / labels_path

    if input_path is None or not input_path.is_file():
        raise FileNotFoundError("An input SSD checkpoint is required.")
    if not labels_path.is_file():
        raise FileNotFoundError(f"Label file not found: {labels_path}")

    class_names = load_label_file(labels_path)
    device = resolve_device(use_cuda=args.use_cuda)
    net, _ = create_ssd(args.net, len(class_names), is_test=True, mb2_width_mult=args.mb2_width_mult)
    net.load(str(input_path))
    net.to(device)
    net.eval()

    output_path = Path(args.output) if args.output else Path(f"{args.net}.onnx")
    if model_dir is not None and not output_path.is_absolute():
        output_path = model_dir / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)

    dummy_input = torch.randn(args.batch_size, 3, args.height, args.width, device=device)
    torch.onnx.export(
        net,
        dummy_input,
        str(output_path),
        verbose=False,
        input_names=["input_0"],
        output_names=["scores", "boxes"],
    )

    print(f"input={input_path.resolve()}")
    print(f"output={output_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

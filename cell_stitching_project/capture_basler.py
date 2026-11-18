from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

import cv2

from .camera import BaslerCamera, BaslerCameraConfig
from .io_utils import save_image
from .text_overlay import put_text


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Capture microscope images from a Basler camera.")
    parser.add_argument("--output-dir", required=True, help="Directory for saved frames.")
    parser.add_argument("--camera-serial", default=None, help="Optional Basler camera serial number.")
    parser.add_argument("--camera-index", type=int, default=0, help="Basler camera index when serial is not provided.")
    parser.add_argument("--width", type=int, default=None, help="Requested camera width.")
    parser.add_argument("--height", type=int, default=None, help="Requested camera height.")
    parser.add_argument("--exposure-us", type=float, default=None, help="Exposure time in microseconds.")
    parser.add_argument("--gain", type=float, default=None, help="Gain value.")
    parser.add_argument("--fps", type=float, default=None, help="Target acquisition FPS.")
    parser.add_argument("--pixel-format", default=None, help="Optional Basler pixel format.")
    parser.add_argument("--prefix", default="basler_cell", help="Filename prefix.")
    parser.add_argument("--no-preview", action="store_true", help="Disable the live preview window.")
    parser.add_argument("--save-every-frame", action="store_true", help="Write every grabbed frame to disk.")
    parser.add_argument("--max-frames", type=int, default=None, help="Optional maximum number of grabbed frames.")
    parser.add_argument("--preview-max-width", type=int, default=1280, help="Downscale the preview window to this width to improve display FPS.")
    return parser


def _make_output_path(output_dir: Path, prefix: str, frame_index: int) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return output_dir / f"{prefix}_{frame_index:06d}_{timestamp}.png"


def _resize_for_preview(frame, max_width: int | None):
    if max_width is None or max_width <= 0 or frame.shape[1] <= max_width:
        return frame
    scale = max_width / float(frame.shape[1])
    resized_height = max(1, int(round(frame.shape[0] * scale)))
    return cv2.resize(frame, (int(max_width), resized_height), interpolation=cv2.INTER_AREA)


def main() -> int:
    args = _parser().parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    config = BaslerCameraConfig(
        camera_serial=args.camera_serial,
        camera_index=args.camera_index,
        width=args.width,
        height=args.height,
        exposure_us=args.exposure_us,
        gain=args.gain,
        fps=args.fps,
        pixel_format=args.pixel_format,
    )

    saved_count = 0
    frame_index = 0
    with BaslerCamera(config) as camera:
        while True:
            frame = camera.read()
            frame_index += 1

            if args.save_every_frame:
                save_image(_make_output_path(output_dir, args.prefix, frame_index), frame)
                saved_count += 1

            if not args.no_preview:
                preview = _resize_for_preview(frame, args.preview_max_width).copy()
                put_text(preview, f"saved={saved_count}", (20, 32), 1.0, (0, 255, 0), 2)
                cv2.imshow("Basler Capture", preview)
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q") or key == 27:
                    break
                if key == ord("s"):
                    save_image(_make_output_path(output_dir, args.prefix, frame_index), frame)
                    saved_count += 1

            if args.max_frames is not None and frame_index >= args.max_frames:
                break

    cv2.destroyAllWindows()
    print(f"output_dir={output_dir.resolve()}")
    print(f"frames_grabbed={frame_index}")
    print(f"frames_saved={saved_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

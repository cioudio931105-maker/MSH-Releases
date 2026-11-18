from __future__ import annotations

# Direct source entrypoints also resolve shared modules from the workspace.
import sys as _msh_sys
from pathlib import Path as _MshPath
if not getattr(_msh_sys, "frozen", False):
    _msh_sys.path.insert(0, str(_MshPath(__file__).resolve().parents[2]))


import logging
import traceback
from pathlib import Path

import cv2

from Image import load_images_from_folder, stitch_images


def _resolve_input_folder() -> Path:
    """Prefer common dataset paths and return the first existing folder."""
    from msh_app.research_paths import original_research_root
    base = original_research_root() / "scripts"
    candidates = [
        base / "cell_images",
        base.parent / "data" / "cell_images",
        base.parent / "1",
    ]
    for folder in candidates:
        if folder.exists() and folder.is_dir():
            return folder
    return candidates[0]


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
        handlers=[
            logging.FileHandler("stitch_log.txt", mode="a", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )

    folder = _resolve_input_folder()
    logging.info("Quick stitch start: folder=%s max_images=5 resize_width=800", folder)

    try:
        images = load_images_from_folder(str(folder), max_images=5, resize_width=800)
    except Exception:
        logging.error("Failed to load input images")
        logging.error(traceback.format_exc())
        return 1

    if not images:
        logging.error("No valid input images found. Please check folder: %s", folder)
        return 1

    try:
        result = stitch_images(images, prewarp=True)
    except Exception:
        logging.error("Stitching failed")
        logging.error(traceback.format_exc())
        return 1

    if result is None:
        logging.error("Stitching returned no output image")
        return 1

    output_path = Path("stitched_output_quick.jpg")
    if not cv2.imwrite(str(output_path), result):
        logging.error("Failed to write output file: %s", output_path)
        return 1

    size_bytes = output_path.stat().st_size
    logging.info("Quick stitch done: %s (%d bytes)", output_path, size_bytes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

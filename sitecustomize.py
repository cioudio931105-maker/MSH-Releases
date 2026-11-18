"""Project-local Python startup hooks.

Python imports this file automatically when the working directory is on
``sys.path``. Keep this tiny: it patches OpenCV text drawing so standalone
scripts in this project can render Chinese labels without importing the package
entrypoint first.
"""

from __future__ import annotations

try:
    from cell_stitching_project.text_overlay import install_cv2_unicode_puttext_patch

    install_cv2_unicode_puttext_patch()
except Exception:
    pass

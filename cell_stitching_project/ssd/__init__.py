from __future__ import annotations

import sys

from . import vision as _vision

# The vendored SSD code uses absolute imports like `vision.ssd...`.
# Registering this alias keeps the upstream module layout working
# while the code lives inside `cell_stitching_project.ssd`.
sys.modules.setdefault("vision", _vision)


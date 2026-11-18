"""Cell stitching project package."""

from .text_overlay import install_cv2_unicode_puttext_patch

install_cv2_unicode_puttext_patch()

from .config import StitchingConfig
from .cell_classes import WBC_5_CLASS_NAMES, WBC_5_CLASS_NAMES_ZH


def analyze_cells(*args, **kwargs):
    from .cell_analysis import analyze_cells as _analyze_cells

    return _analyze_cells(*args, **kwargs)


def identify_cells(*args, **kwargs):
    from .cell_identification import run_cell_identification as _run_cell_identification

    return _run_cell_identification(*args, **kwargs)


def cell_identfication(*args, **kwargs):
    from .cell_identification import run_cell_identification as _run_cell_identification

    return _run_cell_identification(*args, **kwargs)


def make_cell_analysis_config(*args, **kwargs):
    from .cell_analysis import CellAnalysisConfig as _CellAnalysisConfig

    return _CellAnalysisConfig(*args, **kwargs)


def make_cell_identification_config(*args, **kwargs):
    from .cell_identification import CellIdentificationConfig as _CellIdentificationConfig

    return _CellIdentificationConfig(*args, **kwargs)


def make_cell_identfication_config(*args, **kwargs):
    from .cell_identification import CellIdentificationConfig as _CellIdentificationConfig

    return _CellIdentificationConfig(*args, **kwargs)


def run_stitch_pipeline(*args, **kwargs):
    from .main import run_stitch_pipeline as _run_stitch_pipeline

    return _run_stitch_pipeline(*args, **kwargs)


__all__ = [
    "StitchingConfig",
    "WBC_5_CLASS_NAMES",
    "WBC_5_CLASS_NAMES_ZH",
    "analyze_cells",
    "cell_identfication",
    "identify_cells",
    "make_cell_analysis_config",
    "make_cell_identfication_config",
    "make_cell_identification_config",
    "run_stitch_pipeline",
]

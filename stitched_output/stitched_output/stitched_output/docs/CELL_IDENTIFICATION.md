# Cell Identification Integration

This project now has a unified module for classification and detect+classify flows:

- `cell_identification/classify.py`
- `cell_identification/detect.py`

For compatibility, a misspelled alias package is also available:

- `cell_identfication` -> redirects to `cell_identification`

## Unified entry points

- `scripts/infer_classify.py` now delegates to `cell_identification.classify`
- `scripts/detect_classify.py` now delegates to `cell_identification.detect`
- `scripts/classify_and_move.py` now reuses `cell_identification.classify.top1_label`

## Why this change

- Removes duplicate YOLO classification logic from multiple scripts
- Keeps one source of truth for model discovery/loading and inference flow
- Preserves old CLI behavior and existing script names


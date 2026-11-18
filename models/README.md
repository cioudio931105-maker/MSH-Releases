# MSH model package

This directory documents the model contract; it intentionally does not commit
research weights. Git ignores common model-weight extensions such as `.pt`,
`.onnx`, and `.engine`.

The installed application searches `%LOCALAPPDATA%\MSH\models\` before its
built-in fallback. Place a release-approved WBC detection model there using one
of these names:

- `wbc_focus_yolov8n_e_20260611.pt`
- `blood_cells_3cls_yolov8n_20260429.pt`
- `best.pt`

The v0.1.1 client review candidate uses the external-preserved
`wbc_focus_yolov8n_e_20260611.pt` as its built-in WBC-only detector. Its
approved file identity is recorded in `msh_release_model.py` and
`models/RELEASE_MODEL_v0.1.1.md`; the weight itself remains ignored by Git.

The packaged `yolov8n.pt` is a small generic YOLO fallback only. It is **not**
a cell-detection model and must not be used to claim WBC accuracy. The WBC-only
release model detects WBC bounding boxes; it does not classify WBC subtypes.

Before distributing any WBC model, record its origin, training-data rights,
license, SHA-256, intended use, and validation evidence in the GitHub Release.

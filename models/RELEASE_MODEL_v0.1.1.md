# MSH v0.1.1 release model record

## Model identity

- File: `wbc_focus_yolov8n_e_20260611.pt`
- Task: YOLO object detection
- Classes: `WBC`
- Parameters: 3,011,043
- Size: 6,226,730 bytes (5.94 MiB)
- SHA-256: `fe5a6587e1fce3a39c7dcb9131c8a1f2a28a40afd2e07b22fac57dd3be1fa885`
- Checkpoint date: `2026-06-11T20:28:54.551240`
- Ultralytics checkpoint version: `8.4.36`
- Embedded checkpoint license: `AGPL-3.0`

The source weight is an external-preserved research asset and is not committed
to Git. It was recovered read-only from the B-site cold backup dated 2026-08-17
and copied to the equivalent ignored `stitched_output/.../models/` path on the
A machine. Source and destination SHA-256 values matched.

On 2026-09-15, the copy returned from the B site under
`02_B地產生_帶回A地_20260911/02_核准WBC模型` was independently re-hashed at the
A site. It matched the recorded SHA-256 and was copied to the Git-ignored
top-level `models/wbc_focus_yolov8n_e_20260611.pt` runtime path and the
`stitched_output/stitched_output/stitched_output/models/` release-build path in
the MSH-036 worktree. This confirms artifact identity across the A-to-B-to-A
handoff; it does not grant new redistribution rights.

## Embedded validation metrics

- Precision: `0.99147`
- Recall: `1.0`
- mAP50: `0.995`
- mAP50-95: `0.68337`
- Validation box loss: `0.57639`
- Validation class loss: `2.71707`
- Validation DFL loss: `0.53583`

The preserved WBC-focus dataset contains 36 training images/labels and 9
validation images/labels with a single `WBC` class. Its preserved
`manifest.csv` SHA-256 is
`0bfa2ada656243b7336986648b374618a04eafdc64910a7cfe7f1ea10ba67ef4`.

On 2026-08-21, a read-only CPU inference smoke test at confidence 0.25 produced
8 detections across 8 of the 9 preserved validation images. This confirms that
the checkpoint loads and produces WBC boxes; it is not independent clinical or
hardware validation.

## Release limits

- The model detects WBC bounding boxes only. It does not identify WBC subtypes.
- The embedded metrics come from the preserved training checkpoint and are not
  a substitute for independent B-site microscope validation.
- Public redistribution remains pending an explicit Ultralytics/model licensing
  decision. Do not upload the weight to a public release merely because it is
  available in the cold backup.

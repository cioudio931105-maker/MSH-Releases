from __future__ import annotations

from cell_stitching_project.serpentine_recording import (
    BaslerRecorderCamera,
    OpenCVCamera,
    RecordingStatus,
    SerpentineRecorder,
    SerialXYStage,
    SimulatedCamera,
    SimulatedStage,
    configure_default_recorder,
    estimate_duration_seconds,
    main,
    move_along_path_smoothly,
    path_total_distance,
    sample_path_at_distance,
    save_video,
    serpentine_path,
    start_recording,
    stop_recording,
)

__all__ = [
    "BaslerRecorderCamera",
    "OpenCVCamera",
    "RecordingStatus",
    "SerpentineRecorder",
    "SerialXYStage",
    "SimulatedCamera",
    "SimulatedStage",
    "configure_default_recorder",
    "estimate_duration_seconds",
    "main",
    "move_along_path_smoothly",
    "path_total_distance",
    "sample_path_at_distance",
    "save_video",
    "serpentine_path",
    "start_recording",
    "stop_recording",
]


if __name__ == "__main__":
    raise SystemExit(main())

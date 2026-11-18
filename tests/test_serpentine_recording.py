from __future__ import annotations

import tempfile
import threading
import time
import unittest
from pathlib import Path

from cell_stitching_project.serpentine_recording import (
    SerialXYStage,
    SerpentineRecorder,
    sample_path_at_distance,
    serpentine_path,
    serpentine_path_from_bounds,
)


class SerpentineRecordingTests(unittest.TestCase):
    def test_serpentine_path_reverses_each_row(self) -> None:
        path = serpentine_path(rows=3, cols=4, step_x=200, step_y=150)

        self.assertEqual(
            path,
            [
                (0, 0),
                (200, 0),
                (400, 0),
                (600, 0),
                (600, 150),
                (400, 150),
                (200, 150),
                (0, 150),
                (0, 300),
                (200, 300),
                (400, 300),
                (600, 300),
            ],
        )

    def test_serpentine_path_from_bounds_uses_absolute_start_and_end(self) -> None:
        path = serpentine_path_from_bounds(
            start_x=100,
            start_y=50,
            end_x=500,
            end_y=250,
            step_x=200,
            step_y=100,
        )

        self.assertEqual(
            path,
            [
                (100.0, 50.0),
                (300.0, 50.0),
                (500.0, 50.0),
                (500.0, 150.0),
                (300.0, 150.0),
                (100.0, 150.0),
                (100.0, 250.0),
                (300.0, 250.0),
                (500.0, 250.0),
            ],
        )

    def test_serpentine_path_from_bounds_keeps_exact_non_multiple_endpoint(self) -> None:
        path = serpentine_path_from_bounds(
            start_x=0,
            start_y=0,
            end_x=450,
            end_y=120,
            step_x=200,
            step_y=100,
        )

        self.assertEqual(path[-1], (450.0, 120.0))
        self.assertIn((450.0, 0.0), path)
        self.assertIn((0.0, 120.0), path)

    def test_sampling_path_interpolates_between_nodes(self) -> None:
        path = serpentine_path(rows=1, cols=2, step_x=100, step_y=50)

        first, segment_index, fraction = sample_path_at_distance(path, 25)
        second, _, _ = sample_path_at_distance(path, 30)

        self.assertEqual(segment_index, 0)
        self.assertAlmostEqual(fraction, 0.25)
        self.assertEqual(first, (25.0, 0.0))
        self.assertEqual(second, (30.0, 0.0))
        self.assertLess(second[0] - first[0], 100.0)

    def test_simulated_recording_writes_a_playable_video_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "serpentine_demo.avi"
            recorder = SerpentineRecorder(
                rows=1,
                cols=2,
                step_x=24,
                step_y=10,
                speed=240,
                fps=12,
                output_path=output_path,
                frame_size=(160, 120),
                preview=False,
            )

            recorder.start_recording()
            status = recorder.move_along_path_smoothly(recorder.path, recorder.speed)
            saved_path = recorder.save_video(output_path)

            self.assertTrue(saved_path.exists())
            self.assertGreater(saved_path.stat().st_size, 0)
            self.assertIsNotNone(status)
            self.assertAlmostEqual(status.progress, 1.0)
            self.assertGreaterEqual(recorder.frame_count, 2)

    def test_pause_holds_position_until_resume(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "pause_resume.avi"
            recorder = SerpentineRecorder(
                rows=1,
                cols=2,
                step_x=80,
                step_y=10,
                speed=80,
                fps=20,
                output_path=output_path,
                frame_size=(120, 90),
                preview=False,
            )

            recorder.start_recording()
            worker = threading.Thread(
                target=recorder.move_along_path_smoothly,
                args=(recorder.path, recorder.speed),
                daemon=True,
            )
            worker.start()

            try:
                time.sleep(0.15)
                recorder.pause()
                time.sleep(0.12)
                paused_position = recorder.stage.position
                time.sleep(0.16)
                still_paused_position = recorder.stage.position

                self.assertEqual(paused_position, still_paused_position)

                recorder.resume()
                worker.join(timeout=5.0)
                self.assertFalse(worker.is_alive())
                saved_path = recorder.save_video(output_path)
                self.assertTrue(saved_path.exists())
                self.assertGreater(saved_path.stat().st_size, 0)
            finally:
                if worker.is_alive():
                    recorder.stop_recording()
                    worker.join(timeout=2.0)
                if recorder.is_recording:
                    recorder.save_video(output_path)

    def test_serial_xy_stage_converts_targets_to_relative_moves(self) -> None:
        class FakeStepper:
            def __init__(self) -> None:
                self.moves: list[int] = []

            def connect(self) -> None:
                pass

            def set_speed_ms(self, _value: int) -> None:
                pass

            def set_hold(self, _enabled: bool) -> None:
                pass

            def move(self, steps: int, **_kwargs) -> str:
                self.moves.append(int(steps))
                return "DONE"

            def close(self) -> None:
                pass

        x_stepper = FakeStepper()
        y_stepper = FakeStepper()
        stage = SerialXYStage(x_stepper=x_stepper, y_stepper=y_stepper, x_sign=1, y_sign=-1)

        stage.move_to(10.2, 5.8)
        stage.move_to(14.7, 1.1)

        self.assertEqual(x_stepper.moves, [10, 5])
        self.assertEqual(y_stepper.moves, [-6, 5])
        self.assertEqual(stage.position, (15.0, 1.0))


if __name__ == "__main__":
    unittest.main()

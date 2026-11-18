from __future__ import annotations

from pathlib import Path
import unittest

from msh_release_model import (
    RELEASE_MODEL_CLASSES,
    RELEASE_MODEL_RELATIVE_PATH,
    RELEASE_MODEL_SHA256,
    RELEASE_MODEL_TASK,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ReleaseModelTests(unittest.TestCase):
    def test_release_model_contract_is_wbc_detection(self) -> None:
        self.assertEqual(RELEASE_MODEL_TASK, "detect")
        self.assertEqual(RELEASE_MODEL_CLASSES, ("WBC",))
        self.assertEqual(RELEASE_MODEL_RELATIVE_PATH.name, "wbc_focus_yolov8n_e_20260611.pt")
        self.assertEqual(len(RELEASE_MODEL_SHA256), 64)

    # Historical identity is metadata only; no real model is required for tests.


if __name__ == "__main__":
    unittest.main()

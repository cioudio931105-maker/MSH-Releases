from __future__ import annotations

import hashlib
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

    def test_local_external_model_matches_approved_hash_when_available(self) -> None:
        model_path = PROJECT_ROOT / RELEASE_MODEL_RELATIVE_PATH
        if not model_path.is_file():
            self.skipTest("External WBC release model is not present on this machine")

        digest = hashlib.sha256(model_path.read_bytes()).hexdigest()

        self.assertEqual(digest, RELEASE_MODEL_SHA256)


if __name__ == "__main__":
    unittest.main()

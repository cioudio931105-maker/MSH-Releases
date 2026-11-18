"""Historical metadata remains readable without becoming a runtime dependency."""
from pathlib import Path
import runpy
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ReleaseModelTests(unittest.TestCase):
    def test_archived_identity_is_metadata_only(self):
        metadata = runpy.run_path(str(ROOT / 'docs/legacy/model-release-v0.1.1/msh_release_model.py'))
        self.assertEqual(metadata['RELEASE_MODEL_TASK'], 'detect')
        self.assertEqual(metadata['RELEASE_MODEL_CLASSES'], ('WBC',))
        self.assertEqual(metadata['RELEASE_MODEL_RELATIVE_PATH'].name, 'wbc_focus_yolov8n_e_20260611.pt')
        self.assertEqual(len(metadata['RELEASE_MODEL_SHA256']), 64)

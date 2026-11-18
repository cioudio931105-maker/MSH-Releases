from __future__ import annotations

import unittest

from cell_stitching_project.verify_environment import _diagnose_import_error


class VerifyEnvironmentTests(unittest.TestCase):
    def test_diagnose_import_error_flags_winerror_193_for_torch(self) -> None:
        diagnoses = _diagnose_import_error(
            "torch",
            OSError('[WinError 193] %1 is not a valid Win32 application. Error loading "shm.dll"'),
        )

        self.assertTrue(any("WinError 193" in item for item in diagnoses))
        self.assertTrue(any("PyTorch/Ultralytics failed" in item for item in diagnoses))


if __name__ == "__main__":
    unittest.main()

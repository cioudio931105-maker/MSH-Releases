from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "finalize_release_bundle.ps1"


class FinalizeReleaseBundleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pwsh = shutil.which("pwsh") or shutil.which("powershell")
        if self.pwsh is None:
            self.skipTest("PowerShell is unavailable")
        self.temp_dir = tempfile.TemporaryDirectory()
        self.bundle = Path(self.temp_dir.name)
        self.installer = self.bundle / "MSH_Setup_v1.2.3_CPU.exe"
        self.installer.write_bytes(b"installer payload")
        digest = hashlib.sha256(self.installer.read_bytes()).hexdigest()
        self.installer.with_suffix(self.installer.suffix + ".sha256").write_text(
            f"{digest} *{self.installer.name}\n", encoding="ascii"
        )
        self.manifest_path = self.installer.with_suffix(
            self.installer.suffix + ".build-manifest.json"
        )
        self.manifest_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "version": "1.2.3",
                    "runtime": "cpu",
                    "build_mode": "release",
                    "git_commit": "a" * 40,
                    "git_worktree_dirty": False,
                }
            ),
            encoding="utf-8",
        )
        (self.bundle / "RELEASE_NOTES_v1.2.3.md").write_text(
            "# MSH v1.2.3\n\nRelease notes.", encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def run_script(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                self.pwsh,
                "-NoProfile",
                "-File",
                str(SCRIPT),
                "-BundleDirectory",
                str(self.bundle),
                "-PublicBaseUrl",
                "https://downloads.example.org/msh",
                "-PublishedAt",
                "2026-09-10",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

    def test_generates_provider_neutral_update_and_evidence_files(self) -> None:
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)

        latest = json.loads((self.bundle / "latest.json").read_text(encoding="utf-8-sig"))
        self.assertEqual(latest["version"], "1.2.3")
        self.assertEqual(latest["sha256"], hashlib.sha256(self.installer.read_bytes()).hexdigest())
        self.assertEqual(
            latest["download_url"],
            "https://downloads.example.org/msh/v1.2.3/MSH_Setup_v1.2.3_CPU.exe",
        )

        record = json.loads(
            (self.bundle / "release-record.json").read_text(encoding="utf-8-sig")
        )
        self.assertEqual(record["git_commit"], "a" * 40)
        self.assertEqual(record["installer_size_bytes"], len(b"installer payload"))

    def test_rejects_dirty_build_manifest(self) -> None:
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        manifest["git_worktree_dirty"] = True
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("clean release-mode build", result.stderr)


if __name__ == "__main__":
    unittest.main()

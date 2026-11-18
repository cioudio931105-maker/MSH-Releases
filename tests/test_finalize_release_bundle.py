from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from msh_update import parse_update_manifest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "finalize_release_bundle.ps1"


class FinalizeReleaseBundleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pwsh = shutil.which("pwsh") or shutil.which("powershell")
        if self.pwsh is None:
            self.skipTest("PowerShell is unavailable")
        # Each shell should discover its own standard modules. A PowerShell 7
        # parent can otherwise expose incompatible modules to Windows PS 5.1.
        self.shell_env = {key: value for key, value in os.environ.items() if key.upper() != "PSMODULEPATH"}
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
                    "application": "MSH",
                    "version": "1.2.3",
                    "runtime": "cpu",
                    "build_mode": "release",
                    "git_commit": "a" * 40,
                    "git_worktree_dirty": False,
                    "app_exe_sha256": "b" * 64,
                    "model_distribution": "user-supplied",
                    "bundled_models": [],
                    "bundled_research_data": False,
                    "source_license": "AGPL-3.0-only",
                }
            ),
            encoding="utf-8",
        )
        (self.bundle / "RELEASE_NOTES_v1.2.3.md").write_text(
            "# MSH v1.2.3\n\nRelease notes.", encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def run_script(self, *, base_url="https://downloads.example.org/msh", executable=None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                executable or self.pwsh,
                "-NoProfile",
                "-File",
                str(SCRIPT),
                "-BundleDirectory",
                str(self.bundle),
                "-PublicBaseUrl",
                base_url,
                "-PublishedAt",
                "2026-09-10",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            env=self.shell_env,
        )

    def test_generates_provider_neutral_update_and_evidence_files(self) -> None:
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)

        latest = json.loads((self.bundle / "latest.json").read_text(encoding="utf-8-sig"))
        self.assertEqual(latest["version"], "1.2.3")
        self.assertEqual(parse_update_manifest(latest).version, "1.2.3")
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
        self.assertEqual(record["model_distribution"], "user-supplied")
        self.assertEqual(record["bundled_models"], [])
        self.assertFalse(record["bundled_research_data"])
        for key, name in (
            ("checksum_sha256", self.installer.name + ".sha256"),
            ("build_manifest_sha256", self.manifest_path.name),
            ("release_notes_sha256", "RELEASE_NOTES_v1.2.3.md"),
            ("latest_manifest_sha256", "latest.json"),
        ):
            self.assertEqual(record[key], hashlib.sha256((self.bundle / name).read_bytes()).hexdigest())

    def test_rejects_dirty_build_manifest(self) -> None:
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        manifest["git_worktree_dirty"] = True
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("clean release-mode build", result.stderr)
        self.assertFalse((self.bundle / "latest.json").exists())

    def test_rejects_old_model_distribution_and_missing_or_false_policy_fields(self):
        original = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        cases = (
            ("model_distribution", "bundled"), ("bundled_models", ["old.pt"]),
            ("bundled_models", None), ("bundled_models", ""),
            ("bundled_research_data", True), ("bundled_research_data", "false"),
            ("bundled_research_data", None), ("source_license", None),
        )
        for key, value in cases:
            with self.subTest(key=key, value=value):
                manifest = dict(original)
                if value is None:
                    manifest.pop(key)
                else:
                    manifest[key] = value
                self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
                result = self.run_script()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("application-only", result.stderr)
                self.assertFalse((self.bundle / "latest.json").exists())

    def test_rejects_candidate_or_untraceable_build_without_generating_metadata(self):
        original = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        for updates in ({"build_mode": "candidate"}, {"git_commit": "missing"}, {"git_worktree_dirty": "false"}):
            with self.subTest(updates=updates):
                self.manifest_path.write_text(json.dumps({**original, **updates}), encoding="utf-8")
                self.assertNotEqual(self.run_script().returncode, 0)
                self.assertFalse((self.bundle / "latest.json").exists())

    def test_rejects_corrupt_installer_checksum(self):
        self.installer.write_bytes(b"changed synthetic installer")
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("checksum", result.stderr)
        self.assertFalse((self.bundle / "latest.json").exists())

    def test_rejects_candidate_filenames_and_versions_the_updater_cannot_use(self):
        for name in ("MSH_Setup_v1.2.3_CPU_CANDIDATE.exe", "MSH_Setup_v01.2.3_CPU.exe",
                     "MSH_Setup_v1.2.3.1_CPU.exe", "MSH_Setup_v1.2.3-alpha..1_CPU.exe"):
            with self.subTest(name=name):
                renamed = self.installer.rename(self.bundle / name)
                try:
                    result = self.run_script()
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("Unexpected installer filename", result.stderr)
                    self.assertFalse((self.bundle / "latest.json").exists())
                finally:
                    renamed.rename(self.installer)

    def test_refuses_extra_data_and_existing_metadata_without_changing_them(self):
        for name in ("old.pt", "capture.jpg", ".env", "latest.json", "release-record.json"):
            with self.subTest(name=name):
                sentinel = self.bundle / name
                sentinel.write_bytes(b"synthetic sentinel; preserve unchanged")
                result = self.run_script()
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(sentinel.read_bytes(), b"synthetic sentinel; preserve unchanged")
                sentinel.unlink()
        (self.bundle / "research").mkdir()
        self.assertNotEqual(self.run_script().returncode, 0)
        self.assertFalse((self.bundle / "latest.json").exists())

    def test_rejects_insecure_or_credential_urls_before_writing_metadata(self):
        for url in ("http://downloads.example.org/msh", "https://user:synthetic@example.org/msh", "https://example.org/msh?token=synthetic"):
            with self.subTest(url=url):
                self.assertNotEqual(self.run_script(base_url=url).returncode, 0)
                self.assertFalse((self.bundle / "latest.json").exists())

    def test_build_rejects_candidate_finalization_before_loading_python(self):
        shells = {self.pwsh, shutil.which("powershell")} - {None}
        for shell in sorted(shells):
            for option in ("-Candidate", "-SkipInstaller"):
                with self.subTest(shell=shell, option=option):
                    result = subprocess.run(
                        [shell, "-NoProfile", "-File", str(ROOT / "scripts/build_release.ps1"),
                         "-PythonPath", str(self.bundle / "nonexistent-python.exe"), option,
                         "-PublicBaseUrl", "https://downloads.example.org/msh"],
                        capture_output=True, text=True, encoding="utf-8", errors="replace", env=self.shell_env,
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("PublicBaseUrl requires a release installer", result.stderr)

    def test_windows_powershell_can_finalize_the_same_application_only_format(self):
        powershell = shutil.which("powershell")
        if powershell is None or Path(powershell).resolve() == Path(self.pwsh).resolve():
            self.skipTest("Separate Windows PowerShell is unavailable")
        result = self.run_script(executable=powershell)
        self.assertEqual(result.returncode, 0, result.stderr)
        latest = json.loads((self.bundle / "latest.json").read_text(encoding="utf-8-sig"))
        self.assertEqual(parse_update_manifest(latest).version, "1.2.3")


if __name__ == "__main__":
    unittest.main()

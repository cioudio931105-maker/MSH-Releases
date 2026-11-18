from __future__ import annotations

import unittest
import json
from pathlib import Path
from unittest.mock import patch

from msh_update import (DEFAULT_UPDATE_MANIFEST_URL, RELEASE_REPOSITORY, UpdateCheckError,
                        UpdateManifest, check_for_update, is_newer_version,
                        parse_update_manifest, validate_installer_url)


def _payload(**overrides):
    payload = {
        "schema_version": 1,
        "version": "0.1.1",
        "release_name": "MSH v0.1.1 委託方檢閱版",
        "release_notes": "修正安裝與更新提示。",
        "download_url": "https://github.com/example/MSH-Releases/releases/download/v0.1.1/MSH_Setup_v0.1.1_CPU.exe",
        "release_page_url": "https://github.com/example/MSH-Releases/releases/tag/v0.1.1",
        "sha256": "a" * 64,
        "published_at": "2026-08-21",
    }
    payload.update(overrides)
    return payload


class VersionComparisonTests(unittest.TestCase):
    def test_patch_release_is_newer(self) -> None:
        self.assertTrue(is_newer_version("0.1.1", "0.1.0"))

    def test_same_or_older_release_is_not_newer(self) -> None:
        self.assertFalse(is_newer_version("0.1.0", "0.1.0"))
        self.assertFalse(is_newer_version("0.1.0", "0.2.0"))

    def test_stable_release_is_newer_than_its_prerelease(self) -> None:
        self.assertTrue(is_newer_version("1.0.0", "1.0.0-rc.1"))
        self.assertTrue(is_newer_version("1.0.0-rc.2", "1.0.0-rc.1"))


class UpdateSourceTests(unittest.TestCase):
    def test_public_release_repository_is_the_only_default_source(self):
        self.assertEqual(RELEASE_REPOSITORY, "cioudio931105-maker/MSH-Releases")
        self.assertEqual(DEFAULT_UPDATE_MANIFEST_URL,
                         "https://raw.githubusercontent.com/cioudio931105-maker/MSH-Releases/main/latest.json")

    def test_private_development_repository_installers_are_rejected(self):
        public_url = "https://github.com/cioudio931105-maker/MSH-Releases/releases/download/v1.0.0/MSH.exe"
        self.assertEqual(validate_installer_url(public_url), public_url)
        with self.assertRaises(UpdateCheckError):
            validate_installer_url(public_url.replace("MSH-Releases", "Microscope-Scanner-Helper_MSH"))

    def test_release_example_uses_the_same_public_source(self):
        payload = json.loads((Path(__file__).resolve().parents[1] / "release/latest.example.json").read_text(encoding="utf-8"))
        validate_installer_url(payload["download_url"])
        self.assertTrue(payload["release_page_url"].startswith(f"https://github.com/{RELEASE_REPOSITORY}/releases/"))


class ManifestValidationTests(unittest.TestCase):
    def test_valid_manifest_is_normalized(self) -> None:
        manifest = parse_update_manifest(_payload(sha256="A" * 64))
        self.assertEqual(manifest.version, "0.1.1")
        self.assertEqual(manifest.sha256, "a" * 64)

    def test_insecure_download_url_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            parse_update_manifest(_payload(download_url="http://example.com/MSH.exe"))

    def test_invalid_checksum_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "sha256"):
            parse_update_manifest(_payload(sha256="not-a-checksum"))


class UpdateSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = UpdateManifest(
            version="0.1.1",
            release_name="MSH v0.1.1",
            release_notes="Test release",
            download_url="https://example.com/MSH.exe",
            release_page_url="https://example.com/release",
            sha256="b" * 64,
            published_at="2026-08-21",
        )

    @patch("msh_update.fetch_update_manifest")
    def test_newer_manifest_is_returned(self, fetch) -> None:
        fetch.return_value = self.manifest
        self.assertIs(check_for_update("0.1.0"), self.manifest)

    @patch("msh_update.fetch_update_manifest")
    def test_current_manifest_returns_none(self, fetch) -> None:
        fetch.return_value = self.manifest
        self.assertIsNone(check_for_update("0.1.1"))


if __name__ == "__main__":
    unittest.main()

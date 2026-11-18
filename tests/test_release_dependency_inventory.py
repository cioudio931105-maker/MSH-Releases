"""Provenance checks must not mistake a filename or overlapping RECORD for ownership."""
import base64
from email.message import Message
import hashlib
import json
from importlib.metadata import PackagePath
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from scripts.inventory_release_dependencies import inventory
from scripts.collect_dependency_licenses import collect
from scripts.collect_runtime_licenses import collect as collect_runtime


class FakeDistribution:
    def __init__(self, root, name, content, recorded_content=None):
        self.metadata = Message()
        self.metadata["Name"] = name
        self.version = "1.0"
        self.root = root
        root.mkdir()
        (root / "shared.dll").write_bytes(content)
        entry = PackagePath("shared.dll")
        digest = hashlib.sha256(content if recorded_content is None else recorded_content).digest()
        entry.hash = SimpleNamespace(mode="sha256", value=base64.urlsafe_b64encode(digest).decode().rstrip("="))
        self.files = [entry]

    def locate_file(self, entry):
        return self.root / entry


class ReleaseDependencyInventoryTests(unittest.TestCase):
    def test_runtime_notice_collection_copies_text_only_and_omits_absolute_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prefix = root / "prefix"
            (prefix / "conda-meta").mkdir(parents=True)
            cache = root / "cache"
            notice_dir = cache / "info/licenses"
            notice_dir.mkdir(parents=True)
            (notice_dir / "license.terms").write_bytes(b"Original runtime terms\r\n")
            (notice_dir / "LICENSE.pt").write_bytes(b"synthetic model excluded")
            (notice_dir / "LICENSE.RTF").write_bytes(b"duplicate rich text")
            (prefix / "conda-meta/example.json").write_text(json.dumps({
                "name":"example", "version":"1.0", "build":"build_1", "extracted_package_dir":str(cache)
            }), encoding="utf-8")
            destination = root / "notices"
            self.assertEqual(collect_runtime(prefix, destination, ["example"]), 1)
            copied = destination / "example/1.0/1/NOTICE_license.terms.txt"
            self.assertEqual(copied.read_bytes(), b"Original runtime terms\r\n")
            self.assertNotIn(directory, (destination / "README.md").read_text(encoding="utf-8"))
            with self.assertRaises(FileExistsError):
                collect_runtime(prefix, destination, ["example"])
            with self.assertRaises(ValueError):
                collect_runtime(prefix, root / "missing", ["absent"])
            self.assertFalse((root / "missing").exists())

    def test_british_spelling_notice_keeps_original_bytes_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            owner = FakeDistribution(root / "installed", "example", b"library")
            notice = b"Original attribution\r\nMIT terms\r\n"
            (owner.root / "LICENCE").write_bytes(notice)
            owner.files.append(PackagePath("LICENCE"))
            destination = root / "notices"
            with patch("scripts.collect_dependency_licenses.metadata.distributions", return_value=[owner]):
                self.assertEqual(collect(destination), (1, 1))
                copied = destination / "third_party/example/1.0/1/LICENSE"
                self.assertEqual(copied.read_bytes(), notice)
                self.assertIn("`LICENCE`", (destination / "README.md").read_text(encoding="utf-8"))
                with self.assertRaises(FileExistsError):
                    collect(destination)

    def test_hash_distinguishes_same_name_and_keeps_overlapping_record_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = root / "payload"
            payload.mkdir()
            (payload / "shared.dll").write_bytes(b"real library")
            (payload / "MSH.exe").write_bytes(b"app")
            (payload / "private.pt").write_bytes(b"not a native library")
            owners = [
                FakeDistribution(root / "one", "correct", b"real library"),
                FakeDistribution(root / "two", "wrong", b"another library"),
                FakeDistribution(root / "three", "overlap", b"real library", b"stale RECORD"),
            ]
            result = inventory(payload, owners)
            self.assertEqual(result["summary"]["native_payload_files"], 2)
            self.assertEqual(result["summary"]["unresolved_native_files"], 1)
            shared = next(row for row in result["native_payload"] if row["path"] == "shared.dll")
            self.assertEqual({c["distribution"] for c in shared["matching_installed_owners"]}, {"correct", "overlap"})
            self.assertEqual(shared["same_name_nonmatching_owners"][0]["distribution"], "wrong")
            claims = {c["distribution"]: c for c in shared["matching_installed_owners"]}
            self.assertTrue(claims["correct"]["installed_matches_record_sha256"])
            self.assertFalse(claims["overlap"]["installed_matches_record_sha256"])
            self.assertNotIn(directory, str(result))


if __name__ == "__main__":
    unittest.main()

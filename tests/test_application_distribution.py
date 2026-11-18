from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from msh_distribution import application_files, is_application_file
from msh_model_policy import local_training_options, require_local_model
from scripts.audit_packaged_application import audit as audit_payload
from offline_cell_analysis.offline_pipeline.model_files import require_local_model as offline_local_model


ROOT = Path(__file__).resolve().parents[1]


class ApplicationDistributionTests(unittest.TestCase):
    def test_ensemble_requires_local_classifier_before_constructing_model(self):
        path = ROOT / "msh_app/scripts/detect_classify_ensemble.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "load_effnet")
        factory, torch = Mock(), Mock()
        namespace = {"Optional": __import__("typing").Optional, "efficientnet_b0": factory,
                     "torch": torch, "require_local_model": require_local_model}
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), "exec"), namespace)
        for value in (None, "", "https://example.com/weights.pth"):
            with self.assertRaises(FileNotFoundError):
                namespace["load_effnet"](value, None, "cpu")
        factory.assert_not_called()
        torch.load.assert_not_called()
        with tempfile.TemporaryDirectory() as directory:
            local = Path(directory) / "classifier.pth"
            local.write_bytes(b"synthetic state_dict stand-in")
            torch.load.return_value = {"state_dict": {"module.layer": "synthetic"}}
            namespace["load_effnet"](str(local), None, "cpu")
            factory.assert_called_once_with(weights=None)
            torch.load.assert_called_once_with(str(local.resolve()), map_location="cpu")
            factory.return_value.load_state_dict.assert_called_once_with({"layer": "synthetic"}, strict=False)

    def test_legacy_ssd_architectures_reject_pretrained_downloads(self):
        for filename, names, constructor in (
            ("alexnet.py", ("alexnet",), "AlexNet"),
            ("squeezenet.py", ("squeezenet1_0", "squeezenet1_1"), "SqueezeNet"),
        ):
            path = ROOT / "cell_stitching_project/ssd/vision/nn" / filename
            tree = ast.parse(path.read_text(encoding="utf-8"))
            functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
            factory, downloader = Mock(), Mock()
            namespace = {constructor: factory, "model_zoo": downloader}
            exec(compile(ast.Module(body=functions, type_ignores=[]), str(path), "exec"), namespace)
            for name in names:
                with self.subTest(name=name):
                    with self.assertRaisesRegex(ValueError, "does not supply or download"):
                        namespace[name](pretrained=True)
            factory.assert_not_called()
            downloader.load_url.assert_not_called()
            for name in names:
                self.assertIs(namespace[name](pretrained=False), factory.return_value)

    def test_new_payload_requires_selected_license_notices_and_manifest_hashes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source"
            app = root / "app"
            internal = app / "_internal"
            internal.mkdir(parents=True)
            files = {"LICENSE": b"synthetic license", "THIRD_PARTY_NOTICES.md": b"synthetic review", "licenses/README.md": b"synthetic notice inventory"}
            for name, content in files.items():
                for parent in (source, internal):
                    path = parent / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(content)
            (app / "MSH.exe").write_bytes(b"synthetic executable")
            manifest = {"model_distribution": "user-supplied", "bundled_models": [], "bundled_research_data": False,
                        "source_license": "AGPL-3.0-only", "app_exe_sha256": hashlib.sha256(b"synthetic executable").hexdigest(),
                        "license_notice_sha256": {"licenses/README.md": hashlib.sha256(files["licenses/README.md"]).hexdigest()}}
            (app / "MSH-build-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            self.assertTrue(audit_payload(app, source)["passed"])
            (internal / "LICENSE").unlink()
            self.assertIn("Required release notice absent: LICENSE", audit_payload(app, source)["issues"])
            (internal / "LICENSE").write_bytes(files["LICENSE"])
            manifest["license_notice_sha256"] = {}
            (app / "MSH-build-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            self.assertIn("Release notice hash inventory differs from source", audit_payload(app, source)["issues"])

    def test_reject_missing_model_alias_url_directory_and_empty_value(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            for loader in (require_local_model, offline_local_model):
                for value in (None, "", " ", temp_dir, str(Path(temp_dir) / "yolov8n.pt"), "https://example.com/model.pt"):
                    with self.subTest(loader=loader.__module__, value=value):
                        with self.assertRaises(FileNotFoundError):
                            loader(value)

    def test_user_model_with_arbitrary_name_is_accepted(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "my model.pt"
            path.write_bytes(b"synthetic stand-in")
            for loader in (require_local_model, offline_local_model):
                self.assertEqual(loader(path), str(path.resolve()))

    def test_training_preserves_supplied_checkpoint_and_avoids_amp_probe_weights(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            checkpoint = Path(temp_dir) / "my_weights.pt"
            architecture = Path(temp_dir) / "my_architecture.yaml"
            checkpoint.write_bytes(b"synthetic stand-in")
            architecture.write_text("synthetic: true", encoding="utf-8")
            self.assertEqual(local_training_options(checkpoint), {"pretrained": str(checkpoint.resolve()), "amp": False})
            self.assertEqual(local_training_options(architecture), {"pretrained": False, "amp": False})

    def test_research_and_secret_files_are_not_distribution_inputs(self):
        forbidden = (
            "yolov8n.pt", "models/my.onnx", ".env", "private.key", "data/training/input.py",
            "tmp/tool.py", "reports/paper_training_charts/generate_charts.py", "runs/labels.txt",
            "licenses/LICENSE.pt", "licenses/LICENSE.png", "licenses/LICENSE.json", "licenses/LICENSE.exe",
            "microscope_stitcher_project/reference/result.json", "datasets/classes.txt",
            "cell_stitching_project/data/smoke_input/sample.jpg", "research/capture.png",
            "msh_app/hardware/camera_profiles/camera.pfs",
        )
        for path in forbidden:
            with self.subTest(path=path):
                self.assertFalse(is_application_file(path))

    def test_application_sources_training_code_and_ui_assets_are_included(self):
        for path in (
            "cell_stitching_project/train_yolo_wbc400.py", "tests/test_application_distribution.py",
            "cell_stitching_project/ssd/vision/datasets/voc_dataset.py", "README.md",
            "assets/branding/v1/msh-pixel-icon-v1.png", "release/latest.example.json",
            "tools/physician_review/MSH_tool.html", "requirements-cpu.txt", "models/README.md",
            "LICENSE", ".gitattributes", "licenses/README.md", "licenses/third_party/pypylon/26.7/1/LICENSE",
            "licenses/third_party/torch/2.6.0/1/LICENSE.txt",
        ):
            with self.subTest(path=path):
                self.assertTrue(is_application_file(path))

    def test_payload_collector_excludes_adjacent_training_assets(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for name in ("module.py", "data/private.png", "models/private.pt", "__pycache__/module.pyc"):
                path = root / "cell_stitching_project" / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"synthetic")
            entries = application_files(root, "cell_stitching_project")
            self.assertEqual(entries, [(str(root / "cell_stitching_project/module.py"), "cell_stitching_project")])

    def test_spec_can_select_payload_without_release_weights(self):
        class AnalysisStub:
            def __init__(self, *args, **kwargs):
                self.datas = [
                    ("ultralytics/assets/bus.jpg", "unused", "DATA"),
                    ("ultralytics/model.pt", "unused", "DATA"),
                    ("matplotlib/mpl-data/sample_data/grace_hopper.jpg", "unused", "DATA"),
                    ("matplotlib/mpl-data/sample_data/data_x_x2_x3.csv", "unused", "DATA"),
                    ("pypylon/pylonDataProcessingPlugins/PylonVToolPackageA/ocr/model.omc", "unused", "DATA"),
                    ("pypylon/DataProcessingPluginsB/model.bin", "unused", "DATA"),
                    ("ultralytics/cfg/default.yaml", "unused", "DATA"),
                ]
                self.binaries = [
                    ("pypylon/pylonDataProcessingPlugins/plugin.dll", "unused", "BINARY"),
                    ("pypylon/_pylon.pyd", "unused", "BINARY"),
                ]
                self.pure = self.scripts = []
                self.kwargs = kwargs

        namespace = dict(SPECPATH=str(ROOT), Analysis=AnalysisStub, PYZ=Mock(), EXE=Mock(), COLLECT=Mock())
        exec(compile((ROOT / "MSH.spec").read_text(encoding="utf-8"), "MSH.spec", "exec"), namespace)
        analysis = namespace["a"]
        selected = {Path(source).relative_to(ROOT).as_posix() for source, _ in analysis.kwargs["datas"]}
        self.assertTrue({"LICENSE", "THIRD_PARTY_NOTICES.md", "licenses/README.md"}.issubset(selected))
        self.assertEqual(analysis.datas, [("ultralytics/cfg/default.yaml", "unused", "DATA")])
        self.assertEqual(analysis.binaries, [("pypylon/_pylon.pyd", "unused", "BINARY")])
        for source, _destination in analysis.kwargs["datas"]:
            self.assertTrue(is_application_file(Path(source).relative_to(ROOT)))

    def test_all_yolo_entrypoints_validate_local_file_before_backend(self):
        count = 0
        for subtree in ("cell_stitching_project", "offline_cell_analysis", "msh_app"):
            for source in (ROOT / subtree).rglob("*.py"):
                if "__pycache__" in source.parts:
                    continue
                for node in ast.walk(ast.parse(source.read_text(encoding="utf-8-sig"))):
                    if not isinstance(node, ast.Call):
                        continue
                    func = node.func
                    if (isinstance(func, ast.Name) and func.id == "YOLO") or (isinstance(func, ast.Attribute) and func.attr == "YOLO"):
                        count += 1
                        self.assertIsInstance(node.args[0], ast.Call, str(source))
                        self.assertEqual(getattr(node.args[0].func, "id", None), "require_local_model", str(source))
        self.assertGreater(count, 20)


if __name__ == "__main__":
    unittest.main()

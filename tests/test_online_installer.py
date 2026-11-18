"""Review installer inputs without installing software or downloading drivers."""
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from msh_version import __version__
from scripts import build_online_installer as builder
from scripts.build_online_installer import inspect_package, pascal_define


class OnlinePackageValidationTests(unittest.TestCase):
    def fixture(self, root, runtime='gpu', **changes):
        path = root / f'MSH_Setup_v{__version__}_{runtime.upper()}_CANDIDATE.exe'
        path.write_bytes(b'MZsynthetic; never execute')
        Path(str(path) + '.sha256').write_text(hashlib.sha256(path.read_bytes()).hexdigest() + ' *' + path.name)
        manifest = dict(version=__version__, runtime=runtime, build_mode='candidate',
                        git_worktree_dirty=True, model_distribution='user-supplied',
                        bundled_models=[], bundled_research_data=False)
        manifest.update(changes)
        Path(str(path) + '.build-manifest.json').write_text(json.dumps(manifest))
        return path

    def test_matching_candidate_is_accepted_for_internal_build(self):
        with TemporaryDirectory() as temp:
            path = self.fixture(Path(temp))
            self.assertEqual(inspect_package(path, 'gpu', True)['path'], path)

    def test_mismatched_runtime_version_and_policy_are_rejected(self):
        for changes in (dict(version='0.0.0'), dict(runtime='cpu'), dict(bundled_models=['private.pt']),
                        dict(bundled_research_data=True), dict(build_mode='release')):
            with self.subTest(changes=changes), TemporaryDirectory() as temp:
                with self.assertRaises(ValueError):
                    inspect_package(self.fixture(Path(temp), **changes), 'gpu', True)

    def test_candidate_cannot_be_promoted_to_formal_release(self):
        with TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                inspect_package(self.fixture(Path(temp)), 'gpu', False)

    def test_changed_installer_bytes_are_rejected(self):
        with TemporaryDirectory() as temp:
            path = self.fixture(Path(temp))
            path.write_bytes(b'MZchanged installer')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                inspect_package(path, 'gpu', True)

    def test_build_defines_reject_preprocessor_and_pascal_injection(self):
        for value in ('x"\n#define y', "x');run();('y", 'x\ny', 'x\ry'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                pascal_define('Url', value)

    def test_old_updater_source_cannot_be_mixed_with_new_online_bootstrapper(self):
        hashes = {name: builder.sha256(builder.ROOT / name) for name in
                  ('installer/MSH_Online.iss', 'scripts/build_online_installer.py', 'msh_update.py')}
        hashes['msh_update.py'] = '0' * 64
        with TemporaryDirectory() as temp:
            root = Path(temp)
            cpu = self.fixture(root, runtime='cpu', git_commit='a' * 40, source_sha256=hashes)
            gpu = self.fixture(root, runtime='gpu', git_commit='a' * 40, source_sha256=hashes)
            with patch.object(builder.subprocess, 'run') as compiler:
                with self.assertRaisesRegex(ValueError, 'msh_update.py'):
                    builder.main(['--candidate', '--cpu', str(cpu), '--gpu', str(gpu)])
                compiler.assert_not_called()

    def test_online_package_urls_use_public_release_repository(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            hashes = {}
            for name in ('installer/MSH_Online.iss', 'scripts/build_online_installer.py', 'msh_update.py'):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((builder.ROOT / name).read_bytes())
                hashes[name] = builder.sha256(path)
            cpu = self.fixture(root, runtime='cpu', git_commit='a' * 40, source_sha256=hashes)
            gpu = self.fixture(root, runtime='gpu', git_commit='a' * 40, source_sha256=hashes)
            compiler = root / 'ISCC.exe'
            compiler.write_bytes(b'MZsynthetic compiler placeholder; never execute')
            name = f'MSH_Setup_v{__version__}_ONLINE_CANDIDATE.exe'

            def compile_fixture(command, **kwargs):
                config = Path(next(item.split('=', 1)[1] for item in command if item.startswith('/DPayloadConfig=')))
                definitions = config.read_text(encoding='utf-8-sig')
                self.assertIn('https://github.com/cioudio931105-maker/MSH-Releases/releases/download/', definitions)
                self.assertNotIn('Microscope-Scanner-Helper_MSH/releases/', definitions)
                (root / 'dist/release' / f'v{__version__}' / name).write_bytes(b'MZsynthetic online installer; never execute')

            with patch.object(builder, 'ROOT', root), patch.object(builder.subprocess, 'run', side_effect=compile_fixture):
                builder.main(['--candidate', '--cpu', str(cpu), '--gpu', str(gpu), '--iscc', str(compiler)])
            evidence = json.loads((root / 'dist/release' / f'v{__version__}' / (name + '.build-manifest.json')).read_text())
            for package in evidence['packages'].values():
                self.assertTrue(package['url'].startswith('https://github.com/cioudio931105-maker/MSH-Releases/releases/download/'))


if __name__ == '__main__':
    unittest.main()

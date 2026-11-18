"""Synthetic delivery/API tests. Never upload files or install/run hardware."""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import zipfile

from msh_app.core.msh_update import RELEASE_REPOSITORY
from scripts import release_bundle as bundle
from scripts import publish_release as publisher
from scripts import ci_release
from scripts import release_pipeline

COMMIT = 'a' * 40
VERSION = '1.2.3'


def write_json(path, value):
    path.write_text(json.dumps(value), encoding='utf-8')


def acceptance():
    return {'schema_version': 1, 'version': VERSION, 'source_commit': COMMIT,
            'checks': {name: {'status': 'passed', 'evidence': 'Synthetic fixture only'} for name in bundle.CHECKS}}


def fixture(directory, candidate=False):
    root = Path(directory)
    (root / 'LICENSE').write_text('Synthetic license fixture', encoding='utf-8')
    (root / 'THIRD_PARTY_NOTICES.md').write_text('Synthetic notices', encoding='utf-8')
    (root / 'README.md').write_text('Synthetic application', encoding='utf-8')
    (root / 'release').mkdir()
    write_json(root / 'release/acceptance.json', acceptance())
    (root / '.env').write_text('private local setting', encoding='utf-8')
    (root / 'model.pt').write_bytes(b'synthetic excluded model')
    (root / 'capture.jpg').write_bytes(b'synthetic excluded capture')
    sources = ['LICENSE', 'THIRD_PARTY_NOTICES.md', 'README.md', 'release/acceptance.json']
    full = {name: bundle.sha256(root / name) for name in sources}
    hashes = {'README.md': full['README.md']}
    release = root / 'dist/release'
    release.mkdir(parents=True)
    manifests = {}
    names = {}
    for runtime in ('cpu', 'gpu', 'online'):
        name = f'MSH_Setup_v{VERSION}_{runtime.upper()}' + ('_CANDIDATE' if candidate else '') + '.exe'
        names[runtime] = name
        executable = release / name
        executable.write_bytes(b'MZ-SYNTHETIC-UNEXECUTABLE-' + runtime.encode())
        digest = bundle.sha256(executable)
        (release / (name + '.sha256')).write_text(f'{digest} *{name}\n', encoding='ascii')
        manifests[runtime] = dict(version=VERSION, runtime=runtime, build_mode='candidate' if candidate else 'release',
                                 git_commit=COMMIT, git_worktree_dirty=False, source_sha256=hashes,
                                 application_source_sha256=full, model_distribution='user-supplied',
                                 bundled_models=[], bundled_research_data=False)
    manifests['online'].update(installer_sha256=bundle.sha256(release / names['online']),
        basler_prerequisite={'url': 'https://www.baslerweb.com/synthetic.exe', 'sha256': 'b' * 64},
        packages={runtime: {'url': f'https://github.com/{RELEASE_REPOSITORY}/releases/download/v{VERSION}/{names[runtime]}',
                            'sha256': bundle.sha256(release / names[runtime])} for runtime in ('cpu', 'gpu')})
    for runtime in manifests:
        write_json(release / (names[runtime] + '.build-manifest.json'), manifests[runtime])

    def git(_root, *args):
        if args[0] == 'rev-parse':
            return COMMIT
        if args[0] == 'status':
            return ''
        if args[0] == 'ls-files':
            return '\0'.join(sources + ['.env', 'model.pt', 'capture.jpg']) + '\0'
        raise AssertionError(args)

    with patch.object(bundle, '__version__', VERSION), patch.object(bundle, 'git', side_effect=git):
        return bundle.prepare(root, release, root / 'delivery', candidate=candidate, acceptance=acceptance())


def rewrite_plan_asset(plan_path, filename):
    plan = bundle.load_json(plan_path)
    path = plan_path.parent / filename
    for entry in plan['assets']:
        if entry['name'] == filename:
            entry.update(sha256=bundle.sha256(path), size_bytes=path.stat().st_size)
    write_json(plan_path, plan)


class FakeClient:
    def __init__(self):
        self.calls = []
        self.release = None
        self.assets = []
        self.latest = None
        self.fail_upload = False
        self.fail_public = False
        self.conflict = False

    def request(self, method, suffix, payload=None):
        self.calls.append((method, suffix, payload))
        if method == 'GET' and suffix == '':
            return {'full_name': RELEASE_REPOSITORY, 'private': False, 'default_branch': 'main', 'archived': False}
        if method == 'GET' and suffix.startswith('/contents/'):
            if self.latest is None:
                raise publisher.APIError(404)
            return {'sha': 'old-blob', 'content': base64.b64encode(json.dumps(self.latest).encode()).decode()}
        if method == 'GET' and suffix.startswith('/releases/tags/'):
            if self.release is None:
                raise publisher.APIError(404)
            return self.release
        if method == 'POST' and suffix == '/releases':
            self.release = {**payload, 'id': 12}
            return self.release
        if method == 'GET' and '/assets?' in suffix:
            return self.assets
        if method == 'PATCH':
            self.release = {**self.release, **payload, 'published_at': '2026-01-01T00:00:00Z'}
            return self.release
        if method == 'PUT' and suffix == '/contents/latest.json':
            if self.conflict:
                raise publisher.APIError(409)
            self.latest = json.loads(base64.b64decode(payload['content']))
            return {}
        raise AssertionError((method, suffix))

    def upload(self, release_id, path):
        self.calls.append(('UPLOAD', path.name, None))
        if self.fail_upload:
            raise publisher.APIError(503)
        asset = {'name': path.name, 'size': path.stat().st_size, 'state': 'uploaded',
                 'digest': 'sha256:' + bundle.sha256(path)}
        self.assets.append(asset)
        return asset

    def verify_public(self, url, entry):
        self.calls.append(('ANONYMOUS', entry['name'], None))
        if self.fail_public:
            raise ValueError('synthetic anonymous verification failure')


class DeliveryTests(unittest.TestCase):
    def test_local_migration_and_workstate_records_are_never_application_sources(self):
        for name in ('.migration-local/TODO.md', '.migration-local/WORK_STATE.md',
                     '.migration-local/snapshots/branch/example.py'):
            self.assertFalse(bundle.public_source_file(name), name)

    def test_publish_uses_only_an_explicit_same_repo_main_job_token(self):
        context = {'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': RELEASE_REPOSITORY,
                   'GITHUB_REF': 'refs/heads/main', 'GITHUB_EVENT_NAME': 'workflow_dispatch',
                   'GITHUB_TOKEN': 'synthetic-short-lived-job-token'}
        with patch.dict(os.environ, context, clear=True), patch.object(publisher, 'GitHubClient') as client:
            self.assertIs(publisher.workflow_client(), client.return_value)
            client.assert_called_once_with('synthetic-short-lived-job-token')
        for key, value in (('GITHUB_ACTIONS', 'false'), ('GITHUB_REPOSITORY', 'other/repo'),
                           ('GITHUB_REF', 'refs/heads/other'), ('GITHUB_EVENT_NAME', 'push')):
            with self.subTest(key=key), patch.dict(os.environ, {**context, key: value}, clear=True):
                with self.assertRaises(ValueError):
                    publisher.workflow_client()
        with patch.dict(os.environ, {**context, 'GITHUB_TOKEN': '', 'MSH_RELEASE_TOKEN': 'synthetic-personal-token'}, clear=True):
            with self.assertRaisesRegex(ValueError, 'temporary GITHUB_TOKEN'):
                publisher.workflow_client()

    def test_public_acceptance_rejects_extra_raw_records_and_secret_candidates(self):
        for record in (dict(acceptance(), raw_samples=['synthetic excluded fixture']),
                       dict(acceptance(), private_attachments=['synthetic attachment'])):
            with self.assertRaises(ValueError):
                bundle.validate_public_acceptance(record, VERSION, COMMIT)
        record = acceptance()
        record['checks']['windows_10']['evidence'] = 'ghp_' + 'A' * 40
        with self.assertRaisesRegex(ValueError, 'Secret candidate'):
            bundle.validate_public_acceptance(record, VERSION, COMMIT)

    def test_root_update_pointer_is_application_configuration_only_at_the_repo_root(self):
        for name in ('latest.json', 'release/latest.example.json'):
            self.assertTrue(bundle.public_source_file(name), name)
        for name in ('other/latest.json', 'data/latest.json', '.env', 'model.pt', 'camera.pfs'):
            self.assertFalse(bundle.public_source_file(name), name)

    def test_public_workflow_limits_write_permission_and_does_not_upload_candidate_binaries(self):
        import yaml
        root = Path(__file__).resolve().parents[1]
        text = (root / '.github/workflows/release.yml').read_text(encoding='utf-8')
        workflow = yaml.safe_load(text)
        self.assertEqual(workflow['permissions']['contents'], 'read')
        self.assertEqual(workflow['jobs']['publish']['permissions']['contents'], 'write')
        self.assertNotIn('secrets.MSH_RELEASE_TOKEN', text)
        self.assertIn("inputs.operation == 'prepare-release'", workflow['jobs']['assemble']['if'])
        for job_name, job in workflow['jobs'].items():
            if job_name != 'publish':
                self.assertNotEqual(job.get('permissions', {}).get('contents'), 'write')
            for step in job['steps']:
                if 'actions/upload-artifact@' in step.get('uses', ''):
                    condition = job.get('if', '') + ' ' + step.get('if', '')
                    self.assertIn("inputs.operation == 'prepare-release'", condition)

    @unittest.skipUnless(os.name == 'nt', 'Native Windows PowerShell build environment')
    def test_build_subprocess_loads_windows_powershell_hash_module_from_a_pwsh_parent(self):
        import subprocess
        original_run = subprocess.run
        with TemporaryDirectory() as directory, patch.object(release_pipeline, 'ROOT', Path(directory)), \
                patch.dict(os.environ, {'PSModulePath': r'C:\synthetic-pwsh-only-modules'}), \
                patch.object(release_pipeline.subprocess, 'run') as child:
            def run(arguments, **kwargs):
                source = Path(directory) / 'hash-fixture.txt'
                source.write_bytes(b'synthetic hash verification')
                command = "(Get-FileHash -LiteralPath 'hash-fixture.txt' -ErrorAction Stop).Hash"
                result = original_run(['powershell.exe', '-NoProfile', '-Command', command], **kwargs)
                self.assertEqual(result.returncode, 0)
                return result
            child.side_effect = run
            release_pipeline.package('cpu', Path('python.exe'), True)
            log = next((Path(directory) / 'build/release-logs').glob('*.log')).read_text(encoding='utf-8')
            self.assertIn(hashlib.sha256(b'synthetic hash verification').hexdigest().upper(), log)

    def test_prerequisite_download_never_deletes_an_existing_file(self):
        with TemporaryDirectory() as directory, patch.object(ci_release, 'build_opener') as network:
            path = Path(directory) / 'existing.exe'
            path.write_bytes(b'MZprevious-reviewed-file')
            with self.assertRaises(FileExistsError):
                ci_release.download('https://www.baslerweb.com/synthetic.exe', 'a' * 64, path)
            self.assertEqual(path.read_bytes(), b'MZprevious-reviewed-file')
            network.assert_not_called()

    def test_only_successful_main_release_workflow_artifacts_can_be_selected(self):
        run = dict(conclusion='success', event='workflow_dispatch', head_branch='main',
                   path='.github/workflows/release.yml', head_sha=COMMIT,
                   repository={'full_name': ci_release.SOURCE_REPOSITORY})
        with patch.dict('os.environ', {'GITHUB_TOKEN': 'synthetic-token', 'GITHUB_REPOSITORY': ci_release.SOURCE_REPOSITORY}), \
                patch.object(ci_release, 'build_opener') as network:
            for key, wrong in (('head_branch', 'other'), ('conclusion', 'failure'), ('path', '.github/workflows/other.yml')):
                network.return_value.open.return_value = io.BytesIO(json.dumps({**run, key: wrong}).encode())
                with self.subTest(key=key), self.assertRaises(ValueError):
                    ci_release.baseline_run('123')
            network.return_value.open.return_value = io.BytesIO(json.dumps(run).encode())
            self.assertEqual(ci_release.baseline_run('123')['head_sha'], COMMIT)
            request = network.return_value.open.call_args.args[0]
            self.assertEqual(request.full_url, f'https://api.github.com/repos/{ci_release.SOURCE_REPOSITORY}/actions/runs/123')

    def test_complete_bundle_contains_matching_source_without_private_evidence_or_data(self):
        with TemporaryDirectory() as directory:
            plan = fixture(directory)
            self.assertEqual(len(publisher.validate_bundle(plan, publication=True)['assets']), 14)
            with zipfile.ZipFile(plan.parent / f'MSH_Source_v{VERSION}.zip') as archive:
                self.assertEqual(set(archive.namelist()), {'LICENSE', 'README.md', 'THIRD_PARTY_NOTICES.md', 'MSH-source-manifest.json'})

    def test_candidates_cannot_be_published_even_with_complete_synthetic_acceptance(self):
        with TemporaryDirectory() as directory:
            plan = fixture(directory, candidate=True)
            publisher.validate_bundle(plan, publication=False)
            with self.assertRaisesRegex(ValueError, 'candidate'):
                publisher.validate_bundle(plan, publication=True)

    def test_incomplete_and_wrong_commit_acceptance_are_rejected(self):
        for name in bundle.CHECKS:
            record = acceptance()
            record['checks'][name]['status'] = 'pending'
            with self.subTest(name=name), self.assertRaises(ValueError):
                bundle.validate_acceptance(record, VERSION, COMMIT)
        with self.assertRaises(ValueError):
            bundle.validate_acceptance(acceptance(), VERSION, 'c' * 40)
        with TemporaryDirectory() as directory, patch.object(bundle, 'git', return_value='dirty'):
            with self.assertRaises(ValueError):
                bundle.formal_source_check(Path(directory), VERSION, acceptance())

    def test_changed_installer_checksum_pointer_and_foreign_destination_fail_before_network(self):
        for change in ('installer', 'pointer', 'repository', 'sidecar'):
            with self.subTest(change=change), TemporaryDirectory() as directory:
                path = fixture(directory)
                plan = bundle.load_json(path)
                if change == 'installer':
                    (path.parent / plan['assets'][0]['name']).write_bytes(b'MZtampered')
                elif change == 'pointer':
                    plan['update']['sha256'] = 'f' * 64
                    write_json(path, plan)
                elif change == 'repository':
                    plan['repository'] = 'other/repo'
                    write_json(path, plan)
                else:
                    filename = plan['assets'][0]['name'] + '.sha256'
                    (path.parent / filename).write_text('f' * 64 + ' *wrong.exe\n', encoding='ascii')
                    rewrite_plan_asset(path, filename)
                with self.assertRaises(ValueError):
                    publisher.validate_bundle(path, publication=True)

    def test_source_tampering_cannot_be_hidden_by_updating_the_outer_zip_checksum(self):
        with TemporaryDirectory() as directory:
            plan = fixture(directory)
            name = f'MSH_Source_v{VERSION}.zip'
            with zipfile.ZipFile(plan.parent / name, 'a') as archive:
                archive.writestr('secret.env', 'synthetic secret fixture')
            checksum = plan.parent / (name + '.sha256')
            checksum.write_text(f'{bundle.sha256(plan.parent / name)} *{name}\n', encoding='ascii')
            rewrite_plan_asset(plan, name)
            rewrite_plan_asset(plan, name + '.sha256')
            with self.assertRaises(ValueError):
                publisher.validate_bundle(plan, publication=True)

    def test_path_allowlist_and_credential_redirects(self):
        for name in ('', '../a.py', 'C:/a.py', '/a.py', 'a\\b.py', './a.py', 'release/acceptance.json', '.git/config'):
            self.assertFalse(bundle.public_source_file(name), name)
        with self.assertRaises(RuntimeError):
            publisher.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://evil.example')
        for url in ('https://baslerweb.com.evil.example/a.exe', 'http://baslerweb.com/a.exe', 'https://user:password@baslerweb.com/a.exe'):
            with self.assertRaises(ValueError):
                ci_release.validate_basler_url(url)


class PublicationTests(unittest.TestCase):
    def test_assets_are_verified_publicly_before_pointer_write_and_retry_is_idempotent(self):
        with TemporaryDirectory() as directory:
            plan = fixture(directory)
            client = FakeClient()
            self.assertEqual(publisher.publish(plan, client)['status'], 'published-and-verified')
            kinds = [method for method, _, _ in client.calls]
            self.assertLess(max(i for i, value in enumerate(kinds) if value == 'ANONYMOUS'), kinds.index('PUT'))
            self.assertEqual(kinds.count('UPLOAD'), 14)
            client.calls.clear()
            self.assertEqual(publisher.publish(plan, client)['status'], 'already-published-and-verified')
            self.assertFalse(any(method in ('UPLOAD', 'PUT', 'PATCH') for method, _, _ in client.calls))

    def test_upload_or_public_download_failure_never_updates_latest(self):
        for failure in ('fail_upload', 'fail_public'):
            with self.subTest(failure=failure), TemporaryDirectory() as directory:
                plan = fixture(directory)
                client = FakeClient()
                setattr(client, failure, True)
                with self.assertRaises((publisher.APIError, ValueError)):
                    publisher.publish(plan, client)
                self.assertIsNone(client.latest)
                self.assertFalse(any(method == 'PUT' for method, _, _ in client.calls))

    def test_mismatched_existing_assets_are_preserved_without_upload_or_delete(self):
        with TemporaryDirectory() as directory:
            plan = fixture(directory)
            client = FakeClient()
            client.release = {'id': 12, 'tag_name': 'v' + VERSION, 'draft': True}
            client.assets = [{'name': bundle.load_json(plan)['assets'][0]['name'], 'size': 1, 'state': 'uploaded', 'digest': 'sha256:' + 'f' * 64}]
            with self.assertRaises(ValueError):
                publisher.publish(plan, client)
            self.assertFalse(any(method in ('UPLOAD', 'DELETE', 'PUT') for method, _, _ in client.calls))

    def test_existing_newer_pointer_and_concurrent_write_are_preserved(self):
        with TemporaryDirectory() as directory:
            plan = fixture(directory)
            client = FakeClient()
            client.latest = {**bundle.load_json(plan)['update'], 'version': '9.0.0', 'published_at': '2026-01-01T00:00:00Z'}
            with self.assertRaisesRegex(ValueError, 'downgrade'):
                publisher.publish(plan, client)
            self.assertFalse(any(method != 'GET' for method, _, _ in client.calls))
            client.latest = {**client.latest, 'version': '1.0.0'}
            client.conflict = True
            with self.assertRaises(publisher.APIError):
                publisher.publish(plan, client)
            self.assertEqual(client.latest['version'], '1.0.0')
            put = next(payload for method, _, payload in client.calls if method == 'PUT')
            self.assertEqual(put['sha'], 'old-blob')


if __name__ == '__main__':
    unittest.main()

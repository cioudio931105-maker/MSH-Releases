"""Prepare an explicit application-only delivery bundle. Never uploads anything."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from msh_distribution import is_application_file
from msh_update import RELEASE_REPOSITORY, is_newer_version
from msh_version import __version__

CHECKS = ('windows_10', 'windows_11', 'b_site_hardware', 'redistribution_and_source')
SECRET = re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|\bgh[pousr]_[A-Za-z0-9]{30,}|\bgithub_pat_[A-Za-z0-9_]{40,}|\bsk-proj-[A-Za-z0-9_-]{30,}')
MAX_ASSET_BYTES = 2 * 1024**3 - 1


def public_source_file(name: str) -> bool:
    # Acceptance evidence may contain private lab/report links; only its template is public.
    return (isinstance(name, str) and bool(name) and '\\' not in name and ':' not in name
            and PurePosixPath(name).as_posix() == name and name != 'release/acceptance.json'
            and is_application_file(name))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def git(root: Path, *arguments: str) -> str:
    return subprocess.check_output(['git', '-C', str(root), *arguments]).decode('utf-8')


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(value, dict):
        raise ValueError('Expected a JSON object')
    return value


def validate_acceptance(record: dict, version: str, commit: str) -> None:
    if record.get('schema_version') != 1 or record.get('version') != version or record.get('source_commit') != commit:
        raise ValueError('Acceptance record does not match this exact version/source commit')
    for name in CHECKS:
        check = record.get('checks', {}).get(name, {})
        evidence = str(check.get('evidence', '')).strip()
        if check.get('status') != 'passed' or not evidence or evidence.upper().startswith(('TODO', 'REPLACE', 'PENDING')):
            raise ValueError(f'Release acceptance is incomplete: {name}')


def formal_source_check(root: Path, version: str, acceptance: dict) -> str:
    if not re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)', version):
        raise ValueError('Public delivery requires a stable version; dev/candidate builds remain private')
    commit = git(root, 'rev-parse', 'HEAD').strip()
    if git(root, 'status', '--porcelain').strip():
        raise ValueError('Formal delivery requires a clean source tree')
    if git(root, 'rev-parse', f'v{version}^{{commit}}').strip() != commit:
        raise ValueError('Release tag does not match source HEAD')
    validate_acceptance(acceptance, version, commit)
    return commit


def source_archive(root: Path, target: Path, version: str, commit: str) -> dict:
    """Export reviewed working files, never Git history or external research trees."""
    names = git(root, 'ls-files', '-z', '--cached', '--others', '--exclude-standard').split('\0')
    inventory = {}
    with zipfile.ZipFile(target, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(set(filter(None, names))):
            if not public_source_file(name):
                continue
            source = root / name
            if source.is_symlink() or not source.is_file() or not source.resolve().is_relative_to(root.resolve()):
                raise ValueError(f'Unsafe source-export input: {name}')
            content = source.read_bytes()
            if SECRET.search(content):
                raise ValueError(f'Secret candidate in source export: {name}')
            archive.writestr(name, content)
            inventory[name] = hashlib.sha256(content).hexdigest()
        manifest = dict(schema_version=1, version=version, source_commit=commit, files=inventory)
        archive.writestr('MSH-source-manifest.json', json.dumps(manifest, indent=2) + '\n')
    if not inventory or 'LICENSE' not in inventory:
        raise ValueError('Source delivery lacks required application/license inputs')
    return manifest


def prepare(root: Path, release_dir: Path, output: Path, *, candidate: bool,
            acceptance: dict | None = None, notes: str = '') -> Path:
    version = __version__
    # Also reject invalid versions in private previews, without requesting any network access.
    is_newer_version(version, '0.0.0')
    commit = git(root, 'rev-parse', 'HEAD').strip()
    if not candidate:
        commit = formal_source_check(root, version, acceptance or {})
    if output.exists():
        raise FileExistsError('Refusing to overwrite an existing delivery bundle')
    mode = 'candidate' if candidate else 'release'
    manifests = {}
    installers = {}
    expected_hashes = None
    expected_application_hashes = None
    for runtime in ('cpu', 'gpu', 'online'):
        suffix = runtime.upper() + ('_CANDIDATE' if candidate else '')
        path = release_dir / f'MSH_Setup_v{version}_{suffix}.exe'
        manifest = load_json(Path(str(path) + '.build-manifest.json'))
        if (manifest.get('version') != version or manifest.get('runtime') != runtime
                or manifest.get('build_mode') != mode or manifest.get('git_commit') != commit
                or manifest.get('model_distribution') != 'user-supplied'
                or manifest.get('bundled_models') != [] or manifest.get('bundled_research_data') is not False):
            raise ValueError(f'{runtime} package identity/policy mismatch')
        hashes = manifest.get('source_sha256', {})
        if not hashes or (expected_hashes is not None and hashes != expected_hashes):
            raise ValueError('Packages use different source snapshots')
        expected_hashes = hashes
        application_hashes = manifest.get('application_source_sha256', {})
        if not application_hashes or (expected_application_hashes is not None and application_hashes != expected_application_hashes):
            raise ValueError('Packages lack a matching complete source inventory')
        expected_application_hashes = application_hashes
        for relative, digest in application_hashes.items():
            if not is_application_file(relative) or sha256(root / relative) != digest:
                raise ValueError(f'Application source changed: {relative}')
        for relative, digest in hashes.items():
            actual_name = 'msh_app/' + relative if relative.startswith('hardware/') else relative
            if sha256(root / actual_name) != digest:
                raise ValueError(f'Package source has changed: {actual_name}')
        if not candidate and manifest.get('git_worktree_dirty', False):
            raise ValueError('Public package contains dirty-source evidence')
        if not 0 < path.stat().st_size <= MAX_ASSET_BYTES:
            raise ValueError('Package exceeds the GitHub release asset size limit')
        actual = sha256(path)
        if actual != Path(str(path) + '.sha256').read_text(encoding='ascii').split()[0].lower():
            raise ValueError(f'{runtime} installer checksum mismatch')
        if runtime == 'online' and actual != manifest.get('installer_sha256'):
            raise ValueError('Online installer identity mismatch')
        manifests[runtime] = manifest
        installers[runtime] = path
    online = manifests['online']
    for runtime in ('cpu', 'gpu'):
        entry = online.get('packages', {}).get(runtime, {})
        expected_url = f'https://github.com/{RELEASE_REPOSITORY}/releases/download/v{version}/{installers[runtime].name}'
        if entry.get('url') != expected_url or entry.get('sha256') != sha256(installers[runtime]):
            raise ValueError('Online installer points at the wrong repository/package')
    if not candidate and not online.get('basler_prerequisite'):
        raise ValueError('Reviewed Basler prerequisite identity is missing')
    if SECRET.search(notes.encode('utf-8')):
        raise ValueError('Secret candidate in release notes')
    output.mkdir(parents=True)
    assets = []

    def register(path: Path) -> None:
        if path.is_symlink() or not 0 < path.stat().st_size <= MAX_ASSET_BYTES:
            raise ValueError('Unsafe or oversized delivery asset')
        assets.append(dict(name=path.name, sha256=sha256(path), size_bytes=path.stat().st_size))

    for installer in installers.values():
        for source in (installer, Path(str(installer) + '.sha256'), Path(str(installer) + '.build-manifest.json')):
            target = output / source.name
            shutil.copy2(source, target)
            register(target)
    source_zip = output / f'MSH_Source_v{version}.zip'
    exported = source_archive(root, source_zip, version, commit)
    if exported['files'] != {name: digest for name, digest in expected_application_hashes.items() if public_source_file(name)}:
        raise ValueError('Source archive differs from the packaged application source inventory')
    register(source_zip)
    source_checksum = Path(str(source_zip) + '.sha256')
    source_checksum.write_text(f'{sha256(source_zip)} *{source_zip.name}\n', encoding='ascii')
    register(source_checksum)
    notes_file = output / 'RELEASE_NOTES.md'
    notes_file.write_text(notes or f'MSH v{version}\n\nApplication-only delivery. See the bundled notices and installation guide.\n', encoding='utf-8')
    register(notes_file)
    for name in ('LICENSE', 'THIRD_PARTY_NOTICES.md'):
        target = output / name
        shutil.copy2(root / name, target)
        register(target)
    installer = installers['online']
    update = dict(schema_version=1, version=version, release_name=f'MSH v{version}',
                  release_notes=notes or 'MSH application update.',
                  download_url=f'https://github.com/{RELEASE_REPOSITORY}/releases/download/v{version}/{installer.name}',
                  release_page_url=f'https://github.com/{RELEASE_REPOSITORY}/releases/tag/v{version}',
                  sha256=sha256(installer), size_bytes=installer.stat().st_size)
    plan = dict(schema_version=1, version=version, source_commit=commit, repository=RELEASE_REPOSITORY,
                publishable=not candidate, acceptance=acceptance if not candidate else None,
                assets=assets, update=update)
    path = output / 'release-plan.json'
    path.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return path

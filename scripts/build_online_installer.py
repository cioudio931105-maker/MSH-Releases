"""Build a hash-pinned Inno bootstrapper from reviewed CPU/GPU package installers.

No downloads, system installs, Git changes or publication are performed here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from msh_update import RELEASE_REPOSITORY, validate_installer_url
from msh_version import __version__


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_package(path: Path, runtime: str, candidate: bool) -> dict:
    manifest = json.loads(Path(str(path) + '.build-manifest.json').read_text(encoding='utf-8-sig'))
    expected_mode = 'candidate' if candidate else 'release'
    if (manifest.get('version') != __version__ or manifest.get('runtime') != runtime
            or manifest.get('build_mode') != expected_mode
            or manifest.get('model_distribution') != 'user-supplied'
            or manifest.get('bundled_models') != [] or manifest.get('bundled_research_data') is not False):
        raise ValueError(f'{runtime} package manifest does not match the requested version/runtime/policy/mode')
    if not candidate and manifest.get('git_worktree_dirty') is not False:
        raise ValueError('Formal package must have clean source evidence')
    actual = sha256(path)
    sidecar = Path(str(path) + '.sha256').read_text(encoding='ascii').split()[0].lower()
    if actual != sidecar:
        raise ValueError(f'{runtime} installer checksum mismatch')
    # Only filenames created by the normal build script are accepted.
    suffix = runtime.upper() + ('_CANDIDATE' if candidate else '')
    if path.name != f'MSH_Setup_v{__version__}_{suffix}.exe':
        raise ValueError('Unexpected package filename')
    return {'path': path, 'sha256': actual, 'manifest': manifest}


def pascal_define(name: str, value: str) -> str:
    if any(character in value for character in ('"', "'", '\n', '\r')):
        raise ValueError(f'Unsafe preprocessor value: {name}')
    return f'#define {name} "{value}"\n'


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cpu', type=Path, required=True)
    parser.add_argument('--gpu', type=Path, required=True)
    parser.add_argument('--candidate', action='store_true')
    parser.add_argument('--iscc', type=Path)
    parser.add_argument('--pylon-installer', type=Path)
    parser.add_argument('--pylon-url')
    parser.add_argument('--pylon-license-reviewed', action='store_true')
    args = parser.parse_args(argv)
    cpu = inspect_package(args.cpu.resolve(), 'cpu', args.candidate)
    gpu = inspect_package(args.gpu.resolve(), 'gpu', args.candidate)
    if (cpu['manifest'].get('git_commit') != gpu['manifest'].get('git_commit')
            or cpu['manifest'].get('source_sha256') != gpu['manifest'].get('source_sha256')
            or cpu['manifest'].get('application_source_sha256') != gpu['manifest'].get('application_source_sha256')):
        raise ValueError('CPU/GPU packages must use the same source revision and source hashes')
    for relative in ('installer/MSH_Online.iss', 'scripts/build_online_installer.py', 'msh_update.py'):
        if cpu['manifest']['source_sha256'].get(relative) != sha256(ROOT / relative):
            raise ValueError(f'Online bootstrap source changed since package build: {relative}')
    pylon = None
    if args.pylon_installer or args.pylon_url:
        parsed = urlparse(args.pylon_url or '')
        if (not args.pylon_installer or parsed.scheme != 'https'
                or not (parsed.hostname == 'baslerweb.com' or (parsed.hostname or '').endswith('.baslerweb.com'))
                or parsed.username or parsed.password or parsed.port not in (None, 443)
                or not args.pylon_license_reviewed):
            raise ValueError('Basler deployment needs a local reviewed installer, official HTTPS URL and license review')
        pylon = {'url': args.pylon_url, 'sha256': sha256(args.pylon_installer)}
    if not args.candidate and pylon is None:
        raise ValueError('Formal online release requires a reviewed, pinned Basler USB prerequisite installer')
    output = ROOT / 'dist' / 'release' / f'v{__version__}'
    output.mkdir(parents=True, exist_ok=True)
    name = f'MSH_Setup_v{__version__}_ONLINE' + ('_CANDIDATE' if args.candidate else '')
    installer = output / f'{name}.exe'
    if installer.exists():
        raise FileExistsError(f'Refusing to overwrite {installer}')
    iscc = args.iscc or shutil.which('ISCC.exe') or Path(r'C:\Program Files (x86)\Inno Setup 6\ISCC.exe')
    if not Path(iscc).is_file():
        raise FileNotFoundError('Inno Setup 6 compiler is required on the build machine')
    urls = {kind: f'https://github.com/{RELEASE_REPOSITORY}/releases/download/v{__version__}/{package["path"].name}'
            for kind, package in (('cpu', cpu), ('gpu', gpu))}
    for url in urls.values():
        validate_installer_url(url)
    defines = {'MyAppVersion': __version__, 'MyOutputDir': str(output), 'MyOutputName': name,
               'CpuUrl': urls['cpu'], 'CpuSha256': cpu['sha256'],
               'GpuUrl': urls['gpu'], 'GpuSha256': gpu['sha256']}
    if pylon:
        defines.update(PylonUrl=pylon['url'], PylonSha256=pylon['sha256'])
    staging = ROOT / 'build' / 'online'
    staging.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=staging) as temp:
        config = Path(temp) / 'payload.iss'
        config.write_text(''.join(pascal_define(key, value) for key, value in defines.items()), encoding='utf-8-sig')
        subprocess.run([str(iscc), f'/DPayloadConfig={config}', str(ROOT / 'installer/MSH_Online.iss')], check=True)
    digest = sha256(installer)
    Path(str(installer) + '.sha256').write_text(f'{digest} *{installer.name}\n', encoding='ascii')
    evidence = {'schema_version': 1, 'version': __version__, 'build_mode': 'candidate' if args.candidate else 'release',
                'runtime': 'online', 'git_commit': cpu['manifest']['git_commit'],
                'source_sha256': cpu['manifest']['source_sha256'],
                'application_source_sha256': cpu['manifest'].get('application_source_sha256', {}),
                'installer_sha256': digest, 'basler_prerequisite': pylon,
                'packages': {kind: {'url': urls[kind], 'sha256': package['sha256']}
                             for kind, package in (('cpu', cpu), ('gpu', gpu))},
                'model_distribution': 'user-supplied', 'bundled_models': [], 'bundled_research_data': False}
    Path(str(installer) + '.build-manifest.json').write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8')
    print(installer)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

"""One local entry for build, software validation, bundle preparation and release preflight."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from msh_version import __version__
from scripts.build_online_installer import main as build_online
from scripts.release_bundle import formal_source_check, git, load_json, prepare


def preflight(candidate: bool, record: Path | None):
    if not candidate:
        if record is None:
            raise ValueError('Formal release needs the reviewed acceptance record')
        formal_source_check(ROOT, __version__, load_json(record))


def package(runtime: str, python: Path, candidate: bool):
    arguments = ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                 str(ROOT / 'scripts/build_release.ps1'), '-Runtime', runtime,
                 '-PythonPath', str(python.resolve()), '-SkipLocalPayloadCopy']
    if candidate:
        arguments.append('-Candidate')
    logs = ROOT / 'build/release-logs'
    logs.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ)
    # pwsh's module search path is incompatible with Windows PowerShell 5.1.
    environment['PSModulePath'] = str(Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/Modules')
    with (logs / f'{__version__}-{runtime}.log').open('w', encoding='utf-8') as output:
        result = subprocess.run(arguments, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT, env=environment)
    if result.returncode:
        raise RuntimeError(f'{runtime} build failed; see its private build/release-logs output')


def assemble(candidate: bool, record: Path | None, output: Path, notes: Path | None,
             pylon_installer: Path | None, pylon_url: str | None, license_reviewed: bool):
    preflight(candidate, record)
    release_dir = ROOT / 'dist/release' / f'v{__version__}'
    suffix = '_CANDIDATE' if candidate else ''
    args = ['--cpu', str(release_dir / f'MSH_Setup_v{__version__}_CPU{suffix}.exe'),
            '--gpu', str(release_dir / f'MSH_Setup_v{__version__}_GPU{suffix}.exe')]
    if candidate:
        args.append('--candidate')
    if pylon_installer and pylon_url and license_reviewed:
        args.extend(['--pylon-installer', str(pylon_installer), '--pylon-url', pylon_url, '--pylon-license-reviewed'])
    build_online(args)
    return prepare(ROOT, release_dir, output, candidate=candidate,
                   acceptance=load_json(record) if record else None,
                   notes=notes.read_text(encoding='utf-8') if notes else '')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('preflight', 'package', 'assemble', 'build'))
    parser.add_argument('--candidate', action='store_true', help='Private build only; cannot publish')
    parser.add_argument('--runtime', choices=('cpu', 'gpu'))
    parser.add_argument('--python', type=Path, default=Path(sys.executable))
    parser.add_argument('--cpu-python', type=Path, default=ROOT / '.venv312-cpu/Scripts/python.exe')
    parser.add_argument('--gpu-python', type=Path, default=ROOT / '.venv312-release-gpu/Scripts/python.exe')
    parser.add_argument('--acceptance-record', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist/delivery' / f'v{__version__}')
    parser.add_argument('--notes', type=Path)
    parser.add_argument('--pylon-installer', type=Path)
    parser.add_argument('--pylon-url')
    parser.add_argument('--pylon-license-reviewed', action='store_true')
    args = parser.parse_args(argv)
    preflight(args.candidate, args.acceptance_record)
    if args.operation == 'preflight':
        print(json.dumps({'version': __version__, 'source_commit': git(ROOT, 'rev-parse', 'HEAD').strip(),
                          'mode': 'candidate' if args.candidate else 'release'}))
        return 0
    if args.operation == 'package':
        if not args.runtime:
            parser.error('--runtime is required for package')
        package(args.runtime, args.python, args.candidate)
        return 0
    if args.operation == 'build':
        # No tests in this suite connect cameras, ports or motors; hardware acceptance is separate.
        environment = {**os.environ, 'YOLO_CONFIG_DIR': str(ROOT / 'build/test-ultralytics')}
        subprocess.run([str(args.cpu_python), '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_*.py'],
                       cwd=ROOT, env=environment, check=True)
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(package, runtime, python, args.candidate)
                       for runtime, python in (('cpu', args.cpu_python), ('gpu', args.gpu_python))]
            for future in futures:
                future.result()
    path = assemble(args.candidate, args.acceptance_record, args.output, args.notes,
                    args.pylon_installer, args.pylon_url, args.pylon_license_reviewed)
    print(f'Delivery plan: {path}')
    print('Public release is a separate explicit publish operation after reviewing this plan.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

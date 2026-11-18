"""Small, fixed-origin helpers for the private release workflow."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.publish_release import NoRedirect, validate_bundle

SOURCE_REPOSITORY = 'cioudio931105-maker/Microscope-Scanner-Helper_MSH'
INNO_URL = 'https://github.com/jrsoftware/issrc/releases/download/is-6_7_4/innosetup-6.7.4.exe'
INNO_SHA256 = 'a549929319f9120716677c685535ca4671e4b937b5fdc87e2585f32d8eb30e8c'


class BaslerRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, url):
        validate_basler_url(url)
        return super().redirect_request(request, fp, code, message, headers, url)


def validate_basler_url(url: str):
    parsed = urlparse(url)
    if (parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in (None, 443)
            or not (parsed.hostname == 'baslerweb.com' or (parsed.hostname or '').endswith('.baslerweb.com'))):
        raise ValueError('Only reviewed official Basler HTTPS URLs are allowed')


def download(url: str, digest: str, target: Path, opener=None):
    if not re.fullmatch('[0-9a-f]{64}', digest):
        raise ValueError('A reviewed SHA-256 is required')
    if target.exists():
        raise FileExistsError('Refusing to replace a previous prerequisite download')
    target.parent.mkdir(parents=True, exist_ok=True)
    hasher = hashlib.sha256()
    size = 0
    try:
        with (opener or build_opener()).open(Request(url, headers={'User-Agent': 'MSH-Release-Builder/1'}), timeout=90) as source, target.open('xb') as output:
            for block in iter(lambda: source.read(1024 * 1024), b''):
                size += len(block)
                if size > 2 * 1024**3:
                    raise ValueError('Prerequisite exceeds the reviewed download limit')
                hasher.update(block)
                output.write(block)
        with target.open('rb') as stream:
            magic = stream.read(2)
        if hasher.hexdigest() != digest or magic != b'MZ':
            raise ValueError('Prerequisite identity/checksum mismatch')
    except Exception:
        if target.exists():
            target.unlink()
        raise


def inno():
    target = ROOT / 'build/tools/innosetup-6.7.4.exe'
    download(INNO_URL, INNO_SHA256, target)
    directory = ROOT / 'build/tools/inno'
    subprocess.run([str(target), '/CURRENTUSER', '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART',
                    '/SP-', f'/DIR={directory}'], check=True)
    if not (directory / 'ISCC.exe').is_file():
        raise ValueError('Pinned Inno Setup compiler was not installed')
    with Path(os.environ['GITHUB_PATH']).open('a', encoding='utf-8') as output:
        output.write(str(directory) + '\n')


def baseline_run(run_id: str):
    if not re.fullmatch(r'[1-9][0-9]*', run_id):
        raise ValueError('Select the successful prepare-release workflow run ID')
    token = os.environ.get('GITHUB_TOKEN', '')
    if not token or os.environ.get('GITHUB_REPOSITORY') != SOURCE_REPOSITORY:
        raise ValueError('Expected the private source repository Actions context')
    request = Request(f'https://api.github.com/repos/{SOURCE_REPOSITORY}/actions/runs/{run_id}',
                      headers={'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json',
                               'X-GitHub-Api-Version': '2026-03-10', 'User-Agent': 'MSH-Artifact-Review/1'})
    with build_opener(NoRedirect()).open(request, timeout=60) as response:
        run = json.load(response)
    if (run.get('conclusion') != 'success' or run.get('event') != 'workflow_dispatch'
            or run.get('head_branch') != 'main' or run.get('path') != '.github/workflows/release.yml'
            or run.get('repository', {}).get('full_name') != SOURCE_REPOSITORY):
        raise ValueError('Only a successful main release workflow can supply a reviewed delivery')
    return run


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('inno', 'pylon', 'review-run', 'verify-run'))
    parser.add_argument('--run-id', default='')
    parser.add_argument('--plan', type=Path)
    args = parser.parse_args(argv)
    if args.operation == 'inno':
        inno()
    elif args.operation == 'pylon':
        url = os.environ.get('MSH_PYLON_URL', '')
        digest = os.environ.get('MSH_PYLON_SHA256', '')
        if not url and not digest:
            return 0
        validate_basler_url(url)
        download(url, digest, ROOT / 'build/prerequisites/Basler_Runtime_Setup.exe', build_opener(BaslerRedirect()))
    else:
        run = baseline_run(args.run_id)
        if args.operation == 'verify-run':
            plan = validate_bundle(args.plan, publication=True)
            if plan['source_commit'] != run['head_sha']:
                raise ValueError('Prepared artifact was not built from the selected main workflow source')
        print('Prepared workflow source and delivery identity verified.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

"""Publish an explicit verified bundle to MSH-Releases; dry-run is the default."""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import sys
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import HTTPRedirectHandler, Request, build_opener
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from msh_distribution import is_application_file
from msh_update import RELEASE_REPOSITORY, _ReleaseRedirectHandler, is_newer_version, parse_update_manifest
from scripts.release_bundle import MAX_ASSET_BYTES, SECRET, load_json, public_source_file, sha256, validate_acceptance


class APIError(RuntimeError):
    def __init__(self, status: int):
        self.status = status
        super().__init__(f'GitHub API returned HTTP {status}; no credentials are included in this error')


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise RuntimeError('Authenticated GitHub API redirects are not allowed')


class GitHubClient:
    def __init__(self, token: str):
        if not token:
            raise ValueError('Set MSH_RELEASE_TOKEN in the release environment; never put it in source or chat')
        self.token = token
        self.prefix = f'/repos/{RELEASE_REPOSITORY}'

    def headers(self):
        return {'Authorization': f'Bearer {self.token}', 'Accept': 'application/vnd.github+json',
                'X-GitHub-Api-Version': '2026-03-10', 'User-Agent': 'MSH-Release-Publisher/1'}

    def request(self, method: str, suffix: str, payload=None):
        if method not in {'GET', 'POST', 'PATCH', 'PUT'} or not suffix.startswith('/') and suffix:
            raise ValueError('Invalid release API operation')
        body = json.dumps(payload).encode() if payload is not None else None
        headers = self.headers()
        if body is not None:
            headers['Content-Type'] = 'application/json'
        request = Request('https://api.github.com' + self.prefix + suffix, data=body, headers=headers, method=method)
        try:
            with build_opener(NoRedirect()).open(request, timeout=60) as response:
                return json.load(response)
        except HTTPError as exc:
            raise APIError(exc.code) from None

    def upload(self, release_id: int, path: Path):
        if type(release_id) is not int or release_id <= 0:
            raise ValueError('Invalid release ID')
        headers = {**self.headers(), 'Content-Type': 'application/octet-stream',
                   'Content-Length': str(path.stat().st_size)}
        connection = http.client.HTTPSConnection('uploads.github.com', timeout=180)
        try:
            # Streaming avoids holding a multi-gigabyte GPU installer in memory.
            with path.open('rb') as source:
                connection.request('POST', self.prefix + f'/releases/{release_id}/assets?name=' + quote(path.name, safe=''),
                                   body=source, headers=headers)
                response = connection.getresponse()
                if response.status != 201:
                    raise APIError(response.status)
                return json.loads(response.read(1024 * 1024))
        finally:
            connection.close()

    def verify_public(self, url: str, expected: dict):
        prefix = f'https://github.com/{RELEASE_REPOSITORY}/releases/download/'
        if not url.startswith(prefix):
            raise ValueError('Invalid anonymous download origin')
        # No token or authenticated headers are sent to download/CDN hosts.
        digest = hashlib.sha256()
        count = 0
        with build_opener(_ReleaseRedirectHandler()).open(Request(url, headers={'User-Agent': 'MSH-Release-Verification/1'}), timeout=90) as response:
            for block in iter(lambda: response.read(1024 * 1024), b''):
                count += len(block)
                if count > expected['size_bytes']:
                    raise ValueError('Public asset exceeds its planned size')
                digest.update(block)
        if count != expected['size_bytes'] or digest.hexdigest() != expected['sha256']:
            raise ValueError('Anonymous public download differs from the reviewed asset')


def validate_bundle(plan_path: Path, *, publication: bool) -> dict:
    plan = load_json(plan_path)
    version = plan.get('version', '')
    if plan.get('schema_version') != 1 or plan.get('repository') != RELEASE_REPOSITORY:
        raise ValueError('Wrong release plan schema/destination')
    if not re.fullmatch(r'[0-9a-f]{40}', plan.get('source_commit', '')) or type(plan.get('publishable')) is not bool:
        raise ValueError('Invalid source identity/publication mode')
    is_newer_version(version, '0.0.0')
    if publication:
        if plan.get('publishable') is not True or not re.fullmatch(r'\d+\.\d+\.\d+', version):
            raise ValueError('Internal candidate/dev bundles cannot be published')
        validate_acceptance(plan.get('acceptance') or {}, version, plan.get('source_commit', ''))
    suffix = '' if plan.get('publishable') else '_CANDIDATE'
    allowed = {'LICENSE', 'THIRD_PARTY_NOTICES.md', 'RELEASE_NOTES.md', f'MSH_Source_v{version}.zip', f'MSH_Source_v{version}.zip.sha256'}
    for runtime in ('CPU', 'GPU', 'ONLINE'):
        name = f'MSH_Setup_v{version}_{runtime}{suffix}.exe'
        allowed.update((name, name + '.sha256', name + '.build-manifest.json'))
    names = [entry.get('name') for entry in plan.get('assets', [])]
    if len(names) != len(set(names)) or set(names) != allowed:
        raise ValueError('Delivery contains missing, duplicate or unapproved asset names')
    for entry in plan['assets']:
        path = plan_path.parent / entry['name']
        if path.is_symlink() or not path.is_file() or Path(entry['name']).name != entry['name']:
            raise ValueError('Unsafe delivery path')
        if (not 0 < entry['size_bytes'] <= MAX_ASSET_BYTES or path.stat().st_size != entry['size_bytes']
                or sha256(path) != entry['sha256']):
            raise ValueError(f'Delivery hash/size changed: {entry["name"]}')
        if path.suffix in {'.md', '.json', '.sha256'} and SECRET.search(path.read_bytes()):
            raise ValueError('Secret candidate in delivery metadata')
    for name in names:
        if name.endswith(('.exe', '.zip')):
            sidecar = (plan_path.parent / (name + '.sha256')).read_text(encoding='ascii').split()
            if sidecar != [sha256(plan_path.parent / name), '*' + name]:
                raise ValueError('Checksum sidecar differs from the delivery asset')
    with zipfile.ZipFile(plan_path.parent / f'MSH_Source_v{version}.zip') as archive:
        if sum(item.file_size for item in archive.infolist()) > 256 * 1024**2:
            raise ValueError('Source archive is unexpectedly large')
        members = [item.filename for item in archive.infolist()]
        if len(members) != len(set(members)) or 'MSH-source-manifest.json' not in members:
            raise ValueError('Missing or duplicate source inventory')
        inventory = json.loads(archive.read('MSH-source-manifest.json'))
        if (inventory.get('schema_version') != 1 or inventory.get('version') != version
                or inventory.get('source_commit') != plan['source_commit']
                or set(members) != set(inventory.get('files', {})) | {'MSH-source-manifest.json'}):
            raise ValueError('Source inventory identity/membership mismatch')
        for item in archive.infolist():
            if item.filename != 'MSH-source-manifest.json' and not public_source_file(item.filename):
                raise ValueError('Unapproved content in source archive')
            content = archive.read(item)
            if (item.external_attr >> 16) & 0o170000 == 0o120000 or SECRET.search(content):
                raise ValueError('Unsafe source archive member')
            if item.filename != 'MSH-source-manifest.json' and hashlib.sha256(content).hexdigest() != inventory['files'][item.filename]:
                raise ValueError('Source member checksum mismatch')
    manifests = {}
    source_hashes = None
    for runtime in ('cpu', 'gpu', 'online'):
        filename = f'MSH_Setup_v{version}_{runtime.upper()}{suffix}.exe'
        manifest = load_json(plan_path.parent / (filename + '.build-manifest.json'))
        if (manifest.get('version') != version or manifest.get('runtime') != runtime
                or manifest.get('git_commit') != plan['source_commit']
                or manifest.get('build_mode') != ('release' if plan.get('publishable') else 'candidate')
                or manifest.get('model_distribution') != 'user-supplied'
                or manifest.get('bundled_models') != [] or manifest.get('bundled_research_data') is not False):
            raise ValueError('Package provenance differs from release plan')
        hashes = manifest.get('source_sha256', {})
        full = manifest.get('application_source_sha256', {})
        if (not hashes or not full or (source_hashes is not None and source_hashes != hashes)
                or {name: digest for name, digest in full.items() if public_source_file(name)} != inventory['files']):
            raise ValueError('Package/source archive snapshots differ')
        for relative, digest in hashes.items():
            name = 'msh_app/' + relative if relative.startswith('hardware/') else relative
            if inventory['files'].get(name) != digest:
                raise ValueError('Critical packaged source differs from source delivery')
        if publication and manifest.get('git_worktree_dirty', False):
            raise ValueError('Public package was built from dirty sources')
        source_hashes = hashes
        manifests[runtime] = manifest
    lookup = {entry['name']: entry for entry in plan['assets']}
    online_name = f'MSH_Setup_v{version}_ONLINE{suffix}.exe'
    base_url = f'https://github.com/{RELEASE_REPOSITORY}/releases/download/v{version}/'
    update = plan.get('update', {})
    if (update.get('version') != version or update.get('download_url') != base_url + online_name
            or update.get('release_page_url') != f'https://github.com/{RELEASE_REPOSITORY}/releases/tag/v{version}'
            or any(update.get(key) != lookup[online_name][key] for key in ('sha256', 'size_bytes'))
            or manifests['online'].get('installer_sha256') != lookup[online_name]['sha256']):
        raise ValueError('Update pointer differs from the reviewed online installer')
    parse_update_manifest({**update, 'published_at': '2000-01-01T00:00:00Z'})
    for runtime in ('cpu', 'gpu'):
        name = f'MSH_Setup_v{version}_{runtime.upper()}{suffix}.exe'
        if manifests['online'].get('packages', {}).get(runtime) != {'url': base_url + name, 'sha256': lookup[name]['sha256']}:
            raise ValueError('Bootstrapper package download differs from the reviewed asset')
    if publication and not manifests['online'].get('basler_prerequisite'):
        raise ValueError('Reviewed Basler prerequisite is missing')
    return plan


def check_remote_asset(remote: dict, expected: dict):
    if (remote.get('name') != expected['name'] or remote.get('size') != expected['size_bytes']
            or remote.get('state') != 'uploaded' or remote.get('digest') != 'sha256:' + expected['sha256']):
        raise ValueError('Existing/uploaded GitHub asset differs; refusing to replace or delete it')


def publish(plan_path: Path, client: GitHubClient) -> dict:
    plan = validate_bundle(plan_path, publication=True)
    repo = client.request('GET', '')
    if (repo.get('full_name', '').lower() != RELEASE_REPOSITORY.lower() or repo.get('private') is not False
            or repo.get('default_branch') != 'main' or repo.get('archived')):
        raise ValueError('Release repository identity/visibility/default branch mismatch')
    previous = None
    old_blob = None
    try:
        current = client.request('GET', '/contents/latest.json?ref=main')
        old_blob = current['sha']
        previous = parse_update_manifest(json.loads(base64.b64decode(current['content'])))
        if not is_newer_version(plan['version'], previous.version):
            if plan['version'] != previous.version or plan['update']['sha256'] != previous.sha256:
                raise ValueError('Refusing to overwrite, replace or downgrade the existing update pointer')
    except APIError as exc:
        if exc.status != 404:
            raise
    tag = 'v' + plan['version']
    try:
        release = client.request('GET', '/releases/tags/' + tag)
    except APIError as exc:
        if exc.status != 404:
            raise
        release = client.request('POST', '/releases', {'tag_name': tag, 'target_commitish': 'main',
                'name': f'MSH {tag}', 'body': (plan_path.parent / 'RELEASE_NOTES.md').read_text(encoding='utf-8'),
                'draft': True, 'prerelease': False})
    if release.get('tag_name') != tag or release.get('prerelease'):
        raise ValueError('Existing release identity does not match')
    existing = {asset['name']: asset for asset in client.request('GET', f'/releases/{release["id"]}/assets?per_page=100')}
    if set(existing) - {entry['name'] for entry in plan['assets']}:
        raise ValueError('Existing release has unexpected assets; manual review required')
    for entry in plan['assets']:
        remote = existing.get(entry['name'])
        if remote is None:
            if not release.get('draft'):
                raise ValueError('Cannot add missing files to an already published release')
            remote = client.upload(release['id'], plan_path.parent / entry['name'])
        check_remote_asset(remote, entry)
    if release.get('draft'):
        release = client.request('PATCH', f'/releases/{release["id"]}', {'draft': False, 'make_latest': 'true'})
    for entry in plan['assets']:
        url = f'https://github.com/{RELEASE_REPOSITORY}/releases/download/{tag}/{entry["name"]}'
        client.verify_public(url, entry)
    if previous is not None and previous.version == plan['version']:
        return {'version': plan['version'], 'status': 'already-published-and-verified'}
    update = {**plan['update'], 'published_at': release.get('published_at') or datetime.now(timezone.utc).isoformat()}
    parse_update_manifest(update)
    encoded = base64.b64encode((json.dumps(update, ensure_ascii=False, indent=2) + '\n').encode()).decode()
    payload = {'message': f'Release MSH {tag}', 'content': encoded, 'branch': 'main'}
    if old_blob:
        payload['sha'] = old_blob
    # Conditional Contents API write is last. On conflict, preserve the existing pointer.
    client.request('PUT', '/contents/latest.json', payload)
    readback = client.request('GET', '/contents/latest.json?ref=main')
    if json.loads(base64.b64decode(readback['content'])) != update:
        raise ValueError('Update pointer readback failed; inspect and retry without overwriting assets')
    return {'version': plan['version'], 'status': 'published-and-verified'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan', type=Path)
    parser.add_argument('--publish', action='store_true')
    args = parser.parse_args(argv)
    plan = validate_bundle(args.plan.resolve(), publication=args.publish)
    if not args.publish:
        print(json.dumps({'mode': 'dry-run', 'repository': plan['repository'], 'version': plan['version'],
                          'publishable': plan['publishable'], 'assets': len(plan['assets'])}))
        return 0
    print(json.dumps(publish(args.plan.resolve(), GitHubClient(os.environ.get('MSH_RELEASE_TOKEN', '')))))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

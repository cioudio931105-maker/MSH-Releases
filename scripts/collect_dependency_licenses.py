"""Collect exact installed dependency notice texts for release review (no dependencies)."""
from __future__ import annotations

import argparse
import hashlib
from importlib import metadata
from pathlib import Path
import re


def collect(destination: Path) -> tuple[int, int]:
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite existing notices: {destination}")
    rows = []
    count = 0
    for distribution in sorted(metadata.distributions(), key=lambda d: d.metadata['Name'].lower()):
        name = distribution.metadata['Name']
        version = distribution.version
        package = re.sub(r'[^A-Za-z0-9_.+-]', '_', name)
        version_dir = re.sub(r'[^A-Za-z0-9_.+-]', '_', version)
        candidates = []
        for relative in sorted(distribution.files or [], key=str):
            if not re.match(r'^(LICEN[CS]E|COPYING|NOTICE|AUTHORS)([._-].*)?$', relative.name, re.I):
                continue
            source = Path(distribution.locate_file(relative))
            if source.is_file():
                content = source.read_bytes()
                if b'\0' not in content:
                    candidates.append((relative, content))
        for index, (relative, content) in enumerate(candidates, 1):
            # Preserve the original notice filename; uppercase the recognized prefix
            # so the narrow Git exceptions also work on case-sensitive systems.
            filename = re.sub(
                r'^(licen[cs]e|copying|notice|authors)',
                lambda m: 'LICENSE' if m[0].lower() == 'licence' else m[0].upper(),
                relative.name, flags=re.I,
            )
            path = destination / 'third_party' / package / version_dir / str(index) / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            digest = hashlib.sha256(content).hexdigest()
            rows.append(f'| {name} | {version} | `{relative.as_posix()}` | `{path.relative_to(destination).as_posix()}` | `{digest}` |')
            count += 1
        if not candidates:
            rows.append(f'| {name} | {version} | No standalone notice found in installed file inventory | — | — |')
    destination.mkdir(parents=True, exist_ok=True)
    (destination / 'README.md').write_text(
        '# Installed dependency notices — review inventory\n\n'
        'Collected from the exact local build environment. Original notice bytes and attribution are retained.\n'
        'This includes build tools and packages that may not be bundled in MSH; membership is not a runtime SBOM.\n'
        'Missing notices, native pylon deployment rights and complete corresponding-source obligations still require review.\n'
        'No model, research data, private environment state or dependency binaries are included.\n\n'
        '| Distribution | Version | Original distribution-relative path | Notice copy | SHA-256 |\n'
        '| --- | --- | --- | --- | --- |\n' + '\n'.join(rows) + '\n', encoding='utf-8')
    return count, len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    count, _ = collect(args.output.resolve())
    print(f'Collected {count} original notice texts; see {args.output / "README.md"}.')


if __name__ == '__main__':
    main()

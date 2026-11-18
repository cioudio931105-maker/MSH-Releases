"""Pin the installed dependency closure from an already tested build environment."""
from __future__ import annotations

import argparse
from importlib import metadata
from pathlib import Path
import sys

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[1]


def requirements(path: Path):
    for raw in path.read_text(encoding='utf-8-sig').splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or line.startswith('--'):
            continue
        if line.startswith('-r '):
            yield from requirements(path.parent / line[3:].strip())
        else:
            yield Requirement(line)


def generate(runtime: str, destination: Path) -> None:
    if sys.version_info[:2] != (3, 12):
        raise ValueError('Generate release locks inside the verified Python 3.12 environment')
    queue = list(requirements(ROOT / f'requirements/{runtime}.txt'))
    queue.extend(requirements(ROOT / 'requirements/build.txt'))
    queue.append(Requirement('pip'))
    environment = {**default_environment(), 'extra': ''}
    pinned = {}
    while queue:
        requirement = queue.pop()
        if requirement.marker and not requirement.marker.evaluate(environment):
            continue
        if requirement.url or requirement.extras:
            raise ValueError('Review direct-URL or extra dependencies explicitly before locking')
        name = canonicalize_name(requirement.name)
        distribution = metadata.distribution(name)
        version = distribution.version
        if requirement.specifier and not requirement.specifier.contains(version, prereleases=True):
            raise ValueError(f'Tested environment does not satisfy {requirement.name}')
        if name in pinned:
            continue
        pinned[name] = version
        queue.extend(Requirement(value) for value in distribution.requires or ())
    expected = '+cpu' if runtime == 'cpu' else '+cu124'
    if not pinned['torch'].endswith(expected):
        raise ValueError('Torch runtime does not match the requested lock')
    index = 'cpu' if runtime == 'cpu' else 'cu124'
    lines = [f'# Tested Windows x64 / Python 3.12.13 {runtime.upper()} dependency closure.',
             '# Regenerate only after validating the build environment; no environment directory is copied.',
             f'--extra-index-url https://download.pytorch.org/whl/{index}', '']
    lines.extend(f'{name}=={version}' for name, version in sorted(pinned.items()))
    destination.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f'Pinned {len(pinned)} distributions for {runtime}.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', choices=('cpu', 'gpu'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    generate(args.runtime, args.output)

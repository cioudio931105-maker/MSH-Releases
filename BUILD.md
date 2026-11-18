# MSH release build

For the complete owner/end-user lifecycle, see
[MSH 直接安裝與往後發佈流程](docs/DIRECT_INSTALL_RELEASE_WORKFLOW_zh_TW.md).

## Supported build baseline

- Windows 10 or 11, 64-bit
- Python 3.12.13 (the tested development baseline)
- PyInstaller 6 and Inno Setup 6

Use a clean, tested Python 3.12 environment. Do not build from Conda base or
rely on a developer PATH. CPU is the default public build because it works on
computers without NVIDIA CUDA. Keep CPU and GPU dependencies in separate
environments.

The source-review snapshot records the tested build environment in
`requirements-release-v0.1.4.txt`. It is an installed-version inventory, not a
guarantee of byte-identical builds. Keep the Python/Windows/toolchain baseline too.
`LICENSE`, `THIRD_PARTY_NOTICES.md` and `licenses/` are required release inputs;
the spec packages their notice texts, and the payload auditor checks them against
the source tree. To refresh notices for another environment, run
`python scripts/collect_dependency_licenses.py --output <new-directory>` and
review the result before replacing the versioned notice set.

```powershell
.\.venv312\python.exe -m venv .venv312-cpu
.\.venv312-cpu\Scripts\python.exe -m pip install -r requirements-cpu.txt -r requirements-build.txt
.\scripts\build_release.ps1 -Runtime cpu -PythonPath .\.venv312-cpu\Scripts\python.exe
```

The CPU build creates an onedir application at `dist\cpu\MSH\` and
`dist\release\v<version>\MSH_Setup_v<version>_CPU.exe` plus its SHA-256 checksum and
`MSH_Setup_v<version>_CPU.exe.build-manifest.json`. The manifest records the Git commit,
the packaged executable hash, the user-supplied-model policy, hashes of release-critical
source files, and whether the source worktree had uncommitted changes. The build always creates a new temporary PyInstaller output first; Inno
Setup never consumes a pre-existing `dist\cpu\MSH` directory. Review the manifest before
publishing and keep it next to the installer and checksum. Onedir
is intentional: PyTorch, OpenCV,
pypylon, and native DLLs are materially more reliable than a self-extracting
onefile executable.

For the optional NVIDIA/CUDA build, prepare a separate environment with
`requirements-gpu.txt`, then run:

```powershell
.\scripts\build_release.ps1 -Runtime gpu -PythonPath .\.venv312\python.exe
```

This creates `dist\gpu\MSH\` and a `_GPU.exe` installer. Both installers use
the same application identity, so installing one variant replaces/upgrades the
other rather than creating two conflicting MSH installations.

## Client review update manifest

MSH checks the public release-only manifest configured in `msh_update.py`. Do
not point client builds at a private repository and never embed a GitHub token
in the application. Start from `release/latest.example.json`, then for every
review release:

1. Build the final installer.
2. Generate its SHA-256 checksum.
3. Upload the installer and checksum to the public release-only repository.
4. Replace every example value, especially `version`, URLs, `sha256`, release
   notes, and date.
5. Publish the completed file as `latest.json` only after the installer asset is
   available at its HTTPS URL.

The updater only opens the download after user confirmation. It does not execute
the unsigned installer or replace running application files.

Do not run `ISCC.exe` directly for a release. Only `scripts\build_release.ps1` creates
the build manifest and guarantees that the installer source came from the same fresh
PyInstaller run.

## Release gates

`build_release.ps1` defaults to **release mode**: the worktree must be clean and
HEAD must carry the matching annotated release tag, such as `v0.1.4` for version
`0.1.4`. It refuses to overwrite any existing installer. Use `-Candidate` only
for internal review; it produces a separately named `_CANDIDATE.exe` and its
manifest records `build_mode: candidate`. Candidate files must never be uploaded
or referenced by `latest.json`.

For a quick packaging smoke test without Inno Setup:

```powershell
.\scripts\build_release.ps1 -Runtime cpu -PythonPath .\.venv312-cpu\Scripts\python.exe -SkipInstaller
```

## Model and hardware prerequisites

No models or research data are packaged. Building requires no WBC model.
The manifest records `model_distribution: user-supplied`, `bundled_models: []`
and `bundled_research_data: false`. First-party payloads use an allowlist;
weights and Ultralytics demo photos collected by dependency hooks are excluded.
Select your own existing local model in the GUI before recognition. See
[the distribution policy](docs/APPLICATION_ONLY_POLICY.md). Basler operation requires the official pylon
Runtime and the correct camera-interface driver on the target computer.

Audit the actual onedir payload before approving an installer:

```powershell
python scripts/audit_packaged_application.py --app-dir dist/cpu/MSH
```

For an isolated source build, also pass `--source-root` with that exact snapshot.
The audit checks resource exclusions, first-party hashes, expected resources,
nested ZIP entries, CPU/CUDA separation and executable/build-manifest identity.
This is a payload check, not clean-machine installation or hardware acceptance.

Never run motor, XY-stage, or camera-motion validation merely to test packaging.
Those tests require an authorised B-site hardware session.

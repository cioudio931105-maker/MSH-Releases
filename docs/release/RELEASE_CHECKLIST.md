# MSH release checklist

1. Set `msh_version.py` to the intended Semantic Version (`MAJOR.MINOR.PATCH`).
2. Review status, diff, requirements and third-party terms. Run `python scripts/audit_application_files.py`; source and payloads must exclude models and research data.
   For v0.1.4, resolve the native pylon/AGPL combination and outstanding source-delivery items in [the source evidence inventory](../THIRD_PARTY_SOURCE_INVENTORY_v0.1.4.md) before public binary distribution. Preserve all applicable runtime notices and place verified corresponding-source access instructions next to the binary download. A version/notice inventory alone is insufficient.
3. Run source tests and record pass/fail/not-tested results.
4. Commit the reviewed source, create the matching annotated tag `v<version>` at HEAD, and verify both locally before building.
5. Build the default CPU release with `scripts\build_release.ps1 -Runtime cpu` from a clean Python 3.12 environment. Do not invoke Inno Setup directly. The script refuses dirty sources, missing/mismatched tags, and an existing output filename.
6. For internal review only, use `-Candidate`; never upload or publish its `_CANDIDATE.exe` output.
7. Review `MSH_Setup_v<version>_CPU.exe.build-manifest.json`: `build_mode` must be `release`, its version and Git commit must be the intended release, `git_worktree_dirty` must be `false`, and its `app_exe_sha256` must match `dist\cpu\MSH\MSH.exe`.
8. Confirm manifest fields `model_distribution: user-supplied`, `bundled_models: []`, and `bundled_research_data: false`; inspect the payload. Verify no-model startup and separately supplied local-model recognition. Smoke-test `dist\cpu\MSH\MSH.exe` on a clean Windows account without Python.
9. Install and uninstall `MSH_Setup_v<version>_CPU.exe`; confirm Documents and LocalAppData user data remain.
10. Perform only authorised B-site hardware checks for Basler, COM, Arduino, XY stage, and scanning.
11. Review the generated SHA-256 file and code-sign only with a valid certificate.
12. When an HTTPS publication location has been selected, run the build with `-PublicBaseUrl`, or run `scripts\finalize_release_bundle.ps1` afterward. Confirm the bundle contains only the installer, checksum, build manifest and release notes before generating `latest.json` and `release-record.json`. The finalizer rejects candidate/dirty/model-containing manifests, extra files and existing finalized metadata; it does not inspect the installer or upload anything.
13. After publication is authorized and required acceptance is complete, upload the immutable version folder to the selected binary store. For GitHub Releases, use the already reviewed tag from step 4; do not move or recreate it. Follow the current source/notice delivery rules; do not make the historical source repository public as a shortcut.
14. Independently download the public installer and verify its SHA-256, then publish the generated `latest.json` at the storage root as the final update switch. Retain local originals/backups until their removal is separately approved; see [storage and sync](../RELEASE_STORAGE_AND_SYNC.md).
15. From the previous installed version, use **說明 > 檢查更新...**, confirm the displayed version/hash, download the new installer, and verify that overwrite installation preserves local settings and user data.

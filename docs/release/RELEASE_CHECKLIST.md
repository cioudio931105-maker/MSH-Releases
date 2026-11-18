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
12. Create the authorized GitHub Release draft for the already reviewed `v<version>` tag from step 4. Do not recreate or move an existing tag.
13. Upload the installer, `.sha256`, and `.build-manifest.json`; mark pre-release until all required smoke and hardware tests pass.
14. Copy `release/latest.example.json`, enter the exact release URLs and post-build SHA-256, validate the JSON, and publish it as `latest.json` in the public release-only repository.
15. From the previous installed version, use **說明 > 檢查更新...**, confirm the displayed version/hash, download the new installer, and verify that overwrite installation preserves local settings and user data.

# MSH release checklist

1. Set `msh_version.py` to the intended Semantic Version (`MAJOR.MINOR.PATCH`).
2. Review status, diff, requirements and third-party terms. Run `python scripts/audit_application_files.py`; source and payloads must exclude models and research data.
   For v0.1.4, resolve the native pylon/AGPL combination and outstanding source-delivery items in [the source evidence inventory](../THIRD_PARTY_SOURCE_INVENTORY_v0.1.4.md) before public binary distribution. Preserve all applicable runtime notices and place verified corresponding-source access instructions next to the binary download. A version/notice inventory alone is insufficient.
3. Run source tests and record pass/fail/not-tested results.
4. Commit the reviewed source, create the matching annotated tag `v<version>` at HEAD, and verify both locally before building.
5. Build both CPU and GPU packages; for CPU use `scripts\build_release.ps1 -Runtime cpu`, for GPU use `-Runtime gpu`, each from its own clean Python 3.12 environment. Then build the online entry using `scripts/build_online_installer.py` with both matching packages and a reviewed Basler prerequisite URL/hash. Do not invoke Inno Setup directly. Formal builds reject dirty sources, missing/mismatched tags and existing output filenames.
6. For internal review only, use `-Candidate`; never upload or publish its `_CANDIDATE.exe` output.
7. Review `MSH_Setup_v<version>_CPU.exe.build-manifest.json`: `build_mode` must be `release`, its version and Git commit must be the intended release, `git_worktree_dirty` must be `false`, and its `app_exe_sha256` must match `dist\cpu\MSH\MSH.exe`.
8. Confirm manifest fields `model_distribution: user-supplied`, `bundled_models: []`, and `bundled_research_data: false`; inspect the payload. Verify no-model startup and separately supplied local-model recognition. Smoke-test `dist\cpu\MSH\MSH.exe` on a clean Windows account without Python.
9. Install and uninstall `MSH_Setup_v<version>_CPU.exe`; confirm Documents and LocalAppData user data remain.
10. Perform only authorised B-site hardware checks for Basler, COM, Arduino, XY stage, and scanning.
11. Review the generated SHA-256 file and code-sign only with a valid certificate.
12. Record actual version/commit-matched acceptance using `release/acceptance.example.json`, including source/redistribution rights and Windows/B-site evidence. Store only a reviewed public-safe summary here; raw lab evidence and research data stay outside this public repository. Run `prepare-release` using [the automated workflow](../AUTOMATED_RELEASE_zh_TW.md); review its public delivery artifact, exact source inventory and hashes.
13. After approval, run `publish` with that successful prepared run ID. The publisher creates the public release draft, uploads only the 14 reviewed assets including application source, verifies their identity, publishes and checks anonymous access. Incomplete candidate/dev deliveries cannot be published. Never copy private history.
14. The publisher updates `MSH-Releases/main/latest.json` only after all asset checks pass, then reads it back. Develop and publish in MSH-Releases with the temporary built-in Actions token; keep the original historical repository private; do not hand-edit a pointer to an unverified installer.
15. From the previous installed version, use **說明 > 檢查更新...**, verify the one-click download/hash, normal-exit installer handoff and automatic restart, and verify that overwrite installation preserves local settings and user data. Device connections/jobs must delay installation without being forcibly stopped.

16. Use the [online acceptance checklist](../ONLINE_INSTALL_AND_UPDATE_zh_TW.md): clean Windows 10/11, NVIDIA/CPU fallback, offline and interrupted downloads, connected-device installation guards and B-site USB acceptance. Final offline delivery remains deferred.

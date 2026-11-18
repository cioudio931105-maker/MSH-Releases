# MSH release checklist

1. Set `msh_version.py` to the intended Semantic Version (`MAJOR.MINOR.PATCH`).
2. Review `git status`, diff, requirements, model provenance, and third-party terms.
3. Run source tests and record pass/fail/not-tested results.
4. Build the default CPU candidate with `scripts\build_release.ps1 -Runtime cpu` from a clean Python 3.12 environment.
5. Smoke-test `dist\cpu\MSH\MSH.exe` on a clean Windows account without Python.
6. Install and uninstall `MSH_Setup_v<version>_CPU.exe`; confirm Documents and LocalAppData user data remain.
7. Perform only authorised B-site hardware checks for Basler, COM, Arduino, XY stage, and scanning.
8. Review the generated SHA-256 file and code-sign only with a valid certificate.
9. Create Git tag `v<version>` and GitHub Release `Microscope Scanner Helper v<version>`.
10. Upload the installer and `.sha256`; mark pre-release until all required smoke and hardware tests pass.
11. Copy `release/latest.example.json`, enter the exact release URLs and post-build SHA-256, validate the JSON, and publish it as `latest.json` in the public release-only repository.
12. From the previous installed version, use **說明 > 檢查更新...**, confirm the displayed version/hash, download the new installer, and verify that overwrite installation preserves local settings and user data.

# Python dependencies

Run pip commands from the project root. Versions and package contents are unchanged by the layout move.

| File | Purpose |
|---|---|
| `base.txt` | Common application dependencies; also exposed by root `requirements.txt` |
| `cpu.txt` / `gpu.txt` | Development runtime selection; include `base.txt` relative to this directory |
| `build.txt` | Build-machine tools |
| `release-cpu.txt` / `release-gpu.txt` | Verified pinned dependency closures for release builds |

Example: `python -m pip install -r requirements/cpu.txt -r requirements/build.txt`.
The historical v0.1.4 inventory is in `docs/legacy/requirements-release-v0.1.4.txt`.
Environments remain local and ignored. No weights or research data are included.

See [local development environments](../docs/DEVELOPMENT_ENVIRONMENTS.md) for independent runtime locations and validation.

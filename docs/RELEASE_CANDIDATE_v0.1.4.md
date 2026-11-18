# MSH v0.1.4 application-only candidate validation

Status: internal candidate built; payload, same-machine install/reinstall/uninstall,
installed GUI, old-version migration and local-model smoke verified on 2026-10-19.
Frozen inference/training was exercised through an isolated test adapter, as scoped below.
Not a stable release. No commit, push, merge, tag, public Release or latest.json update.

## Deliverables

- `dist/release/v0.1.4/MSH_Setup_v0.1.4_CPU_CANDIDATE.exe`
- The adjacent `.sha256` and `.build-manifest.json` sidecars.
- Installer size: 229,093,351 bytes (about 218.5 MiB).
- SHA-256: `236bcc28e3e66b6f1828efc740fb73b21ab5b95b176422a76fb767a32d5cb388`.
- Authenticode status: `NotSigned`. Internal review only.

The installer was created with the repository build script, fresh PyInstaller
output and Inno Setup; it was copied into the normal local release archive and
all three deliverable files passed SHA-256 copy/readback verification. No previous
installer was overwritten. Do not point the public updater to this candidate.

## Source and environment

- Branch: `codex/user-supplied-models`; base HEAD `eccb6786778612b9f003cab0edb068fd509db231`.
- The actual candidate includes uncommitted changes; manifest records dirty sources
  and `build_mode: candidate`. There is no clean release tag for these changes.
- Built from 340 application-only files copied into `tmp/rc014b`; each source copy
  was SHA-256 verified. The local source snapshot inventory is
  `tmp/msh014-source-snapshot-b.json`.
- Build runtime: Python 3.12.13, PyInstaller 6.22.2, hooks-contrib 2026.6,
  torch 2.6.0+cpu, Ultralytics 8.4.123, pypylon 26.7, Inno Setup 6.
- Local build-environment metadata inventory: `tmp/msh014-cpu-dependencies.json`
  (61 distributions). This inventory is not dependency redistribution clearance.

## Checks performed

| Check | Result |
| --- | --- |
| Full suite in CPU runtime and source snapshot | 122 run: 121 passed, 1 skipped (ONNX export dependency absent) |
| Focused distribution tests after vendor exclusions | 8 passed |
| Existing-candidate collision guard | Rejected before starting build; synthetic fixture bytes unchanged |
| Actual payload audit | 4,710 files, 934,758,048 bytes; 137 first-party resources matched source SHA-256; 0 issues |
| Models/data/vendor demos | Forbidden suffixes, vendor sample data and unused OCR/data-processing plugins absent; nested ZIP names checked |
| CPU runtime | No CUDA DLLs detected by the payload audit |
| Build identity | Manifest v0.1.4, CPU, candidate, user-supplied models, empty bundled_models and bundled_research_data=false |
| Installer integrity | Sidecar checksum and final archive-copy SHA-256 match |
| Packaged GUI startup | Opened actual frozen MSH.exe without a selected model; model-selection prompt visible |
| Packaged version | About dialog displayed v0.1.4 |
| Normal close | Candidate window closed and exact candidate process path absent afterwards; no force termination |
| Runtime writes | GUI smoke did not add files under the packaged application folder |
| Older artifacts | All 20 previous release files retain original size/mtime; all v0.1.3 hashes also match |
| Local research assets | All 16 previously untracked originals still exist with unchanged SHA-256 |
| Actual installer | Installed into a dedicated test directory; Inno Setup exit 0, version 0.1.4 registration, no reboot |
| Installed payload | All 4,710 build files match SHA-256; only unins000.exe/dat added by installer; 4,712-file audit passes |
| Installed GUI | Started with developer Python removed from PATH and an isolated writable profile; no model initially; external model selection and clear work; normal exit code 0 |
| Same-version reinstall | Installer exit 0; five user-file/model retention checks pass |
| Uninstall | Exit 0; application and registration removed; initial shortcut state restored; five retention hashes unchanged |
| Actual source CPU model workflow | Local WBC checkpoint inference on a synthetic image and one training epoch on synthetic images completed; original checkpoint unchanged |
| Local-only model guards | Four missing/empty/remote inputs rejected; network connects blocked in the test Python process, with no connection attempts observed |
| Frozen model workflows, test adapter | Same candidate EXE/dependencies: production GUI ObjectDetector and core CellIdentificationDetector inferred on synthetic images; one CPU training epoch completed; input weights unchanged; exit 0 |
| Older bundled-build migration | Actual v0.1.3 install → verified complete backup → old uninstall → v0.1.4 install/audit → new uninstall; all four installer/uninstaller exits 0; user sentinel and initial shortcuts preserved |
| Clean-Windows validation kit | Six explicitly selected ZIP entries readback SHA-256 verified; no model, images, dataset or local test outputs included; test results remain blank |

The earlier onedir smoke returned a null exit code. The subsequent installed-GUI
test retained its process handle and observed exit code 0. The earlier source-mode
MSH window was left untouched; it was no longer present at installation preflight.

## Installation and model validation scope

No existing MSH uninstall registration or default installation directory was found
before testing. The existing desktop shortcut was hashed and preserved. The actual
candidate was installed at `tmp/install014`; GUI writes used a synthetic profile
under `tmp/msh014-install-user`, with developer Python removed from PATH and no
PYTHONHOME/PYTHONPATH. This remains an existing developer Windows installation,
not a clean operating system or a newly created Windows account.

The installer created a Start Menu shortcut despite `/NOICONS` and empty tasks.
The initial validation wrapper therefore exited 1 after the installer itself
succeeded with exit 0. This was a real test expectation failure, not a failed
installation. No pre-existing Start Menu shortcut was overwritten. Uninstallation
removed the new shortcut and restored the initial shortcut state; the desktop
shortcut remained byte-identical. Do not treat `/NOICONS` as suppressing every
shortcut in the current installer. No installer code was changed during validation.

Same-version overwrite installation and uninstall preserved five hashes: two
user-created files inside the test install directory (including a synthetic `.pt`
retention sentinel), synthetic Documents/AppData files, and the external existing
WBC checkpoint. Uninstallation intentionally left the two user-created install
files. The uninstaller's delayed self-removal was checked again; no executable or
packaged runtime files remain in the test install directory. This does not test
migration from an older model-bundled version or guarantee retention at all paths.

The installed GUI accepted and cleared the external checkpoint path; its status
explicitly said the model was not yet loaded. No camera preview was opened to
trigger inference. Actual inference/training was separately run with the source
CPU runtime using synthetic images only. It produced a temporary training
checkpoint without changing the supplied weights or attempting a network
connection in that test process. Detections and synthetic training metrics do not
establish model accuracy. The later adapter test below also passed frozen backend
smoke; unmodified production GUI/camera inference remains unverified.

Creating the isolated test profile initially omitted its Desktop directory, causing
a Windows file-dialog location warning. The test directory was added and the
dialog continued normally; this was a test-fixture issue. The installed launcher
also logged the expected update-manifest HTTP 404; no release was published or
updater manifest changed.

## Frozen backend and older-build migration continuation

The isolated copy at `tmp/frozen014check` started from the same 4,710-file payload,
verified before instrumentation. Its EXE and dependency files were unchanged.
Only its dynamically loaded GUI resource was replaced with a test adapter; the
original GUI resource was preserved verbatim alongside it. The adapter imported
the original GUI definitions without constructing hardware objects and invoked
the original ObjectDetector, core CellIdentificationDetector and training backend
using the external existing checkpoint and synthetic images. Both inference
paths and one CPU training epoch passed under the frozen EXE; exit code was 0.
No production source, installer or installed application was patched for this test.
This proves the scoped frozen backend, not unmodified GUI/camera acceptance or a
training feature exposed in the installed GUI.

The first adapter attempt was started before fixture preparation finished, opened
the ordinary GUI and produced no inference report. It was closed normally and is
not counted as a pass. Readiness/hash guards were added before the successful
second run. A further run traced the observed network attempt to Ultralytics
`check_det_dataset` → `check_font` → HTTP HEAD for a plotting font. Python TCP
connects were blocked; training still completed and no replacement model download
was observed. This is different from the earlier source smoke, whose existing
font cache avoided that request. Both `onnx` and `onnxruntime` are absent in the
actual frozen process: ONNX is unavailable in this CPU candidate even though
the file picker lists that extension.

Migration used the preserved v0.1.3 CPU installer with SHA-256
`79dc8cbccb6d420dfeb0668efb1cd44db091c720802c43f5805ec67fa7e59457`.
The old test EXE matched its manifest. Before removing it, all 4,897 files
(1,197,534,444 bytes, including 60 model-format resources such as vendor OCR
resources) were copied to `tmp/migrate014/old-install-backup` and individually
SHA-256 verified. The backup remains local and ignored; it is not part of any
source archive, validation kit or release. After old uninstall, the new candidate
passed its 4,713-file audit (4,710 payload files, two Inno uninstall files, one
user-created sentinel). The new test app was then uninstalled; the user-created
sentinel and original shortcut state were preserved. No old/new GUI or hardware
was operated during this migration. This validates the documented backup/remove/
install path on the current machine, not an in-place cleanup or clean Windows.

The local clean-Windows kit is
`dist/release/v0.1.4/MSH_v0.1.4_CPU_CANDIDATE_Validation_Kit.zip`
(229,106,048 bytes; SHA-256
`dd843ffccfb89c82816ae5df3848fb177eed0ab93e4e2e4557efa81bbb3ee8bf`).
It contains only the candidate installer, two sidecars, acceptance instructions,
a blank result form and a kit manifest. See
[clean-Windows instructions](CLEAN_WINDOWS_ACCEPTANCE_v0.1.4_zh_TW.md).
Creating a kit does not mean clean-Windows acceptance passed.

The dependency review was updated in `THIRD_PARTY_NOTICES.md`. It identifies
missing standalone Ultralytics/pypylon wheel license files in the current payload,
and separates wrapper notices from native pylon deployment rights. That review
and the new instructions do not retroactively change the installer. Applicable
notices and the licensing/source-disclosure decision remain required for a new
public build. No license or publication decision was made automatically.

## Build corrections

The first build failed while copying an unused Basler OCR plugin model through an
overlong Windows path; it produced no candidate installer. The successful second
build used a shorter source path and excluded vendor resources not used by MSH:
Ultralytics demo assets, Matplotlib sample datasets/photos, and Basler
pylonDataProcessingPlugins/DataProcessingPluginsB plus vendor demo documentation.
Acquisition modules/runtime files remain present. Camera behavior is unverified.

The nonfatal Conda/MKL probe warning was recorded. The actual frozen GUI started;
this is not proof that every optional inference, export or training backend works.

## Evidence kept locally, outside source Git

- `tmp/msh014-build.log` (failed first attempt).
- `tmp/msh014-build-b.log` (successful build/installer).
- `tmp/msh014-cpu-source-tests.log`.
- `tmp/msh014-payload-audit.json` (all payload-file hashes).
- `tmp/msh014-installer-verification.json` and `tmp/msh014-smoke-exit.json`.
- `tmp/msh014-existing-installer-inventory.json`.
- `tmp/msh014-installed-payload-audit.json` and `tmp/msh014-installed-exit.json`.
- `tmp/msh014-install.log`, `tmp/msh014-reinstall.log`, `tmp/msh014-uninstall.log`.
- `tmp/msh014-reinstall-verification.json`, `tmp/msh014-uninstall-verification.json`.
- `tmp/msh014-model-validation.log` and `tmp/msh014-model-validation/verification.json`.
- `tmp/msh014-validation-summary.json` (final cross-checks, retention and limitations).
- `tmp/msh014-frozen-fixture-manifest-b.json` and `tmp/msh014-frozen-fixture-manifest.json`.
- `tmp/msh014-frozen-validation-b/verification.json` and `tmp/msh014-frozen-validation-c/verification.json`, plus their exit records.
- `tmp/migrate014/backup-verification.json`, `new-payload-audit.json`, `verification.json` and installer/uninstaller logs.
- `tmp/msh014-validation-kit-verification.json` and `tmp/msh014-continuation-summary.json`.

The reusable read-only payload checker is `scripts/audit_packaged_application.py`.
Its synthetic checks accepted a clean payload and rejected a vendor model and a
modified first-party source. Source Git checks and diff review also pass.

## Not yet accepted / required before stable release

- Clean-Windows installation, launch, uninstall and data retention without
  developer Python/Git. Same-machine candidate install/reinstall/uninstall and
  v0.1.3 backup/remove/install migration now pass within the scope above.
- Unmodified production GUI/camera inference and representative-data training
  acceptance. Source and adapter-driven frozen CPU synthetic smoke now pass.
  ONNX is unavailable in this CPU candidate, pending any separately scoped support.
- Separately authorized GUI/firmware branch integration and matching deployment.
  Fixed-RPM motor and launcher-diagnostics branches were not merged automatically.
- B-site Basler/COM/Arduino/XY, STOP/RELEASE, temperature, movement and scan acceptance.
  No preview, camera open, serial connection, movement or firmware upload was done.
- Exact dependency redistribution review, signing decision, clean reviewed source
  commit/tag, authorized publication and fresh external download/update tests.
- Existing Git history and old installers still contain prior assets; only the
  new candidate payload was checked against the current application-only policy.

Keep this as a local internal candidate until these gates are resolved.

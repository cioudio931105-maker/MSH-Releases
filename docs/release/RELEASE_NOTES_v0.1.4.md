# MSH v0.1.4 application-only candidate

Internal validation candidate only. This is not a published or accepted stable
release. Do not upload the `_CANDIDATE.exe` or point `latest.json` to it.

## Changes

- Users supply their own local detection/classification models. GUI startup selects
  no model; missing files do not trigger a replacement-weight download.
- Installer and source payloads exclude model weights, microscope images, labels,
  datasets, experiment results and device-specific camera profiles.
- Recognition, classification, stitching and local training code remain in the
  project. User checkpoint weights are retained; training AMP is disabled to avoid
  downloading a separate backend probe model (potential speed/VRAM cost).
- Git exclusions and source/payload audits preserve research files locally.
- Installation/update and release instructions distinguish the direct installer
  from a developer source environment.

## Validation and release gates

See `docs/RELEASE_CANDIDATE_v0.1.4.md` for the actual build and software checks.
Source tests are not evidence of clean-machine installation, real user-model
accuracy, physical hardware behavior or firmware compatibility.

This branch does not automatically integrate the separate fixed-RPM motor or
launcher-diagnostics branches. Installed GUI/firmware matching and B-site hardware
acceptance remain pending. No hardware settings or firmware are changed here.

Candidate sources contain reviewed working-tree changes and are not a clean
tagged release. Public distribution still requires dependency-license review,
explicit source/release authorization, installation and scoped hardware acceptance.
Old Git history and previous installers are not retroactively data-free.

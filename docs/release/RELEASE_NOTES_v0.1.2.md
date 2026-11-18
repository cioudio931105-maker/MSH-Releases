# MSH v0.1.2 Client Review Update (unpublished)

## Changes in this build

- The live camera preview is embedded in the MSH GUI.
- Manual motor controls use the existing fixed low-speed settings from the
  current source branch.
- Updated MSH microscope and scanner-ring icon assets are included.
- The desktop-shortcut option is selected by default in the installer.

## Verification status

- This package is built from the current `codex/client-update-check` branch.
- Software tests and packaging checks are recorded with the build result.
- No Basler, COM, Arduino, XY-stage, motor, or scanning hardware test is
  performed as part of packaging.

## Known limitations

- This review build is not publicly released or code-signed; Windows or
  antivirus software may show an unknown-publisher warning.
- The bundled WBC-only model draws WBC bounding boxes but does not classify
  WBC subtypes and is not clinical validation.
- The prior v0.1.1 installer is retained as a backup; do not treat this build
  as B-site hardware validation.

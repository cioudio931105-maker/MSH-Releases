# MSH application-only distribution policy

MSH supplies the application, recognition/classification/stitching tools and local
training functionality. Users supply their own models and research data. New source
commits, source handoffs and installers must not include weights, datasets,
microscope images, annotations, captures, experimental results or device-specific
camera profiles. Icons and splash images are application assets. Tests create
synthetic fixtures in temporary directories instead of using real research samples.

## Model use

- Choose your local detection model in the GUI. Startup selects no model;
  **清除模型** clears the selection. Without a model, non-AI tools remain available.
- Recognition requires an existing local file. MSH does not download a replacement.
- CLI recognition and local training remain supported. Supply a local checkpoint
  or, for training from scratch, a local architecture YAML. Training does not request
  downloaded pretrained initialization; supplied checkpoints already contain weights.
- Automatic mixed precision is disabled in these training entrypoints because the
  backend's AMP self-test can download an unrelated probe model. This can increase
  GPU memory use and reduce training speed; no supplied checkpoint weights are discarded.
- Historical research presets are path/configuration conveniences for local files,
  not included models or accuracy guarantees. Supply any required label lists too.
- Building MSH requires no particular model, dataset or model hash.

## Research and Git

Keep datasets, labels, captures, checkpoints, experiment references and results in
ignored local directories or external storage. Do not use `git add -f` to bypass
these exclusions. Ignored files are not backups: preserve them separately.
Stopping tracking must leave the local originals intact.

Before committing source, run:

```powershell
python scripts/audit_application_files.py
git diff --cached --check
git diff --cached --name-status
```

The audit checks paths/types, not all possible secrets or research values embedded
in source text. Review actual diffs as well. The source handoff uses the same
allowlist. Its old IncludeModels/IncludeOutputs/IncludeStitchedOutput/IncludeEnvs
switches now fail explicitly, so it cannot distribute private assets.

Documentation and historical release-identity records describe behavior and prior
work; they are not datasets, weights or authorization to distribute those assets.

## Existing history and installers

This policy applies to future versions. Earlier Git commits and existing v0.1.x
installers may still contain prior models, image fixtures and research results.
Untracking does not remove a file from Git history. Do not describe the existing
repository history or old installers as data-free. A public source release with no
historical data needs a separately authorized clean repository/export. Do not
rewrite history or republish old installers automatically.

This change does not alter hardware settings or firmware. Software checks do not
establish Basler/COM/XY/motor or complete microscope-scan hardware acceptance.

## Single-repository source migration (2026-11-18)

MSH-Releases becomes the public application development and release repository after authorized publication. Only the current application snapshot is carried into its clean README-only history; the original private research repository and its .git are preserved separately. No datasets, weights, captures, profiles, environments or old binaries are transferred. Public Actions artifacts and acceptance records must contain reviewed public-safe material only. This does not clear the existing native runtime/source-license or hardware acceptance gates.
